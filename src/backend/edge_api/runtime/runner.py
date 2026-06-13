from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from backend.edge_api.runtime.camera import CameraSource, encode_frame_to_jpeg_base64
from backend.edge_api.runtime.client import CloudClient, EdgeClient, LatestFramePublisher
from backend.edge_api.runtime.debug import close_debug_window, render_debug_window
from backend.edge_api.runtime.detector import YoloDetector
from backend.edge_api.runtime.pose import PoseAnalyzer
from backend.shared.core.config import get_settings
from backend.shared.domain.models import AgentRequest, DetectionResult, EdgeStatus, ExecutionTarget, PoseAction, ScheduleDecision, TaskComplexity, TaskLog, TaskRequest
from backend.shared.domain.scheduler import TaskScheduler


@dataclass
class CycleSnapshot:
    result: object
    request: TaskRequest
    decision: object
    cloud_available: bool
    summary: str
    reason: str
    cloud_fallback: bool = False


def _build_mock_cloud_summary(task: str, frame_id: str, pose: object | None) -> str:
    pose_action = getattr(getattr(pose, "action", None), "value", PoseAction.UNKNOWN.value)
    if pose is not None and pose_action != PoseAction.UNKNOWN.value:
        return f"云端模拟结果：{task} 已由边端识别为 {pose_action}，帧 {frame_id} 将在后续接入真实云端分析。"
    return f"云端模拟结果：{task} 暂未获得稳定姿态判定，帧 {frame_id} 已标记为待云端复核。"


