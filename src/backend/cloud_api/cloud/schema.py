from __future__ import annotations

from backend.shared.core.config import Settings


def qualified(settings: Settings, table: str):
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
                _create_persistence_tables(cursor, settings)


def _create_persistence_tables(cursor, settings: Settings) -> None:
    from psycopg import sql

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
        ).format(qualified(settings, "cloud_events"))
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
        ).format(qualified(settings, "cloud_analysis_results"))
    )
    cursor.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (created_at DESC)").format(
            sql.Identifier(f"{settings.postgres_schema}_cloud_events_created_at_idx"),
            qualified(settings, "cloud_events"),
        )
    )
    cursor.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (device_id, created_at DESC)").format(
            sql.Identifier(f"{settings.postgres_schema}_cloud_events_device_idx"),
            qualified(settings, "cloud_events"),
        )
    )
