"""
tests/test_schema_dialect.py — DDL для PostgreSQL: AUTOINCREMENT не просачивается.
Регрессия прод-инцидента 2026-11-01: sqlite-синтаксис валился на PostgreSQL.
"""
from infrastructure.schema import _pg_statement

SQLITE_DDL = (
    "CREATE TABLE IF NOT EXISTS houses ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)"
)


def test_pg_statement_replaces_autoincrement():
    pg = _pg_statement(SQLITE_DDL)
    assert "AUTOINCREMENT" not in pg
    assert "BIGSERIAL PRIMARY KEY" in pg


def test_sqlite_statement_untouched_by_transformation():
    # На sqlite трансформация не применяется вовсе (см. ensure_schema),
    # а сама функция обязана быть точечной: не трогает прочий текст.
    assert _pg_statement("CREATE TABLE t (tg_id INTEGER PRIMARY KEY, v TEXT)") == (
        "CREATE TABLE t (tg_id INTEGER PRIMARY KEY, v TEXT)"
    )


def test_all_statements_transform_cleanly():
    from infrastructure.schema import _STATEMENTS

    for statement in _STATEMENTS:
        pg = _pg_statement(statement)
        assert "AUTOINCREMENT" not in pg, "SQLite-синтаксис просочился в DDL для PostgreSQL"
        assert "BIGSERIAL PRIMARY KEY" in pg or "AUTOINCREMENT" not in statement
