from __future__ import annotations

from collections.abc import Iterable

from backend.cloud_api.cloud.schema import qualified
from backend.shared.core.config import Settings
from backend.shared.domain.models import CloudAnalysisResponse, SafetyEvent


class CloudEventRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.postgres_persistence_enabled

    def _connect(self):
        from psycopg import connect
        from psycopg.rows import dict_row

        return connect(
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            dbname=self.settings.postgres_db,
            user=self.settings.postgres_user,
            password=self.settings.postgres_password,
            row_factory=dict_row,
        )

    def save_event(self, event: SafetyEvent) -> None:
        if not self.enabled:
            return
        from psycopg import sql
        from psycopg.types.json import Jsonb

        payload = event.model_dump(mode="json")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO {} (
                            event_id, event_type, device_id, frame_id, severity, status,
                            summary, evidence, metrics, payload, search_text, created_at
                        )
                        VALUES (
                            %(event_id)s, %(event_type)s, %(device_id)s, %(frame_id)s,
                            %(severity)s, %(status)s, %(summary)s, %(evidence)s,
                            %(metrics)s, %(payload)s, %(search_text)s, %(created_at)s
                        )
                        ON CONFLICT (event_id) DO UPDATE SET
                            event_type = EXCLUDED.event_type,
                            device_id = EXCLUDED.device_id,
                            frame_id = EXCLUDED.frame_id,
                            severity = EXCLUDED.severity,
                            status = EXCLUDED.status,
                            summary = EXCLUDED.summary,
                            evidence = EXCLUDED.evidence,
                            metrics = EXCLUDED.metrics,
                            payload = EXCLUDED.payload,
                            search_text = EXCLUDED.search_text,
                            created_at = EXCLUDED.created_at
                        """
                    ).format(qualified(self.settings, "cloud_events")),
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "device_id": event.device_id,
                        "frame_id": event.frame_id,
                        "severity": event.severity.value,
                        "status": event.status.value,
                        "summary": event.summary,
                        "evidence": Jsonb(event.evidence),
                        "metrics": Jsonb(event.metrics),
                        "payload": Jsonb(payload),
                        "search_text": _event_search_text(event),
                        "created_at": event.created_at,
                    },
                )

    def save_analysis_result(self, result: CloudAnalysisResponse) -> None:
        if not self.enabled:
            return
        from psycopg import sql
        from psycopg.types.json import Jsonb

        payload = result.model_dump(mode="json")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO {} (
                            event_id, risk_level, conclusion, reasoning, suggestions,
                            report, used_search, used_knowledge, traces, payload,
                            search_text, created_at
                        )
                        VALUES (
                            %(event_id)s, %(risk_level)s, %(conclusion)s, %(reasoning)s,
                            %(suggestions)s, %(report)s, %(used_search)s, %(used_knowledge)s,
                            %(traces)s, %(payload)s, %(search_text)s, %(created_at)s
                        )
                        ON CONFLICT (event_id) DO UPDATE SET
                            risk_level = EXCLUDED.risk_level,
                            conclusion = EXCLUDED.conclusion,
                            reasoning = EXCLUDED.reasoning,
                            suggestions = EXCLUDED.suggestions,
                            report = EXCLUDED.report,
                            used_search = EXCLUDED.used_search,
                            used_knowledge = EXCLUDED.used_knowledge,
                            traces = EXCLUDED.traces,
                            payload = EXCLUDED.payload,
                            search_text = EXCLUDED.search_text,
                            created_at = EXCLUDED.created_at
                        """
                    ).format(qualified(self.settings, "cloud_analysis_results")),
                    {
                        "event_id": result.event_id,
                        "risk_level": result.risk_level.value,
                        "conclusion": result.conclusion,
                        "reasoning": Jsonb(result.reasoning),
                        "suggestions": Jsonb(result.suggestions),
                        "report": result.report,
                        "used_search": result.used_search,
                        "used_knowledge": result.used_knowledge,
                        "traces": Jsonb(result.traces),
                        "payload": Jsonb(payload),
                        "search_text": _analysis_search_text(result),
                        "created_at": result.created_at,
                    },
                )

    def list_events(self, limit: int = 200) -> list[SafetyEvent]:
        if not self.enabled:
            return []
        from psycopg import sql

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT payload FROM {} ORDER BY created_at DESC LIMIT %(limit)s").format(
                        qualified(self.settings, "cloud_events")
                    ),
                    {"limit": limit},
                )
                return [SafetyEvent.model_validate(row["payload"]) for row in cursor.fetchall()]

    def list_analysis_results(self, limit: int = 200) -> list[CloudAnalysisResponse]:
        if not self.enabled:
            return []
        from psycopg import sql

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT payload FROM {} ORDER BY created_at DESC LIMIT %(limit)s").format(
                        qualified(self.settings, "cloud_analysis_results")
                    ),
                    {"limit": limit},
                )
                return [CloudAnalysisResponse.model_validate(row["payload"]) for row in cursor.fetchall()]

    def get_event(self, event_id: str) -> SafetyEvent | None:
        if not self.enabled:
            return None
        from psycopg import sql

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT payload FROM {} WHERE event_id = %(event_id)s").format(
                        qualified(self.settings, "cloud_events")
                    ),
                    {"event_id": event_id},
                )
                row = cursor.fetchone()
        return SafetyEvent.model_validate(row["payload"]) if row else None

    def get_analysis_result(self, event_id: str) -> CloudAnalysisResponse | None:
        if not self.enabled:
            return None
        from psycopg import sql

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT payload FROM {} WHERE event_id = %(event_id)s").format(
                        qualified(self.settings, "cloud_analysis_results")
                    ),
                    {"event_id": event_id},
                )
                row = cursor.fetchone()
        return CloudAnalysisResponse.model_validate(row["payload"]) if row else None

    def search_events(self, query: str, limit: int = 50) -> list[SafetyEvent]:
        if not self.enabled:
            return []
        from psycopg import sql

        pattern = f"%{query.strip()}%"
        if not query.strip():
            return self.list_events(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        """
                        SELECT e.payload
                        FROM {} e
                        LEFT JOIN {} a ON a.event_id = e.event_id
                        WHERE e.search_text ILIKE %(pattern)s
                           OR COALESCE(a.search_text, '') ILIKE %(pattern)s
                        ORDER BY e.created_at DESC
                        LIMIT %(limit)s
                        """
                    ).format(
                        qualified(self.settings, "cloud_events"),
                        qualified(self.settings, "cloud_analysis_results"),
                    ),
                    {"pattern": pattern, "limit": limit},
                )
                return [SafetyEvent.model_validate(row["payload"]) for row in cursor.fetchall()]


def _event_search_text(event: SafetyEvent) -> str:
    return " ".join(
        _compact(
            [
                event.event_id,
                event.event_type,
                event.device_id,
                event.frame_id,
                event.severity.value,
                event.status.value,
                event.summary,
                *event.evidence,
                *[f"{key}={value}" for key, value in event.metrics.items()],
            ]
        )
    )


def _analysis_search_text(result: CloudAnalysisResponse) -> str:
    return " ".join(
        _compact(
            [
                result.event_id,
                result.risk_level.value,
                result.conclusion,
                result.report,
                *result.reasoning,
                *result.suggestions,
                *result.traces,
            ]
        )
    )


def _compact(items: Iterable[object | None]) -> list[str]:
    return [str(item) for item in items if item is not None and str(item)]
