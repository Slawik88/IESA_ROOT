// ── Путеводитель администрации: тот же экран, что Путеводитель игрока (app.57.js), слоем поверх админки ──
// Слой — страница bot-admin/guide (guide.html + guide-host.js) в рамке: экран и стили приходят из Mini App без копий,
// а админка под слоем остаётся как была — открытая карточка, недописанное окно, отсчёт «Отменить» не прерываются.
// Входы: вкладка «Путеводитель» (в доке или «Ещё»), значок «?» в шапке — тема раздела, где ты сейчас, «Что это значит?»
// в окне опасного действия, ссылка из бота (?open=guide, startapp=admin_guide). Темы роли отдаёт сервер (services/admin_guide.py).
// Новая функция админки = тема в guide-admin.json в том же коммите (tools/test_admin_guide_contract.py сверит разделы, действия и пороги с кодом).
const AG = {data: null, pending: null, want: '', open: false, ready: false};

// Какая тема про раздел или действие: те же правила видимости, что на сервере (тему другой роли «?» не откроет).
function agVisible(t) {
  if (!ME) return false;
  if (ME.owner) return !!t.owner;   // владелец чата: только про свои чаты
  return ME.rank >= t.min_rank && (!t.section || t.section === 'mychats' || ME.sections.some(s => s.key === t.section));
}
const agTopics = () => (AG.data ? AG.data.topics.filter(agVisible) : []);
function agLoad() {
  if (AG.data) return Promise.resolve(AG.data);
  if (!AG.pending) AG.pending = fetch(BASE + '/bot-admin/guide-admin.json', {cache: 'no-cache'})
    .then(r => { if (!r.ok) throw new Error('Путеводитель не загрузился'); return r.json(); })
    .then(d => { if (!d || !Array.isArray(d.topics)) throw new Error('Путеводитель повреждён'); AG.data = d; return d; })
    .finally(() => { AG.pending = null; });
  return AG.pending;
}

// Для страницы слоя (guide-host.js): вход теми же заголовками, что у админки, и тема, которую ждут.
function agHeaders() {
  const h = {};
  if (INIT) h['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) h['x-session-token'] = s; } catch (_) {}
  return h;
}
function agWanted() { AG.ready = true; return AG.want; }

const agFrame = () => $('#guide-layer iframe');
function agBackPress() { const f = agFrame(); try { f.contentWindow.navBack(); } catch (_) { agClose(); } }
// «Назад» Telegram, пока открыт слой, листает Путеводитель; после закрытия — снова тот, что был у раздела или карточки.
function agBackButton(on) {
  const bb = TG && TG.BackButton; if (!bb) return;
  const own = PEOPLE.bb || goApp;
  if (on) { bb.offClick(own); bb.onClick(agBackPress); } else { bb.offClick(agBackPress); bb.onClick(own); }
  bb.show();
}
function agShow(topicId = '') {
  AG.want = topicId || '';
  let layer = $('#guide-layer');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'guide-layer'; layer.className = 'guide-layer'; layer.setAttribute('role', 'dialog'); layer.setAttribute('aria-label', 'Путеводитель администрации');
    layer.innerHTML = `<iframe title="Путеводитель администрации" src="${BASE}/bot-admin/guide#t=${encodeURIComponent(AG.want)}"></iframe>`;
    document.body.append(layer);
  } else if (AG.ready) {
    try { agFrame().contentWindow.agHostOpen(AG.want); } catch (_) {}
  }
  if (!AG.open) agBackButton(true);
  AG.open = true; layer.hidden = false;
  document.documentElement.classList.add('guide-open');
  setTimeout(() => { try { agFrame().focus(); } catch (_) {} }, 50);
}
function agClose() {
  const layer = $('#guide-layer');
  if (!AG.open || !layer) return;
  AG.open = false; layer.hidden = true;
  document.documentElement.classList.remove('guide-open');
  agBackButton(false);
}
// Кнопка темы «Открыть раздел»: окно действия под слоем закрывается — человек сознательно уходит в другой раздел.
function agOpenSection(key) {
  agClose();
  const box = $('#sheet'); box.hidden = true; box.innerHTML = '';
  if (ME.sections.some(s => s.key === key)) open(key);
}
// Тема раздела (или главная, если её нет); данные не пришли — главная.
function agOpenFor(pick) {
  agLoad().then(() => agShow((agTopics().find(pick) || {}).id || '')).catch(() => agShow(''));
}
function agContext() {
  const here = currentSection();
  agOpenFor(t => t.section === here && !t.actions);
}
const agWhy = action => agOpenFor(t => (t.actions || []).includes(action));   // окно действия остаётся под слоем

// Вкладка «Путеводитель» не уводит из раздела: открывает слой поверх него.
document.addEventListener('click', e => {
  const tab = e.target.closest('[data-tab="guide"], [data-go="guide"]');
  if (tab) {
    e.preventDefault(); e.stopImmediatePropagation();
    if (tab.dataset.go) { const box = $('#sheet'); box.hidden = true; box.innerHTML = ''; }   // лист «Ещё»
    agShow('');
    return;
  }
  const why = e.target.closest('[data-ag-why]'); if (why) agWhy(why.dataset.agWhy);
}, true);
document.addEventListener('keydown', e => {
  if (AG.open && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); agBackPress(); }
}, true);

// Раздел «guide» сам не рисуется: старая сохранённая вкладка или ссылка открывают обычный раздел и слой над ним.
SECTIONS.guide = () => { open((ME.sections.find(s => s.key !== 'guide') || {}).key); agShow(''); };
SECTION_META.guide = ['📘', 'Путеводитель', 'Открываем Путеводитель администрации'];
ICONS.guide = '<path d="M5 4.5h9.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h9.5M9 8.5h5"/>';
SHORT.guide = 'Путеводитель';
