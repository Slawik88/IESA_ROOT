"""Тонкий HTTP-адаптер с отдельной Telegram-авторизацией и проверкой дома."""
import base64
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from core import config
from core.constants import JOURNAL_SEARCH_LIMIT
from services import cleaning, households, journal, money, settings, transfers, web_commands
from services.households import DomainError
from services.transaction_dates import parse_month
from services.web_auth import verify_init_data
from web.receipt_routes import register_receipt_routes
from web.management import router as management_router

STATIC = Path(__file__).with_name("static")
ASSET_TYPES = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2"}
# Файлы интерфейса одинаковы для всех и без данных; адрес содержит отпечаток содержимого, поэтому
# браузер хранит их навсегда, а любая правка получает новый адрес. Страница и API остаются no-store.
ASSET_HEADERS = {"Cache-Control": "private, max-age=31536000, immutable"}
SECURITY_HEADERS = {
    "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow, noarchive",
    "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; script-src 'self' https://telegram.org; "
    "style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self' data: blob:; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'self' https://web.telegram.org https://*.telegram.org",
}


class TransactionInput(BaseModel):
    request_id: UUID
    kind: Literal["expense", "contribution"]
    amount: str = Field(min_length=1, max_length=32)
    date: str = Field(max_length=10)
    month: str = Field(default="", max_length=7)
    category_id: int | None = None
    mode: Literal["house", "personal"] = "house"
    description: str = Field(default="", max_length=200)


class ImportInput(BaseModel):
    extension: Literal["csv", "tsv", "json", "xlsx"]
    content: str = Field(max_length=2800000)


class Decision(BaseModel):
    confirm: bool


class ExpenseEditInput(TransactionInput):
    kind: Literal["expense"] = "expense"
    version: str = Field(min_length=64, max_length=64)


class RecordVersion(BaseModel):
    version: str = Field(min_length=64, max_length=64)


def journal_params(
    month: str | None = None, q: str = Query(default="", max_length=JOURNAL_SEARCH_LIMIT), kind: str = "all",
    member: int | None = None, category: int | None = None, mode: str = "all", sort: str = "newest",
) -> journal.JournalQuery:
    return journal.JournalQuery(month, q, kind, member, category, mode, sort)


