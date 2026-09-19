"""Focused behaviour checks for the global marriage audit query."""
import asyncio

from infrastructure.repositories.marriage_integrity import (
    assert_one_marriage_per_account,
    audit_family_migration_readiness,
    migration_is_safe,
)


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql):
        return _Cursor(self.rows)


class _AuditDb:
    def __init__(self, values):
        self._values = iter(values)

    def execute(self, sql):
        return _Cursor([(next(self._values),)])


async def main():
    await assert_one_marriage_per_account(_Db([]))
    try:
        await assert_one_marriage_per_account(_Db([{"user_id": 12, "marriage_count": 2}]))
    except RuntimeError as error:
        assert "12" in str(error)
    else:
        raise AssertionError("duplicate marriage membership must fail closed")

    clean = await audit_family_migration_readiness(_AuditDb([0, 0, 0, 0, 0]))
    assert migration_is_safe(clean)
    unsafe = await audit_family_migration_readiness(_AuditDb([0, 1, 0, 0, 0]))
    assert not migration_is_safe(unsafe)


asyncio.run(main())
print("marriage integrity: duplicate membership fails closed")
