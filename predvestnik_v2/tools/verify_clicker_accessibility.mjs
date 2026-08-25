import puppeteer from 'puppeteer';

const base = process.env.PREVIEW_URL || 'http://localhost:8402';
const session = `a11y-${Date.now()}`;
const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
  args: ['--no-sandbox'],
});
const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };

try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.setExtraHTTPHeaders({ 'x-reconstruction-test-clock': 'fixed-step-100' });
  await page.evaluateOnNewDocument((key) => {
    sessionStorage.setItem('reconstruction-preview-session', key);
    sessionStorage.removeItem('reconstruction-mvp-ui-v1');
  }, session);
  await page.goto(`${base}/__preview/reconstruction-lab`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#menuLayer:not([hidden])');

  const tabs = await page.evaluate(() => ({
    listRole: document.querySelector('.menu-tabs')?.getAttribute('role'),
    count: document.querySelectorAll('[role="tab"]').length,
    selected: document.querySelectorAll('[role="tab"][aria-selected="true"]').length,
    tabbable: [...document.querySelectorAll('[role="tab"]')].filter((node) => node.tabIndex === 0).length,
    dialogName: document.querySelector('.menu-card')?.getAttribute('aria-label'),
  }));
  check(tabs.listRole === 'tablist', 'menu navigation is not exposed as a tab list');
  check(tabs.count === 5 && tabs.selected === 1 && tabs.tabbable === 1, 'tab selection contract is ambiguous');
  check(tabs.dialogName === 'Меню игры', 'menu dialog has no stable accessible name');

  await page.focus('[data-menu-tab="play"]');
  await page.keyboard.press('ArrowRight');
  const keyboardTab = await page.evaluate(() => ({
    selected: document.querySelector('[role="tab"][aria-selected="true"]')?.dataset.menuTab,
    focused: document.activeElement?.dataset?.menuTab,
    panelVisible: !document.getElementById('companionPanel')?.hidden,
    outline: getComputedStyle(document.activeElement).outlineStyle,
  }));
  check(keyboardTab.selected === 'companion' && keyboardTab.focused === 'companion' && keyboardTab.panelVisible,
    'arrow-key tab navigation did not move selection and focus together');
  check(keyboardTab.outline !== 'none', 'keyboard focus is not visibly indicated');

  await page.click('[data-menu-tab="play"]');
  await page.click('#startRunButton');
  await page.waitForFunction(() => document.querySelector('.tap-stage')?.classList.contains('signal'), { timeout: 3000 });
  const runeLabels = await page.$$eval('.strike-rune', (nodes) => nodes.map((node) => node.getAttribute('aria-label')));
  check(runeLabels.every((label) => /^(Слева|По центру|Справа): руна /.test(label || '')),
    `rune labels are not localized: ${JSON.stringify(runeLabels)}`);

  await page.click('#menuButton');
  await page.waitForSelector('#pauseLayer:not([hidden])');
  await page.waitForFunction(() => document.activeElement?.id === 'continueButton');
  const pause = await page.evaluate(() => ({
    role: document.querySelector('.pause-card')?.getAttribute('role'),
    modal: document.querySelector('.pause-card')?.getAttribute('aria-modal'),
    focused: document.activeElement?.id,
  }));
  check(pause.role === 'dialog' && pause.modal === 'true' && pause.focused === 'continueButton',
    'pause dialog does not announce itself or receive focus');
  await page.keyboard.press('Escape');
  await page.waitForSelector('#pauseLayer[hidden]');
  check(errors.length === 0, `browser errors: ${errors.join(', ')}`);
  await page.close();
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}
console.log('clicker accessibility: tabs, focus, dialogs and localized rune labels OK');
