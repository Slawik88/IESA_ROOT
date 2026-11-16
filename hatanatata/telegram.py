"""Minimal Telegram Bot API client; token-bearing URLs never reach logs."""

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)


class TelegramError(Exception):
    def __init__(self, code, retry=30):
        super().__init__("Telegram API error " + str(code))
        self.code, self.retry = code, retry


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
                {"command": "settings", "description": "Настроить мой поиск"},
                {"command": "current", "description": "Подходящие объявления сейчас"},
                {"command": "status", "description": "Проверки и доступность сайтов"},
                {"command": "pause", "description": "Приостановить уведомления"},
                {"command": "resume", "description": "Возобновить уведомления"},
                {"command": "cancel", "description": "Отменить ввод"},
                {"command": "help", "description": "Как пользоваться ботом"},
            ],
        )
        return me
