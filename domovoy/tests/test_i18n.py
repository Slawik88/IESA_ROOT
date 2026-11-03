"""Каждая строка интерфейса имеет три перевода с теми же {0}; подписи реестров и вызовы t() покрыты."""
import ast
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from core.permissions import PERMISSIONS
from core.settings_registry import HOUSE_SETTINGS, NOTIFY_SETTINGS

ROOT = Path(__file__).parents[1]
STATIC = ROOT / "web" / "static"
LANGUAGES = ("uk", "fr", "de")
CYRILLIC = re.compile("[А-Яа-яЁё]")
SERVER_ERRORS = ("DomainError", "AmountError")
INTERNAL_MESSAGES = {"Missing authorization"}  # ответ 404 без подписи Telegram: приложение показывает свой экран входа


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


def module_constants() -> dict:
    """Константы модулей: ими заполняются сообщения-f-строки (например, предел длины названия)."""
    values = {}
    for folder in ("core", "services"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                        and isinstance(node.value, ast.Constant)):
                    values[node.targets[0].id] = node.value.value
    return values


def server_messages() -> set[str]:
    """Тексты ошибок, которые сервер показывает человеку: литералы и f-строки, заполняемые только константами."""
    constants = module_constants()
    found = set()
    for folder in ("core", "services", "web"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in SERVER_ERRORS
                        and node.args):
                    continue
                message = node.args[0]
                if isinstance(message, ast.Constant) and isinstance(message.value, str):
                    found.add(message.value)
                elif isinstance(message, ast.JoinedStr) and {
                    name.id for name in ast.walk(message) if isinstance(name, ast.Name)
                } <= constants.keys():
                    found.add(eval(compile(ast.Expression(message), path.name, "eval"), {}, constants))
    return found - INTERNAL_MESSAGES


def test_every_server_message_is_translated():
    """Ошибка сервера приходит по-русски; без перевода немецкий или французский интерфейс показал бы её как есть."""
    messages = catalog("uk")
    assert sorted(text for text in server_messages() if text not in messages) == []


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
