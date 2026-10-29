// ── Живые обновления админки (S10) ──────────────────────────────────────────
// Тот же сокет, что у Mini App (/ws/<id>): значок «Жалобы» перечитывается сразу, как жалоба пришла или её закрыли
// (data_changed{scope:'admin_reports'}), ход «Чистки» — как только он изменился (scope:'purge'). Опрос раз в минуту
// остаётся запасным (admin-boot.js). Без сокета (браузер без входа, сбой) всё работает как раньше.
// Загружается после admin.js и до admin-boot.js.

const LIVE = {ws: null, tries: 0, timer: 0};

function liveConnect() {
  if (LIVE.ws || !ME || !ME.user_id || typeof WebSocket === 'undefined') return;
  let token = '';
  try { token = localStorage.getItem('pv_sess') || ''; } catch (_) {}
  if (!INIT && !token) return;
  let ws;
  try { ws = new WebSocket(`${(BASE || location.origin).replace(/^http/, 'ws')}/ws/${ME.user_id}`); } catch (_) { return; }
  LIVE.ws = ws;
  // Вход — первым сообщением, не в адресе: адреса попадают в журналы прокси.
  ws.onopen = () => { LIVE.tries = 0; try { ws.send(JSON.stringify(INIT ? {type: 'auth', init: INIT} : {type: 'auth', token})); } catch (_) {} };
  ws.onmessage = ev => {
    let event; try { event = JSON.parse(ev.data); } catch (_) { return; }
    if (!event || event.type !== 'data_changed') return;
    if (event.scope === 'admin_reports') refreshBadges();
    else if (event.scope === 'purge' && typeof purgeLive === 'function') purgeLive(event);
  };
  ws.onclose = ev => {
    if (LIVE.ws === ws) LIVE.ws = null;
    clearTimeout(LIVE.timer);
    if (ev && ev.code === 1008) return;   // вход не принят: не стучимся по кругу
    LIVE.timer = setTimeout(() => { if (!document.hidden) liveConnect(); }, Math.min(60000, 2000 * 2 ** Math.min(LIVE.tries++, 5)));
  };
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
}
setInterval(() => { if (LIVE.ws && LIVE.ws.readyState === 1) { try { LIVE.ws.send('ping'); } catch (_) {} } }, 25000);   // прокси рвут молчащие соединения
document.addEventListener('visibilitychange', () => { if (!document.hidden && !LIVE.ws) liveConnect(); });

// «Забанить во всех чатах» идёт в фоне: «N из M» обновляется, пока задание не закончится, итог — в той же полосе.
async function globalProgress(uid, job, title) {
  let host = $('#undobar');
  if (!host) { host = document.createElement('div'); host.id = 'undobar'; host.className = 'undobar'; host.setAttribute('role', 'status'); document.body.append(host); }
  const row = document.createElement('div'); row.className = 'undo progress';
  host.append(row);
  const draw = j => { row.innerHTML = `<span>${esc(title)}: <b>${num(j.done)} из ${num(j.total)}</b>${j.failed ? ` · не вышло ${num(j.failed)}` : ''}${j.finished ? ' · готово' : ''}</span>`; };
  draw(job);
  for (let i = 0; i < 400 && !job.finished; i++) {
    await new Promise(r => setTimeout(r, 1500));
    try {
      const now = await api(`/player/${uid}/global-progress`);
      job = (job.kind === 'global_unban' ? now.unban : now.ban) || job;
    } catch (_) { break; }
    draw(job);
  }
  setTimeout(() => row.remove(), 6000);
}
