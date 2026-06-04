import argparse
import time
from datetime import datetime, timezone

from edge_cloud_system.core.config import get_settings
from edge_cloud_system.domain.models import AgentRequest, EdgeStatus, ExecutionTarget, TaskLog, TaskRequest
from edge_cloud_system.domain.scheduler import TaskScheduler
from edge_cloud_system.edge.camera import CameraSource, encode_frame_to_jpeg_base64
from edge_cloud_system.edge.debug import close_debug_window, render_debug_window
from edge_cloud_system.edge.client import CloudClient
from edge_cloud_system.edge.detector import YoloDetector


def run_cycle(
    *,
    task: str,
    offline: bool,
    detector: YoloDetector,
    scheduler: TaskScheduler,
    client: CloudClient,
    device_id: str,
    frame: object | None,
    debug_window: bool,
    wait_for_key: bool,
) -> None:
    if frame is None:
        raise RuntimeError("未读取到摄像头帧，请检查摄像头权限、索引和占用情况。")
    encoded_frame = encode_frame_to_jpeg_base64(frame)
    result = detector.detect(device_id, frame=frame, image_jpeg_base64=encoded_frame)
    request = TaskRequest(task=task, device_id=device_id, frame_id=result.frame_id)
    decision = scheduler.decide(request)
    summary = f"{detector.mode} 检测到 {len(result.detections)} 个目标，调度至 {decision.target.value}。"

    print(summary)
    print(decision.reason)

    if debug_window:
        cloud_available = client.is_available()
        key = render_debug_window(
            frame,
            result=result,
            request=request,
            decision=decision,
            cloud_available=cloud_available,
            wait_for_key=wait_for_key,
        )
        if key in (27, ord("q"), ord("Q")):
            raise KeyboardInterrupt

    if offline:
        return

    if not client.is_available():
        print("云端 API 当前不可用，边端将继续本地运行并跳过上报。")
        return

    client.publish_status(
        EdgeStatus(
            device_id=device_id,
            fps=result.fps,
            cpu_percent=12.5,
            memory_percent=33.0,
            last_seen=datetime.now(timezone.utc),
        )
    )
    client.publish_detection(result)

    if decision.target == ExecutionTarget.CLOUD:
        agent_result = client.ask_agent(
            AgentRequest(question=task, device_id=device_id, context={"frame_id": result.frame_id})
        )
        summary = agent_result.answer

    client.publish_task_log(TaskLog(task=task, device_id=device_id, target=decision.target, result_summary=summary))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one edge detection and scheduling cycle.")
    parser.add_argument("--task", default="车辆计数", help="任务描述")
    parser.add_argument("--offline", action="store_true", help="只在本地运行，不上报云端")
    parser.add_argument("--camera-index", type=int, default=None, help="摄像头索引，默认读取配置")
    parser.add_argument("--once", action="store_true", help="只采集和处理一帧")
    parser.add_argument("--interval", type=float, default=None, help="循环采集间隔秒数")
    parser.add_argument("--debug-window", action="store_true", help="打开调试窗口显示画面、数据和标注框")
    args = parser.parse_args()

    settings = get_settings()
    detector = YoloDetector(settings.yolo_model_path, public_dir=settings.public_dir)
    scheduler = TaskScheduler()
    camera_index = settings.edge_camera_index if args.camera_index is None else args.camera_index
    client = CloudClient(settings.api_base_url)
    interval = settings.edge_loop_interval_seconds if args.interval is None else args.interval

    print(f"使用 YOLO 模型：{detector.model_path}")

    try:
        with CameraSource(camera_index) as camera:
            while True:
                run_cycle(
                    task=args.task,
                    offline=args.offline,
                    detector=detector,
                    scheduler=scheduler,
                    client=client,
                    device_id=settings.edge_device_id,
                    frame=camera.read(),
                    debug_window=args.debug_window,
                    wait_for_key=args.once,
                )
                if args.once:
                    break
                time.sleep(interval)
    except KeyboardInterrupt:
        print("已退出调试窗口。")
    finally:
        close_debug_window()


if __name__ == "__main__":
    main()
