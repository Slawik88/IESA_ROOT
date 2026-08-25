#!/usr/bin/env node
/** Verify the local /game bridge against the production Reconstruction contract. */
import puppeteer from 'puppeteer';

const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8402';
const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH || undefined;
const fail = (message) => { throw new Error(message); };
const token = (label) => `preview-contract-${label}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

async function api(path, { session, method = 'GET', body, headers = {} } = {}) {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: {
      'content-type': 'application/json',
      ...(session ? { 'x-session-token': session } : {}),
      ...headers,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return { response, data: await response.json() };
}

const primary = token('primary');
const isolated = token('isolated');

const first = await api('/reconstruction', { session: primary });
if (!first.response.ok) fail(`overview: HTTP ${first.response.status}`);
for (const key of ['content', 'progress', 'units', 'active_run', 'stats']) {
  if (!(key in first.data)) fail(`overview omits ${key}`);
}
if (first.data.active_run !== null) fail('a fresh production session unexpectedly has an active run');
if (!first.data.progress.next_step?.encounter_id) fail('overview does not expose a playable next step');

const start = await api('/reconstruction/start', {
  session: primary,
  method: 'POST',
  body: { encounter_id: 'e01_two_bells', practice: false },
});
if (!start.response.ok || !Number.isInteger(start.data.run_id) || start.data.revision !== 0 || !start.data.team?.units?.length) {
  fail(`start contract: ${start.response.status} ${JSON.stringify(start.data)}`);
}

const actionBody = {
  action_id: 'verify-preview-contract-frame',
  expected_revision: 0,
  type: 'frame',
  delta_ms: 100,
};
const action = await api(`/reconstruction/runs/${start.data.run_id}/actions`, {
  session: primary, method: 'POST', body: actionBody,
});
if (!action.response.ok || action.data.revision !== 1 || !action.data.turn?.ok || !action.data.wave
  || action.data.turn.server_revision !== action.data.revision) {
  fail(`action contract: ${action.response.status} ${JSON.stringify(action.data)}`);
}
const replay = await api(`/reconstruction/runs/${start.data.run_id}/actions`, {
  session: primary, method: 'POST', body: actionBody,
});
if (!replay.response.ok || replay.data.idempotent_replay !== true || replay.data.revision !== 1) {
  fail(`idempotency contract: ${replay.response.status} ${JSON.stringify(replay.data)}`);
}
const stale = await api(`/reconstruction/runs/${start.data.run_id}/actions`, {
  session: primary,
  method: 'POST',
  body: { ...actionBody, action_id: 'verify-preview-contract-stale' },
});
if (stale.response.status !== 409) fail(`revision conflict: expected 409, got ${stale.response.status}`);

const other = await api('/reconstruction', { session: isolated });
if (!other.response.ok || other.data.active_run !== null) fail('production sessions leak active runs across tokens');

const companions = await api('/reconstruction/companions', { session: primary });
if (!companions.response.ok || !Array.isArray(companions.data.pets) || !companions.data.policy?.roles?.length) {
  fail(`companions contract: ${companions.response.status} ${JSON.stringify(companions.data)}`);
}
const role = await api('/reconstruction/companions/role', {
  session: primary, method: 'POST', body: { role_id: 'guardian' },
});
if (!role.response.ok || role.data.selected_role_id !== 'guardian') {
  fail(`companion mutation: ${role.response.status} ${JSON.stringify(role.data)}`);
}
const cancelled = await api(`/reconstruction/runs/${start.data.run_id}/cancel`, {
  session: primary, method: 'POST', body: {},
});
if (!cancelled.response.ok || cancelled.data.ok !== true || cancelled.data.idempotent_replay !== false
  || cancelled.data.terminal_result?.outcome !== 'cancelled' || !cancelled.data.shadow_reward) {
  fail(`cancel contract: ${cancelled.response.status} ${JSON.stringify(cancelled.data)}`);
}
const cancelledReplay = await api(`/reconstruction/runs/${start.data.run_id}/cancel`, {
  session: primary, method: 'POST', body: {},
});
if (!cancelledReplay.response.ok || cancelledReplay.data.idempotent_replay !== true
  || cancelledReplay.data.revision !== cancelled.data.revision
  || cancelledReplay.data.terminal_result?.id !== cancelled.data.terminal_result?.id
  || !cancelledReplay.data.shadow_reward) {
  fail(`cancel replay contract: ${cancelledReplay.response.status} ${JSON.stringify(cancelledReplay.data)}`);
}
const restarted = await api('/reconstruction/start', {
  session: primary,
  method: 'POST',
  body: { encounter_id: 'e01_two_bells', practice: false },
});
if (!restarted.response.ok || restarted.data.run_id <= start.data.run_id) {
  fail(`new runs must receive a new id: ${restarted.response.status} ${JSON.stringify(restarted.data)}`);
}
const oldCancelAfterRestart = await api(`/reconstruction/runs/${start.data.run_id}/cancel`, {
  session: primary, method: 'POST', body: {},
});
if (!oldCancelAfterRestart.response.ok || oldCancelAfterRestart.data.idempotent_replay !== true
  || oldCancelAfterRestart.data.terminal_result?.id !== cancelled.data.terminal_result?.id) {
  fail(`cancel replay after next run: ${oldCancelAfterRestart.response.status} ${JSON.stringify(oldCancelAfterRestart.data)}`);
}

// The bridge is a ThreadingHTTPServer.  Same-session mutations must retain the
// production lock/revision contract even when a browser retries in parallel.
const concurrent = token('concurrent');
const concurrentStarts = await Promise.all(Array.from({ length: 8 }, () => api('/reconstruction/start', {
  session: concurrent, method: 'POST', body: { encounter_id: 'e01_two_bells', practice: false },
})));
const freshStarts = concurrentStarts.filter((item) => item.response.ok && item.data.resumed === false);
const concurrentRunIds = new Set(concurrentStarts.map((item) => item.data.run_id));
if (freshStarts.length !== 1 || concurrentRunIds.size !== 1) {
  fail(`parallel start contract: ${JSON.stringify(concurrentStarts.map((item) => item.data))}`);
}
const concurrentRunId = freshStarts[0].data.run_id;
const concurrentActions = await Promise.all(Array.from({ length: 8 }, (_, index) => api(
  `/reconstruction/runs/${concurrentRunId}/actions`, {
    session: concurrent, method: 'POST',
    body: { action_id: `parallel-frame-${index}`, expected_revision: 0, type: 'frame', delta_ms: 100 },
  },
)));
if (concurrentActions.filter((item) => item.response.status === 200).length !== 1
  || concurrentActions.filter((item) => item.response.status === 409).length !== 7) {
  fail(`parallel revision contract: ${JSON.stringify(concurrentActions.map((item) => item.response.status))}`);
}

// A terminal action is cached in production before a later run can begin.  A
// retry must therefore remain replayable after that next run has been created.
const terminalSession = token('terminal');
const terminalStart = await api('/reconstruction/start', {
  session: terminalSession, method: 'POST', body: { encounter_id: 'e01_two_bells', practice: false },
});
if (!terminalStart.response.ok) fail(`terminal test start: ${JSON.stringify(terminalStart.data)}`);
let terminalAction = null;
let terminalActionBody = null;
for (let frame = 0; frame < 240; frame += 1) {
  const body = {
    action_id: `terminal-loss-frame-${frame}`,
    expected_revision: frame,
    type: 'frame', delta_ms: 100,
  };
  const result = await api(`/reconstruction/runs/${terminalStart.data.run_id}/actions`, {
    session: terminalSession, method: 'POST', body,
    headers: { 'x-reconstruction-test-clock': 'fixed-step-100' },
  });
  if (!result.response.ok) fail(`terminal test frame ${frame}: ${JSON.stringify(result.data)}`);
  if (result.data.terminal_result) {
    terminalAction = result;
    terminalActionBody = body;
    break;
  }
}
if (!terminalAction || terminalAction.data.terminal_result?.outcome !== 'lost'
  || !terminalAction.data.shadow_reward
  || terminalAction.data.turn?.server_revision !== terminalAction.data.revision) {
  fail(`terminal loss contract: ${JSON.stringify(terminalAction?.data)}`);
}
const runAfterTerminal = await api('/reconstruction/start', {
  session: terminalSession, method: 'POST', body: { encounter_id: 'e01_two_bells', practice: false },
});
if (!runAfterTerminal.response.ok || runAfterTerminal.data.run_id <= terminalStart.data.run_id) {
  fail(`terminal follow-up start: ${JSON.stringify(runAfterTerminal.data)}`);
}
const terminalReplay = await api(`/reconstruction/runs/${terminalStart.data.run_id}/actions`, {
  session: terminalSession, method: 'POST', body: terminalActionBody,
});
if (!terminalReplay.response.ok || terminalReplay.data.idempotent_replay !== true
  || terminalReplay.data.terminal_result?.id !== terminalAction.data.terminal_result.id) {
  fail(`terminal action replay after next run: ${JSON.stringify(terminalReplay.data)}`);
}

const browser = await puppeteer.launch({
  headless: 'new', executablePath, args: ['--no-sandbox'],
});
try {
  const firstContext = await browser.createBrowserContext();
  const secondContext = await browser.createBrowserContext();
  const page = await firstContext.newPage();
  const isolatedPage = await secondContext.newPage();
  const errors = [];
  const reconstructionRequests = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/reconstruction')) reconstructionRequests.push(url.pathname);
  });
  await page.setExtraHTTPHeaders({ 'x-reconstruction-test-clock': 'fixed-step-100' });
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  // The ordinary journey must not let the root's lightweight mock session
  // become a shared Reconstruction profile across independent browser contexts.
  await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' });
  await isolatedPage.goto(`${base}/`, { waitUntil: 'domcontentloaded' });
  await page.goto(`${base}/game`, { waitUntil: 'domcontentloaded' });
  await isolatedPage.goto(`${base}/game`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#menuLayer:not([hidden])');
  await isolatedPage.waitForSelector('#menuLayer:not([hidden])');
  const [firstBrowserSession, secondBrowserSession] = await Promise.all([
    page.evaluate(() => localStorage.getItem('pv_sess')),
    isolatedPage.evaluate(() => localStorage.getItem('pv_sess')),
  ]);
  if (!firstBrowserSession?.startsWith('preview-reconstruction-')
    || !secondBrowserSession?.startsWith('preview-reconstruction-')
    || firstBrowserSession === secondBrowserSession) {
    fail(`root-to-game session isolation: ${firstBrowserSession} / ${secondBrowserSession}`);
  }
  const labels = await page.evaluate(() => ({
    runtime: document.getElementById('runtimeEyebrow')?.textContent.trim(),
    profile: document.getElementById('profileKind')?.textContent.trim(),
    stats: document.getElementById('statsEyebrow')?.textContent.trim(),
    rawRuntimeMarker: document.body.dataset.runtime,
  }));
  if (labels.runtime !== 'БОЕВАЯ СИСТЕМА' || labels.profile !== 'ПРОФИЛЬ ИГРОКА'
    || labels.stats !== 'ПРОФИЛЬ РАЗЛОМА' || labels.rawRuntimeMarker !== 'production') {
    fail(`production labels: ${JSON.stringify(labels)}`);
  }
  await page.click('#startRunButton');
  await page.waitForSelector('.squad-member');
  await page.waitForFunction(() => document.querySelectorAll('.squad-member').length === 3);
  const isolatedOverview = await isolatedPage.evaluate(async () => {
    const response = await fetch('/reconstruction', {
      headers: { 'x-session-token': localStorage.getItem('pv_sess') || '' },
    });
    return { status: response.status, body: await response.json() };
  });
  if (isolatedOverview.status !== 200 || isolatedOverview.body.active_run !== null) {
    fail(`root-to-game active run isolation: ${JSON.stringify(isolatedOverview)}`);
  }
  if (!reconstructionRequests.includes('/reconstruction')
    || !reconstructionRequests.includes('/reconstruction/start')
    || reconstructionRequests.some((path) => path.includes('__reconstruction'))) {
    fail(`browser used the wrong API surface: ${reconstructionRequests.join(', ')}`);
  }
  if (errors.length) fail(`browser errors: ${errors.join(', ')}`);
  console.log('reconstruction preview production contract: OK');
} finally {
  await browser.close();
}
