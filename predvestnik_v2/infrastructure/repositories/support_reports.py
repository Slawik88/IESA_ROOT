"""Player support reports with atomic quotas and idempotent delivery receipts."""
import hashlib
import json
from uuid import uuid4

from core import support_reports as rules


async def ensure_tables(db) -> None:
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('schema:support-reports',0))")
        await _create_tables(db)


async def _create_tables(db) -> None:
    await db.execute("""CREATE TABLE IF NOT EXISTS support_reports (
        id UUID PRIMARY KEY, user_id BIGINT NOT NULL, client_report_id UUID NOT NULL,
        body_digest TEXT NOT NULL, category TEXT NOT NULL, comment TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new', payload JSONB NOT NULL, server_context JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), updated_by BIGINT,
        UNIQUE(user_id,client_report_id))""")
    await db.execute("CREATE INDEX IF NOT EXISTS support_reports_created ON support_reports(created_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS support_reports_status_created ON support_reports(status,created_at DESC)")


def decode(row) -> dict:
    out = dict(row)
    for key in ("payload","server_context"):
        if key in out and isinstance(out[key],str):
            out[key] = json.loads(out[key])
    for key in ("id","client_report_id"):
        if key in out:
            out[key] = str(out[key])
    for key in ("created_at","updated_at"):
        if key in out:
            out[key] = out[key].isoformat()
    out["code"] = "PV-"+out["id"].replace("-","")[:12].upper()
    return out


async def submit(db, user_id: int, payload: dict, context: dict) -> dict:
    encoded = json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?,0))",(f"support-report:{user_id}",))
        async with db.execute("SELECT id,body_digest,created_at,status FROM support_reports WHERE user_id=? AND client_report_id=?::uuid",(user_id,payload["client_report_id"])) as cur:
            previous = await cur.fetchone()
        if previous:
            if previous["body_digest"] != digest:
                raise ValueError("Этот отчёт уже отправлен с другим содержимым.")
            return {**decode(previous),"replayed":True}
        async with db.execute("SELECT COUNT(*) FROM support_reports WHERE user_id=? AND created_at>CLOCK_TIMESTAMP()-INTERVAL '1 hour'",(user_id,)) as cur:
            count = (await cur.fetchone())[0]
        if count >= rules.REPORTS_PER_HOUR:
            raise rules.ReportQuotaExceeded(f"За час уже отправлено {rules.REPORTS_PER_HOUR} отчётов. Попробуй позже — сообщение сохранено на устройстве.")
        async with db.execute("INSERT INTO support_reports(id,user_id,client_report_id,body_digest,category,comment,payload,server_context) VALUES (?::uuid,?,?::uuid,?,?,?,?::jsonb,?::jsonb) RETURNING id,created_at,status",
                              (str(uuid4()),user_id,payload["client_report_id"],digest,payload["category"],payload["comment"],encoded,json.dumps(context,ensure_ascii=False,allow_nan=False))) as cur:
            result = decode(await cur.fetchone())
    return {**result,"replayed":False}


async def cleanup(db) -> None:
    await db.execute("DELETE FROM support_reports WHERE created_at<CLOCK_TIMESTAMP()-make_interval(days=>?)",(rules.RETENTION_DAYS,))


async def listing(db, *, status: str = "", category: str = "", page: int = 0) -> dict:
    conditions, args = [], []
    if status:
        conditions.append("status=?"); args.append(status)
    if category:
        conditions.append("category=?"); args.append(category)
    where = " WHERE "+" AND ".join(conditions) if conditions else ""
    async with db.execute("SELECT COUNT(*) FROM support_reports"+where,tuple(args)) as cur:
        total = int((await cur.fetchone())[0])
    page = max(0,min(page,(max(0,total-1))//30))
    async with db.execute("SELECT id,user_id,category,comment,status,created_at,updated_at FROM support_reports"+where+" ORDER BY created_at DESC,id DESC LIMIT 30 OFFSET ?",(*args,page*30)) as cur:
        items = [decode(row) for row in await cur.fetchall()]
    async with db.execute("SELECT status,COUNT(*) FROM support_reports GROUP BY status") as cur:
        counts = {row[0]:int(row[1]) for row in await cur.fetchall()}
    return {"items":items,"total":total,"page":page,"counts":counts}


async def get(db, report_id: str) -> dict | None:
    async with db.execute("SELECT id,user_id,client_report_id,category,comment,status,payload,server_context,created_at,updated_at,updated_by FROM support_reports WHERE id=?::uuid",(report_id,)) as cur:
        row = await cur.fetchone()
    return decode(row) if row else None


async def set_status(db, report_id: str, status: str, actor: int) -> bool:
    async with db.execute("UPDATE support_reports SET status=?,updated_by=?,updated_at=CLOCK_TIMESTAMP() WHERE id=?::uuid RETURNING id",(status,actor,report_id)) as cur:
        return await cur.fetchone() is not None
