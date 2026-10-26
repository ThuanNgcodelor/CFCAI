"""Small ordered SQL migration runner for the Docker Compose deployment."""

from __future__ import annotations

from pathlib import Path


def apply_migrations(database_url: str, migrations_dir: Path | None = None) -> list[str]:
    import psycopg2  # type: ignore[import-untyped]

    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    root = migrations_dir or Path(__file__).resolve().parents[4] / "migrations"
    applied: list[str] = []
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("cfc-zeo-migrations",))
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations(
            migration_name TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
        )
        cursor.execute("SELECT migration_name FROM schema_migrations")
        completed = {row[0] for row in cursor.fetchall()}
        for path in sorted(root.glob("*.sql")):
            if path.name in completed:
                continue
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute(
                "INSERT INTO schema_migrations(migration_name) VALUES (%s)",
                (path.name,),
            )
            applied.append(path.name)
    return applied
