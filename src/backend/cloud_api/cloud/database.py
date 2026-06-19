from __future__ import annotations

from collections.abc import Iterable

from backend.shared.core.config import Settings
from backend.shared.core.state import RuntimeState
from backend.shared.domain.models import CloudAnalysisResponse, SafetyEvent


def _qualified(settings: Settings, table: str):
    from psycopg import sql

    return sql.SQL("{}.{}").format(sql.Identifier(settings.postgres_schema), sql.Identifier(table))


def initialize_database(settings: Settings) -> None:
    """Let the cloud service own optional PostgreSQL capabilities."""
    if not settings.postgres_persistence_enabled and not settings.postgres_vector_enabled:
        return

    from psycopg import connect, sql

    with connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(settings.postgres_schema)
                )
            )
            if settings.postgres_vector_enabled:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            if settings.postgres_persistence_enabled:
                cursor.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            event_id TEXT PRIMARY KEY,
                            event_type TEXT NOT NULL,
                            device_id TEXT NOT NULL,
                            frame_id TEXT,
                            severity TEXT NOT NULL,
                            status TEXT NOT NULL,
                            summary TEXT NOT NULL,
                            evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
                            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                            payload JSONB NOT NULL,
                            search_text TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    ).format(_qualified(settings, "cloud_events"))
                )
                cursor.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            event_id TEXT PRIMARY KEY,
                            risk_level TEXT NOT NULL,
                            conclusion TEXT NOT NULL,
                            reasoning JSONB NOT NULL DEFAULT '[]'::jsonb,
                            suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
                            report TEXT NOT NULL,
                            used_search BOOLEAN NOT NULL DEFAULT false,
                            used_knowledge BOOLEAN NOT NULL DEFAULT false,
                            traces JSONB NOT NULL DEFAULT '[]'::jsonb,
                            payload JSONB NOT NULL,
                            search_text TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    ).format(_qualified(settings, "cloud_analysis_results"))
                )
                cursor.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (created_at DESC)").format(
                        sql.Identifier(f"{settings.postgres_schema}_cloud_events_created_at_idx"),
                        _qualified(settings, "cloud_events"),
                    )
                )
                cursor.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (device_id, created_at DESC)").format(
                        sql.Identifier(f"{settings.postgres_schema}_cloud_events_device_idx"),
                        _qualified(settings, "cloud_events"),
                    )
                )


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
        search_text = _event_search_text(event)
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
                    ).format(_qualified(self.settings, "cloud_events")),
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
                        "search_text": search_text,
                        "created_at": event.created_at,
                    },
                )

    def save_analysis_result(self, result: CloudAnalysisResponse) -> None:
        if not self.enabled:
            return
        from psycopg import sql
        from psycopg.types.json import Jsonb

        payload = result.model_dump(mode="json")
        search_text = _analysis_search_text(result)
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
                    ).format(_qualified(self.settings, "cloud_analysis_results")),
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
                        "search_text": search_text,
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
                        _qualified(self.settings, "cloud_events")
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
                        _qualified(self.settings, "cloud_analysis_results")
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
                        _qualified(self.settings, "cloud_events")
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
                        _qualified(self.settings, "cloud_analysis_results")
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
                        _qualified(self.settings, "cloud_events"),
                        _qualified(self.settings, "cloud_analysis_results"),
                    ),
                    {"pattern": pattern, "limit": limit},
                )
                return [SafetyEvent.model_validate(row["payload"]) for row in cursor.fetchall()]


def hydrate_runtime_state(state: RuntimeState, repository: CloudEventRepository, limit: int = 200) -> None:
    if not repository.enabled:
        return
    state.replace_history(
        events=repository.list_events(limit),
        analysis_results=repository.list_analysis_results(limit),
    )


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
