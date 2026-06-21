"""日报生成接口。

GET /api/reports/daily → 返回当日 JSON 或 Markdown 检测报告，
包含事件统计、风险分布和隐患扫描结果。
"""

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

    chats = _fetch_day_chats(target_date)

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
        "chats": chats,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if fmt == "md":
        return PlainTextResponse(_build_markdown(report_data), media_type="text/markdown")

    if fmt == "html":
        return PlainTextResponse(_build_html(report_data), media_type="text/html")

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

    if data.get("chats"):
        lines.extend(["", "---", "", "## 智能体对话记录", ""])
        for chat in data["chats"]:
            lines.append(f"- **Q**: {chat['question']}")
            lines.append(f"  **A**: {chat['answer'][:200]}{'...' if len(chat.get('answer','')) > 200 else ''}")
            lines.append("")

    lines.extend([
        "",
        "---",
        "",
        "*本报告由边云协同安全监测系统自动生成*",
    ])
    return "\n".join(lines)


def _fetch_day_chats(target_date: date) -> list[dict]:
    from backend.shared.core.config import get_settings
    s = get_settings()
    if not s.postgres_persistence_enabled:
        return []
    try:
        from psycopg import connect, sql
        from backend.cloud_api.cloud.schema import qualified
        day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        day_end = day_start.replace(hour=23, minute=59, second=59)
        with connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db,
                     user=s.postgres_user, password=s.postgres_password) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT question, answer, device_id, created_at FROM {} WHERE created_at >= %s AND created_at <= %s ORDER BY created_at DESC LIMIT 30").format(
                        qualified(s, "cloud_chat_history")),
                    (day_start, day_end),
                )
                return [{"question": r[0], "answer": r[1], "device_id": r[2], "created_at": r[3].isoformat() if r[3] else None} for r in cur.fetchall()]
    except Exception:
        return []


def _build_html(data: dict) -> str:
    def esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>边云协同安全监测日报</title>",
        "<style>body{font-family:sans-serif;max-width:800px;margin:40px auto;line-height:1.7;color:#222}",
        "h1{font-size:22px}h2{font-size:16px;margin-top:24px}h3{font-size:14px}",
        "table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #ddd;padding:6px 12px;text-align:left}th{background:#f5f5f5}",
        ".tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;margin-right:4px}",
        ".critical{background:#fff0f0;color:#c00}.warning{background:#fff8e0;color:#960}",
        "ul{margin:0;padding-left:18px}li{margin:4px 0}",
        "@media print{body{margin:0;padding:20px}}",
        "</style></head><body>",
        f"<h1>边云协同安全监测日报</h1>",
        f"<p><strong>日期:</strong> {esc(data['date'])} | <strong>生成时间:</strong> {esc(data['generated_at'])}</p>",
        "<h2>概览</h2>",
        "<table><tr><th>指标</th><th>数值</th></tr>",
        f"<tr><td>事件总数</td><td>{data['total']}</td></tr>",
        f"<tr><td>高风险</td><td class='tag critical'>{data['by_severity'].get('critical',0)}</td></tr>",
        f"<tr><td>警告</td><td class='tag warning'>{data['by_severity'].get('warning',0)}</td></tr>",
        f"<tr><td>信息</td><td>{data['by_severity'].get('info',0)}</td></tr>",
        f"<tr><td>待处理</td><td>{data['pending_count']}</td></tr>",
        "</table>",
    ]
    if data["critical_events"]:
        parts.append("<h2>高风险事件</h2><ul>")
        for e in data["critical_events"]:
            parts.append(f"<li><strong>{esc(e['event_type'])}</strong> [{e['time']}]: {esc(e['summary'])}</li>")
        parts.append("</ul>")
    if data["warning_events"]:
        parts.append("<h2>警告事件</h2><ul>")
        for e in data["warning_events"]:
            parts.append(f"<li><strong>{esc(e['event_type'])}</strong> [{e['time']}]: {esc(e['summary'])}</li>")
        parts.append("</ul>")
    if data["hazards"]:
        parts.append("<h2>隐患扫描</h2><ul>")
        for h in data["hazards"]:
            parts.append(f"<li><strong>[{esc(h['severity'])}] {esc(h['type'])}</strong> ({h['count']}条): {esc(h['suggestion'])}</li>")
        parts.append("</ul>")
    if data.get("chats"):
        parts.append("<h2>智能体对话记录</h2>")
        for chat in data["chats"]:
            parts.append(f"<p><strong>Q:</strong> {esc(chat['question'])}</p>")
            parts.append(f"<p><strong>A:</strong> {esc(chat['answer'][:300])}</p><hr>")
    parts.append("<p><em>本报告由边云协同安全监测系统自动生成</em></p></body></html>")
    return "\n".join(parts)
