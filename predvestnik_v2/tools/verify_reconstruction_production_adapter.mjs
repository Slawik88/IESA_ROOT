#!/usr/bin/env node
import fs from 'fs';
import puppeteer from 'puppeteer';

const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8402';
const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH;
const source = fs.readFileSync(
  new URL('../FastAPI/static/reconstruction-lab.html', import.meta.url),
  'utf8',
);
const productionHtml = source
  .replace('data-runtime="preview"', 'data-runtime="production"')
  .replace('data-api-base="/__reconstruction"', 'data-api-base=""');

const [manifest, initialState, companionOverview] = await Promise.all([
  fetch(`${base}/__reconstruction/manifest`).then((response) => response.json()),
  fetch(`${base}/__reconstruction/state`, {
    headers: { 'x-reconstruction-session': 'production-adapter-verifier' },
  }).then((response) => response.json()),
  fetch(`${base}/__reconstruction/companions`, {
    headers: { 'x-reconstruction-session': 'production-adapter-verifier' },
  }).then((response) => response.json()),
]);

const completedState = {
  ...initialState,
  run_id: 77,
  status: 'won',
  outcome_reason: 'all_echoes_broken',
};
const memory = {
  id: 'm_mobile_oath',
  unit_id: manifest.starter_units[0].id,
  name: 'Клятва движения',
  effect: 'Проверочный постоянный выбор.',
  tradeoff: 'Нельзя выбрать второй вариант.',
};
const overview = {
  content: manifest,
  units: manifest.starter_units.map((unit) => ({
    unit_id: unit.id,
    name: unit.name,
    short_name: unit.short_name,
    emoji: unit.emoji,
    level: 1,
    total_xp: 0,
    xp_in_level: 0,
    xp_to_next: 120,
    branch_choices: {},
    next_branch_level: 5,
    proven_challenges: [],
  })),
  progress: {
    started: true,
    current_encounter: 'e02_shattered_causeway',
    completed: ['e01_two_bells'],
    memories: [],
    pending_memory: { encounter_id: 'e01_two_bells', choices: [memory] },
    next_step: {
      type: 'choose_memory', encounter_id: 'e01_two_bells',
      title: 'Сохрани Память первой победы',
      description: 'Выбор постоянный.',
    },
  },
  active_run: completedState,
  stats: {
    runs_started: 1,
    runs_won: 1,
    runs_lost: 0,
    correct_taps: 8,
    total_taps: 10,
    mistakes: 2,
    missed_signals: 1,
    best_combo: 5,
    fastest_win_ms: 42000,
    total_play_ms: 42000,
    upgrades: {},
  },
};
let overviewResponse = overview;
const actionBodies = [];
const pathBodies = [];
let rejectNextAction = false;

const browser = await puppeteer.launch({
  headless: true,
  executablePath,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});

