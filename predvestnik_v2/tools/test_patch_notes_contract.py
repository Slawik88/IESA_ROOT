#!/usr/bin/env python3
"""Патч-ноуты: каждый файл годен, каждая запись «Что нового» попала в пост дня, разметка и картинки проверены.

Запуск: python tools/test_patch_notes_contract.py (база и Telegram не нужны). Правила: docs/PATCH_NOTES.md.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from core import patch_notes as rules  # noqa: E402
from services import patch_notes_format as fmt, patch_notes_images as pictures, patch_notes_send as sender  # noqa: E402


def files_are_valid() -> dict[str, dict]:
    notes, item_ids = {}, set()
    assert fmt.note_files(), "нет ни одного патч-ноута"
    for path in fmt.note_files():
        note = fmt.load(path)
        errors = fmt.validate(note)
        assert not errors, f"{path.name}: {errors}"
        assert path.stem.startswith(note["date"]), f"{path.name}: имя файла начинается с даты поста"
        for item in note["items"]:
            assert item["id"] not in item_ids, f"пункт {item['id']} встречается дважды"
            item_ids.add(item["id"])
        notes[path.stem] = note
    return notes


def whatsnew_is_covered(notes: dict[str, dict]) -> None:
    feed = json.loads((ROOT / "FastAPI/static/updates.json").read_text(encoding="utf-8"))["updates"]
    covered = set().union(*(fmt.covered_ids(n) for n in notes.values()))
    missing = [e["id"] for e in feed if e["date"] >= rules.COVERAGE_SINCE and e["id"] not in covered]
    assert not missing, ("записи «Что нового» без патч-ноута (добавьте пункт в FastAPI/static/patch-notes/<дата>.json "
                         f"или строку в skipped с причиной; правила docs/PATCH_NOTES.md): {missing}")
    known = {e["id"] for e in feed}
    for note in notes.values():
        for item in note["items"]:
            for cid in item.get("covers") or []:
                assert cid in known, f"{item['id']}: covers ссылается на неизвестную запись {cid}"


def images_are_referenced(notes: dict[str, dict]) -> None:
    used = {i["image"] for n in notes.values() for i in n["items"] if i.get("image") not in (None, "cover")}
    present = {p.name for p in rules.IMAGES_DIR.glob("*")} if rules.IMAGES_DIR.is_dir() else set()
    assert not present - used, f"картинки без патч-ноута (удалите или используйте): {sorted(present - used)}"


def markup_rules() -> None:
    good = ['<b>жирно</b> и <i>курсив</i>', 'a &lt; b &amp; c', '<a href="https://t.me/x">ссылка</a>',
            '<blockquote expandable>• один\n• два</blockquote>', '<tg-spoiler>тайна</tg-spoiler> &#128512;']
    for text in good:
        assert not fmt.markup_errors(text), (text, fmt.markup_errors(text))
    bad = ['<b>не закрыт', '<div>блок</div>', '<b><i>крест</b></i>', 'a < b', 'Tom & Jerry', '&nbsp;',
           '<a href="http://x">ссылка</a>', '<a>без адреса</a>', '<b class="x">x</b>', '</b>']
    for text in bad:
        assert fmt.markup_errors(text), f"пропустили плохую разметку: {text}"
    assert fmt.tg_len("🔮ab") == 4 and fmt.plain_text("<b>a &amp; b</b>") == "a & b"


def composition() -> None:
    note = {"date": "2026-10-21", "headline": "Тест & «кавычки»", "items": [
        {"id": "x-new-thing", "kind": "new", "title": "Новое", "text": "Текст", "image": "cover"},
        *[{"id": f"x-fix-{i}", "kind": "fix", "text": f"Исправление {i}"} for i in range(rules.FIXES_FOLD + 1)]]}
    assert not fmt.validate(note), fmt.validate(note)
    text = fmt.compose(note)
    assert not fmt.markup_errors(text), fmt.markup_errors(text)
    assert "Тест &amp; «кавычки»" in text and "\n\n" in text and "<blockquote expandable>" in text and "21 октября" in text
    short = {**note, "items": note["items"][:2]}
    assert "<blockquote" not in fmt.compose(short), "короткий список исправлений не сворачивается"
    assert fmt.images(note) == [{"ref": "cover", "title": "Новое", "kind": "new", "alt": "Обложка: Новое"}]
    assert fmt.button(note) == "home"
    broken = {**note, "items": [{"id": "x-new", "kind": "new", "title": "Без картинки", "text": "Текст"}]}
    assert any("картинка" in e for e in fmt.validate(broken)), "новинка без картинки прошла"
    fix_img = {**note, "items": [{"id": "x-fix", "kind": "fix", "text": "Мелочь", "image": "cover"}]}
    assert fmt.validate(fix_img), "исправление с картинкой прошло"
    long = {**note, "items": [{"id": f"x-{i}-long", "kind": "better", "title": "Пункт", "text": "я" * 410} for i in range(8)]
            + [{"id": f"x-{i}-fix", "kind": "fix", "text": "ы" * 160} for i in range(12)]}
    assert any("4000" in e for e in fmt.validate(long)), "слишком длинный пост прошёл"


def delivery_plan() -> None:
    assert sender.plan("коротко", 0) == "text"
    assert sender.plan("коротко", 1) == "photo"
    assert sender.plan("я" * (rules.MAX_CAPTION + 1), 1) == "photos_then_text"
    assert sender.plan("коротко", 2) == "photos_then_text"
    assert sender.keyboard(None) is None
    js = (ROOT / "FastAPI/static/bot-admin/admin-patchnotes-actions.js").read_text(encoding="utf-8")
    assert f"n <= {rules.MAX_CAPTION}" in js, "предпросмотр админки считает подпись к фото не так, как отправка"


def images() -> None:
    png = Image.open(io.BytesIO(pictures.cover("Очень длинный заголовок обложки, который переносится на строки", "fix")))
    assert png.size == (1280, 720) and png.format == "PNG"
    photo = Image.new("RGB", (1600, 1000), (40, 30, 90))
    exif = Image.Exif()
    exif[0x010F] = "Phone Maker"
    exif[0x8825] = {2: (55.0, 45.0, 0.0)}   # GPS
    raw = io.BytesIO()
    photo.save(raw, "JPEG", exif=exif.tobytes(), quality=95)
    data, mime, width, height = pictures.normalize_upload(raw.getvalue())
    clean = Image.open(io.BytesIO(data))
    assert mime == "image/jpeg" and (width, height) == (1600, 1000) and not clean.getexif(), "EXIF не вычищен"
    for raw_bad in (b"x" * 3000, Image.new("RGB", (100, 100)).tobytes()[:2500]):
        try:
            pictures.normalize_upload(raw_bad)
        except pictures.ImageRejected:
            continue
        raise AssertionError("мусор принят как фото")
    tiny = io.BytesIO()
    Image.new("RGB", (120, 900), (0, 0, 0)).save(tiny, "PNG")
    try:
        pictures.normalize_upload(tiny.getvalue() + b"\0" * 2000)
    except pictures.ImageRejected:
        pass
    else:
        raise AssertionError("узкая картинка принята")


def wiring() -> None:
    from FastAPI.routers.bot_admin import auth, page
    assert auth.SECTIONS["patchnotes"][1] == 6, "раздел только для создателя"
    index = (ROOT / "FastAPI/static/bot-admin/index.html").read_text(encoding="utf-8")
    for name in ("admin-patchnotes.js", "admin-patchnotes-edit.js", "admin-patchnotes-actions.js"):
        assert name in page._TYPES and f"/bot-admin/{name}?v=" in index, name
        subprocess.run(["node", "--check", str(ROOT / "FastAPI/static/bot-admin" / name)], check=True)
    assert index.index("admin-patchnotes-actions.js") < index.index("admin-boot.js")
    repo_root = ROOT.parent
    for doc in ("CLAUDE.md", "AGENTS.md"):
        assert "predvestnik_v2/docs/PATCH_NOTES.md" in (repo_root / doc).read_text(encoding="utf-8"), f"{doc} не ведёт к правилам патч-ноутов"


def preview_renderer() -> None:
    """Предпросмотр админки экранирует всё, кроме разметки Telegram (скрипт из текста не исполняется)."""
    script = (ROOT / "FastAPI/static/bot-admin/admin-patchnotes.js").read_text(encoding="utf-8")
    probe = """
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SECTIONS = {};
""" + script + """
const out = pnHtml('<b>жир</b> <img src=x onerror=alert(1)> <a href="javascript:alert(1)">x</a> <a href="https://t.me">ok</a> &lt;b&gt; <tg-spoiler>s</tg-spoiler> <blockquote expandable>q</blockquote> <i>open');
if (out.includes('<img') || out.includes('href="javascript') || !out.includes('<b>жир</b>') || !out.includes('href="https://t.me"')) throw new Error(out);
if (!out.includes('&lt;b&gt;') || !out.includes('pn-spoiler') || !out.includes('pn-fold') || !out.endsWith('</i>')) throw new Error(out);
if (pnMarkupIssue('<b>x') === '' || pnMarkupIssue('<div>x</div>') === '' || pnMarkupIssue('<b>x</b>') !== '') throw new Error('markup issue');
"""
    run = subprocess.run(["node", "-"], input=probe, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr[-800:]


def main() -> None:
    notes = files_are_valid()
    whatsnew_is_covered(notes)
    images_are_referenced(notes)
    markup_rules()
    composition()
    delivery_plan()
    images()
    wiring()
    preview_renderer()
    print(f"OK: {len(notes)} патч-ноутов годны, «Что нового» с {rules.COVERAGE_SINCE} покрыто, разметка, картинки и отправка проверены")


if __name__ == "__main__":
    main()
