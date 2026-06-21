from datetime import datetime, timedelta, timezone

from backend.shared.core.state import runtime_state
from backend.shared.domain.models import SafetyEvent


class LogQueryTool:
    def query_events(
        self,
        hours_back: int = 24,
        event_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[SafetyEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        result: list[SafetyEvent] = []
        for event in runtime_state.snapshot()["events"]:
            if event.created_at < cutoff:
                continue
            if event_type and event.event_type != event_type:
                continue
            if severity and event.severity.value != severity:
                continue
            if status and event.status.value != status:
                continue
            result.append(event)
        return sorted(result, key=lambda e: e.created_at, reverse=True)[:limit]

    def summarize(self, hours_back: int = 24) -> dict:
        events = self.query_events(hours_back=hours_back)
        if not events:
            return {"total": 0, "by_type": {}, "by_severity": {}, "by_status": {}, "trend": "过去 {} 小时内无事件记录。".format(hours_back)}

        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for event in events:
            by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
            by_severity[event.severity.value] = by_severity.get(event.severity.value, 0) + 1
            by_status[event.status.value] = by_status.get(event.status.value, 0) + 1

        critical_count = by_severity.get("critical", 0)
        warning_count = by_severity.get("warning", 0)
        if critical_count > 0:
            trend = f"存在 {critical_count} 条 CRITICAL 高风险事件，需要立即关注"
        elif warning_count > 3:
            trend = f"存在 {warning_count} 条 WARNING 警告事件，建议持续关注"
        elif len(events) > 0:
            trend = "当前时段以低风险事件为主，状态正常"
        else:
            trend = "无异常"

        return {
            "total": len(events),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_status": by_status,
            "trend": trend,
            "period_hours": hours_back,
        }

    def scan_hazards(self, hours_back: int = 168) -> list[dict]:
        events = self.query_events(hours_back=hours_back)
        hazards: list[dict] = []

        critical_unhandled = [
            e for e in events
            if e.severity.value == "critical" and e.status.value != "cloud_analyzed"
        ]
        if critical_unhandled:
            hazards.append({
                "type": "unhandled_critical",
                "severity": "high",
                "count": len(critical_unhandled),
                "sample_ids": [e.event_id for e in critical_unhandled[:3]],
                "suggestion": f"发现 {len(critical_unhandled)} 条未处理的高风险事件，建议立即人工复核。",
            })

        unauthorized = [e for e in events if e.event_type == "unauthorized_time"]
        if len(unauthorized) >= 3:
            hazards.append({
                "type": "repeated_unauthorized",
                "severity": "medium",
                "count": len(unauthorized),
                "sample_ids": [e.event_id for e in unauthorized[:3]],
                "suggestion": f"过去 {hours_back // 24} 天内出现 {len(unauthorized)} 次非授权时段进入，建议加强门禁管理。",
            })

        crowding = [e for e in events if e.event_type == "crowding"]
        if len(crowding) >= 5:
            hazards.append({
                "type": "frequent_crowding",
                "severity": "medium",
                "count": len(crowding),
                "sample_ids": [e.event_id for e in crowding[:3]],
                "suggestion": f"过去 {hours_back // 24} 天内出现 {len(crowding)} 次多人聚集事件，建议检查容量管理策略。",
            })

        falls = [e for e in events if e.event_type == "fall_suspected"]
        if falls:
            hazards.append({
                "type": "fall_events",
                "severity": "high",
                "count": len(falls),
                "sample_ids": [e.event_id for e in falls[:3]],
                "suggestion": f"过去 {hours_back // 24} 天内出现 {len(falls)} 次疑似摔倒事件，需确认是否为误报并检查环境安全。",
            })

        excessive = [e for e in events if e.event_type == "excessive_people"]
        if len(excessive) >= 3:
            hazards.append({
                "type": "repeated_excessive",
                "severity": "medium",
                "count": len(excessive),
                "sample_ids": [e.event_id for e in excessive[:3]],
                "suggestion": f"过去 {hours_back // 24} 天内出现 {len(excessive)} 次超容量事件，建议评估扩容或分流方案。",
            })

        return hazards

    def format_events_for_prompt(self, events: list[SafetyEvent], max_items: int = 10) -> str:
        if not events:
            return "（无匹配事件）"
        lines: list[str] = []
        for event in events[:max_items]:
            lines.append(
                f"  [{event.severity.value.upper()}] {event.event_type} | {event.status.value} | "
                f"{event.summary} | {event.created_at.strftime('%m-%d %H:%M')}"
            )
        return "\n".join(lines)

    def format_summary_for_prompt(self, summary: dict) -> str:
        lines = [
            f"统计时段：过去 {summary['period_hours']} 小时",
            f"事件总数：{summary['total']}",
            f"按类型：{summary['by_type']}",
            f"按等级：{summary['by_severity']}",
            f"按状态：{summary['by_status']}",
            f"趋势判断：{summary['trend']}",
        ]
        return "\n".join(lines)

    def format_hazards_for_prompt(self, hazards: list[dict]) -> str:
        if not hazards:
            return "未发现明显隐患。"
        lines: list[str] = []
        for i, h in enumerate(hazards, 1):
            lines.append(f"{i}. [{h['severity']}] {h['type']}: {h['count']} 条 | {h['suggestion']}")
        return "\n".join(lines)
