"""Registry-driven redirect boundary for surfaces that genuinely need Mini App.

The parity registry is the source of truth: lightweight actions and summaries
are handled by chat adapters, while only complex interactions receive a
`startapp=<section>` deep-link. Retired surfaces return an honest archive
message instead of pretending that a dead command still works.
"""
import os

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.surface_parity import surfaces_for_redirect

router = Router(name="web_redirect_router")
_BOT = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")

# (алиасы, section-для-startapp, заголовок)
_REDIRECTS = [
    (list(spec.aliases), spec.start_param, spec.title, spec.chat_mode)
    for spec in surfaces_for_redirect()
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


def _make(section: str, title: str, mode: str):
    # UX_AUDIT Б4: в ЛС тоже отвечаем — кнопка мини-аппа работает откуда угодно.
    async def handler(message: types.Message, text_args: str = ""):
        status = (
            "<i>Эта старая механика закрыта: новых покупок, наград или прогресса нет. "
            "В Mini App доступен только честный архив и сохранённые права.</i>"
            if mode == "retired"
            else "<i>Сложное управление доступно в Mini App; состояние общее с чатом.</i>"
        )
        await message.answer(
            f"<b>{title}</b>\n{status}",
            reply_markup=_kb(section, private=message.chat.type == "private"), parse_mode="HTML",
        )
    return handler


for _aliases, _section, _title, _mode in _REDIRECTS:
    router.message(TextCmd(_aliases))(_make(_section, _title, _mode))
