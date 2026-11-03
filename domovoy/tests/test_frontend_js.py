"""Чистые модули интерфейса (деньги, даты, язык) проверяются в Node без браузера."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).parents[1] / "web" / "static" / "js"
NODE = shutil.which("node")


def node_major() -> int:
    if not NODE:
        return 0
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True, check=True).stdout
    return int(re.match(r"v(\d+)", version)[1])


# Модули — ES-модули в файлах .js без package.json: Node распознаёт их с версии 22.
needs_node = pytest.mark.skipif(node_major() < 22, reason="Node 22+ нужен для проверки ES-модулей интерфейса")


def run(script: str, module: str) -> None:
    command = [NODE, "--input-type=module", "-e", script, str(JS / module)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@needs_node
def test_money_follows_language_and_keeps_a_real_minus():
    # Знак группы разрядов в de-CH зависит от версии ICU (' или ’) — проверяется шаблоном.
    run(r"""
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const f = await import(pathToFileURL(process.argv[1]).href);
const nb = ' ';
assert.equal(f.formatMoney(32806, 'ru-RU', 'CHF'), `328,06${nb}CHF`);
assert.equal(f.formatMoney(130050, 'ru-RU', 'CHF'), `1 300,50${nb}CHF`);
assert.equal(f.formatMoney(-7650, 'ru-RU', 'CHF'), `−76,50${nb}CHF`);
assert.equal(f.formatMoney(20000, 'ru-RU', 'CHF', { plus: true }), `+200,00${nb}CHF`);
assert.match(f.formatMoney(130050, 'de-CH', 'CHF'), /^1['’]300\.50 CHF$/);
assert.equal(f.formatMoney(5, 'ru-RU'), '0,05');
assert.equal(f.decimalString(8745), '87.45');
assert.equal(f.sanitizeAmount('1 2a3,456'), '123,45');
assert.equal(f.sanitizeAmount('12..5'), '12.5');
assert.equal(f.sanitizeAmount('abc'), '');
assert.equal(f.toBase64(new Uint8Array([104, 105])), 'aGk=');
""", "format.js")


@needs_node
def test_dates_and_months_are_calendar_correct():
    run(r"""
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const f = await import(pathToFileURL(process.argv[1]).href);
assert.equal(f.shiftMonth('2026-12', 1), '2027-01');
assert.equal(f.shiftMonth('2026-01', -1), '2025-12');
assert.equal(f.shiftMonth('0001-01', -1), null);
assert.equal(f.shiftMonth('9999-12', 1), null);
assert.equal(f.addDays('2026-03-01', -1), '2026-02-28');
const labels = { today: 'Сегодня', yesterday: 'Вчера' };
assert.equal(f.relativeDay('2026-11-03', '2026-11-03', 'ru-RU', labels), 'Сегодня');
assert.equal(f.relativeDay('2026-11-02', '2026-11-03', 'ru-RU', labels), 'Вчера');
assert.equal(f.relativeDay('2026-10-30', '2026-11-03', 'ru-RU', labels), f.formatDay('2026-10-30', 'ru-RU'));
assert.equal(f.weekdayName(0, 'ru-RU'), 'Пн');
assert.equal(f.monthNames('ru-RU').length, 12);
assert.equal(f.formatMonth('2026-11', 'ru-RU', { month: 'long' }), 'Ноябрь');
""", "format.js")


@needs_node
def test_language_choice_and_switch_keep_launch_data_without_storage():
    run(r"""
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const events = [];
let fragment = '#tgWebAppData=example&tgWebAppVersion=8.0', reloads = 0;
globalThis.Event = class { constructor(type) { this.type = type; } };
globalThis.window = { dispatchEvent: event => events.push(event.type) };
globalThis.location = {
  get hash() { return fragment; },
  set hash(value) { fragment = '#' + value.replace(/^#/, ''); },
  reload() { reloads++; },
};
globalThis.document = { documentElement: {} };
Object.defineProperty(globalThis, 'navigator', { value: { language: 'fr-CH' }, configurable: true });
const blocked = () => { throw Error('blocked'); };
globalThis.localStorage = { getItem: blocked, setItem: blocked };
const i18n = await import(pathToFileURL(process.argv[1]).href);
assert.equal(i18n.pickLanguage({ fragment: 'xx', saved: '', telegram: 'de', browser: 'fr-CH' }), 'de');
assert.equal(i18n.pickLanguage({ fragment: 'uk', saved: 'de' }), 'uk');
assert.equal(i18n.pickLanguage({}), 'ru');
await i18n.initI18n(undefined);
assert.equal(document.documentElement.lang, 'fr');
assert.equal(i18n.t('Сегодня'), 'Aujourd’hui');
assert.equal(i18n.t('Неизвестная строка {0}', [5]), 'Неизвестная строка 5');
const row = i18n.translateError('Строка 3: Сегодня');
assert.equal(row, i18n.t('Строка {0}: {1}', ['3', 'Aujourd’hui']));
i18n.applyLanguage('de');
const parameters = new URLSearchParams(fragment.slice(1));
assert.equal(parameters.get('tgWebAppData'), 'example');
assert.equal(parameters.get('tgWebAppVersion'), '8.0');
assert.equal(parameters.get('lang'), 'de');
assert.equal(reloads, 1);
assert.deepEqual(events, ['domovoy:languagechanging']);
""", "i18n.js")
