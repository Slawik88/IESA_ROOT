const base = (process.env.PREVIEW_URL || 'http://127.0.0.1:8402').replace(/\/$/, '');
const failures = [];

function check(label, condition) {
  if (condition) console.log(`OK  ${label}`);
  else {
    console.error(`FAIL ${label}`);
    failures.push(label);
  }
}

async function response(path) {
  const res = await fetch(`${base}${path}`);
  const text = await res.text();
  check(`${path} returns HTTP 200`, res.status === 200);
  return {res, text};
}

async function redirect(path, method = 'GET') {
  const res = await fetch(`${base}${path}`, {method, redirect: 'manual'});
  check(`${method} ${path} redirects like FastAPI`, res.status === 307
    && res.headers.get('location') === `${base}${path.slice(0, -1)}`);
}

async function missing(path, options = {}) {
  const res = await fetch(`${base}${path}`, options);
  const body = await res.json();
  check(`${options.method || 'GET'} ${path} fails closed like FastAPI`,
    res.status === 404 && body.detail === 'Not Found');
}

async function wrongMethod(path, method, allow) {
  const res = await fetch(`${base}${path}`, {method});
  const body = await res.json();
  check(`${method} ${path} returns FastAPI-compatible 405`, res.status === 405
    && body.detail === 'Method Not Allowed' && res.headers.get('allow') === allow);
}

