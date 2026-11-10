"""Keep Telegram's polling offset behind the durable group-message counters."""
import asyncio
from dataclasses import dataclass

from aiogram.methods import GetUpdates
from loguru import logger

from core import ops_metrics
from infrastructure.database import get_pool
from infrastructure.lazy_db import lazy_connection
from infrastructure.repositories import update_receipts
from services import chat_bots, membership


@dataclass(frozen=True)
class Receipt:
    bot_id: int
    update_id: int
    outcome: asyncio.Future[bool]

    async def claim(self, db) -> bool:
        return await update_receipts.claim(db, self.bot_id, self.update_id)

    def complete(self) -> None:
        if not self.outcome.done():
            self.outcome.set_result(True)

    async def finish(self, db) -> bool:
        first = await self.claim(db)
        self.complete()
        return first


class PollingDelivery:
    def __init__(self) -> None:
        self._offset: int | None = None
        self._batch: dict[int, Receipt] = {}
        self._retrying = False

    async def __call__(self, make_request, bot, method):
        if not isinstance(method, GetUpdates):
            return await make_request(bot, method)

        if self._batch:
            outcomes = await asyncio.gather(*(receipt.outcome for receipt in self._batch.values()))
            if all(outcomes):
                self._offset = max(self._batch) + 1
                if self._retrying:
                    logger.info("Telegram polling receipts recovered; resuming offset advancement")
                self._retrying = False
            else:
                ops_metrics.count("telegram_receipt_retry", "get_updates")
                if not self._retrying:
                    logger.warning("Telegram polling offset held: {} of {} updates still need a durable receipt",
                                   outcomes.count(False), len(outcomes))
                self._retrying = True
                await asyncio.sleep(1)

        # aiogram advances its own offset when scheduling, before handlers finish. Keep our own.
        updates = await make_request(bot, method.model_copy(update={"offset": self._offset}))
        if not updates:
            # The offset was accepted. Do not keep sending an old ID after a long idle period.
            self._offset = None
            if self._retrying:
                logger.error("Telegram returned an empty queue while polling receipts were still pending")
                self._retrying = False
        loop = asyncio.get_running_loop()
        self._batch = {update.update_id: Receipt(bot.id, update.update_id, loop.create_future()) for update in updates}
        return updates

    async def update(self, handler, event, data):
        receipt = self._batch.get(event.update_id)
        if receipt is None:
            return await handler(event, data)

        try:
            message = event.message
            counted = (message is not None and message.chat.type in ("group", "supergroup")
                       and message.from_user and not chat_bots.is_bot(message.from_user)
                       and not membership.is_service(message))
            async with lazy_connection(get_pool(), source="bot") as db:
                if not counted:
                    if not await receipt.finish(db):
                        return None
                elif await update_receipts.seen(db, receipt.bot_id, receipt.update_id):
                    receipt.complete()
                    return None
            if counted:
                data["delivery_receipt"] = receipt
            result = await handler(event, data)
            if not receipt.outcome.done():
                # The normal route returned without counting (e.g. ignored by chat policy).
                async with lazy_connection(get_pool(), source="bot") as db:
                    await receipt.finish(db)
            return result
        finally:
            if not receipt.outcome.done():
                receipt.outcome.set_result(False)

    async def message(self, handler, event, data):
        receipt = data.get("delivery_receipt")
        if receipt and not data["handler"].flags.get("counts_group_message"):
            # Earlier message routes (such as /start) don't increment the counters.
            if not await receipt.finish(data["db"]):
                return None
            data.pop("delivery_receipt")
        return await handler(event, data)