def process_frame(*, task: str, offline: bool, detector: YoloDetector, scheduler: TaskScheduler, edge_client: EdgeClient, cloud_client: CloudClient, device_id: str, frame: object | None, publish: bool, cloud_available: bool | None = None, include_image: bool = True, mock_cloud: bool = True) -> CycleSnapshot:
    if frame is None:
        raise RuntimeError("未读取到摄像头帧，请检查摄像头权限、索引和占用情况。")
    encoded_frame = encode_frame_to_jpeg_base64(frame) if include_image else None
    result = detector.detect(device_id, frame=frame, image_jpeg_base64=encoded_frame)
    cloud_fallback = False
    pose_summary: str | None = None
    if "姿态" in task or "pose" in task.lower() or result.model_task == "pose":
        pose_decision = PoseAnalyzer().analyze(result.detections, (result.frame_width, result.frame_height))
        result.pose = pose_decision.analysis
        pose_summary = f"边端识别到姿态动作：{pose_decision.analysis.action.value}，置信度 {pose_decision.analysis.confidence:.2f}。" if pose_decision.analysis.action != PoseAction.UNKNOWN else "边端未能稳定识别姿态动作，建议转云端复核。"
        cloud_fallback = pose_decision.analysis.needs_cloud
    request = TaskRequest(task=task, device_id=device_id, frame_id=result.frame_id)
    decision = scheduler.decide(request)
    if cloud_fallback and decision.target == ExecutionTarget.EDGE:
        decision = ScheduleDecision(target=ExecutionTarget.CLOUD, complexity=TaskComplexity.COMPLEX, reason="边端姿态规则未能稳定匹配结果，转云端模拟复核。")
    summary = pose_summary or f"{detector.mode}/{detector.task} 检测到 {len(result.detections)} 个目标，YOLO FPS {result.fps:.2f}，调度至 {decision.target.value}。"
    if cloud_available is None:
        cloud_available = cloud_client.is_available() if publish and not offline else False
    print(summary); print(decision.reason)
    if offline or not publish:
        return CycleSnapshot(result=result, request=request, decision=decision, cloud_available=cloud_available, summary=summary, reason=decision.reason, cloud_fallback=cloud_fallback)
    edge_client.publish_status(EdgeStatus(device_id=device_id, fps=result.fps, cpu_percent=12.5, memory_percent=33.0, last_seen=datetime.now(timezone.utc)))
    edge_client.publish_detection(result)
    if not cloud_available:
        if cloud_fallback and mock_cloud:
            summary = _build_mock_cloud_summary(task, result.frame_id, result.pose)
        print("云端 API 当前不可用，边端将继续本地运行并跳过上报。")
        edge_client.publish_task_log(TaskLog(task=task, device_id=device_id, target=decision.target, result_summary=summary))
        return CycleSnapshot(result=result, request=request, decision=decision, cloud_available=cloud_available, summary=summary, reason=decision.reason, cloud_fallback=cloud_fallback)
    cloud_client.publish_status(EdgeStatus(device_id=device_id, fps=result.fps, cpu_percent=12.5, memory_percent=33.0, last_seen=datetime.now(timezone.utc)))
    cloud_client.publish_detection(result)
    if decision.target == ExecutionTarget.CLOUD:
        summary = _build_mock_cloud_summary(task, result.frame_id, result.pose) if mock_cloud or cloud_fallback else cloud_client.ask_agent(AgentRequest(question=task, device_id=device_id, context={"frame_id": result.frame_id})).answer
    edge_client.publish_task_log(TaskLog(task=task, device_id=device_id, target=decision.target, result_summary=summary))
    cloud_client.publish_task_log(TaskLog(task=task, device_id=device_id, target=decision.target, result_summary=summary))
    return CycleSnapshot(result=result, request=request, decision=decision, cloud_available=cloud_available, summary=summary, reason=decision.reason, cloud_fallback=cloud_fallback)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one edge detection and scheduling cycle.")
    parser.add_argument("--task", default="车辆计数", help="任务描述")
    parser.add_argument("--offline", action="store_true", help="只在本地运行，不上报云端")
    parser.add_argument("--camera-index", type=int, default=None, help="摄像头索引，默认读取配置")
    parser.add_argument("--camera-width", type=int, default=None, help="请求摄像头输出宽度，默认读取配置")
    parser.add_argument("--camera-height", type=int, default=None, help="请求摄像头输出高度，默认读取配置")
    parser.add_argument("--once", action="store_true", help="只采集和处理一帧")
    parser.add_argument("--interval", type=float, default=None, help="循环采集间隔秒数")
    parser.add_argument("--debug-window", action="store_true", help="打开调试窗口显示画面、数据和标注框")
    parser.add_argument("--skip-frames", type=int, default=None, help="每 N 帧执行一次 YOLO 推理，其余帧复用上次检测框")
    parser.add_argument("--real-cloud", action="store_true", help="启用真实云端调用，默认使用模拟结果")
    args = parser.parse_args()
    mock_cloud = not args.real_cloud
    settings = get_settings()
    detector = YoloDetector(settings.yolo_model_path, public_dir=settings.public_dir, imgsz=settings.yolo_input_size, conf_threshold=settings.yolo_conf_threshold, iou_threshold=settings.yolo_iou_threshold)
    scheduler = TaskScheduler()
    camera_index = settings.edge_camera_index if args.camera_index is None else args.camera_index
    camera_width = settings.edge_camera_width if args.camera_width is None else args.camera_width
    camera_height = settings.edge_camera_height if args.camera_height is None else args.camera_height
    edge_client = EdgeClient(settings.edge_api_base_url)
    cloud_client = CloudClient(settings.cloud_api_base_url)
    interval = settings.edge_loop_interval_seconds if args.interval is None else args.interval
    skip_frames = max(1, settings.edge_skip_frames if args.skip_frames is None else args.skip_frames)
    cloud_cache_available = False; cloud_cache_checked_at = 0.0; frame_index = 0; last_snapshot: CycleSnapshot | None = None; fps_samples: list[float] = []; last_frame_id = -1; last_frame_time: float | None = None
    def get_cloud_available() -> bool:
        nonlocal cloud_cache_available, cloud_cache_checked_at
        now = time.monotonic()
        if args.offline:
            return False
        if now - cloud_cache_checked_at > 5.0:
            cloud_cache_available = cloud_client.is_available(); cloud_cache_checked_at = now
        return cloud_cache_available
    print(f"使用 YOLO 模型：{detector.model_path}"); print(f"模型任务：{detector.task}"); print(f"推理后端：{detector.mode}，输入尺寸：{settings.yolo_input_size}，检测间隔：{skip_frames} 帧"); print(f"请求摄像头尺寸：{camera_width}x{camera_height}")

    # 后台检测锁：防止多个检测线程同时使用 ONNX session
    detection_lock = threading.Lock()
    # 上一轮检测结果，供 debug_window 模式复用
    last_detection: DetectionResult | None = None

    def _run_background_detect(frame_copy: object, device_id: str, task_desc: str) -> None:
        """后台线程：对当前帧执行 YOLO 检测 + 姿态分析 + 上报"""
        nonlocal last_detection
        acquired = detection_lock.acquire(blocking=False)
        if not acquired:
            return  # 上一轮检测尚未完成，丢弃本帧
        try:
            result = detector.detect(device_id, frame=frame_copy)
            if "姿态" in task_desc or "pose" in task_desc.lower() or result.model_task == "pose":
                pose_decision = PoseAnalyzer().analyze(result.detections, (result.frame_width, result.frame_height))
                result.pose = pose_decision.analysis
            last_detection = result
            # 发布检测结果
            if publish:
                edge_client.publish_detection(result)
        except Exception as exc:
            print(f"检测线程异常：{exc}")
        finally:
            detection_lock.release()

    publish = not args.offline
    device_id = settings.edge_device_id
    task_desc = args.task

    try:
        with CameraSource(camera_index, width=camera_width, height=camera_height) as camera:
            actual_width, actual_height = camera.source_size
            if actual_width and actual_height:
                print(f"实际摄像头尺寸：{actual_width}x{actual_height}")

            if args.debug_window:
                # --- 调试窗口模式：本地渲染优先，检测异步后台执行 ---
                try:
                    while True:
                        frame, current_frame_id = camera.read_latest()
                        if frame is None:
                            time.sleep(0.02); continue
                        if current_frame_id == last_frame_id:
                            time.sleep(0.001); continue
                        now = time.perf_counter()
                        if last_frame_time is not None:
                            frame_interval = now - last_frame_time
                            if frame_interval > 0:
                                fps_samples.append(1.0 / frame_interval)
                                if len(fps_samples) > 30:
                                    fps_samples.pop(0)
                        last_frame_time = now; last_frame_id = current_frame_id

                        # 检测路径：仅在需要时编码 JPEG + 后台异步执行
                        if frame_index % skip_frames == 0 or last_detection is None:
                            threading.Thread(
                                target=_run_background_detect,
                                args=(frame.copy(), device_id, task_desc),
                                daemon=True,
                            ).start()

                        display_fps = sum(fps_samples) / len(fps_samples) if fps_samples else 0.0
                        key = render_debug_window(frame, result=last_detection,
                                                  display_fps=display_fps,
                                                  source_fps=camera.source_fps,
                                                  source_size=camera.source_size,
                                                  wait_for_key=False)
                        if key in (27, ord("q"), ord("Q")):
                            break
                        frame_index += 1
                except RuntimeError as exc:
                    print(exc)

            else:
                # --- 正常模式：原始 BGR 字节推送 + 后台异步检测 ---
                last_status_at = 0.0
                frame_publisher = LatestFramePublisher(
                    edge_client,
                    device_id=device_id,
                    stream_width=settings.edge_stream_width,
                    jpeg_quality=settings.edge_stream_jpeg_quality,
                    max_fps=settings.edge_stream_max_fps,
                ) if publish else None
                if frame_publisher:
                    frame_publisher.start()
                try:
                    while True:
                        frame = camera.read()
                        if frame_publisher:
                            frame_publisher.submit(frame)

                        # 定时推送设备状态（~每秒一次）
                        now = time.monotonic()
                        if publish and now - last_status_at > 1.0:
                            edge_client.publish_status(EdgeStatus(
                                device_id=device_id,
                                fps=round(frame_publisher.fps if frame_publisher else 0.0, 1),
                                cpu_percent=12.5,
                                memory_percent=33.0,
                                last_seen=datetime.now(timezone.utc),
                            ))
                            last_status_at = now

                        if frame_index % skip_frames == 0:
                            threading.Thread(
                                target=_run_background_detect,
                                args=(frame.copy(), device_id, task_desc),
                                daemon=True,
                            ).start()

                        if args.once:
                            break
                        frame_index += 1
                        if interval > 0:
                            time.sleep(interval)
                finally:
                    if frame_publisher:
                        frame_publisher.close()
                        print(f"[Runner] 视频推送完成：成功 {frame_publisher.published}，丢弃 {frame_publisher.dropped}，失败 {frame_publisher.failed}")

    except KeyboardInterrupt:
        print("已退出。")
    finally:
        close_debug_window()


if __name__ == "__main__":
    main()
