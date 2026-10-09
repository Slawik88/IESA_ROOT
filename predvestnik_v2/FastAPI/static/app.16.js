// ── Shell V3 · постоянная панель, «Дальше», печать VIP, путь по аспектам ─────────
function _v3Wallet(d) { return (d && typeof d.balances === 'object' && d.balances) ? d.balances : (d || {}); }
function _v3Short(n, from = 1e4) {
  const v = Number(n) || 0;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1).replace('.', ',').replace(',0', '')}М`;
  if (v >= from) return `${(v / 1e3).toFixed(1).replace('.', ',').replace(',0', '')}к`;
  return fmt(Math.round(v));
}
// Цифры валют не должны теряться. Не влезает ряд: сначала чипы уплотняются (fit-1, затем fit-2), и только если и так не помещается,
// край ряда затухает и ряд прокручивается; Зарники закреплены справа
function v3ChipsFade() {
  const bar = el('v3-bar'), main = el('v3-chips-main'); if (!bar || !main) return;
  const over = () => main.scrollWidth > main.clientWidth + 1;
  if (bar.classList.contains('fit-3')) _v3BarNumbers(false);
  bar.classList.remove('fit-1', 'fit-2', 'fit-3');
  if (over()) {
    bar.classList.add('fit-1');
    if (over()) { bar.classList.add('fit-2'); if (over()) { bar.classList.add('fit-3'); _v3BarNumbers(true); } }   // fit-3: суммы от тысячи сокращаются
  }
  main.classList.toggle('has-more', over());
}
// Суммы в панели; compact сокращает уже от тысячи («2,6к»), обычный вид только от десяти тысяч
let _v3BarVals = null, _v3BarFirstAt = 0;
function _v3BarNumbers(compact) {
  const v = _v3BarVals; if (!v) return;
  const set = (id, value) => { const node = el(id); if (node) node.textContent = _v3Short(value, compact ? 1e3 : 1e4); };
  set('vb-mora', v.mora); set('vb-dia', v.diamonds); set('vb-ess', v.essence); set('vb-zar', v.zarniki);   // порядок как на экране: Мора, Алмазы, остальные, Зарники
}
window.addEventListener('resize', v3ChipsFade);
document.fonts?.ready?.then(v3ChipsFade);   // шрифт приходит позже первой отрисовки и меняет ширину цифр
// Панель не зависит от вкладки: игрок всегда видит свой уровень, ресурсы и «Что нового»
function renderV3Bar(d) {
  const bar = el('v3-bar'); if (!bar || !d) return;
  const wallet = _v3Wallet(d), level = Math.max(1, Number(d.account_level) || 1);
  const need = Number(d.xp_to_next) > 0 ? Number(d.xp_to_next) : 0, xp = Math.max(0, Number(d.xp_into) || 0);
  const me = el('v3-bar-me');
  if (me) {
    me.innerHTML = `${_v3Ring(need ? xp / need * 100 : 100)}<span class="v3-bar-lv">${level}</span>`;
    me.classList.toggle('is-vip', !!d.vip);
  }
  const was = _v3BarVals;
  _v3BarVals = { mora: wallet.mora, diamonds: wallet.diamonds, essence: d.essence, zarniki: wallet.zarniki };
  _v3BarNumbers(false);
  v3ChipsFade();
  if (!was) _v3BarFirstAt = Date.now(); else if (typeof v3BalanceFx === 'function') v3BalanceFx(was, _v3BarVals, _v3BarFirstAt);   // пульс числа и «+N» под чипом (app.31.js)
  bar.classList.add('is-ready');
}

// Печать VIP: кольцо показывает остаток срока (до 30 дней = полный круг), аура вокруг аватара задаётся CSS
function _v3VipSeal(vip) {
  if (!vip) return '';
  const days = Math.max(0, Number(vip.days_left) || 0), share = Math.min(1, days / 30);
  const ring = `<svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="11" class="v3-seal-track"/><circle cx="14" cy="14" r="11" class="v3-seal-arc" stroke-dasharray="69.1" stroke-dashoffset="${(69.1 * (1 - share)).toFixed(1)}"/><path d="M8.5 17.5l1.4-6 2.6 3 1.5-4.2 1.5 4.2 2.6-3 1.4 6z" class="v3-seal-crown"/></svg>`;
  const until = vip.expires_at ? ` · до ${_profileDate(vip.expires_at)}` : '';
  return `<button type="button" class="v3-seal" onclick="openStoreV3('vip')" aria-label="VIP активен, осталось ${fmt(days)} дн. Открыть VIP">${ring}<span><b>VIP</b> ещё ${fmt(days)} дн.${until}</span></button>`;
}

// «Дальше»: одно понятное действие вместо выбора из списка
function _v3QuestRoute(metric) {
  const m = String(metric || ''), on = key => typeof _sysFlags !== 'undefined' && _sysFlags[key] === true;
  if (m.startsWith('rhythm_') && on('game_rhythm_v2')) return 'openRhythmV2Game()';
  if (m.startsWith('minesweeper_') && on('game_minesweeper_v2')) return 'openMinesweeperGame()';
  if (m === 'chest_revealed') return 'openChestsV1()';
  if (m === 'pet_fed' || m === 'pet_activity_completed') return 'openPetsV1()';
  return "openQuestsV1()";
}
function renderV3Next() {
  const host = el('v3-next'); if (!host) return;
  const quests = _v3Quests?.daily?.quests || [], items = _v3Quests?.rewards?.items || {};
  const ready = ['daily', 'weekly', 'combined'].find(kind => items[kind]?.claimable);
  const todo = quests.find(q => !q.completed);
  let title, hint, action;
  if (ready) { title = 'Заберите награду'; hint = `+${fmt(items[ready].amount_mora || 0)} Моры${items[ready].amount_essence ? ` и +${fmt(items[ready].amount_essence)} Эссенции` : ''} уже ждут`; action = `v3ClaimQuestReward('${ready}')`; }
  else if (todo) {
    const target = Math.max(1, Number(todo.target) || 1);
    title = todo.title; hint = `${Math.min(target, Number(todo.progress) || 0)} из ${target} · ${quests.filter(q => q.completed).length} из ${quests.length} заданий за день`;
    action = _v3QuestRoute(todo.metric);
  } else if (quests.length) { title = 'На сегодня всё выполнено'; hint = _v3Tip(); action = 'openLooksModal()'; }
  else { title = 'Откройте «Игры»'; hint = 'Задания на сегодня появятся позже'; action = "switchPage('arena')"; }
  const attrs = ready ? ` id="v3-claim" data-kind="${_profileEsc(ready)}" ${_v3Claiming ? 'disabled aria-busy="true"' : ''}` : '';
  if (ready) action = 'v3ClaimQuestReward(this.dataset.kind)';
  host.innerHTML = `<button type="button" class="v3-next"${attrs} onclick="${action}"><span class="v3-next-go" aria-hidden="true">${_v3Icon('chev')}</span>
    <span class="v3-next-t"><span class="v3-eyebrow">Дальше</span><b>${_profileEsc(title)}</b><small>${_profileEsc(hint)}</small></span></button>`;
}

// «Путь»: пять аспектов игры одной строкой, без списка
let _v3Path = null;
function _v3PathShell() {
  return `<section class="v3-path" id="v3-path" aria-label="Прогресс по аспектам игры"><div class="v3-sec"><span class="v3-eyebrow">Путь</span><button type="button" class="v3-link" onclick="openAchievementsV1()">Достижения</button></div><div class="v3-path-row"><div class="sk" style="height:76px;border-radius:14px;flex:1"></div></div></section>`;
}
function loadV3Path() {
  return api('/achievements-v1/me').then(d => { _v3Path = d; renderV3Path(); }).catch(() => renderV3Path(true));
}
function renderV3Path(failed) {
  const host = el('v3-path'); if (!host) return;
  const head = '<div class="v3-sec"><span class="v3-eyebrow">Путь</span><button type="button" class="v3-link" onclick="openAchievementsV1()">Достижения</button></div>';
  const families = _v3Path?.families || [];
  if (failed || !families.length) { host.innerHTML = `${head}<div class="v3-empty">${failed ? 'Прогресс не загрузился. <button type="button" class="v3-link" onclick="loadV3Path()">Повторить</button>' : 'Сыграйте разок, и здесь вспыхнут первые кольца.'}</div>`; return; }
  host.innerHTML = `${head}<div class="v3-path-row">${families.map(f => {
    const max = Math.max(1, Number(f.max_level) || 40), level = Math.min(max, Number(f.level) || 0);
    return `<button type="button" class="v3-aspect" onclick="openAchievementsV1()" aria-label="${_profileEsc(f.title)}: уровень ${level} из ${max}">
      <span class="v3-aspect-ring">${_v3Ring(level / max * 100)}<b>${level}</b></span><span>${_profileEsc(f.title)}</span></button>`;
  }).join('')}</div>`;
}

// ── Профиль открывается мгновенно: последний ответ показывается сразу, свежий заменяет его ─────────────
// Осторожно: loadProfile() вызывается при загрузке app.02.js, раньше этого файла, поэтому
// v3PaintCachedProfile запускается через setTimeout(0): const верхнего уровня к тому времени уже инициализированы.
let _v3LastSync = Date.now();
function _v3ProfileKey() { return 'pv_profile_v3'; }
function _v3ProfileFields() { return ['user_id', 'username', 'display_name', 'rank', 'account_level', 'xp_into', 'xp_to_next', 'mora', 'diamonds', 'zarniki', 'streak', 'achievements', 'messages_all_time', 'is_vip', 'vip']; }
function v3SaveProfileCache(d) {
  try {
    const slim = {}; _v3ProfileFields().forEach(key => { if (d[key] !== undefined) slim[key] = d[key]; });
    slim.look = d.look || null;
    localStorage.setItem(_v3ProfileKey(), JSON.stringify(slim));
  } catch (_) { /* хранилище недоступно: профиль просто загрузится как обычно */ }
}
function v3ProfileSkeleton() {
  const bar = (w, h = 14) => `<div class="sk" style="height:${h}px;width:${w};border-radius:${h / 2}px"></div>`;
  return `<div class="v3-id" aria-hidden="true"><div class="sk" style="width:76px;height:76px;border-radius:50%;flex:none"></div><div style="flex:1;display:grid;gap:10px">${bar('50%', 22)}${bar('70%')}${bar('40%')}</div></div>
    <div class="sk" style="height:76px;border-radius:14px;margin-top:22px"></div>
    <div class="sk" style="height:150px;border-radius:14px;margin-top:22px"></div>
    <div class="sk" style="height:84px;border-radius:14px;margin-top:22px"></div>`;
}
// true, если показан кэш; иначе вызывающий рисует скелет
function v3PaintCachedProfile() {
  const host = el('pro-main'); if (!host || _profileData) return false;
  try {
    const cached = JSON.parse(localStorage.getItem(_v3ProfileKey()) || 'null');
    const me = tg?.initDataUnsafe?.user?.id;
    if (!cached || !me || Number(cached.user_id) !== Number(me)) { host.innerHTML = v3ProfileSkeleton(); return false; }
    if (typeof v3ApplyLook === 'function') v3ApplyLook(cached.look);
    host.innerHTML = renderProfileHome(cached); if(typeof v3EnterSync==='function')v3EnterSync(host); v3CountUp(host); renderV3Bar(cached); host.dataset.stale = '1';
    return true;
  } catch (_) { host.innerHTML = v3ProfileSkeleton(); return false; }
}
// Вернулся в приложение через минуту и дольше: тихо обновляем «Сегодня» и баланс
document.addEventListener('visibilitychange', () => {
  if (document.hidden || Date.now() - _v3LastSync < 60000) return;
  if (_activePage !== 'profile' || !_profileData) return;
  _v3LastSync = Date.now(); loadV3Today(); _v3RefreshBalance();
});

// Подсказки, когда задания закончились: живая польза вместо пустоты (меняются день ото дня)
function _v3Tip() {
  const tips = ['Эссенция уже капнула: загляните в «Образы» и прокачайте скин', 'Соберите сет скинов: за него положен бонус Эссенции', 'Те же рейтинги видны в чате по команде «бот топ»', 'Питомцам тоже приятно внимание: загляните к ним', 'Завтра будут новые задания, а сегодня можно сыграть для души'];
  return tips[Math.floor(Date.now() / 864e5) % tips.length];
}
