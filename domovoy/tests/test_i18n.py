"""All authored UI messages have three translations with intact value slots."""
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from core.permissions import PERMISSIONS
from core.settings_registry import HOUSE_SETTINGS, NOTIFY_SETTINGS

STATIC = Path(__file__).parents[1] / "web" / "static"


def catalog():
    script = (STATIC / "i18n.js").read_text(encoding="utf-8")
    return json.loads(script.split("const messages = ", 1)[1].split(";\n  const languages", 1)[0])


def test_every_translation_keeps_dynamic_values():
    for source, translations in catalog().items():
        slots = sorted(re.findall(r"\{\d+\}", source))
        assert len(translations) == 3, source
        for translated in translations:
            assert translated.strip(), source
            assert sorted(re.findall(r"\{\d+\}", translated)) == slots, source


def test_dynamic_ui_and_registry_labels_have_translations():
    messages = catalog()
    for name in ("app.js", "house.js", "receipts.js"):
        source = (STATIC / name).read_text(encoding="utf-8")
        for match in re.finditer(r'\bt\(("(?:[^"\\]|\\.)*")', source):
            assert json.loads(match[1]) in messages, (name, match[1])
    for definition in (*HOUSE_SETTINGS, *NOTIFY_SETTINGS):
        assert definition.label in messages
    for permission in PERMISSIONS:
        assert permission.label in messages
        assert permission.hint in messages


class AuthoredText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, value):
        self.text.append(value.strip())

    def handle_starttag(self, tag, attrs):
        self.text.extend(value for key, value in attrs if key in ("aria-label", "placeholder", "title") and value)


def test_static_interface_is_covered_including_accessible_labels():
    parser = AuthoredText()
    parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    messages = catalog()
    for text in parser.text:
        if re.search("[А-Яа-яЁё]", text):
            assert text in messages, text


@pytest.mark.skipif(not shutil.which("node"), reason="Node is required for the browser-independent JS runtime check")
def test_language_storage_fallback_preserves_launch_data_and_dirty_guard():
    script = r"""
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
let reloads = 0, close;
const select = {}, confirm = {}, cancel = {};
const dialog = { open: false, showModal() { this.open = true; }, close() { this.open = false; close(); },
  addEventListener(name, fn) { if (name === 'close') close = fn; } };
let fragment = '#tgWebAppData=example&tgWebAppVersion=8.0';
const location = { get hash() { return fragment; }, set hash(value) { fragment = '#' + value.replace(/^#/, ''); },
  reload() { reloads++; } };
const document = { documentElement: {}, createTreeWalker: () => ({ nextNode: () => false }),
  querySelectorAll: selector => selector === '[data-language]' ? [select] : [],
  querySelector: () => null, addEventListener() {},
  getElementById: id => id === 'language-dialog' ? dialog : id === 'confirm-language' ? confirm : cancel };
const context = { document, location, window: { dispatchEvent() {} }, navigator: { language: 'ru' },
  localStorage: { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } },
  URLSearchParams, NodeFilter: { SHOW_TEXT: 4 }, Event: class {} };
vm.runInNewContext(source, context);
context.window.DomovoyI18n.setDirtyCheck(() => true);
select.value = 'fr'; select.onchange();
assert.equal(reloads, 0); assert.equal(select.value, 'ru'); assert.equal(dialog.open, true);
cancel.onclick(); assert.equal(dialog.open, false);
context.window.DomovoyI18n.setDirtyCheck(() => false);
select.value = 'de'; select.onchange();
const params = new URLSearchParams(location.hash.slice(1));
assert.equal(params.get('tgWebAppData'), 'example');
assert.equal(params.get('tgWebAppVersion'), '8.0');
assert.equal(params.get('lang'), 'de'); assert.equal(reloads, 1);
"""
    result = subprocess.run([shutil.which("node"), "-e", script, str(STATIC / "i18n.js")],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
