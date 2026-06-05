from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.edge_api.runtime.camera import CameraSource, encode_frame_to_jpeg_base64
from backend.edge_api.runtime.client import CloudClient, EdgeClient
from backend.edge_api.runtime.debug import close_debug_window, render_debug_window
from backend.edge_api.runtime.detector import YoloDetector
from backend.edge_api.runtime.pose import PoseAnalyzer
from backend.shared.edge_cloud_system.core.config import get_settings
from backend.shared.edge_cloud_system.domain.models import AgentRequest, EdgeStatus, ExecutionTarget, PoseAction, ScheduleDecision, TaskComplexity, TaskLog, TaskRequest
from backend.shared.edge_cloud_system.domain.scheduler import TaskScheduler


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
    print(f"使用 YOLO 模型：{detector.model_path}"); print(f"模型任务：{detector.task}"); print(f"推理后端：{detector.mode}，输入尺寸：{settings.yolo_input_size}，跳帧：{skip_frames}"); print(f"请求摄像头尺寸：{camera_width}x{camera_height}")
    try:
        with CameraSource(camera_index, width=camera_width, height=camera_height) as camera:
            actual_width, actual_height = camera.source_size
            if actual_width and actual_height:
                print(f"实际摄像头尺寸：{actual_width}x{actual_height}")
            if args.debug_window:
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
                        if frame_index % skip_frames == 0 or last_snapshot is None:
                            last_snapshot = process_frame(task=args.task, offline=args.offline, detector=detector, scheduler=scheduler, edge_client=edge_client, cloud_client=cloud_client, device_id=settings.edge_device_id, frame=frame, publish=False, cloud_available=False, include_image=False, mock_cloud=mock_cloud)
                        display_fps = sum(fps_samples) / len(fps_samples) if fps_samples else 0.0
                        snapshot = last_snapshot
                        key = render_debug_window(frame, result=snapshot.result, request=snapshot.request, decision=snapshot.decision, cloud_available=snapshot.cloud_available, display_fps=display_fps, source_fps=camera.source_fps, source_size=camera.source_size, wait_for_key=False)
                        if key in (27, ord("q"), ord("Q")):
                            break
                        frame_index += 1
                except RuntimeError as exc:
                    print(exc)
            else:
                while True:
                    frame = camera.read()
                    if frame_index % skip_frames == 0:
                        process_frame(task=args.task, offline=args.offline, detector=detector, scheduler=scheduler, edge_client=edge_client, cloud_client=cloud_client, device_id=settings.edge_device_id, frame=frame, publish=True, cloud_available=get_cloud_available(), include_image=True, mock_cloud=mock_cloud)
                    if args.once:
                        break
                    frame_index += 1
                    if interval > 0:
                        time.sleep(interval)
    except KeyboardInterrupt:
        print("已退出调试窗口。")
    finally:
        close_debug_window()


if __name__ == "__main__":
    main()
