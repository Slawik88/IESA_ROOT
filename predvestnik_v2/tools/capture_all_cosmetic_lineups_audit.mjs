import {mkdirSync} from 'fs';
import {resolve} from 'path';
import {spawnSync} from 'child_process';
import puppeteer from 'puppeteer';

const outputDir = resolve(process.env.OUTPUT_DIR || '/tmp/predvestnik-lineups-audit');
mkdirSync(outputDir, {recursive: true});

const python = String.raw`
import json
from core.cosmetics import COSMETICS, LINEUPS, COSMETIC_SLOTS

slots = {slot: [] for slot in COSMETIC_SLOTS}
for cosmetic_id, item in COSMETICS.items():
    row = {"id": cosmetic_id, **item, "owned": False, "equipped": False}
    slots[item["slot"]].append(row)

print(json.dumps({
    "vip": True,
    "balances": {"zarniki": 999999, "mora": 125430, "diamonds": 42.5, "dark_mora": 340},
    "currency_icons": {"zarniki": "✨", "mora": "🪙", "diamonds": "💎"},
    "lineups": LINEUPS,
    "slots": slots,
}, ensure_ascii=False))
`;
const registry = spawnSync('python3', ['-c', python], {cwd: resolve('.'), encoding: 'utf8'});
if (registry.status !== 0) throw new Error(registry.stderr || 'Unable to read core cosmetics registry');
const catalog = JSON.parse(registry.stdout);

const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
await page.goto('http://localhost:8402/', {waitUntil: 'load'});
await page.waitForFunction(() => typeof openLooksModal === 'function');
await page.mouse.click(195, 700);
await page.waitForFunction(() => !document.getElementById('preloader'));
await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);
await page.evaluate(data => {
  _looksData = data;
  _looksSaved = {};
  _looksSel = {};
  _looksClearTrial();
  document.body.classList.add('no-fx');
}, catalog);

const lineupIds = Object.keys(catalog.lineups);
const variants = [0, 1];
const results = [];

for (const lineup of lineupIds) {
  for (const variant of variants) {
    const picked = {};
    for (const slot of Object.keys(catalog.slots)) {
      const items = catalog.slots[slot].filter(item => item.lineup === lineup);
      if (!items.length) continue;
      picked[slot] = items[Math.min(variant, items.length - 1)].id;
    }
    if (Object.keys(picked).length !== Object.keys(catalog.slots).length) {
      throw new Error(`Lineup ${lineup} cannot form a complete profile: ${Object.keys(picked).length}/${Object.keys(catalog.slots).length} slots`);
    }
    await page.evaluate(selection => {
      _looksSel = {};
      _looksSaved = {};
      _looksClearTrial();
      Object.entries(selection).forEach(([slot, id]) => _looksTapUnowned(slot, id));
      if (!document.getElementById('modal')?.open) _looksOpenFittingSheet();
      else _looksRerenderFittingSheetIfOpen();
    }, picked);
    await page.waitForFunction(() => document.querySelectorAll('#mb .fit-outfit-row.trial').length === 6);
    await new Promise(resolveWait => setTimeout(resolveWait, 120));

    const hero = await page.$('#looks-fit-top .fit-player-card');
    const file = resolve(outputDir, `${lineup}-v${variant + 1}.png`);
    await hero.screenshot({path: file});
    results.push({lineup, variant: variant + 1, file, picked});
  }
}

console.log(JSON.stringify(results, null, 2));
await browser.close();
