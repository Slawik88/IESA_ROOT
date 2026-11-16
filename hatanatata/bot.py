"""Private bot workers; interaction and presentation live in dedicated modules."""

import asyncio
import json
import logging
import time

from .interaction import Interaction
from .models import Listing
from .telegram import TelegramError
from .views import listing_keyboard, listing_text

log = logging.getLogger(__name__)


class Bot(Interaction):
    def __init__(self, store, telegram, allowed_ids):
        self.store, self.telegram, self.allowed_ids = store, telegram, set(allowed_ids)
        self.panels = {}

    async def poll(self):
        offset = self.store.get("telegram_offset", 0)
        while True:
            try:
                updates = await self.telegram.call(
                    "getUpdates",
                    offset=offset,
                    timeout=45,
                    allowed_updates=["message", "callback_query"],
                )
                for update in updates:
                    try:
                        await self.handle(update)
                    except TelegramError as exc:
                        if exc.code == 429 or exc.code == 0 or exc.code >= 500:
                            raise
                        log.warning("update response failed code=%s", exc.code)
                    # Only acknowledge updates after handling; transient failures are retried.
                    offset = update["update_id"] + 1
                    self.store.put("telegram_offset", offset)
            except TelegramError as exc:
                if exc.code in {401, 409}:
                    raise RuntimeError(
                        "Telegram authorization or competing polling receiver"
                    ) from None
                log.warning("poll retry code=%s", exc.code)
                await asyncio.sleep(min(300, max(5, exc.retry)))

    async def deliver(self):
        while True:
            for row in self.store.pending():
                user_id = row["user_id"]
                user = self.store.user(user_id)
                listing = Listing(**json.loads(row["data"]))
                if user_id not in self.allowed_ids or not user or not user["active"]:
                    self.store.delivery_result(row, "cancelled")
                    continue
                search = self.store.search(user_id)
                if (
                    search.paused
                    or not search.matches(listing)
                    or row["created"] < time.time() - 86400
                ):
                    self.store.delivery_result(row, "cancelled")
                    continue
                try:
                    await self.telegram.send(
                        user_id,
                        listing_text(listing, detected=row["created"]),
                        listing_keyboard(
                            listing, self.store.is_favorite(user_id, listing.key)
                        ),
                    )
                except TelegramError as exc:
                    if exc.code in {400, 403}:
                        self.store.set_user(user_id, active=False)
                        self.store.delivery_result(row, "cancelled")
                    elif exc.code == 401:
                        raise RuntimeError("Telegram token rejected") from None
                    else:
                        self.store.delivery_result(
                            row,
                            "pending",
                            min(
                                3600, max(exc.retry, 30 * 2 ** min(row["attempts"], 6))
                            ),
                        )
                        if exc.code == 429:
                            await asyncio.sleep(min(300, exc.retry))
                else:
                    self.store.delivery_result(row, "sent")
                await asyncio.sleep(1)
            await asyncio.sleep(3)
