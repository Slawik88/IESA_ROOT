# services/telegram_http.py
# Raw HTTP-транспорт к Telegram Bot API для сервисного слоя: когда live
# aiogram.Bot недоступен (веб-процесс) или не нужен. Паттерн services/purge.py::_tg.
# Токен тот же, что у бота, поэтому callback-кнопки из таких сообщений
# обрабатывают обычные aiogram-хендлеры.
import os

import httpx


async def tg_call(method: str, **kwargs) -> dict:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "no token"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}
