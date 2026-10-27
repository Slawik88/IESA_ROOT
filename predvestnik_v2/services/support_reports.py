"""Submission and staff triage, shared by web adapters."""
import asyncio
import time

from core import support_reports as rules
from infrastructure.repositories import support_reports as repo
from services import admin_people
from services.support_diagnostics import recent
from services.vip import is_vip_active


class ReportStorage:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.ready = False
        self.cleaned_at = 0.0

    async def prepare(self, db) -> None:
        async with self.lock:
            if not self.ready:
                await repo.ensure_tables(db)
                self.ready = True
            if time.monotonic()-self.cleaned_at > rules.WINDOW_SECONDS:
                await repo.cleanup(db)
                self.cleaned_at = time.monotonic()


storage = ReportStorage()


async def submit(db, user: dict, body: dict, *, server_version: str = "") -> dict:
    payload = rules.normalize(body)
    uid = int(user["id"])
    await storage.prepare(db)
    context = {}
    if payload["include_diagnostics"]:
        context = {"app_version":rules.safe_text(server_version,80),"received_at":int(time.time()*1000),
                   "vip":bool(await is_vip_active(db,uid)),"telegram_photo_available":bool(user.get("photo_url")),
                   "diagnostics":recent.for_user(uid)}
    result = await repo.submit(db,uid,payload,context)
    return {**{k:result[k] for k in ("id","code","created_at","status","replayed")},
            "client_report_id":payload["client_report_id"]}


async def listing(db, *, status: str = "", category: str = "", page: int = 0) -> dict:
    if status and status not in rules.STATUSES or category and category not in rules.CATEGORIES:
        raise ValueError("Неизвестный фильтр.")
    await storage.prepare(db)
    result = await repo.listing(db,status=status,category=category,page=page)
    result["monitor"] = recent.overview()
    return result


async def set_status(db, report_id: str, status: str, actor: int) -> bool:
    if status not in rules.STATUSES:
        raise ValueError("Неизвестный статус.")
    await storage.prepare(db)
    async with db.connection.transaction():
        if not await repo.set_status(db,report_id,status,actor):
            return False
        await admin_people.audit(db,actor,"support_report_status",details={"report_id":report_id,"status":status})
    return True
