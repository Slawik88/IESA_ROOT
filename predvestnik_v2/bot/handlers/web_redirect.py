"""bot/handlers/web_redirect.py — БЛОК19 Часть1 «Web First».

Тяжёлые механики (магазин, гача, аукцион, кастомизация, БП, квесты, инвентарь,
кланы и т.п.) переехали в мини-апп. Чтобы не было «мёртвых» команд (Правило
Консистентности), ловим старые алиасы и отдаём ТОНКИЙ редирект — кнопку, которая
открывает нужный раздел Web App через `startapp=<section>` (его парсит app.js).

ОСТАВЛЕНЫ в чате (не здесь): лёгкие/соц (я/профиль/поход/топ/стрик/ник/варпы/брак/
контрабанда/промо/вип), мини-игры (нет веб-UI), god-логи (dev), вся админка.
"""
import os

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd

router = Router(name="web_redirect_router")
_BOT = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")

# (алиасы, section-для-startapp, заголовок)
_REDIRECTS: list[tuple[list[str], str, str]] = [
    (["магазин", "лавка", "шоп"], "shop", "🛒 Магазин"),
    (["акция", "акция дня", "магазин дня", "ежедневный магазин"], "deal", "🏷 Акции дня"),
    (["крутка", "гача", "гаша", "лутбокс", "пити", "pity", "мои пити"], "gacha", "🗃 Архив находок"),
    (["аукцион", "аукцион выставить", "аукцион создать", "аукцион мои", "аукцион ставка"],
     "auction", "🏛 Аукцион"),
    (["темы", "тема профиля", "профиль темы"], "themes", "🎨 Темы профиля"),
    (["крафт", "craft", "скрафтить", "создать предмет"], "craft", "🔨 Крафт"),
    (["реликвии", "реликвия", "relics"], "relics", "🏛 Реликвии"),
    (["обмен", "конвертация", "обменять"], "exchange", "💱 Обменник"),
    (["биржа", "крипто", "crypto", "криптобиржа"], "crypto", "📈 Крипто-Биржа"),
    (["дуэль", "дуэли", "pvp"], "game", "🔔 Разлом колокола"),
    (["бп", "боевой пропуск", "пропуск"], "bp", "🎫 Боевой пропуск"),
    (["задания", "квесты", "дейлики"], "quests", "📋 Квесты"),
    (["инвентарь", "рюкзак", "вещи", "использовать", "открыть"], "inventory", "🎒 Инвентарь"),
    (["достижения", "ачивки", "ачивменты"], "ach", "🏆 Достижения"),
    (["питомец", "мой питомец", "активный питомец", "зоопарк", "питомник",
      "питомцы", "питомци", "мои питомцы", "мои питомци"], "zoo", "🐾 Питомцы"),
    (["поход", "походы", "экспедиция", "экспедиции", "ускорить поход"],
     "game", "🗺 Поход спутника"),
    (["уведомления", "настройки уведомлений", "нотификации"], "notifications", "🔔 Уведомления"),
    (["клан", "кланы", "гильдия", "гильдии", "клан создать", "клан основать",
      "клан выйти", "клан покинуть"], "clans", "🛡 Кланы"),
    (["косметика", "внешний вид", "скин", "облик", "образ", "looks"], "cosmetics", "🎨 Косметика"),
    # Старые юниты и Казарма выведены из продукта. Не оставляем битый deep-link:
    # показываем актуальную игру, не старую витрину владения.
    (["казарма", "юниты", "юнит", "отряд", "призыв", "призыв юнита", "боевые юниты"],
     "game", "🔔 Разлом колокола"),
    (["врата", "бездна", "битва", "бой", "арена"], "game", "🔔 Разлом колокола"),
]


_MINIAPP_URL = os.getenv("MINIAPP_URL", "")


def section_url(section: str) -> str:
    """Telegram deep link that opens the registered Mini App, not a browser tab."""
    return f"https://t.me/{_BOT}?startapp={section}"


def _kb(section: str, *, private: bool) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if private and _MINIAPP_URL.startswith("https://"):
        separator = "&" if "?" in _MINIAPP_URL else "?"
        b.button(
            text="🚀 Открыть в мини-аппе",
            web_app=types.WebAppInfo(url=f"{_MINIAPP_URL}{separator}startapp={section}"),
        )
    else:
        b.button(text="🚀 Открыть в мини-аппе", url=section_url(section))
    return b.as_markup()


def _make(section: str, title: str):
    # UX_AUDIT Б4: в ЛС тоже отвечаем — кнопка мини-аппа работает откуда угодно.
    async def handler(message: types.Message, text_args: str = ""):
        await message.answer(
            f"<b>{title}</b> теперь в мини-аппе 📱\n"
            "<i>Тяжёлый контент переехал в Web App — там удобнее и нагляднее.</i>",
            reply_markup=_kb(section, private=message.chat.type == "private"), parse_mode="HTML",
        )
    return handler


for _aliases, _section, _title in _REDIRECTS:
    router.message(TextCmd(_aliases))(_make(_section, _title))
