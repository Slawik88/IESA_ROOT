"""Explicit player-initiated diagnostic reports; authenticated and body limited."""
import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from core.support_reports import MAX_BODY_BYTES, ReportQuotaExceeded
from FastAPI.deps import assert_account_active, require_tg_user_base
from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from services import support_reports

router = APIRouter(prefix="/support",tags=["support"])


@router.post("/reports")
async def submit(request: Request, user=Depends(require_tg_user_base)):
    body = bytearray()
    try:
        async with asyncio.timeout(12):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    raise HTTPException(413,"Отчёт слишком большой. Открой форму заново.")
    except TimeoutError as error:
        raise HTTPException(408,"Отправка заняла слишком много времени. Попробуй ещё раз.") from error
    try:
        payload = json.loads(body)
        if not isinstance(payload,dict) or str(payload.get("expected_user_id","")) != str(user["id"]):
            raise HTTPException(409,"Аккаунт изменился. Открой приложение под автором отчёта и повтори отправку.")
        # Read the upload before taking a database slot (slow mobile networks).
        await create_pool()
        async with get_pool().acquire() as connection:
            db = PGAdapter(connection)
            await assert_account_active(db,int(user["id"]))
            return await support_reports.submit(db,user,payload,server_version=getattr(request.app.state,"asset_version",""))
    except ReportQuotaExceeded as error:
        raise HTTPException(429,str(error),headers={"Retry-After":"3600"}) from error
    except (ValueError,TypeError) as error:
        raise HTTPException(400,"Не удалось отправить отчёт. "+str(error)[:160]) from error
