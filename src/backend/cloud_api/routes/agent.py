"""云端智能体对话接口。

POST /api/agent/chat   → 自由对话（含日志意图识别）
GET  /api/agent/scan    → 隐患扫描报告
GET  /api/agent/history → 对话历史
GET  /api/agent/tools   → 可用工具列表
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from backend.cloud_api.dependencies import get_agent, get_event_repository
from backend.shared.core.config import get_settings
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import AgentRequest, AgentResponse, TaskLog

router = APIRouter(prefix="/api/agent", tags=["cloud-agent"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=AgentResponse)
def chat(request: AgentRequest) -> AgentResponse:
    latest_detection = runtime_state.latest_detection(request.device_id)
    enriched_context = dict(request.context)
    if latest_detection is not None:
        enriched_context["latest_detection"] = latest_detection.model_dump(mode="json", exclude={"image_jpeg_base64"})

    response = get_agent().answer(request.model_copy(update={"context": enriched_context}))
    runtime_state.add_task_log(
        TaskLog(
            task=request.question,
            device_id=request.device_id or "web-console",
            target="cloud",
            result_summary=response.answer,
        )
    )
    _save_chat(
        question=request.question,
        answer=response.answer,
        device_id=request.device_id or "web-console",
        traces=response.traces,
        used_knowledge=response.used_knowledge,
        used_search=response.used_search,
    )
    return response


@router.get("/history")
def chat_history(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    settings = get_settings()
    if not settings.postgres_persistence_enabled:
        return []
    import json
    try:
        from psycopg import connect, sql
        with connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        ) as conn:
            with conn.cursor() as cur:
                from backend.cloud_api.cloud.schema import qualified
                cur.execute(
                    sql.SQL(
                        "SELECT id, question, answer, device_id, traces, "
                        "used_knowledge, used_search, created_at "
                        "FROM {} ORDER BY created_at DESC LIMIT %s"
                    ).format(qualified(settings, "cloud_chat_history")),
                    (limit,),
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "question": row[1],
                        "answer": row[2],
                        "device_id": row[3],
                        "traces": json.loads(row[4]) if isinstance(row[4], str) else row[4],
                        "used_knowledge": row[5],
                        "used_search": row[6],
                        "created_at": row[7].isoformat() if row[7] else None,
                    }
                    for row in rows
                ]
    except Exception:
        logger.exception("Failed to load chat history")
        return []


@router.get("/scan")
def scan_hazards(
    hours: int = Query(default=168, ge=1, le=720, description="扫描时间范围（小时），默认 168（7天）"),
) -> dict:
    return get_agent().scan(hours_back=hours)


@router.get("/tools")
def tools() -> dict:
    return {
        "llm": "configurable",
        "search": "local-or-provider-adapter",
        "knowledge_base": "local-text-knowledge-base",
        "log_query": "runtime-state-log-query",
        "hazard_scan": "available-at-/api/agent/scan",
        "chat_history": "available-at-/api/agent/history",
    }


def _save_chat(
    *,
    question: str,
    answer: str,
    device_id: str,
    traces: list[str],
    used_knowledge: bool,
    used_search: bool,
) -> None:
    settings = get_settings()
    if not settings.postgres_persistence_enabled:
        return
    import json
    try:
        from psycopg import connect, sql
        from backend.cloud_api.cloud.schema import qualified
        with connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            autocommit=True,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} (question, answer, device_id, traces, "
                        "used_knowledge, used_search, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    ).format(qualified(settings, "cloud_chat_history")),
                    (
                        question,
                        answer,
                        device_id,
                        json.dumps(traces),
                        used_knowledge,
                        used_search,
                        datetime.now(timezone.utc),
                    ),
                )
    except Exception:
        logger.exception("Failed to persist chat")
