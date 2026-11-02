"""HTTP-адаптер закрытых фото-чеков и удаления расхода."""
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.receipt_limits import MAX_RECEIPT_BASE64_CHARS
from services import web_receipts


class ReceiptUpload(BaseModel):
    request_id: UUID
    content: str = Field(min_length=1, max_length=MAX_RECEIPT_BASE64_CHARS)


class ExpenseRemoval(BaseModel):
    version: str = Field(min_length=64, max_length=64)


def register_receipt_routes(app: FastAPI, bot=None) -> None:
    @app.get("/api/houses/{house_id}/expenses/{expense_id}/receipts")
    async def listing(request: Request, house_id: int, expense_id: int):
        return await web_receipts.list_receipts(house_id, expense_id, request.state.actor, available=bot is not None)

    @app.get("/api/houses/{house_id}/expenses/{expense_id}/receipts/{photo_id}")
    async def image(request: Request, house_id: int, expense_id: int, photo_id: int):
        content, media_type = await web_receipts.download_receipt(house_id, expense_id, photo_id,
                                                                request.state.actor, bot=bot)
        return Response(content, media_type=media_type,
                        headers={"Content-Disposition": 'inline; filename="receipt"', "Cache-Control": "no-store"})

    @app.post("/api/houses/{house_id}/expenses/{expense_id}/receipts")
    async def upload(request: Request, house_id: int, expense_id: int, payload: ReceiptUpload):
        return await web_receipts.upload_receipt(house_id, expense_id, request.state.actor,
                                                str(payload.request_id), payload.content, bot=bot)

    @app.post("/api/houses/{house_id}/expenses/{expense_id}/delete")
    async def remove(request: Request, house_id: int, expense_id: int, payload: ExpenseRemoval):
        await web_receipts.delete_expense(house_id, expense_id, request.state.actor, payload.version)
        return {"ok": True}
