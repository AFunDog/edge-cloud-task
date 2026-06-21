from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from backend.cloud_api.cloud.log_query import LogQueryTool
from backend.cloud_api.dependencies import get_agent

router = APIRouter(prefix="/api/reports", tags=["cloud-reports"])


def _tool() -> LogQueryTool:
    from backend.cloud_api.dependencies import get_agent
    return get_agent().log_query


@router.get("/daily")
def daily_report(d: str = Query(default="", description="日期 YYYY-MM-DD，默认今天"), fmt: str = Query(default="json", description="输出格式: json 或 md")) -> Any:
    try:
        target_date = date.fromisoformat(d) if d else date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    tool = _tool()
    all_events = tool.query_events(hours_back=720, limit=500)
    day_events = [e for e in all_events if e.created_at.date() == target_date]

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    critical_events: list[dict] = []
    warning_events: list[dict] = []
    pending_events: list[dict] = []

    for event in day_events:
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
        by_severity[event.severity.value] = by_severity.get(event.severity.value, 0) + 1
        by_status[event.status.value] = by_status.get(event.status.value, 0) + 1
        item = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "severity": event.severity.value,
            "status": event.status.value,
            "summary": event.summary,
            "time": event.created_at.strftime("%H:%M"),
        }
        if event.severity.value == "critical":
            critical_events.append(item)
        elif event.severity.value == "warning":
            warning_events.append(item)
        if event.status.value == "cloud_pending":
            pending_events.append(item)

    hazards = tool.scan_hazards(hours_back=720)
    day_hazards = [h for h in hazards if h["count"] > 0]

    total = len(day_events)
    report_data = {
        "date": target_date.isoformat(),
        "total": total,
        "by_type": by_type,
        "by_severity": by_severity,
        "by_status": by_status,
        "pending_count": len(pending_events),
        "critical_events": critical_events,
        "warning_events": warning_events,
        "pending_events": pending_events,
        "hazards": day_hazards,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if fmt == "md":
        return PlainTextResponse(_build_markdown(report_data), media_type="text/markdown")

    return report_data


def _build_markdown(data: dict) -> str:
    lines = [
        f"# 边云协同安全监测日报",
        "",
        f"**日期**: {data['date']}",
        f"**生成时间**: {data['generated_at']}",
        "",
        "---",
        "",
        "## 概览",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 事件总数 | {data['total']} |",
        f"| 高风险 (CRITICAL) | {data['by_severity'].get('critical', 0)} |",
        f"| 警告 (WARNING) | {data['by_severity'].get('warning', 0)} |",
        f"| 信息 (INFO) | {data['by_severity'].get('info', 0)} |",
        f"| 待云端处理 | {data['pending_count']} |",
        f"| 边端已处理 | {data['by_status'].get('edge_resolved', 0)} |",
        f"| 云端已分析 | {data['by_status'].get('cloud_analyzed', 0)} |",
        "",
        "---",
        "",
        "## 事件类型分布",
        "",
    ]
    for event_type, count in sorted(data["by_type"].items(), key=lambda x: -x[1]):
        lines.append(f"- **{event_type}**: {count} 次")

    if data["critical_events"]:
        lines.extend([
            "",
            "---",
            "",
            "## 高风险事件",
            "",
        ])
        for event in data["critical_events"]:
            lines.append(f"- [{event['time']}] **{event['event_type']}** | {event['status']} | {event['summary']}")

    if data["warning_events"]:
        lines.extend([
            "",
            "---",
            "",
            "## 警告事件",
            "",
        ])
        for event in data["warning_events"]:
            lines.append(f"- [{event['time']}] **{event['event_type']}** | {event['status']} | {event['summary']}")

    if data["pending_events"]:
        lines.extend([
            "",
            "---",
            "",
            "## 待处理事件",
            "",
        ])
        for event in data["pending_events"]:
            lines.append(f"- [{event['time']}] **{event['event_type']}** | {event['summary']}")

    if data["hazards"]:
        lines.extend([
            "",
            "---",
            "",
            "## 隐患扫描",
            "",
        ])
        for h in data["hazards"]:
            lines.append(f"- **[{h['severity']}] {h['type']}** ({h['count']} 条): {h['suggestion']}")

    if data["total"] == 0:
        lines.extend(["", "当日无事件记录，系统运行正常。"])

    lines.extend([
        "",
        "---",
        "",
        "*本报告由边云协同安全监测系统自动生成*",
    ])
    return "\n".join(lines)
