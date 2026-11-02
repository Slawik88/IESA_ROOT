"""Приватные фото-чеков сайта; Telegram остаётся закрытым транспортом файлов."""
import base64
import binascii
import hashlib
from io import BytesIO

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile
from loguru import logger

from core.constants import MAX_PHOTOS_PER_EXPENSE
from core.receipt_limits import MAX_RECEIPT_DOWNLOAD_BYTES, MAX_RECEIPT_UPLOAD_BYTES, RECEIPT_TRANSFER_TIMEOUT
from core.transaction_versions import expense_version
from infrastructure.repositories import receipts
from services import households, money
from services.households import DomainError


def _image_type(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise DomainError("Выберите фото JPEG или PNG")


def decode_upload(raw: str) -> tuple[bytes, str]:
    try:
        content = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DomainError("Не удалось прочитать фото") from exc
    if not content or len(content) > MAX_RECEIPT_UPLOAD_BYTES:
        raise DomainError("Фото должно быть не больше 2 МБ")
    return content, _image_type(content)


async def _expense(house_id: int, expense_id: int, actor: int, *, edit: bool = False):
    await households.require_member(house_id, actor)
    expense = await money.get_expense(expense_id)
    if expense is None or expense["house_id"] != house_id:
        raise DomainError("Расход не найден")
    if edit:
        if expense["tg_id"] != actor:
            await households.require(house_id, actor, "manage_all_expenses")
        if expense["reimbursed"]:
            raise DomainError("Расход уже возвращён из котла; его нельзя изменять")
    return expense


async def list_receipts(house_id: int, expense_id: int, actor: int, *, available: bool) -> dict:
    expense = await _expense(house_id, expense_id, actor)
    photos = await money.expense_photos(house_id, expense_id)
    pending = await receipts.pending_count(expense_id)
    can_edit = expense["tg_id"] == actor or await households.can(house_id, actor, "manage_all_expenses")
    return {"receipts": [{"id": row["id"]} for row in photos],
            "can_upload": available and can_edit and not expense["reimbursed"]
            and len(photos) + pending < MAX_PHOTOS_PER_EXPENSE,
            "available": available, "max_count": MAX_PHOTOS_PER_EXPENSE,
            "max_bytes": MAX_RECEIPT_UPLOAD_BYTES,
            "upload_notice": "Фото также появится в вашем личном чате с ботом"}


class _BoundedImage(BytesIO):
    def write(self, data):
        if self.tell() + len(data) > MAX_RECEIPT_DOWNLOAD_BYTES:
            raise DomainError("Фото слишком большое для просмотра")
        return super().write(data)


async def download_receipt(house_id: int, expense_id: int, photo_id: int, actor: int, *, bot) -> tuple[bytes, str]:
    await _expense(house_id, expense_id, actor)
    photo = await receipts.get_photo(expense_id, photo_id)
    if photo is None:
        raise DomainError("Чек не найден")
    if bot is None:
        raise DomainError("Просмотр чеков временно недоступен")
    try:
        remote = await bot.get_file(photo["file_id"])
        if not remote.file_path or (remote.file_size or 0) > MAX_RECEIPT_DOWNLOAD_BYTES:
            raise DomainError("Фото слишком большое для просмотра")
        buffer = _BoundedImage()
        await bot.download_file(remote.file_path, destination=buffer, timeout=RECEIPT_TRANSFER_TIMEOUT)
    except (TelegramAPIError, OSError, TimeoutError) as exc:
        logger.warning("Не удалось загрузить приватный чек из Telegram: {}", type(exc).__name__)
        raise DomainError("Не удалось открыть чек. Попробуйте ещё раз позже.") from exc
    content = buffer.getvalue()
    await _expense(house_id, expense_id, actor)
    return content, _image_type(content)


async def upload_receipt(house_id: int, expense_id: int, actor: int, request_id: str, raw: str, *, bot) -> dict:
    await _expense(house_id, expense_id, actor, edit=True)
    if bot is None:
        raise DomainError("Загрузка чеков временно недоступна")
    content, media_type = decode_upload(raw)
    fingerprint = hashlib.sha256(content).hexdigest()
    reservation, created = await receipts.reserve_upload(house_id, expense_id, actor, request_id,
                                                         fingerprint, MAX_PHOTOS_PER_EXPENSE)
    if reservation is None:
        raise DomainError("Нельзя добавить чек: расход изменился или достигнут лимит 10 фото")
    if (reservation["house_id"], reservation["expense_id"], reservation["actor_id"], reservation["fingerprint"]) != (
            house_id, expense_id, actor, fingerprint):
        raise DomainError("Этот ключ загрузки уже использован для другого фото")
    if not created:
        if reservation["state"] == "complete":
            return {"id": reservation["photo_id"], "duplicate": True}
        raise DomainError("Предыдущая загрузка ещё не завершена. Обновите список чеков; фото повторно не отправлено.")
    try:
        filename = "receipt.png" if media_type == "image/png" else "receipt.jpg"
        message = await bot.send_photo(
            actor, BufferedInputFile(content, filename=filename),
            caption="Чек к расходу в домашнем кабинете", request_timeout=RECEIPT_TRANSFER_TIMEOUT,
        )
        file_id = message.photo[-1].file_id
    except TelegramBadRequest as exc:
        await receipts.fail_upload(request_id, uncertain=False)
        raise DomainError("Telegram не принял фото. Выберите другое фото JPEG или PNG.") from exc
    except (TelegramAPIError, OSError, TimeoutError, IndexError, TypeError) as exc:
        await receipts.fail_upload(request_id, uncertain=True)
        logger.warning("Не удалось подтвердить загрузку приватного чека: {}", type(exc).__name__)
        raise DomainError("Не удалось подтвердить загрузку. Проверьте список чеков и личный чат; "
                          "повторной отправки не было.") from exc
    try:
        await _expense(house_id, expense_id, actor, edit=True)
        photo_id = await receipts.complete_upload(request_id, expense_id, house_id, file_id, MAX_PHOTOS_PER_EXPENSE)
    except DomainError:
        await receipts.fail_upload(request_id, uncertain=False)
        raise
    if photo_id is None:
        await receipts.fail_upload(request_id, uncertain=False)
        raise DomainError("Расход изменился во время загрузки. Фото осталось в вашем личном чате.")
    return {"id": photo_id, "duplicate": False}


async def delete_expense(house_id: int, expense_id: int, actor: int, version: str) -> None:
    expense = await _expense(house_id, expense_id, actor, edit=True)
    if expense_version(expense) != version:
        raise DomainError("Расход изменился. Обновите историю перед удалением.")
    if not await receipts.delete_expense_if_unchanged(house_id, expense_id, dict(expense)):
        raise DomainError("Расход изменился. Обновите историю перед удалением.")
