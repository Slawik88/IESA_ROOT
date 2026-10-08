"""Cheap read-path check; explicit migrations still install the complete schema."""


async def schema_ready(db, *, tables, columns=(), triggers=()) -> bool:
    # No process cache: a rolled-back migration or a different test schema must
    # never inherit readiness. Resolve names using this connection's search_path.
    sql = """
        SELECT NOT EXISTS (
            SELECT 1 FROM unnest(?::text[]) AS r(name)
            WHERE to_regclass(r.name) IS NULL
        ) AND NOT EXISTS (
            SELECT 1 FROM unnest(?::text[], ?::text[]) AS r(tbl, col)
            WHERE NOT EXISTS (
                SELECT 1 FROM pg_attribute a
                WHERE a.attrelid=to_regclass(r.tbl) AND a.attname=r.col
                  AND a.attnum>0 AND NOT a.attisdropped
            )
        ) AND NOT EXISTS (
            SELECT 1 FROM unnest(?::text[], ?::text[], ?::text[]) AS r(tbl, trg, fn)
            WHERE NOT EXISTS (
                SELECT 1 FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
                WHERE t.tgrelid=to_regclass(r.tbl) AND t.tgname=r.trg
                  AND NOT t.tgisinternal AND t.tgenabled IN ('O','A')
                  AND p.proname=r.fn
            )
        )
    """
    args = (
        list(tables), [r[0] for r in columns], [r[1] for r in columns],
        [r[0] for r in triggers], [r[1] for r in triggers], [r[2] for r in triggers],
    )
    async with db.execute(sql, args) as cursor:
        return bool((await cursor.fetchone())[0])


async def ensure_read_schema(db, *, install, name, **spec) -> None:
    if await schema_ready(db, **spec):
        return
    # Cold ASGI/lifespan-off fallback. PostgreSQL serializes initializers across
    # processes; the second caller rechecks rather than replacing live triggers.
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?,0))",
                         ("predvestnik:read-schema:" + name,))
        if not await schema_ready(db, **spec):
            await install(db)
