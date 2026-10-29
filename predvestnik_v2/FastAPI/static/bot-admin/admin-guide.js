// ── Путеводитель администрации: показывает экран Путеводителя Mini App (тот же, что у игрока), здесь только входы ──
// Данные — guide-admin.json (сервер отдаёт роли только её темы: services/admin_guide.py). Входы: раздел «Путеводитель»
// (в доке или «Ещё»), значок «?» в шапке — тема раздела, где ты сейчас, «Что это значит?» в окне опасного действия.
// В Mini App адрес ?startapp=adminguide_<тема>_<раздел>: «Назад» там вернёт в этот раздел (pv_admin_tab).
// Новая функция админки = тема в guide-admin.json в том же коммите (tools/test_admin_guide_contract.py сверит разделы, действия и пороги с кодом).
const AG = {data: null, pending: null, from: ''};

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

// Переход в Путеводитель Mini App. Раздел, откуда пришли, запоминается вкладкой: «Назад» в Путеводителе вернёт туда.
function agGoMiniApp(topicId, from) {
  const back = from && from !== 'guide' ? from : ((ME.sections.find(s => s.key !== 'guide') || {}).key || '');
  try { if (back) localStorage.setItem('pv_admin_tab', back); } catch (_) {}
  location.href = `${BASE}/?startapp=adminguide_${encodeURIComponent(topicId || '')}_${encodeURIComponent(back)}`;
}
// Тема раздела (или главная Путеводителя, если её нет), найденная по данным; данные не пришли — главная.
function agOpenFor(pick, from) {
  agLoad().then(() => agGoMiniApp((agTopics().find(pick) || {}).id || '', from)).catch(() => agGoMiniApp('', from));
}
function agContext() {
  const here = currentSection();
  agOpenFor(t => t.section === here && !t.actions, here);
}
function agWhy(action) {
  const box = $('#sheet'); if (box) { box.hidden = true; box.innerHTML = ''; }
  agOpenFor(t => (t.actions || []).includes(action), currentSection());
}

// Нажатие на вкладку «Путеводитель»: раздел, откуда нажали, запоминаем до того, как вкладка сменится.
document.addEventListener('click', e => {
  if (e.target.closest('[data-tab="guide"], [data-go="guide"]')) AG.from = currentSection();
}, true);
document.addEventListener('click', e => {
  const why = e.target.closest('[data-ag-why]'); if (why) agWhy(why.dataset.agWhy);
});

SECTIONS.guide = main => {
  main.removeAttribute('aria-busy');
  agGoMiniApp('', AG.from);
};
SECTION_META.guide = ['📘', 'Путеводитель', 'Открываем Путеводитель администрации'];
ICONS.guide = '<path d="M5 4.5h9.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h9.5M9 8.5h5"/>';
SHORT.guide = 'Путеводитель';
