"""Проверка фикса «хаоса» переносов в «бот топ» (2026-07-23): реальные TG-юзернеймы
(до 32 симв.) + админ-тайтл/серый тег (до 16 симв., suffixes_for) давали строки от
~5 до ~50+ видимых символов без предела — на узком экране один ряд переносился,
другой нет. Печатает худший случай (макс. длина юзернейма + макс. длина тега) ДО
и ПОСЛЕ обрезки — глазами видно разброс. Не рендерит визуально (Telegram-клиента
нет), стриповает HTML-теги для замера видимой длины, как test_profile_text_wrap.py."""
import re
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bot.handlers.stats import _trunc_name, _TOP_NAME_MAX
from services.profile_render import format_display_name
from services.utils import safe_html

_TAG_RE = re.compile(r"<[^>]+>")


def visible_len(s: str) -> int:
    return len(_TAG_RE.sub("", s))


# Реальные крайние случаи: макс. длина TG-юзернейма (32) и обычный короткий (5),
# суффикс — макс. длина админ-тайтла/тега (16, см. admin_titles.py [:16]).
LONG_USERNAME = "a" * 32
SHORT_USERNAME = "ann"
SUFFIX = ' <i>· ' + "з" * 16 + '</i>'  # формат suffix_of()/title_suffix()


def build_row(username: str, suffix: str, truncate: bool, msg_count: int = 1234567) -> str:
    uname = _trunc_name(username) if truncate else username
    name = format_display_name(safe_html(uname), is_vip=True) + suffix
    link = f'<a href="tg://user?id=1">{name}</a>'
    return f"🥇 <code>{msg_count}</code>  {link}"


print(f"_TOP_NAME_MAX = {_TOP_NAME_MAX}\n")

for label, uname, suffix in [
    ("длинный юзернейм + тег", LONG_USERNAME, SUFFIX),
    ("длинный юзернейм, без тега", LONG_USERNAME, ""),
    ("короткий юзернейм + тег", SHORT_USERNAME, SUFFIX),
    ("короткий юзернейм, без тега", SHORT_USERNAME, ""),
]:
    before = build_row(uname, suffix, truncate=False)
    after = build_row(uname, suffix, truncate=True)
    print(f"{label}:")
    print(f"  ДО   [{visible_len(before):3d}] {before}")
    print(f"  ПОСЛЕ[{visible_len(after):3d}] {after}")
    print()

lengths_after = [
    visible_len(build_row(u, s, truncate=True))
    for u in (LONG_USERNAME, SHORT_USERNAME)
    for s in (SUFFIX, "")
]
spread_before = visible_len(build_row(LONG_USERNAME, SUFFIX, truncate=False)) - \
    visible_len(build_row(SHORT_USERNAME, "", truncate=False))
spread_after = max(lengths_after) - min(lengths_after)

print(f"Разброс длины строки ДО фикса:    {spread_before} символов "
      f"(юзернейм был не ограничен, до 32 символов)")
print(f"Разброс длины строки ПОСЛЕ фикса: {spread_after} символов")
assert spread_after < spread_before, "фикс не уменьшил разброс длины строк топа"
print("\nOK: разброс длины ряда сократился — переносы предсказуемее, не хаотичны")