try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname === '/production-harness') {
      request.respond({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: productionHtml,
      });
      return;
    }
    if (url.pathname === '/reconstruction' && request.method() === 'GET') {
      request.respond({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify(overviewResponse),
      });
      return;
    }
    if (url.pathname === '/reconstruction/companions' && request.method() === 'GET') {
      request.respond({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify(companionOverview),
      });
      return;
    }
    if (url.pathname === '/reconstruction/runs/88/actions' && request.method() === 'POST') {
      const actionBody = JSON.parse(request.postData() || '{}');
      actionBodies.push(actionBody);
      if (rejectNextAction) {
        rejectNextAction = false;
        overviewResponse = {
          ...overviewResponse,
          active_run: { ...overviewResponse.active_run, revision: actionBody.expected_revision + 1 },
        };
        request.respond({
          status: 409,
          contentType: 'application/json; charset=utf-8',
          body: JSON.stringify({ detail: 'Забег уже изменился в другой вкладке.' }),
        });
        return;
      }
      request.respond({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify({
          ...overviewResponse.active_run,
          revision: actionBody.expected_revision + 1,
          turn: { ok: true, phase: 'active' },
          pending_memory: null,
          career_stats: overviewResponse.stats,
          idempotent_replay: false,
        }),
      });
      return;
    }
    if (url.pathname === '/reconstruction/memory' && request.method() === 'POST') {
      request.respond({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify({
          ok: true,
          memory_id: memory.id,
          idempotent_replay: false,
          next_step: {
            type: 'play_encounter', encounter_id: 'e02_shattered_causeway',
            title: 'Разломанный тракт', description: 'Провести Фонарь.', practice: false,
          },
        }),
      });
      return;
    }
    if (url.pathname === '/reconstruction/chronicle/path' && request.method() === 'POST') {
      pathBodies.push(JSON.parse(request.postData() || '{}'));
      request.respond({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify({
          ok: true, path_id: 'ink', encounter_id: 'e03_ink_path',
          idempotent_replay: false,
          next_step: {
            type: 'play_encounter', encounter_id: 'e03_ink_path',
            title: 'Чернильная тропа', description: 'Отличить настоящую руну.', practice: false,
          },
        }),
      });
      return;
    }
    request.continue();
  });

  await page.goto(`${base}/production-harness`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#resultLayer:not([hidden])');
  const labels = await page.evaluate(() => ({
    runtime: document.getElementById('runtimeEyebrow').textContent.trim(),
    profile: document.getElementById('profileKind').textContent.trim(),
    stats: document.getElementById('statsEyebrow').textContent.trim(),
    statsCopy: document.getElementById('statsCopy').textContent.trim(),
    resultAction: document.getElementById('resultReset').textContent.trim(),
    unitCards: document.querySelectorAll('[data-unit-progress]').length,
  }));
  if (labels.runtime !== 'БОЕВАЯ СИСТЕМА') throw new Error(`runtime label: ${labels.runtime}`);
  if (labels.profile !== 'ПРОФИЛЬ ИГРОКА') throw new Error(`profile label: ${labels.profile}`);
  if (labels.stats !== 'ПРОФИЛЬ РАЗЛОМА') throw new Error(`stats label: ${labels.stats}`);
  if (!labels.statsCopy.includes('Сервер') || !labels.statsCopy.includes('пропуски входят в точность')) {
    throw new Error(`stats copy is still preview-only: ${labels.statsCopy}`);
  }
  if (!labels.resultAction.includes('Выбрать Память')) {
    throw new Error(`pending memory action is missing: ${labels.resultAction}`);
  }
  if (labels.unitCards !== 3) throw new Error(`unit progress cards: ${labels.unitCards}`);

  await page.click('#resultReset');
  await page.waitForSelector('[data-memory-id]');
  await page.click('[data-memory-id]');
  await page.waitForFunction(
    () => document.getElementById('resultReset')?.textContent.includes('Продолжить Хронику'),
  );
  const resultStats = await page.$$eval('#resultStats span', (nodes) =>
    nodes.map((node) => node.textContent.trim()));
  if (!resultStats.some((value) => value.includes('пропущено'))) {
    throw new Error(`missed signals absent from result: ${resultStats.join(' | ')}`);
  }

  overviewResponse = {
    ...overview,
    progress: {
      ...overview.progress,
      current_encounter: 'choose_chapter_1_path',
      completed: ['e01_two_bells', 'e02_shattered_causeway'],
      memories: [memory.id],
      pending_memory: null,
      route_choices: {},
      next_step: {
        type: 'choose_chronicle_path',
        title: 'Выбери тропу первой главы',
        description: 'Две разные грамматики.',
        choices: [
          { id: 'ink', encounter_id: 'e03_ink_path', name: 'Чернильная тропа', description: 'Ложные знаки.', mastery: 'Без ошибок.' },
          { id: 'ash', encounter_id: 'e03_ash_path', name: 'Пепельная тропа', description: 'Сохрани огонь.', mastery: 'Огонь 70%.' },
        ],
      },
    },
    active_run: { ...completedState, encounter_id: 'e02_shattered_causeway' },
  };
  await page.evaluate(() => sessionStorage.removeItem('reconstruction-mvp-ui-v1'));
  await page.goto(`${base}/production-harness`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#resultLayer:not([hidden])');
  await page.click('#resultReset');
  await page.waitForSelector('[data-chronicle-path="ink"]');
  await page.click('[data-chronicle-path="ink"]');
  await page.waitForFunction(
    () => document.getElementById('resultReset')?.textContent.includes('Продолжить Хронику'),
  );
  if (pathBodies.length !== 1 || pathBodies[0].path_id !== 'ink') {
    throw new Error(`chronicle path body: ${JSON.stringify(pathBodies)}`);
  }

  overviewResponse = {
    ...overview,
    progress: { ...overview.progress, pending_memory: null },
    active_run: {
      ...initialState,
      run_id: 88,
      revision: 12,
      status: 'active',
    },
  };
  await page.evaluate(() => sessionStorage.removeItem('reconstruction-mvp-ui-v1'));
  await page.goto(`${base}/production-harness`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#menuLayer:not([hidden])');
  await page.click('#startRunButton');
  await page.waitForFunction(() => document.querySelector('#roundClock strong'));
  for (let attempt = 0; attempt < 20 && !actionBodies.length; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  const firstActionBody = actionBodies[0];
  if (firstActionBody?.expected_revision !== 12) {
    throw new Error(`server revision missing from action: ${JSON.stringify(firstActionBody)}`);
  }
  if (!String(firstActionBody?.action_id || '').startsWith('web:')) {
    throw new Error(`action id missing from action: ${JSON.stringify(firstActionBody)}`);
  }

  actionBodies.length = 0;
  overviewResponse = {
    ...overviewResponse,
    active_run: { ...overviewResponse.active_run, revision: 20 },
  };
  rejectNextAction = true;
  await page.evaluate(() => sessionStorage.removeItem('reconstruction-mvp-ui-v1'));
  await page.goto(`${base}/production-harness`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#menuLayer:not([hidden])');
  await page.click('#startRunButton');
  await page.waitForSelector('#pauseLayer:not([hidden])');
  const visibleLayers = await page.evaluate(() =>
    ['menuLayer', 'pauseLayer', 'choiceLayer', 'resultLayer']
      .filter((id) => !document.getElementById(id).hidden));
  if (visibleLayers.join(',') !== 'pauseLayer') {
    throw new Error(`revision conflict changed to wrong modal: ${visibleLayers.join(',')}`);
  }
  if (actionBodies[0]?.expected_revision !== 20) {
    throw new Error(`conflict request used wrong revision: ${JSON.stringify(actionBodies[0])}`);
  }
  if (errors.length) throw new Error(`browser errors: ${errors.join(' | ')}`);
  console.log('OK: production adapter labels, server stats, Memory handoff and revision contract');
} finally {
  await browser.close();
}
