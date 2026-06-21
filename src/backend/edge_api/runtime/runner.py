from __future__ import annotations

import argparse
import queue
import threading
import time

from backend.edge_api.runtime.camera import CameraSource, encode_frame_to_jpeg_base64
from backend.edge_api.runtime.client import CloudClient, EdgeClient, LatestFramePublisher
from backend.edge_api.runtime.debug import close_debug_window, render_debug_window
from backend.edge_api.runtime.detector import YoloDetector
from backend.edge_api.runtime.monitoring import collect_edge_status
from backend.edge_api.runtime.pipeline import EdgeCycle, EdgePipeline
from backend.shared.core.config import get_settings
from backend.shared.domain.models import DetectionResult


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one edge detection and scheduling cycle.")
    parser.add_argument("--task", default="车辆计数", help="任务描述")
    parser.add_argument("--offline", action="store_true", help="只在本地运行，不上报云端")
    parser.add_argument("--camera-index", type=int, default=None, help="摄像头索引，默认读取配置")
    parser.add_argument("--camera-width", type=int, default=None, help="请求摄像头输出宽度，默认读取配置")
    parser.add_argument("--camera-height", type=int, default=None, help="请求摄像头输出高度，默认读取配置")
    parser.add_argument("--once", action="store_true", help="只采集和处理一帧")
    parser.add_argument("--interval", type=float, default=None, help="循环采集间隔秒数")
    parser.add_argument("--debug-window", "--debug_window", action="store_true", help="打开调试窗口显示画面、数据和标注框")
    parser.add_argument("--skip-frames", type=int, default=None, help="每 N 帧执行一次 YOLO 推理，其余帧复用上次检测框")
    parser.add_argument("--no-cloud-sync", action="store_true", help="关闭检测结果、状态和任务日志的云端同步")
    parser.add_argument("--no-cloud-agent", action="store_true", help="关闭复杂任务的云端智能体调用")
    args = parser.parse_args()
    if args.debug_window and not args.offline:
        print("调试窗口模式默认只做本地预览，不上报边端或云端；需要完整链路时请启动边端 API 后使用网页工作台。")
        args.offline = True
    settings = get_settings()
    detector = YoloDetector(settings.yolo_model_path, public_dir=settings.public_dir, imgsz=settings.yolo_input_size, conf_threshold=settings.yolo_conf_threshold, iou_threshold=settings.yolo_iou_threshold)
    camera_index = settings.edge_camera_index if args.camera_index is None else args.camera_index
    camera_width = settings.edge_camera_width if args.camera_width is None else args.camera_width
    camera_height = settings.edge_camera_height if args.camera_height is None else args.camera_height
    edge_client = EdgeClient(settings.edge_api_base_url)
    cloud_client = CloudClient(settings.cloud_api_base_url)
    pipeline = EdgePipeline(
        task=args.task,
        cloud_client=cloud_client,
        cloud_sync_enabled=settings.edge_cloud_sync_enabled and not args.no_cloud_sync and not args.offline,
        cloud_agent_enabled=settings.edge_cloud_agent_enabled and not args.no_cloud_agent,
        cloud_agent_cooldown_seconds=settings.edge_cloud_agent_cooldown_seconds,
        cloud_analysis_cooldown_seconds=settings.edge_cloud_analysis_cooldown_seconds,
    )
    interval = settings.edge_loop_interval_seconds if args.interval is None else args.interval
    skip_frames = max(1, settings.edge_skip_frames if args.skip_frames is None else args.skip_frames)
    frame_index = 0; fps_samples: list[float] = []; last_frame_id = -1; last_frame_time: float | None = None
    print(f"使用 YOLO 模型：{detector.model_path}"); print(f"模型任务：{detector.task}"); print(f"推理后端：{detector.mode}，输入尺寸：{settings.yolo_input_size}，检测间隔：{skip_frames} 帧"); print(f"请求摄像头尺寸：{camera_width}x{camera_height}")

    # 后台检测锁：防止多个检测线程同时使用 ONNX session
    detection_lock = threading.Lock()
    cloud_sync_lock = threading.Lock()
    detection_queue: queue.Queue[object | None] = queue.Queue(maxsize=1)
    detector_stop = threading.Event()
    # 上一轮检测结果，供 debug_window 模式复用
    last_detection: DetectionResult | None = None

    def _run_cloud_sync(cycle: EdgeCycle) -> None:
        if not cloud_sync_lock.acquire(blocking=False):
            return
        try:
            pipeline.sync_cloud(cycle)
        finally:
            cloud_sync_lock.release()

    def _run_background_detect(frame_copy: object, device_id: str, sync_cloud_inline: bool = False) -> None:
        """后台线程：对当前帧执行 YOLO 检测 + 姿态分析 + 上报"""
        nonlocal last_detection
        acquired = detection_lock.acquire(blocking=False)
        if not acquired:
            return  # 上一轮检测尚未完成，丢弃本帧
        try:
            image = (
                encode_frame_to_jpeg_base64(frame_copy)
                if pipeline.cloud_sync_enabled and settings.edge_cloud_include_image
                else None
            )
            cycle = pipeline.process(
                detector.detect(device_id, frame=frame_copy, image_jpeg_base64=image)
            )
            last_detection = cycle.detection
            if publish:
                edge_client.publish_detection(cycle.detection)
                edge_client.publish_task_log(cycle.task_log)
                for event in cycle.events:
                    edge_client.publish_event(event)
            if sync_cloud_inline:
                _run_cloud_sync(cycle)
            else:
                threading.Thread(target=_run_cloud_sync, args=(cycle,), daemon=True).start()
        except Exception as exc:
            print(f"检测线程异常：{exc}")
        finally:
            detection_lock.release()

    def _submit_latest_debug_frame(frame_copy: object) -> None:
        try:
            detection_queue.put_nowait(frame_copy)
        except queue.Full:
            try:
                detection_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                detection_queue.put_nowait(frame_copy)
            except queue.Full:
                pass

    def _run_debug_detector() -> None:
        while not detector_stop.is_set():
            try:
                frame_copy = detection_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if frame_copy is None:
                break
            _run_background_detect(frame_copy, device_id)

    publish = not args.offline
    device_id = settings.edge_device_id

    try:
        with CameraSource(camera_index, width=camera_width, height=camera_height) as camera:
            actual_width, actual_height = camera.source_size
            if actual_width and actual_height:
                print(f"实际摄像头尺寸：{actual_width}x{actual_height}")

            if args.debug_window:
                # --- 调试窗口模式：本地渲染优先，检测异步后台执行 ---
                detector_thread = threading.Thread(target=_run_debug_detector, name="edge-debug-detector", daemon=True)
                detector_thread.start()
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
                            _submit_latest_debug_frame(frame.copy())

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
                finally:
                    detector_stop.set()
                    _submit_latest_debug_frame(None)
                    detector_thread.join(timeout=2)

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
                            status = collect_edge_status(
                                device_id,
                                frame_publisher.fps if frame_publisher else 0.0,
                            )
                            edge_client.publish_status(status)
                            pipeline.publish_status(status)
                            last_status_at = now

                        if frame_index % skip_frames == 0:
                            detection_thread = threading.Thread(
                                target=_run_background_detect,
                                args=(frame.copy(), device_id, args.once),
                                daemon=True,
                            )
                            detection_thread.start()

                        if args.once:
                            detection_thread.join()
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
