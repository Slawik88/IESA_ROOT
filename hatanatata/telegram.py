"""Minimal Telegram Bot API client; token-bearing URLs never reach logs."""

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)


class TelegramError(Exception):
    def __init__(self, code, retry=30, *, not_modified=False):
        super().__init__("Telegram API error " + str(code))
        self.code, self.retry = code, retry
        self.not_modified = not_modified


class Telegram:
    def __init__(self, token, session):
        self.base = "https://api.telegram.org/bot" + token + "/"
        self.session = session
        self.send_lock = asyncio.Lock()

    async def call(self, method, **payload):
        try:
            async with self.session.post(
                self.base + method,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=55),
            ) as response:
                data = await response.json(content_type=None)
                if not data.get("ok"):
                    raise TelegramError(
                        data.get("error_code", response.status),
                        data.get("parameters", {}).get("retry_after", 30),
                        not_modified="message is not modified"
                        in data.get("description", "").lower(),
                    )
                return data["result"]
        except (TimeoutError, aiohttp.ClientError, ValueError) as exc:
            raise TelegramError(0) from exc

    async def send(self, user_id, text, keyboard=None):
        async with self.send_lock:
            payload = {
                "chat_id": user_id,
                "text": text[:4000],
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            }
            if keyboard:
                payload["reply_markup"] = keyboard
            result = await self.call("sendMessage", **payload)
            await asyncio.sleep(0.06)
            return result

    async def panel(self, user_id, text, keyboard, message_id=None):
        """Navigate in place; an expired/deleted panel becomes a fresh message."""
        if message_id is not None:
            try:
                return await self.call(
                    "editMessageText",
                    chat_id=user_id,
                    message_id=message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    link_preview_options={"is_disabled": True},
                )
            except TelegramError as exc:
                if exc.not_modified:
                    return {"message_id": message_id}
                if exc.code != 400:
                    raise
        return await self.send(user_id, text, keyboard)

    async def setup(self):
        me = await self.call("getMe")
        if me.get("username", "").lower() != "hatanatata1bot":
            raise RuntimeError("Unexpected bot identity; refusing to start")
        webhook = await self.call("getWebhookInfo")
        if webhook.get("url"):
            raise RuntimeError("Webhook already configured; refusing a second receiver")
        await self.call(
            "setMyCommands",
            commands=[
                {"command": "start", "description": "Открыть меню поиска жилья"},
                {"command": "menu", "description": "Главный экран"},
                {"command": "settings", "description": "Настроить мой поиск"},
                {"command": "current", "description": "Подходящие объявления сейчас"},
                {"command": "favorites", "description": "Сохранённые объявления"},
                {"command": "status", "description": "Проверки и доступность сайтов"},
                {"command": "pause", "description": "Приостановить уведомления"},
                {"command": "resume", "description": "Возобновить уведомления"},
                {"command": "cancel", "description": "Отменить ввод"},
                {"command": "help", "description": "Как пользоваться ботом"},
            ],
        )
        return me
