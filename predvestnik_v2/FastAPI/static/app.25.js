// ── Мелочи, от которых приятно ───────────────────────────────────────────────────
// Приветствие по времени игрока (если часы устройства сбиты, берётся время бота; в годовщину и после долгого отсутствия оно меняется),
// счёт чисел при открытии, поздравления с уровнем и серией, пасхалка.
const _V3_LS = { visit: 'pv_last_visit', level: 'pv_last_level', streak: 'pv_streak_step', anniv: 'pv_anniv_seen', counts: 'pv_counts_v3' };
const _lsGet = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
const _lsSet = (key, value) => { try { localStorage.setItem(key, value); } catch (_) { /* приватный режим: просто без памяти */ } };
let _v3Skew = 0, _v3ServerTz = 180, _v3SkewKnown = false, _v3Gap = null;
const _v3Plural = (n, one, few, many) => { const m = Math.abs(n) % 100, d = m % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };

// Часы бота (UTC+3 по умолчанию) нужны как запасной вариант, если часы на устройстве явно врут
function v3NoteServerClock(clock) {
  const server = clock?.iso ? Date.parse(clock.iso) : NaN;
  if (Number.isNaN(server)) return;
  _v3Skew = server - Date.now(); _v3ServerTz = Number.isFinite(clock.offset_min) ? clock.offset_min : 180; _v3SkewKnown = true;
}
function v3Hour() {
  const device = new Date(), broken = Number.isNaN(device.getTime()) || device.getFullYear() < 2024 || (_v3SkewKnown && Math.abs(_v3Skew) > 36 * 3600e3);
  if (!broken || !_v3SkewKnown) return device.getHours();
  return new Date(Date.now() + _v3Skew + _v3ServerTz * 60e3).getUTCHours();
}
function _v3Hello() {
  const h = v3Hour();
  return h >= 23 || h < 2 ? 'Доброй ночи' : h < 5 ? 'Не спится? Доброй ночи' : h < 12 ? 'Доброе утро' : h < 18 ? 'Добрый день' : 'Добрый вечер';
}
// Приветствие подводит к имени, которое стоит строкой ниже: «Добрый день, <ник>». Серия не вставляется в приветствие: она есть в показателях
// под шапкой и в поздравлении на рубеже, а «приветствие + цифра» читается как галочка. Исключения: годовщина и возвращение, это слова человеку.
function _v3GreetLead(d) {
  const joined = d?.joined_date ? new Date(d.joined_date) : null, now = new Date();
  if (joined && !Number.isNaN(joined.getTime()) && joined.getMonth() === now.getMonth() && joined.getDate() === now.getDate() && now.getFullYear() > joined.getFullYear()) {
    const years = now.getFullYear() - joined.getFullYear();
    return `Сегодня ${years} ${_v3Plural(years, 'год', 'года', 'лет')} с нами`;
  }
  if (_v3Gap != null && _v3Gap >= 3) return 'С возвращением';
  return _v3Hello();
}
function v3GreetHtml(d) { return `${_profileEsc(_v3GreetLead(d))},`; }

// Сколько осталось до обновления заданий (период считается по UTC)
function v3UntilReset() {
  const now = new Date(), next = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1), mins = Math.max(1, Math.round((next - now.getTime()) / 60000));
  return mins >= 60 ? `${Math.floor(mins / 60)} ч${mins % 60 >= 5 && mins < 600 ? ` ${mins % 60} мин` : ''}` : `${mins} мин`;
}

// Числа не прыгают, а набегают: от того, что игрок видел раньше, до нового значения
function v3CountUp(root) {
  const calm = typeof _v3Calm === 'function' ? _v3Calm() : false, prevAll = JSON.parse(_lsGet(_V3_LS.counts) || '{}'), seen = {};
  root.querySelectorAll('[data-n]').forEach(node => {
    const key = node.dataset.key, to = Number(node.dataset.n) || 0, from = Number(prevAll[key]) || 0, short = node.dataset.f === 'short';
    seen[key] = to;
    const draw = value => { node.textContent = short ? _v3Short(Math.round(value)) : fmt(Math.round(value)); };
    if (calm || from === to || Math.abs(to - from) < 1) { draw(to); return; }
    const t0 = performance.now(), span = Math.min(900, 380 + Math.abs(to - from) / Math.max(1, to) * 700);
    const tick = now => { const k = Math.min(1, (now - t0) / span), ease = 1 - Math.pow(1 - k, 3); draw(from + (to - from) * ease); if (k < 1 && node.isConnected) requestAnimationFrame(tick); else draw(to); };
    requestAnimationFrame(tick);
  });
  if (typeof v3RingIn === 'function') v3RingIn(root, prevAll, seen);
  _lsSet(_V3_LS.counts, JSON.stringify({ ...prevAll, ...seen }));
}

// Один раз за запуск: возвращение, новый уровень, серия, годовщина, новые регалии
const _V3_STREAK_STEPS = [3, 7, 14, 30, 50, 100, 200, 365];
function v3Delights(d) {
  const today = new Date().toISOString().slice(0, 10), level = Number(d.account_level) || 1, streak = Number(d.streak) || 0;
  const prevLevel = Number(_lsGet(_V3_LS.level)) || 0;
  if (prevLevel && level > prevLevel) { setTimeout(() => { toast(`Новый уровень: ${level}`); v3Reward(el('pro-showcase-ava')); v3GrowStar(prevLevel, level); }, 700); }
  _lsSet(_V3_LS.level, String(level));
  const step = _V3_STREAK_STEPS.filter(n => streak >= n).pop() || 0, done = Number(_lsGet(_V3_LS.streak)) || 0;
  if (step > done) setTimeout(() => { toast(`${streak} ${_v3Plural(streak, 'день', 'дня', 'дней')} подряд. Спасибо, что вы с нами`); v3Reward(el('pro-showcase-ava')); }, 1300);
  if (step !== done) _lsSet(_V3_LS.streak, String(step));   // серия сорвалась: праздник снова станет доступен
  if (typeof v3MarksNotice === 'function') setTimeout(() => v3MarksNotice(d.marks), 3200);   // после поздравлений: тост один и заменяет предыдущий
  const joined = d.joined_date ? new Date(d.joined_date) : null, now = new Date();
  if (joined && joined.getMonth() === now.getMonth() && joined.getDate() === now.getDate() && now.getFullYear() > joined.getFullYear() && _lsGet(_V3_LS.anniv) !== today) {
    _lsSet(_V3_LS.anniv, today); setTimeout(() => v3Reward(el('pro-showcase-ava')), 1000);
  }
}
// Время с последнего визита считается один раз за запуск, дальше строка не меняется
(function noteVisit() {
  const last = Number(_lsGet(_V3_LS.visit)) || 0;
  _v3Gap = last ? Math.floor((Date.now() - last) / 864e5) : null;
  _lsSet(_V3_LS.visit, String(Date.now()));
})();

// Пасхалка: семь касаний по аватару за две секунды
let _v3Taps = [];
document.addEventListener('click', e => {
  const ava = e.target.closest('#pro-showcase-ava'); if (!ava) return;
  const now = Date.now(); _v3Taps = _v3Taps.filter(t => now - t < 2000); _v3Taps.push(now);
  const rect = ava.getBoundingClientRect(); _haptic('light');
  if (_v3Taps.length >= 7) { _v3Taps = []; v3Reward(ava); toast('Вы нашли секрет: Эхо шлёт вам привет'); }
  else if (_v3Taps.length >= 3 && typeof v3Reward === 'function') v3Reward({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
}, true);
