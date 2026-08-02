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

try {
  const home = await response('/');
  check('index contains the mini-app shell', home.text.includes('id="app-header"') && home.text.includes('id="pg-profile"'));
  check('preview pre-seeds the local session', home.text.includes("localStorage.setItem('pv_sess','dev-session')"));
  check('preview injects automatic live reload', home.text.includes("new EventSource('/__preview/live')"));

  const liveController = new AbortController();
  const live = await fetch(`${base}/__preview/live`, {signal: liveController.signal});
  check('live reload stream is available', live.status === 200 && (live.headers.get('content-type') || '').includes('text/event-stream'));
  liveController.abort();

  const css = await response('/static/app.css');
  check('real stylesheet is served', css.text.length > 100_000);

  const js = await response('/static/app.js');
  check('all JavaScript parts are concatenated', js.text.length > 500_000);

  const closeIcon = await response('/static/icons/x.svg');
  check('static SVG assets keep an image content type', (closeIcon.res.headers.get('content-type') || '').includes('image/svg+xml')
    && closeIcon.text.includes('<svg'));

  const profile = await response('/profile/me');
  const profileData = JSON.parse(profile.text);
  check('profile mock has the expected developer identity', profileData.user_id === 1460945748);

  const cosmetics = await response('/cosmetics/');
  const cosmeticsData = JSON.parse(cosmetics.text);
  check('cosmetics mock exposes slots', cosmeticsData.slots && Object.keys(cosmeticsData.slots).length >= 6);

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
