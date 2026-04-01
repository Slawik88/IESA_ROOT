"""
Погода: бот погода [город]

Использует бесплатный API wttr.in.
"""
import html

import aiohttp
from aiogram import Router
from aiogram.types import Message

from filters.bot_command import BotCommand

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())


_WTTR_URL = "https://wttr.in/{city}?format=j1&lang=ru"
_WIND_DIR = {
    "N": "↑", "NNE": "↑↗", "NE": "↗", "ENE": "→↗",
    "E": "→", "ESE": "→↘", "SE": "↘", "SSE": "↓↘",
    "S": "↓", "SSW": "↓↙", "SW": "↙", "WSW": "←↙",
    "W": "←", "WNW": "←↖", "NW": "↖", "NNW": "↑↖",
}


def _weather_emoji(code: int) -> str:
    if code in (113,):           return "☀️"
    if code in (116,):           return "⛅"
    if code in (119, 122):       return "☁️"
    if code in (143, 248, 260):  return "🌫"
    if 176 <= code <= 185:       return "🌦"
    if 200 <= code <= 202:       return "⛈"
    if 227 <= code <= 260:       return "🌨"
    if 263 <= code <= 299:       return "🌧"
    if 302 <= code <= 395:       return "🌧"
    return "🌤"


@router.message(BotCommand("погода", "weather", "прогноз погоды"))
async def cmd_weather(message: Message, cmd_args: str):
    city = (cmd_args or "").strip()
    if not city:
        await message.answer(
            "🌤 Укажи город: <code>бот погода Москва</code>\n"
            "Или по-английски: <code>бот погода Berlin</code>",
            parse_mode="HTML",
        )
        return

    try:
        async with aiohttp.ClientSession() as session:
            url = _WTTR_URL.format(city=city)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 404:
                    await message.answer("❌ Город не найден. Проверь название.")
                    return
                if resp.status != 200:
                    await message.answer("⚠️ Сервис недоступен, попробуй позже.")
                    return
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    await message.answer("⚠️ Сервис вернул неожиданный ответ.")
                    return
    except aiohttp.ClientError:
        await message.answer("⚠️ Не удалось подключиться к сервису погоды.")
        return

    try:
        cur   = data["current_condition"][0]
        area  = data["nearest_area"][0]

        city_name    = area["areaName"][0]["value"]
        country      = area["country"][0]["value"]
        temp_c       = cur["temp_C"]
        feels_c      = cur["FeelsLikeC"]
        humidity     = cur["humidity"]
        wind_kmph    = cur["windspeedKmph"]
        wind_dir_16  = cur.get("winddir16Point", "")
        wind_arrow   = _WIND_DIR.get(wind_dir_16, "")
        vis_km       = cur.get("visibility", "?")
        pressure     = cur.get("pressure", "?")
        weather_code = int(cur["weatherCode"])

        # Description: prefer Russian, fallback to English
        desc_list = cur.get("lang_ru") or cur.get("weatherDesc") or []
        desc = desc_list[0]["value"] if desc_list else "—"

        emoji = _weather_emoji(weather_code)

        text = (
            f"{emoji} <b>Погода: {html.escape(city_name)}, {html.escape(country)}</b>\n\n"
            f"🌡 Температура: <b>{temp_c}°C</b>  (ощущается {feels_c}°C)\n"
            f"💧 Влажность: {humidity}%    💨 Ветер: {wind_kmph} км/ч {wind_arrow}\n"
            f"👁 Видимость: {vis_km} км    📊 Давление: {pressure} мбар\n"
            f"☁️ {html.escape(desc)}"
        )
    except (KeyError, IndexError, TypeError):
        await message.answer("⚠️ Не удалось обработать данные о погоде.")
        return

    await message.answer(text, parse_mode="HTML")

