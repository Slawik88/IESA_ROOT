"""Каждая строка интерфейса имеет три перевода с теми же {0}; подписи реестров и вызовы t() покрыты."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from core.permissions import PERMISSIONS
from core.settings_registry import HOUSE_SETTINGS, NOTIFY_SETTINGS

STATIC = Path(__file__).parents[1] / "web" / "static"
LANGUAGES = ("uk", "fr", "de")
CYRILLIC = re.compile("[А-Яа-яЁё]")


def catalog(code: str) -> dict:
    source = (STATIC / "js" / "i18n" / f"{code}.js").read_text(encoding="utf-8")
    return json.loads(source.split("export default ", 1)[1].rstrip().removesuffix(";"))


def test_catalogs_cover_the_same_strings_and_keep_dynamic_values():
    catalogs = {code: catalog(code) for code in LANGUAGES}
    assert catalogs["uk"].keys() == catalogs["fr"].keys() == catalogs["de"].keys()
    for source in catalogs["uk"]:
        slots = sorted(re.findall(r"\{\d+\}", source))
        for code in LANGUAGES:
            translated = catalogs[code][source]
            assert translated.strip(), (code, source)
            assert sorted(re.findall(r"\{\d+\}", translated)) == slots, (code, source)


def test_every_literal_t_call_and_registry_label_is_translated():
    messages = catalog("uk")
    for path in (STATIC / "js").rglob("*.js"):
        if "i18n" in path.parts:
            continue
        for match in re.finditer(r'\bt\(("(?:[^"\\]|\\.)*")', path.read_text(encoding="utf-8")):
            assert json.loads(match[1]) in messages, (path.name, match[1])
    for definition in (*HOUSE_SETTINGS, *NOTIFY_SETTINGS):
        assert definition.label in messages
        for label in (definition.choice_labels or {}).values():
            assert label in messages
    for permission in PERMISSIONS:
        assert permission.label in messages
        assert permission.hint in messages


class VisibleText(HTMLParser):
    """Текст страницы вне <title>, <script> и <style>: он показывался бы без перевода."""

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("title", "script", "style"):
            self.skip += 1
        self.text.extend(value for key, value in attrs if key in ("aria-label", "placeholder", "title") and value)

    def handle_endtag(self, tag):
        if tag in ("title", "script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.text.append(data.strip())


def test_static_page_has_no_untranslated_text():
    """Весь видимый текст строится из кода через t(); в index.html его быть не должно."""
    parser = VisibleText()
    parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    assert [text for text in parser.text if CYRILLIC.search(text)] == []
