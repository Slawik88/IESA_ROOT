"""Патч-ноуты: проверка разметки Telegram, чтение файлов дня и сборка готового текста поста.

Без базы и без Telegram: этим же модулем пользуется тест формата (tools/test_patch_notes_contract.py),
поэтому ошибка в файле патч-ноута видна до выкладки, а не в момент нажатия «Отправить».
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from core import patch_notes as rules

_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s[^<>]*)?)>")
_ENTITY_RE = re.compile(r"&(?:#\d{1,7}|#x[0-9a-fA-F]{1,6}|lt|gt|amp|quot);")
_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{5,79}")
_IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,90}")
_JARGON_RE = re.compile(r"(?<![\w-])(?:" + "|".join(rules.JARGON) + r")(?![\w-])", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"[.!?…]+(?=\s|$)")


def tg_len(text: str) -> int:
    """Длина так, как считает Telegram: в UTF-16 (эмодзи — два знака)."""
    return len(text.encode("utf-16-le")) // 2


def plain_text(markup: str) -> str:
    return html.unescape(_TAG_RE.sub("", markup))


class _Checker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in rules.ALLOWED_TAGS:
            self.errors.append(f"тег <{tag}> Telegram не поддерживает")
            return
        for name, value in attrs:
            if name not in rules.ALLOWED_ATTRS.get(tag, set()):
                self.errors.append(f"у <{tag}> нельзя атрибут {name}")
            elif name == "href" and not str(value or "").startswith(rules.LINK_SCHEMES):
                self.errors.append("ссылка должна начинаться с https://")
        if tag == "a" and not any(n == "href" for n, _ in attrs):
            self.errors.append("у <a> нет href")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"лишний или не по порядку закрыт </{tag}>")
            return
        self.stack.pop()


def markup_errors(markup: str) -> list[str]:
    """Ошибки разметки Telegram HTML. Пустой список — Telegram примет текст."""
    errors: list[str] = []
    for i, ch in enumerate(markup):
        if ch == "<" and not _TAG_RE.match(markup, i):
            errors.append("знак < вне тега: пишите &lt;")
            break
        if ch == "&" and not _ENTITY_RE.match(markup, i):
            errors.append("знак & вне сущности: пишите &amp;")
            break
    checker = _Checker()
    checker.feed(markup)
    checker.close()
    errors += checker.errors
    if checker.stack:
        errors.append("не закрыт тег <" + checker.stack[-1] + ">")
    return list(dict.fromkeys(errors))


def long_date(value: str) -> str:
    day = date.fromisoformat(value)
    return f"{day.day} {rules.MONTHS[day.month - 1]}"


def jargon(text: str) -> list[str]:
    """Слова разработчика в тексте для игроков (без разметки)."""
    return sorted({m.group(0).lower() for m in _JARGON_RE.finditer(plain_text(text))})


def text_issues(text: str) -> list[str]:
    """Текст поста целиком глазами игрока: технические слова. Пусто — можно показывать."""
    words = jargon(text)
    return [f"технические слова, игроку непонятно: {', '.join(words)}"] if words else []


def _check_text(where: str, value, limit: int, required: bool, markup: bool) -> list[str]:
    if value is None or value == "":
        return [f"{where}: пусто"] if required else []
    if not isinstance(value, str):
        return [f"{where}: должна быть строка"]
    errors = [f"{where}: {e}" for e in markup_errors(value)] if markup else []
    if not markup and ("<" in value or ">" in value):
        errors.append(f"{where}: без разметки")
    plain = plain_text(value) if markup else value
    if tg_len(plain) > limit:
        errors.append(f"{where}: длиннее {limit} знаков — короче, одной мыслью")
    if len(_SENTENCE_RE.findall(plain.strip())) > rules.MAX_SENTENCES:
        errors.append(f"{where}: больше {rules.MAX_SENTENCES} предложений — оставьте главное")
    if jargon(plain):
        errors.append(f"{where}: технические слова ({', '.join(jargon(plain))}) — напишите языком игрока")
    return errors


def _check_image(where: str, item: dict) -> list[str]:
    image, kind = item.get("image"), item.get("kind")
    if kind == "fix":
        return [f"{where}: у исправления нет картинки"] if image else []
    if not image:
        return [f"{where}: у новинки нужна картинка (скриншот или \"cover\")"] if kind == "new" else []
    if image == "cover":
        return []
    if not isinstance(image, str) or not _IMAGE_RE.fullmatch(image) or not image.endswith(rules.IMAGE_EXT):
        return [f"{where}: имя картинки — латиница, цифры, дефис и .png/.jpg"]
    path = rules.IMAGES_DIR / image
    if not path.is_file():
        return [f"{where}: нет файла img/{image}"]
    if not rules.IMAGE_MIN_BYTES <= path.stat().st_size <= rules.IMAGE_MAX_BYTES:
        return [f"{where}: размер img/{image} вне 2 КБ–9 МБ"]
    if not item.get("image_alt"):
        return [f"{where}: опишите в image_alt, что на картинке"]
    return _check_size(where, path)


def _check_size(where: str, path: Path) -> list[str]:
    from PIL import Image
    try:
        with Image.open(path) as img:
            width, height = img.size
    except Exception:
        return [f"{where}: img/{path.name} не открывается как картинка"]
    if min(width, height) < rules.IMAGE_MIN_SIDE or max(width, height) / min(width, height) > rules.IMAGE_MAX_RATIO:
        return [f"{where}: img/{path.name} {width}×{height} — нужна сторона от {rules.IMAGE_MIN_SIDE} px и соотношение до 1:3"]
    if width + height > 10_000:
        return [f"{where}: img/{path.name} слишком большая для Telegram (ширина + высота до 10 000)"]
    return []


def _check_item(where: str, item) -> list[str]:
    if not isinstance(item, dict):
        return [f"{where}: должен быть объект"]
    errors = []
    if not isinstance(item.get("id"), str) or not _ID_RE.fullmatch(item["id"]):
        errors.append(f"{where}: id — латиница, цифры и дефис")
    if item.get("kind") not in rules.KINDS:
        errors.append(f"{where}: kind — new, better или fix")
    fix = item.get("kind") == "fix"
    errors += _check_text(f"{where}.title", item.get("title"), rules.MAX_TITLE, not fix, markup=False)
    errors += _check_text(f"{where}.text", item.get("text"), rules.MAX_FIX if fix else rules.MAX_TEXT, True, markup=True)
    if item.get("open") is not None and item["open"] not in rules.BUTTONS:
        errors.append(f"{where}.open: неизвестный раздел")
    if item.get("flag") is not None and not (isinstance(item["flag"], str) and re.fullmatch(r"[a-z0-9_]{2,40}", item["flag"])):
        errors.append(f"{where}.flag: ключ модуля, например pets_v2")
    covers = item.get("covers", [])
    if not isinstance(covers, list) or not all(isinstance(c, str) for c in covers):
        errors.append(f"{where}.covers: список id из «Что нового»")
    return errors + _check_image(where, item) + _check_extra(where, item)


def _check_extra(where: str, item: dict) -> list[str]:
    """Дополнительные фото пункта (extra_images): когда за день сведено несколько обновлений, их скриншоты остаются в посте-альбоме."""
    extra = item.get("extra_images")
    if extra is None:
        return []
    if item.get("kind") == "fix" or not isinstance(extra, list) or not all(isinstance(e, dict) for e in extra):
        return [f"{where}.extra_images: список {{image, image_alt}} у новинки или улучшения"]
    errors = []
    for n, e in enumerate(extra):
        if e.get("image") in (None, "cover"):
            errors.append(f"{where}.extra_images[{n}]: нужен файл из img/")
        else:
            errors += _check_image(f"{where}.extra_images[{n}]", {**e, "kind": item.get("kind")})
    return errors


def validate(note) -> list[str]:
    """Ошибки файла патч-ноута; пустой список — файл годен."""
    if not isinstance(note, dict):
        return ["файл должен быть объектом"]
    try:
        date.fromisoformat(str(note.get("date")))
    except ValueError:
        return ["date: дата ГГГГ-ММ-ДД"]
    errors = _check_text("headline", note.get("headline"), rules.MAX_HEADLINE, True, markup=False)
    errors += _check_text("intro", note.get("intro"), rules.MAX_INTRO, False, markup=True)
    items = note.get("items")
    if not isinstance(items, list) or not items:
        return errors + ["items: нужен хотя бы один пункт"]
    for i, item in enumerate(items):
        errors += _check_item(f"items[{i}]", item)
    kinds = [i.get("kind") for i in items if isinstance(i, dict)]
    if len([k for k in kinds if k != "fix"]) > rules.MAX_ITEMS:
        errors.append(f"items: не больше {rules.MAX_ITEMS} новинок в посте, остальное в следующий")
    if kinds.count("fix") > rules.MAX_FIXES:
        errors.append(f"items: не больше {rules.MAX_FIXES} исправлений, мелочь объединяйте")
    photos = sum(bool(i.get("image")) + len(i.get("extra_images") or []) for i in items if isinstance(i, dict) and isinstance(i.get("extra_images") or [], list))
    if photos > rules.MAX_IMAGES:
        errors.append(f"в посте {photos} фото, Telegram берёт в альбом не больше {rules.MAX_IMAGES}")
    if note.get("button") is not None and note["button"] not in rules.BUTTONS:
        errors.append("button: неизвестный раздел")
    for skip in note.get("skipped") or []:
        if not isinstance(skip, dict) or not skip.get("id") or len(str(skip.get("why", ""))) < 8:
            errors.append("skipped: у каждой пропущенной записи нужны id и причина why")
    if not errors and tg_len(plain_text(compose(note))) > rules.MAX_MESSAGE:
        errors.append(f"пост длиннее {rules.MAX_MESSAGE} знаков: сократите пункты или перенесите часть в другой день")
    return errors


def load(path: Path) -> dict:
    note = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(note, dict):
        note["note_id"] = path.stem
    return note


def note_files() -> list[Path]:
    if not rules.NOTES_DIR.is_dir():
        return []
    return sorted(p for p in rules.NOTES_DIR.glob("*.json") if re.fullmatch(r"\d{4}-\d{2}-\d{2}(-[a-z0-9-]{1,40})?", p.stem))


def _item_line(item: dict) -> str:
    emoji = (item.get("emoji") or ("✨" if item["kind"] == "new" else "⚡")).strip()
    return f"{emoji} <b>{html.escape(item['title'], quote=False)}</b> — {item['text'].strip()}"


def _fixes_block(fixes: list[dict]) -> str:
    lines = "\n".join(f"• {f['text'].strip()}" for f in fixes)
    body = f"<blockquote expandable>{lines}</blockquote>" if len(fixes) > rules.FIXES_FOLD else lines
    return f"🛠 <b>Исправили</b>\n{body}"


def compose(note: dict) -> str:
    """Готовый текст поста: заголовок, по строке на новинку, короткий список исправлений. Без воды."""
    head = f"<b>🔮 {html.escape(note['headline'], quote=False)}</b>"
    if note.get("intro"):
        head += "\n" + note["intro"].strip()
    items = note["items"]
    lines = [_item_line(i) for i in items if i["kind"] == "new"] + [_item_line(i) for i in items if i["kind"] == "better"]
    parts = [head] + (["\n".join(lines)] if lines else [])
    fixes = [i for i in items if i["kind"] == "fix"]
    if fixes:
        parts.append(_fixes_block(fixes))
    return "\n\n".join(parts)


def images(note: dict) -> list[dict]:
    """Картинки поста по порядку пунктов: сначала новинки, потом улучшения."""
    ordered = [i for i in note["items"] if i["kind"] == "new"] + [i for i in note["items"] if i["kind"] == "better"]
    out = []
    for item in ordered:
        if item.get("image") == "cover":
            out.append({"ref": "cover", "title": item["title"], "kind": item["kind"], "alt": f"Обложка: {item['title']}"})
        elif item.get("image"):
            out.append({"ref": f"repo:{item['image']}", "alt": item.get("image_alt") or item["title"]})
        out += [{"ref": f"repo:{e['image']}", "alt": e.get("image_alt") or item["title"]} for e in item.get("extra_images") or []]
    return out[:rules.MAX_IMAGES]


def button(note: dict) -> str:
    if note.get("button"):
        return note["button"]
    for item in note["items"]:
        if item["kind"] != "fix" and item.get("open"):
            return item["open"]
    return "home"


def covered_ids(note: dict) -> set[str]:
    ids = set()
    for item in note.get("items", []):
        ids.update(item.get("covers") or [item.get("id")])
    ids.update(s.get("id") for s in note.get("skipped", []) if isinstance(s, dict))
    return ids


def flags(note: dict) -> list[str]:
    return sorted({i["flag"] for i in note.get("items", []) if i.get("flag")})
