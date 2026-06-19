from __future__ import annotations

from backend.shared.core.config import Settings


def initialize_database(settings: Settings) -> None:
    """Let the cloud service own optional PostgreSQL capabilities."""
    if not settings.postgres_vector_enabled:
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
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