def asset_version() -> str:
    """Короткий отпечаток всех файлов интерфейса: меняется с любой правкой."""
    digest = hashlib.sha256()
    for path in sorted(STATIC.rglob("*")):
        if path.is_file() and path.suffix in (*ASSET_TYPES, ".html"):
            digest.update(path.relative_to(STATIC).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def create_app(*, bot=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.state.bot = bot
    page = (STATIC / "index.html").read_text(encoding="utf-8").replace("__V__", asset_version())

    @app.middleware("http")
    async def private_boundary(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            raw = request.headers.get("authorization", "")
            try:
                if not raw.startswith("tma "):
                    raise DomainError("Missing authorization")
                request.state.actor = verify_init_data(raw[4:], config.BOT_TOKEN)
            except DomainError:
                return JSONResponse({"detail": "Not Found"}, status_code=404, headers=SECURITY_HEADERS)
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse({"detail": str(exc)}, status_code=422, headers=SECURITY_HEADERS)

    async def context(request: Request, house_id: int):
        await households.require_member(house_id, request.state.actor)
        return await settings.house_settings(house_id)

    @app.get("/")
    async def index():
        return Response(page, media_type="text/html; charset=utf-8")

    @app.get("/v/{build}/{asset:path}")
    async def static_asset(build: str, asset: str):
        path = (STATIC / asset).resolve()
        if STATIC.resolve() not in path.parents or path.suffix not in ASSET_TYPES or not path.is_file():
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(path, media_type=ASSET_TYPES[path.suffix], headers=ASSET_HEADERS)

    def legacy_asset(name: str, media_type: str, folder: str = "") -> None:
        """Действующий интерфейс подключает файлы по коротким адресам, пока не заменён новым."""
        async def serve():
            return FileResponse(STATIC / folder / name, media_type=media_type)
        app.get(f"/{name}")(serve)

    for script in ("app.js", "house.js", "i18n.js", "receipts.js"):
        legacy_asset(script, "text/javascript")
    legacy_asset("app.css", "text/css")
    legacy_asset("onest.ttf", "font/ttf", "fonts")

    @app.get("/api/houses")
    async def houses(request: Request):
        return {"houses": [dict(row) for row in await households.houses_of_user(request.state.actor)]}

    @app.get("/api/houses/{house_id}")
    async def overview(
        request: Request, house_id: int, query: journal.JournalQuery = Depends(journal_params),
        page: int = 0, all_months: bool = False,
    ):
        values = await context(request, house_id)
        today = settings.house_today(values)
        selected = None if all_months else parse_month(query.month or today[:7])
        query = replace(query, month=selected)
        await cleaning.ensure_days(house_id, today)
        entries = await journal.view(house_id, request.state.actor, query, page)
        permissions = {}
        for code in ("confirm_contributions", "import_transactions", "manage_schedule", "close_others_days"):
            permissions[code] = await households.can(house_id, request.state.actor, code)
        house = await households.get_house(house_id)
        return {
            "title": "Домовой", "actor": request.state.actor, "house": {"id": house_id, "name": house["name"]},
            "today": today, "month": selected or today[:7], "all_months": all_months, "currency": values["currency"],
            "balance": await money.pot_balance(house_id), "permissions": permissions,
            "categories": [dict(row) for row in await money.categories(house_id)],
            "members": [dict(row) for row in await households.members(house_id)],
            "cleaning": [dict(row) for row in await cleaning.open_days_up_to(house_id, today)],
            "upcoming": [dict(row) for row in await cleaning.upcoming_days(house_id, today)],
            "pending": [dict(row) for row in await money.pending_contributions(house_id)]
                       if permissions["confirm_contributions"] else [],
            **entries,
        }

    @app.post("/api/houses/{house_id}/transactions")
    async def create(request: Request, house_id: int, payload: TransactionInput):
        await context(request, house_id)
        return await web_commands.create_transaction(house_id, request.state.actor,
                                                     payload.model_dump(mode="json"), bot=bot)

    @app.post("/api/houses/{house_id}/expenses/{expense_id}/edit")
    async def edit(request: Request, house_id: int, expense_id: int, payload: ExpenseEditInput):
        await context(request, house_id)
        return await web_commands.edit_expense(house_id, request.state.actor, expense_id,
                                               payload.model_dump(mode="json"), payload.version)

    @app.post("/api/houses/{house_id}/expenses/{expense_id}/reimburse")
    async def reimburse(request: Request, house_id: int, expense_id: int, payload: RecordVersion):
        await context(request, house_id)
        await money.reimburse_expense(house_id, expense_id, request.state.actor,
                                      expected_version=payload.version, idempotent=True)
        return {"ok": True}

    @app.post("/api/houses/{house_id}/clean/{day_id}")
    async def close_cleaning(request: Request, house_id: int, day_id: int):
        values = await context(request, house_id)
        today = settings.house_today(values)
        await cleaning.close_day_for(house_id, day_id, request.state.actor, today)
        return {"ok": True}

    @app.post("/api/houses/{house_id}/contributions/{contribution_id}")
    async def decide(request: Request, house_id: int, contribution_id: int, payload: Decision):
        await context(request, house_id)
        row = await money.resolve_contribution(contribution_id, payload.confirm, request.state.actor, house_id=house_id)
        return {"status": row["status"]}

    @app.get("/api/houses/{house_id}/export/{extension}")
    async def export(
        request: Request, house_id: int, extension: str, query: journal.JournalQuery = Depends(journal_params),
    ):
        await context(request, house_id)
        content = await transfers.export_file(house_id, request.state.actor, extension, query=query)
        return Response(content, media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="operations.{extension}"',
        })

    @app.get("/api/houses/{house_id}/template/{extension}")
    async def template(request: Request, house_id: int, extension: str):
        await households.require(house_id, request.state.actor, "import_transactions")
        return Response(transfers.template_file(extension), media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="template.{extension}"',
        })

    async def import_content(payload: ImportInput) -> bytes:
        try:
            return base64.b64decode(payload.content, validate=True)
        except ValueError as exc:
            raise DomainError("Файл повреждён. Выберите его заново.") from exc

    @app.post("/api/houses/{house_id}/import/preview")
    async def preview(request: Request, house_id: int, payload: ImportInput):
        await context(request, house_id)
        result = await transfers.preview_import(house_id, request.state.actor,
                                                 await import_content(payload), payload.extension)
        return {"new": len(result.rows), "duplicates": result.duplicates,
                "errors": result.errors[:20], "error_count": len(result.errors), "balance_delta": result.balance_delta}

    @app.post("/api/houses/{house_id}/import/confirm")
    async def apply(request: Request, house_id: int, payload: ImportInput):
        await context(request, house_id)
        added, skipped = await transfers.import_file(house_id, request.state.actor,
                                                     await import_content(payload), payload.extension)
        return {"added": added, "duplicates": skipped}

    app.include_router(management_router)
    register_receipt_routes(app, bot)
    return app
