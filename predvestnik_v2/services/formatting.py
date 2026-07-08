# services/formatting.py
# Pure text-formatting utilities. No DB, no platform, no side effects.
import html as _html
from datetime import datetime as _dt


def format_currency(amount: float) -> str:
    """1500.5 → '1 500.50'"""
    return f"{amount:,.2f}".replace(",", " ")


def format_number(value: int) -> str:
    """1000000 → '1 000 000'"""
    return f"{value:,}".replace(",", " ")


def safe_html(text: str | None) -> str:
    """Escape HTML special chars to prevent injection in bot messages."""
    if text is None:
        return "Неизвестно"
    return _html.escape(str(text))


def format_progress_bar(current: int, max_value: int, length: int = 10) -> str:
    """Render a Unicode progress bar: ████░░░░░░"""
    if max_value <= 0:
        return "░" * length
    filled = int((min(current, max_value) / max_value) * length)
    return "█" * filled + "░" * (length - filled)


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def parse_dt(val) -> '_dt | None':
    """Parse a TIMESTAMP value from PostgreSQL (datetime obj) or SQLite (str).
    Always returns a naive datetime or None. Handles both formats transparently."""
    if val is None:
        return None
    if isinstance(val, _dt):
        # asyncpg already decoded it — return as-is (strip tzinfo for consistency)
        return val.replace(tzinfo=None)
    s = str(val)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return _dt.strptime(s, fmt)
        except ValueError:
            continue
    return None


def format_chest_rewards_text(rewards: dict[int, float], top3_bonus_label: str = "🎟 Жетон") -> str:
    """Полная и честная разбивка наград сундука-события по позициям — строится
    ИЗ CHEST_REWARDS_BY_POSITION, не копируется руками (копии дрейфуют от
    правды — найдено 3 разных хардкода одного и того же текста, один с фейковыми
    числами). Позиции 4+ группируются только когда значения РЕАЛЬНО равны подряд,
    без потери данных о неравных позициях."""
    positions = sorted(rewards)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for p in positions[:3]:
        lines.append(f"{medals.get(p, '•')} {p} место: <b>{int(rewards[p])} 🪙</b> + {top3_bonus_label}")
    rest = positions[3:]
    i = 0
    while i < len(rest):
        j = i
        while j + 1 < len(rest) and rewards[rest[j + 1]] == rewards[rest[i]]:
            j += 1
        p_from, p_to = rest[i], rest[j]
        label = f"{p_from}" if p_from == p_to else f"{p_from}–{p_to}"
        lines.append(f"{label} место: <b>{int(rewards[rest[i]])} 🪙</b>")
        i = j + 1
    return "\n".join(lines)


def format_seconds_to_time(seconds: int) -> str:
    """3661 → '1ч 1м 1с'"""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    if secs or not parts:
        parts.append(f"{secs}с")
    return " ".join(parts)
