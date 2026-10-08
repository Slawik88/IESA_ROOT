"""Render the fake-Telegram call log as a readable chat transcript (group + private chats)."""
from __future__ import annotations

from tools.mafia_sim.world import World, parse_html


def _plain(params: dict) -> str:
    text = params.get("text") or ""
    return parse_html(text)[0] if params.get("parse_mode") == "HTML" else text


def _buttons(markup) -> str:
    if markup is None:
        return ""
    rows = markup.inline_keyboard if hasattr(markup, "inline_keyboard") else []
    lines = ["      " + " ".join(f"[ {b.text} ]" + ("↗" if getattr(b, "url", None) else "") for b in row) for row in rows]
    return "\n" + "\n".join(lines)


def _indent(text: str) -> str:
    return "\n".join("   " + line for line in text.splitlines())


def render(world: World, *, group: int, names: dict[int, str], watch: set[int] | None = None, start: int = 0) -> str:
    """Chronological transcript.  ``watch`` limits private chats to those users (None = all)."""
    out: list[str] = []
    for name, params in world.calls[start:]:
        chat = params.get("chat_id")
        where = "ГРУППА" if chat == group else f"ЛС {names.get(chat, chat)}"
        private = chat is not None and chat != group
        if private and watch is not None and chat not in watch:
            continue
        if name == "NOTE":
            out.append(f"\n▶ {params['text']}")
        elif name == "SendMessage":
            out.append(f"[{where}] новое сообщение:\n{_indent(_plain(params))}{_buttons(params.get('reply_markup'))}")
        elif name == "EditMessageText":
            out.append(f"[{where}] сообщение обновлено:\n{_indent(_plain(params))}{_buttons(params.get('reply_markup'))}")
        elif name == "DeleteMessage":
            out.append(f"[{where}] 🗑 сообщение удалено ботом")
        elif name == "AnswerCallbackQuery":
            kind = "всплывающее окно" if params.get("show_alert") else "подсказка"
            link = f" (откроет {params['url']})" if params.get("url") else ""
            out.append(f"   ↳ {kind} для нажавшего: «{params.get('text') or ''}»{link}")
    return "\n".join(out)
