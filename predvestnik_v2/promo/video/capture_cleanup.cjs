/* Capture the existing cleanup renderer with isolated, invented API fixtures.
 * No Telegram, production backend, or real participant data are accessed.
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const pwPath = process.env.PREDVESTNIK_PLAYWRIGHT || 'C:/Users/makss/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const { chromium } = require(pwPath);
const root = path.resolve(__dirname, '../..');
const out = path.join(__dirname, 'assets');
fs.mkdirSync(out, { recursive: true });
const jsPath = path.join(root, 'FastAPI/static/app.07.js');
const js = fs.readFileSync(jsPath, 'utf8');
const start = js.indexOf('function loadPurgePanel()');
const end = js.indexOf('\nfunction doPurgeStart()', start);
if (start < 0 || end < 0) throw new Error('Current cleanup renderer not found');
const render = js.slice(start, end);
const fixture = {
  active: true, can_verdict: true, purge_action_rank: 2,
  session: { id: 1, norm: 50, date_from: '2026-10-08', date_to: '2026-10-14' },
  counts: { total: 2, sent: 2, decided: 0, warned: 0, kicked: 0, banned: 0, skipped: 0 },
  targets: [
    { user_id: 101, username: 'Лена', msg_count: 12, warns: 0, dossier_sent: true, verdict: null },
    { user_id: 102, username: 'Марк', msg_count: 8, warns: 0, dossier_sent: true, verdict: null },
  ],
};
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 440, height: 660 }, deviceScaleFactor: 3 });
    await page.route('**/*', route => route.abort());
    await page.setContent('<html lang="ru"><head><meta charset="utf-8"></head><body><section class="card" id="capture"><div class="card-title">Чистка активности</div><div id="purge-panel"></div></section></body></html>');
    await page.addStyleTag({ content: fs.readFileSync(path.join(root, 'FastAPI/static/app.css'), 'utf8') });
    await page.addStyleTag({ content: 'body{margin:0;padding:20px;width:440px;box-sizing:border-box;min-height:0!important;overflow:visible!important;background:#07080f;font-family:"Segoe UI",sans-serif}#capture{margin:0;width:400px;box-sizing:border-box}#capture .card-title{margin-bottom:16px}input{min-width:0}button{cursor:default}' });
    await page.evaluate(() => {
      window._adminChatId = -100000000001;
      window.el = id => document.getElementById(id);
      window.esc = text => String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
      window.api = async () => structuredClone(window.fixture);
      window.loadPurgePanel = null;
    });
    await page.addScriptTag({ content: render });
    const states = [];
    async function capture(name, data, fill = false) {
      await page.evaluate(data => { window.fixture = data; window.loadPurgePanel(); }, data);
      await page.locator('#purge-panel button').first().waitFor();
      if (fill) {
        await page.locator('#purge-start').fill('2026-10-08');
        await page.locator('#purge-end').fill('2026-10-14');
      }
      await page.evaluate(() => document.fonts.ready);
      const box = await page.locator('#capture').boundingBox();
      const rowPoints = await page.locator('#purge-panel [style*="border-bottom"]').evaluateAll((rows, origin) => rows.map(row => {
        const r = row.getBoundingClientRect();
        return { x: (r.right - origin.x - 16) * 3, y: (r.y - origin.y + r.height / 2) * 3 };
      }), box);
      await page.locator('#capture').screenshot({ path: path.join(out, name + '.png'), animations: 'disabled' });
      states.push({ name, width: Math.round(box.width * 3), height: Math.round(box.height * 3), rowPoints, fixture: structuredClone(data) });
    }
    await capture('setup', { active: false }, true);
    await capture('candidates', fixture);
    fixture.targets[0].verdict = 'skip';
    fixture.counts.decided = 1; fixture.counts.skipped = 1;
    await capture('skipped', fixture);
    fixture.targets[1].verdict = 'warn';
    fixture.counts.decided = 2; fixture.counts.warned = 1;
    await capture('resolved', fixture);
    fs.writeFileSync(path.join(out, 'capture_manifest.json'), JSON.stringify({
      status: 'rendered_demo', source: 'FastAPI/static/app.07.js::loadPurgePanel',
      sha256: crypto.createHash('sha256').update(js).digest('hex'),
      method: 'Unmodified current UI renderer; invented API fixtures; no live backend',
      real_participants: false, production_mutations: false, states,
    }, null, 2));
    console.log('Captured ' + states.map(s => s.name).join(', '));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });

