import argparse
from datetime import datetime, timezone

from edge_cloud_system.core.config import get_settings
from edge_cloud_system.domain.models import AgentRequest, EdgeStatus, TaskLog, TaskRequest
from edge_cloud_system.edge.client import CloudClient
from edge_cloud_system.edge.detector import YoloDetector
from edge_cloud_system.edge.scheduler import TaskScheduler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one edge detection and scheduling cycle.")
    parser.add_argument("--task", default="车辆计数", help="任务描述")
    parser.add_argument("--offline", action="store_true", help="只在本地运行，不上报云端")
    args = parser.parse_args()

    settings = get_settings()
    detector = YoloDetector(settings.yolo_model_path)
    scheduler = TaskScheduler()
    result = detector.detect(settings.edge_device_id)
    request = TaskRequest(task=args.task, device_id=settings.edge_device_id, frame_id=result.frame_id)
    decision = scheduler.decide(request)
    summary = f"{detector.mode} 检测到 {len(result.detections)} 个目标，调度至 {decision.target}。"

    print(summary)
    print(decision.reason)

    if args.offline:
        return

    client = CloudClient(settings.api_base_url)
    client.publish_status(
        EdgeStatus(
            device_id=settings.edge_device_id,
            fps=result.fps,
            cpu_percent=12.5,
            memory_percent=33.0,
            last_seen=datetime.now(timezone.utc),
        )
    )
    client.publish_detection(result)

    if decision.target == "cloud":
        agent_result = client.ask_agent(
            AgentRequest(question=args.task, device_id=settings.edge_device_id, context={"frame_id": result.frame_id})
        )
        summary = agent_result.answer

    client.publish_task_log(
        TaskLog(task=args.task, device_id=settings.edge_device_id, target=decision.target, result_summary=summary)
    )


if __name__ == "__main__":
    main()
