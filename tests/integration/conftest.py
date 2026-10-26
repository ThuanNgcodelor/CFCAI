from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from urllib.parse import quote

import psycopg2
import pytest
from psycopg2 import sql

from src.chatbot.infrastructure.db.migrations import apply_migrations


@pytest.fixture
def isolated_database_url() -> Iterator[str]:
    """Use a disposable PostgreSQL schema and never modify workspace data."""
    base_dsn = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://cfc_admin:cfc_secret_password@localhost:5432/cfc_zeo_db",
    )
    schema = f"test_{uuid.uuid4().hex}"
    try:
        with psycopg2.connect(base_dsn) as connection, connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    except psycopg2.Error as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    separator = "&" if "?" in base_dsn else "?"
    scoped_dsn = f"{base_dsn}{separator}options={quote(f'-csearch_path={schema}') }"
    try:
        apply_migrations(scoped_dsn)
        yield scoped_dsn
    finally:
        with psycopg2.connect(base_dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )
