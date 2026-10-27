// Local, bounded technical history. Uploaded only when the player sends a report.
(() => {
  'use strict';
  if (window.PVDiagnostics) return;
  const script = document.currentScript, scriptURL = new URL(script.src, location.href);
  const base = scriptURL.pathname.replace(/\/static\/support-diagnostics\.js$/, '');
  const version = scriptURL.searchParams.get('v') || '';
  const WINDOW = 3600000, MAX_EVENTS = 3000, MAX_BYTES = 600000, WRITE_DELAY = 15000;
  const nativeFetch = window.fetch.bind(window);
  const words = new Set(('profile me avatar mafia-online mafia-v1 minesweeper-v2 rhythm-v2 league-v1 api hub leaderboard leaderboards top stats rooms room match matches state action actions chat messages history settings join leave start stop ready vote send read players seats table events account restore deleted skins-v3 appearance cosmetics marks-v1 pets-v1 pets-v2 inventory-v1 inventory shop-v1 gifts-v2 payments wallet vip analytics presence-v1 notifications quests-v1 achievements-v1 chests-v1 season-pass star-dust player-exchange-v1 coin-market-v2 purge-v1 public-profile-v3 public u easy normal hard casual ranked status sync daily home games more help looks family pass').split(' '));
  const allowedText = new Set(['method','route','request_id','error_kind','page','state','source','stage','outcome']);
  const allowedNumbers = new Set(['status','duration_ms','line','column','code','count']);
  const allowedBools = new Set(['vip','has_avatar','photo_available','cached']);
  let bound = null, owner = '', events = [], dropped = 0, started = Date.now(), writeTimer = null, storageAvailable = true;
  const safeText = (value, max = 120) => String(value || '').slice(0,2048)
    .replace(/(?:\b\d{5,}:[\w-]{12,}|\bBearer\s+\S+|\beyJ[\w.-]{20,}|(?:tgWebAppData|initData|x-init-data|x-session-token|authorization|password|token)\s*[=:]\s*\S+)/gi,'[скрыто]')
    .replace(/(?:https?|wss?):\/\/[^\s<>"']+/gi,'[ссылка]').replace(/[\u0000-\u0008\u000b-\u001f]/g,'').slice(0,max);
  function routeName(value) {
    try {
      const url = new URL(value, location.href);
      if (url.origin !== location.origin) return '/external';
      const path = url.pathname.startsWith(base + '/') ? url.pathname.slice(base.length) : url.pathname;
      return '/' + path.split('/').filter(Boolean).slice(0,8).map(p => words.has(p) || /^\{[a-z_]{1,40}\}$/.test(p) ? p : ':value').join('/');
    } catch (_) { return '/unknown'; }
  }
  function authState() {
    const tg = window.Telegram?.WebApp;
    let session = '';
    try { session = localStorage.getItem('pv_sess') || ''; } catch (_) {}
    const key = `${tg?.initData || ''}|${session}`;
    const explicit = String((tg?.initData ? tg?.initDataUnsafe?.user?.id : 0) || (/^(\d+):/.exec(session) || [])[1] || '');
    return {key, owner:explicit || (bound?.key === key ? bound.owner : '')};
  }
  const storageKey = id => `pv_support_history_v1:${id}`;
  function trim() {
    const since = Date.now()-WINDOW;
    events = events.filter(e => e && Number.isFinite(e.at) && e.at >= since && e.at <= Date.now()+60000);
    if (events.length > MAX_EVENTS) { dropped += events.length-MAX_EVENTS; events = events.slice(-MAX_EVENTS); }
    while (JSON.stringify(events).length > MAX_BYTES && events.length) { events.shift(); dropped++; }
  }
  function flush() {
    clearTimeout(writeTimer); writeTimer = null;
    trim();
    if (!owner) return;
    try { localStorage.setItem(storageKey(owner),JSON.stringify({events,dropped,started})); }
    catch (_) { storageAvailable = false; }
  }
  function bind() {
    const next = authState().owner;
    if (next === owner) return;
    flush();
    // Anonymous events have no bodies or identities and stay in this tab only.
    const anonymous = owner ? [] : events;
    owner = next; events = []; dropped = 0; started = Date.now();
    window.dispatchEvent(new Event('pv-support-account'));
    if (owner) {
      try {
        const raw = localStorage.getItem(storageKey(owner));
        if (raw && raw.length <= MAX_BYTES+10000) {
          const old = JSON.parse(raw);
          if (Array.isArray(old.events)) events = old.events;
          dropped = Number(old.dropped)||0; started = Number(old.started)||started;
        }
      } catch (_) { storageAvailable = false; }
      events.push(...anonymous); trim();
    }
  }
  function clean(data) {
    const out = {};
    for (const [k,v] of Object.entries(data || {})) {
      if (allowedText.has(k) && typeof v === 'string') out[k] = k === 'route' || k === 'page' ? routeName(v) : safeText(v);
      if (allowedNumbers.has(k) && Number.isFinite(v) && Math.abs(v) <= 1e8) out[k] = v;
      if (allowedBools.has(k) && typeof v === 'boolean') out[k] = v;
    }
    if (Array.isArray(data?.frames)) out.frames = data.frames.filter(v => /^[\w.-]{1,80}:\d{1,8}:\d{1,8}$/.test(v)).slice(0,8);
    return out;
  }
  function record(kind, data) {
    try {
      bind(); events.push({at:Date.now(),kind,data:clean(data)}); trim();
      if (!writeTimer) writeTimer = setTimeout(flush,WRITE_DELAY);
    } catch (_) { /* diagnostics must not break gameplay */ }
  }
  function issue() { window.dispatchEvent(new Event('pv-support-issue')); }
  function errorData(error, file, line, column) {
    const name = error?.name || 'Error';
    const frames = [...String(error?.stack || '').matchAll(/(?:https?:\/\/[^\s)]+\/)?([A-Za-z0-9_.-]{1,80}\.js)(?:\?[^\s):]*)?:(\d+):(\d+)/g)].slice(0,8).map(m => `${m[1]}:${m[2]}:${m[3]}`);
    if (file) { const part = String(file).split('?')[0].split('/').pop(); if (/^[\w.-]{1,80}$/.test(part)) frames.unshift(`${part}:${Number(line)||0}:${Number(column)||0}`); }
    return {error_kind:/^[A-Za-z]{1,40}$/.test(name)?name:'Error',frames:frames.slice(0,8),line:Number(line)||0,column:Number(column)||0};
  }
  window.fetch = async function(input, init) {
    let url;
    try { url = new URL(input instanceof Request ? input.url : input,location.href); } catch (_) { return nativeFetch(input,init); }
    const relative = url.pathname.startsWith(base + '/') ? url.pathname.slice(base.length) : url.pathname;
    if (url.origin !== location.origin || relative.startsWith('/support/') || relative.startsWith('/bot-admin/') || relative.startsWith('/static/')) return nativeFetch(input,init);
    const began = performance.now(), auth = authState(), method = String(init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    try {
      const response = await nativeFetch(input,init);
      if (auth.key !== authState().key) return response;
      const verified = response.headers.get('x-support-owner');
      if (verified && auth.owner && auth.owner !== verified) {
        record('lifecycle',{state:'auth_mismatch'}); issue(); return response;
      }
      if (verified && /^\d+$/.test(verified) && (!auth.owner || auth.owner === verified)) bound = {owner:verified,key:auth.key};
      record('request',{route:response.headers.get('x-diagnostic-route')||relative,method,status:response.status,
                        duration_ms:Math.round(performance.now()-began),request_id:response.headers.get('x-request-id')||''});
      if (response.status >= 500 || response.status === 401) issue();
      // Only these booleans are read from JSON. Names, photos, messages and bodies are never retained.
      if (response.ok && ['/profile/avatar','/profile/me'].includes(relative)) {
        response.clone().json().then(data => {
          if (auth.key === authState().key) record('avatar',{vip:!!(data.vip === true || data.is_vip),has_avatar:!!data.avatar,stage:'received'});
        }).catch(() => {});
      }
      return response;
    } catch (error) {
      if (auth.key === authState().key) {
        record('request',{route:relative,method,status:0,duration_ms:Math.round(performance.now()-began),error_kind:error?.name || 'NetworkError'});
        if (error?.name !== 'AbortError') issue();
      }
      throw error;
    }
  };
  window.addEventListener('error',event => {
    if (event.target !== window) { record('resource',{error_kind:'ResourceError',source:event.target?.tagName || 'resource'}); if (['SCRIPT','LINK'].includes(event.target?.tagName)) issue(); return; }
    record('runtime',errorData(event.error,event.filename,event.lineno,event.colno)); issue();
  },true);
  window.addEventListener('unhandledrejection',event => { record('runtime',errorData(event.reason)); issue(); });
  for (const name of ['online','offline','pageshow','pagehide']) window.addEventListener(name,() => { record(name === 'online' || name === 'offline' ? 'connection' : 'lifecycle',{state:name}); if (name === 'pagehide') flush(); });
  document.addEventListener('visibilitychange',() => { record('lifecycle',{state:document.visibilityState}); if (document.hidden) flush(); });
  document.addEventListener('click',event => {
    const target = event.target.closest?.('[data-page],[data-nav-key],[data-tab]');
    const value = target?.dataset.page || target?.dataset.navKey || target?.dataset.tab;
    if (value && /^[a-z-]{1,32}$/.test(value)) record('navigation',{page:`/${value}`});
  },true);
  function credentials() {
    const h = {'Content-Type':'application/json'};
    const tg = window.Telegram?.WebApp;
    if (tg?.initData) h['x-init-data'] = tg.initData;
    try {
      const session = localStorage.getItem('pv_sess');
      if (session && !tg?.initData) h['x-session-token'] = session;
      if (location.hostname === '127.0.0.1' && location.port === '8403') {
        const ticket = sessionStorage.getItem('pv_preprod_ticket');
        if (ticket) h['x-preprod-browser-ticket'] = ticket;
      }
    } catch (_) {}
    return h;
  }
  async function environment() {
    const tg = window.Telegram?.WebApp, connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    let tz = '', region = '';
    try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; region = new Intl.Locale(navigator.language).region || ''; } catch (_) {}
    const env = {user_agent:safeText(navigator.userAgent,512),platform:safeText(navigator.platform),language:navigator.language,
      languages:(navigator.languages||[]).join(', '),locale_region:region,timezone:tz,timezone_offset:new Date().getTimezoneOffset(),
      telegram_platform:tg?.platform||'unknown',telegram_api_version:tg?.version||'',tg_photo_available:!!(tg?.initData && tg?.initDataUnsafe?.user?.photo_url),
      color_scheme:tg?.colorScheme||'',app_version:version,page:routeName(location.href),screen_width:screen.width,screen_height:screen.height,
      viewport_width:Math.round(window.visualViewport?.width||innerWidth),viewport_height:Math.round(window.visualViewport?.height||innerHeight),
      pixel_ratio:devicePixelRatio,touch_points:navigator.maxTouchPoints||0,cpu_threads:navigator.hardwareConcurrency,
      device_memory_gb:navigator.deviceMemory,online:navigator.onLine,save_data:!!connection?.saveData,
      rtt_ms:connection?.rtt,downlink_mbps:connection?.downlink,connection_type:connection?.effectiveType||'',
      reduced_motion:!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,no_fx:document.body?.classList.contains('no-fx')||false,
      fullscreen:!!tg?.isFullscreen,secure_context:window.isSecureContext,storage_available:storageAvailable,
      service_worker:!!navigator.serviceWorker?.controller?'controlled':'none',orientation:screen.orientation?.type||'',capture_started:new Date(Math.max(started,Date.now()-WINDOW)).toISOString()};
    try {
      const hints = navigator.userAgentData;
      if (hints) {
        env.mobile = !!hints.mobile; env.platform = hints.platform || env.platform;
        const high = await Promise.race([hints.getHighEntropyValues?.(['model','platformVersion','architecture','uaFullVersion'])||{},new Promise(resolve => setTimeout(() => resolve({}),700))]);
        env.model = safeText(high.model); env.os_version = safeText(high.platformVersion); env.architecture = safeText(high.architecture); env.browser_version = safeText(high.uaFullVersion);
      }
    } catch (_) {}
    return env;
  }
  async function snapshot() { const env = await environment(); bind(); trim(); return {captured_at:Date.now(),environment:env,events:events.map(e => ({at:e.at,kind:e.kind,data:clean(e.data)})),dropped_events:dropped}; }
  window.PVDiagnostics = {record,snapshot,owner:() => { bind(); return owner; },credentials,nativeFetch,base,version,safeText,flush};
  setInterval(() => { if (events.length && events[0].at < Date.now()-WINDOW) flush(); },60000);
  record('lifecycle',{state:'open',page:routeName(location.href)});
})();