try {
  const home = await response('/');
  check('index contains the mini-app shell', home.text.includes('id="app-header"') && home.text.includes('id="pg-profile"'));
  check('mini-app shows the development-status notice', home.text.includes('class="development-notice"')
    && home.text.includes('Предвестник в активной разработке'));
  check('preview pre-seeds the local session', home.text.includes("localStorage.setItem('pv_sess','dev-session')"));
  check('preview injects automatic live reload', home.text.includes("new EventSource('/__preview/live')"));

  const liveController = new AbortController();
  const live = await fetch(`${base}/__preview/live`, {signal: liveController.signal});
  check('live reload stream is available', live.status === 200 && (live.headers.get('content-type') || '').includes('text/event-stream'));
  liveController.abort();

  const css = await response('/static/app.css');
  check('real stylesheet is served', css.text.length > 100_000);
  check('current stylesheet does not retain the retired saved-look close-icon dependency', !css.text.includes('icons/x.svg'));

  const js = await response('/static/app.js');
  check('all JavaScript parts are concatenated', js.text.length > 500_000);

  for (const [path, type] of [
    ['/static/app.devmode.js', 'application/javascript'],
    ['/static/reconstruction-lab.css', 'text/css'],
    ['/static/reconstruction-lab.js', 'application/javascript'],
  ]) {
    const asset = await response(path);
    check(`${path} keeps its production content type`, (asset.res.headers.get('content-type') || '').includes(type));
  }

  const closeIcon = await response('/static/icons/x.svg?v=stale-telegram-webview');
  check('legacy cached stylesheet remains compatible with its close-icon URL', (closeIcon.res.headers.get('content-type') || '').includes('image/svg+xml')
    && closeIcon.text.includes('<svg'));

  await redirect('/static/app.css/');
  await redirect('/reconstruction/');
  await redirect('/reconstruction/start/', 'POST');

  for (const path of [
    '/static/app.01.js',
    '/static/reconstruction-lab.html',
    '/static/concept-gallery.html',
    '/static/concept-gallery-production.html',
    '/static/concept-gallery-profile-card.html',
    '/static/design-concepts/profile-card/01-open-central-stage.png',
    '/static/economy-masterplan-report.html',
  ]) {
    const asset = await fetch(`${base}${path}`);
    check(`${path} is not exposed by the production-like preview`, asset.status === 404);
  }

  const game = await response('/game');
  check('game uses the production runtime branch', game.text.includes('data-runtime="production"')
    && game.text.includes('data-api-base=""') && game.text.includes("localStorage.getItem('pv_sess')")
    && game.text.includes('href="/static/reconstruction-lab.css?v=')
    && game.text.includes('src="/static/reconstruction-lab.js?v='));
  const rawGame = await response('/__preview/reconstruction-lab');
  check('raw reconstruction markup is isolated under an explicit preview route', rawGame.text.includes('data-runtime="preview"'));

  const profile = await response('/profile/me');
  const profileData = JSON.parse(profile.text);
  check('profile mock has the expected developer identity', profileData.user_id === 1460945748);
  check('profile mock does not resurrect the retired power index', profileData.combat_power === null
    && profileData.cp_breakdown === null);

  const apiHealth = await response('/api/health');
  check('preview keeps FastAPI\'s only health endpoint', JSON.parse(apiHealth.text).status === 'ok');
  for (const [path, options] of [
    ['/health', {}],
    ['/BASE_PROMPT.md', {}],
    ['/api/reconstruction/manifest', {}],
    ['/totally-unknown', {method: 'POST'}],
  ]) await missing(path, options);
  for (const [path, method, allow] of [
    ['/', 'POST', 'GET'],
    ['/game', 'POST', 'GET'],
    ['/static/app.css', 'POST', 'GET'],
    ['/manifest.json', 'POST', 'GET'],
    ['/profile/u/999', 'POST', 'GET'],
    ['/themes/preview/unknown', 'POST', 'GET'],
    ['/profile/me', 'POST', 'GET'],
    ['/themes/', 'POST', 'GET'],
    ['/cosmetics/presets/1/apply', 'PATCH', 'POST'],
    ['/gacha/spin', 'PATCH', 'POST'],
  ]) await wrongMethod(path, method, allow);
  const retiredSpin = await fetch(`${base}/gacha/spin`, {method:'POST'});
  check('the correct method for a retired mutation stays an explicit 410', retiredSpin.status === 410);

  const cosmetics = await response('/cosmetics/');
  const cosmeticsData = JSON.parse(cosmetics.text);
  check('cosmetics mock exposes slots', cosmeticsData.slots && Object.keys(cosmeticsData.slots).length >= 6);

  const paymentPackages = await response('/payments/zarniki/packages');
  const paymentData = JSON.parse(paymentPackages.text);
  check('preview Stars catalog matches the active v1 package shape and limits', paymentData.per_star === 10
    && paymentData.custom_min === 1 && paymentData.custom_max === 100000
    && JSON.stringify(paymentData.packages) === JSON.stringify([
      {stars: 20, zarniki: 200, bonus: 15, total: 215, popular: false},
      {stars: 50, zarniki: 500, bonus: 50, total: 550, popular: false},
      {stars: 100, zarniki: 1000, bonus: 100, total: 1100, popular: true},
      {stars: 200, zarniki: 2000, bonus: 200, total: 2200, popular: false},
      {stars: 300, zarniki: 3000, bonus: 300, total: 3300, popular: false},
      {stars: 400, zarniki: 4000, bonus: 400, total: 4400, popular: false},
    ]));
  const previewInvoice = await fetch(`${base}/payments/zarniki/invoice`, {
    method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({stars: 20}),
  });
  const previewInvoiceError = await previewInvoice.json();
  check('preview explicitly blocks real Stars invoice creation instead of fabricating payment success', previewInvoice.status === 503
    && /не создаёт реальный счёт Stars/.test(previewInvoiceError.detail || ''));

  const deletePreset = await fetch(`${base}/cosmetics/presets/1`, {method: 'DELETE'});
  check('saved-look deletion has an explicit local mock', deletePreset.status === 200 && (await deletePreset.json()).ok === true);

  const clans = await response('/clans/');
  const clansData = JSON.parse(clans.text);
  check('clans mock matches the overview contract', Array.isArray(clansData.top)
    && Array.isArray(clansData.emblems) && typeof clansData.create_cost === 'number');

  const reset = await fetch(`${base}/__preview/reset`, {method: 'POST'});
  check('stateful preview reset works', reset.status === 200 && (await reset.json()).ok === true);
} catch (error) {
  console.error(error);
  failures.push(`unexpected error: ${error.message}`);
}

if (failures.length) {
  console.error(`\n${failures.length} preview check(s) failed.`);
  process.exit(1);
}

console.log('\nALL OK');
