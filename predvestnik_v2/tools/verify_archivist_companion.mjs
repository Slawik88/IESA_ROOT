import fs from 'fs';
import puppeteer from 'puppeteer';

const base = process.env.PREVIEW_URL || 'http://localhost:8402';
const output = process.env.ARCHIVIST_SCREENSHOT_DIR || '';
const session = `archivist-${Date.now()}`;
const headers = {
  'content-type': 'application/json',
  'x-reconstruction-session': session,
  'x-reconstruction-test-clock': 'fixed-step-100',
};

async function request(path, options = {}) {
  const response = await fetch(`${base}/__reconstruction${path}`, {
    headers, ...options,
  });
  if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`);
  return response.json();
}

await request('/companions/role', {
  method: 'POST', body: JSON.stringify({ role_id: 'archivist' }),
});
await request('/reset', {
  method: 'POST', body: JSON.stringify({
    encounter_id: 'e01_two_bells', companion_role_id: 'archivist',
  }),
});

let state;
for (let step = 0; step < 420; step += 1) {
  state = await request('/state');
  if (state.status === 'reward') break;
  if (state.status !== 'active') throw new Error(`unexpected phase: ${state.status}`);
  const challenge = state.challenge;
  if (challenge?.active) {
    const target = challenge.options.find((item) => item.symbol === challenge.target_symbol);
    if (!target) throw new Error('active signal has no matching target');
    await request('/action', {
      method: 'POST', body: JSON.stringify({
        type: 'strike', delta_ms: 0,
        challenge_id: challenge.id, target_slot: target.slot,
      }),
    });
  } else {
    await request('/action', {
      method: 'POST', body: JSON.stringify({ type: 'frame', delta_ms: 500 }),
    });
  }
}

if (state?.status !== 'reward') {
  throw new Error(`first wave did not reach reward screen: ${JSON.stringify({
    status: state?.status, hp: state?.wave?.hp, elapsed: state?.wave?.elapsed_ms,
    correct: state?.mastery?.correct_taps, missed: state?.mastery?.missed_signals,
  })}`);
}
const review = state.companion_state?.archivist_review;
if (!review || review.reveals_answer !== false) throw new Error('safe Archivist review missing');
if (state.reward_options.length !== 2) throw new Error('Archivist must leave exactly two upgrades');

if (output) fs.mkdirSync(output, { recursive: true });
const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
  args: ['--no-sandbox'],
});
const failures = [];
try {
  for (const width of [320, 390]) {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.setViewport({ width, height: 844, deviceScaleFactor: 1 });
    await page.evaluateOnNewDocument((key) => {
      sessionStorage.setItem('reconstruction-preview-session', key);
      sessionStorage.setItem('reconstruction-mvp-ui-v1', JSON.stringify({ view: 'choice', tab: 'play' }));
    }, session);
    await page.goto(`${base}/static/reconstruction-lab.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#choiceLayer:not([hidden]) .archivist-review');
    const metrics = await page.evaluate(() => {
      const reviewNode = document.querySelector('.archivist-review');
      const cards = [...document.querySelectorAll('#upgradeList .upgrade-card')];
      return {
        overflow: document.documentElement.scrollWidth - innerWidth,
        reviewWidth: reviewNode.getBoundingClientRect().width,
        sheetWidth: document.querySelector('.choice-sheet').getBoundingClientRect().width,
        cards: cards.length,
        copy: reviewNode.textContent.replace(/\s+/g, ' ').trim(),
        sizes: [...reviewNode.querySelectorAll('small,strong,p,em')]
          .map((node) => parseFloat(getComputedStyle(node).fontSize)),
        cardHeights: cards.map((node) => node.getBoundingClientRect().height),
      };
    });
    if (metrics.overflow > 0) failures.push(`${width}px: horizontal overflow ${metrics.overflow}`);
    if (metrics.reviewWidth > metrics.sheetWidth) failures.push(`${width}px: review exceeds sheet`);
    if (metrics.cards !== 2) failures.push(`${width}px: ${metrics.cards} upgrades instead of 2`);
    if (!metrics.copy.includes('точных') || !metrics.copy.includes('ошибок') || !metrics.copy.includes('пропущено')) {
      failures.push(`${width}px: review lacks actionable metrics`);
    }
    if (metrics.sizes.some((size) => size < 9)) failures.push(`${width}px: unreadable review text`);
    if (metrics.cardHeights.some((height) => height < 76)) failures.push(`${width}px: upgrade target too short`);
    if (errors.length) failures.push(`${width}px: ${errors.join(', ')}`);
    if (output) await page.screenshot({ path: `${output}/archivist-reward-${width}.png`, fullPage: true });
    await page.close();
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}
console.log('archivist companion: per-wave review + compact 320/390px choice UI OK');
