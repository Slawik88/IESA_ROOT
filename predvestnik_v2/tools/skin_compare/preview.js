/* Test context only. Every look, scene, profile and top renderer comes from its checkout. */
const labRoot = document.getElementById('lab-root');
const labFixture = {
  user_id: 'skin-review', seed: 'skin-review', display_name: 'Предвестник',
  account_level: 12, xp_into: 45, xp_to_next: 100, rank: 'Путешественник',
  marks: [], vip: null, is_vip: false, avatar: null, wallet: {mora: 1200},
  streak: 7, achievements: 12, messages_all_time: 840,
};
let labRendering = 0;
labRoot.addEventListener('click', event => {event.preventDefault();event.stopImmediatePropagation();}, true);

async function labAssetsReady() {
  let timeout;
  try {
    await Promise.race([
      Promise.all([document.fonts.ready, ...[...document.querySelectorAll('link[rel=stylesheet]')].map(link => link.sheet
        ? Promise.resolve() : new Promise((resolve, reject) => {
          link.addEventListener('load', resolve, {once:true});
          link.addEventListener('error', () => reject(new Error(`Stylesheet missing: ${link.href}`)), {once:true});
        })), ...[...labRoot.querySelectorAll('img')].map(img => img.decode())]),
      new Promise((_, reject) => {timeout = setTimeout(() => reject(new Error('Preview assets did not load in 8 seconds')), 8000);}),
    ]);
  } finally { clearTimeout(timeout); }
  const ready = [...labRoot.querySelectorAll('.sc[data-al]')].every(node => {
    const file = globalThis.__pvSceneArt[node.dataset.al]?.[0];
    return file && [...document.querySelectorAll('link[rel=stylesheet]')].some(link =>
      link.href === new URL(file, location.href).href && link.sheet) && getComputedStyle(node).visibility === 'visible';
  });
  if (!ready) throw new Error('A requested scene picture is missing');
  return ready;
}

async function labRender(options) {
  const generation = ++labRendering;
  const {skin, tier, mode = 'profile', device = 'high', phase = 'normal'} = options;
  const [memory, cores] = device === 'low' ? [2, 2] : device === 'mid' ? [4, 6] : [8, 8];
  Object.defineProperty(navigator, 'deviceMemory', {get: () => memory, configurable: true});
  Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => cores, configurable: true});
  let randomSeed = [...`${skin}:${tier}:${mode}:${device}:${phase}`].reduce((sum, char) => (sum * 31 + char.codePointAt(0)) >>> 0, 1);
  Math.random = () => {randomSeed = (Math.imul(randomSeed, 1664525) + 1013904223) >>> 0; return randomSeed / 4294967296;};
  const look = LAB_DATA.looks[skin]?.[tier];
  if (!look) throw new Error('Unknown skin or tier');
  document.documentElement.dataset.ready = '';
  document.documentElement.dataset.live = '';
  _v3Watchdog = true;  // device mode is an explicit test input, never inferred from this test machine's speed
  document.body.classList.toggle('no-fx', device === 'calm');
  localStorage.setItem('v3_lite', device === 'mid' ? '1' : '0');
  localStorage.setItem('v3_low', device === 'low' ? '1' : '0');
  _V3_FX.frozen = true;
  v3ApplyLook(look);
  applySkinTier({tier}, {force: device === 'high'});
  _v3Skew = Date.now() - Date.UTC(2026, 9, 30, 12);
  _v3SkewKnown = true;
  _v3ServerTz = 0;
  const ap = apFromLook(look);
  const data = {...labFixture, look};
  if (mode === 'profile') {
    // Production profile, cropped to its first stage; no hand-written replacement hero.
    const template = document.createElement('template');
    template.innerHTML = renderProfileHome(data);
    const stage = template.content.querySelector('.ap-stage');
    if (!stage) throw new Error('Production profile stage missing');
    labRoot.innerHTML = '<div id="pg-profile" class="page active"><div id="pro-main"></div></div>';
    document.getElementById('pro-main').append(stage);
  } else if (mode === 'nick') {
    labRoot.innerHTML = `<div class="lab-nick"><div class="v3-name">${apName(ap, esc(data.display_name))}</div>${apTitle(ap)}</div>`;
  } else if (mode === 'top') {
    const row = {place: 4, name: data.display_name, look, ref: 'skin_review_player_ref', level: 12,
      is_me: false, is_vip: true, count: 840};
    labRoot.innerHTML = `<ol class="v3-top-list">${_v3FullRow(row, 'global')}</ol>`;
  } else if (mode === 'telegram') {
    labRoot.innerHTML = `<img class="lab-card" src="cards/${skin}-${tier}.webp" alt="Тестовая карточка Telegram">`;
  } else throw new Error('Unknown preview mode');
  const sceneArtReady = await labAssetsReady();
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const rare = {peek: .89, flash: .915, cross: .5, sweep: .14, rise: .35, ripple: .3, twinkle: .5};
  for (const animation of document.getAnimations()) {
    animation.pause();
    const timing = animation.effect.getComputedTiming();
    const target = animation.effect.target;
    const key = phase === 'rare' && Object.keys(rare).find(name => target?.classList?.contains(name));
    // Finish entry animations; only repeating cosmetic motion is sampled mid-cycle.
    animation.currentTime = Number.isFinite(timing.iterations)
      ? timing.endTime + 1
      : (timing.delay || 0) + timing.duration * (key ? rare[key] : .37);
  }
  _v3FxFrame(9000);
  await new Promise(resolve => requestAnimationFrame(resolve));
  if (generation !== labRendering) return;
  window.LAB_STATE = {skin, tier, mode, device, phase,
    font: document.fonts.check('16px Onest'), classes: document.body.className,
    reduced_motion:matchMedia('(prefers-reduced-motion: reduce)').matches, calm:document.body.classList.contains('no-fx'),
    device_cap: _v3DeviceCap(), fx_level: v3FxLevelNow(),
    scene: _AP_SCENES.get(skin) || [], animations: document.getAnimations().length,
    scene_art_ready:sceneArtReady, nodes: labRoot.querySelectorAll('*').length};
  document.documentElement.dataset.ready = 'yes';
}

function labFromHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  return labRender(Object.fromEntries(params)).catch(error => {
    labRoot.textContent = `Не удалось открыть образ: ${error.message}`;
    document.documentElement.dataset.ready = 'error';
    throw error;
  });
}
addEventListener('hashchange', labFromHash);
addEventListener('message', event => {
  if (event.source !== parent) return;
  if (event.data?.type === 'lab-play') {
    document.documentElement.dataset.live = 'yes';
    _V3_FX.frozen = false;
    _v3FxRun();
    document.getAnimations().forEach(animation => animation.play());
  }
  if (event.data?.type === 'lab-pause') labFromHash();
});
if (location.hash) labFromHash();
