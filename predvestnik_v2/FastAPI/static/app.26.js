// ── Настройки: полноэкранная страница в стиле каркаса v3 ─────────────────────────
// Секции без карточек: внешний вид, приватность («был(а) в сети»), уведомления, документы, вход, аккаунт.
// Всё сохраняется сразу; опасное (удаление аккаунта) вынесено вниз и идёт через подтверждения (_acc* в app.02.js).
const _ST = { presence: null, notif: null, warps: null, account: null, failed: {}, busy: '' };
// Значки строк: один нейтральный цвет (правило «один акцент на экран»), красный только у удаления аккаунта
const _ST_ICO = {
  look: '<path d="M12 3.5l2.2 5.1 5.3.5-4 3.6 1.2 5.3L12 15.2 7.3 18l1.2-5.3-4-3.6 5.3-.5z"/>',
  calm: '<path d="M19.5 14.6A7.8 7.8 0 1 1 9.4 4.5a6.3 6.3 0 0 0 10.1 10.1z"/>',
  easy: '<path d="M9 11.5V5.8a1.6 1.6 0 0 1 3.2 0v5"/><path d="M12.2 10.3V9a1.6 1.6 0 0 1 3.2 0v2.3M15.4 10.6a1.6 1.6 0 0 1 3.1.4v3.2a6.3 6.3 0 0 1-6.3 6.3h-.6a5.9 5.9 0 0 1-4.5-2.1L4.6 15a1.6 1.6 0 0 1 2.4-2.1L9 14.7"/>',
  oled: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17A8.5 8.5 0 0 0 12 3.5z" fill="currentColor"/>',
  big: '<path d="M3.5 18.5L8 6.5l4.5 12M5.2 14h5.6"/><path d="M14.5 18.5l3-7.5 3 7.5M15.6 16h3.8"/>',
  eye: '<path d="M2.8 12s3.3-6 9.2-6 9.2 6 9.2 6-3.3 6-9.2 6-9.2-6-9.2-6z"/><circle cx="12" cy="12" r="2.8"/>',
  bell: '<path d="M6.3 16.5V11a5.7 5.7 0 0 1 11.4 0v5.5l1.6 1.8H4.7z"/><path d="M10 20.3a2.2 2.2 0 0 0 4 0"/>',
  warp: '<path d="M12 19.5s-7.5-4.4-7.5-9.6A4.1 4.1 0 0 1 12 7.6a4.1 4.1 0 0 1 7.5 2.3c0 5.2-7.5 9.6-7.5 9.6z"/>',
  promo: '<path d="M4 8.2V6.5h16v1.7a2.2 2.2 0 0 0 0 4.3v1.7a2.2 2.2 0 0 0 0 4.3v1.7H4v-1.7a2.2 2.2 0 0 0 0-4.3v-1.7a2.2 2.2 0 0 0 0-4.3z" transform="translate(0 -1.2)"/><path d="M14 6v12" stroke-dasharray="1.6 2"/>',
  doc: '<path d="M6.5 3.5h7.5l4 4v13h-11.5z"/><path d="M13.5 3.5V8h4.5M9.5 12h5M9.5 15.5h5"/>',
  shield: '<path d="M12 3.5l7 2.6v5.6c0 4.4-3 7.6-7 8.8-4-1.2-7-4.4-7-8.8V6.1z"/><path d="M9 12.2l2.2 2.2 4-4.2"/>',
  key: '<circle cx="8" cy="14" r="3.8"/><path d="M10.8 11.3l8.2-8.1M16.3 6l2.4 2.4M14 8.3l2 2"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  trash: '<path d="M4.5 6.5h15M9.5 6.5V4.5h5v2M6.5 6.5l.9 13h9.2l.9-13M10.3 10.5v6M13.7 10.5v6"/>',
};
const _stIco = name => `<span class="st-ico${name === 'trash' ? ' st-ico--danger' : ''}" aria-hidden="true"><svg viewBox="0 0 24 24">${_ST_ICO[name] || _ST_ICO.doc}</svg></span>`;
// Секция: подпись над группой, строки — в одной карточке, пояснение под ней
const _stSec = (title, body, hint, mod) => `<section class="st-sec"><div class="v3-sec"><span class="v3-eyebrow">${title}</span></div><div class="st-card${mod ? ` st-card--${mod}` : ''}">${body}</div>${hint ? `<p class="st-hint">${hint}</p>` : ''}</section>`;
const _stLine = (n = 3) => Array.from({ length: n }, () => '<div class="sk" style="height:44px;border-radius:12px;margin:8px 14px"></div>').join('');
const _stFail = (key, what) => `<div class="v3-empty">${what} не загрузились. <button type="button" class="v3-link" onclick="_stLoad('${key}')">Повторить</button></div>`;
// Вся строка — подпись переключателя: нажать можно по тексту, а не только по «таблетке»
function _stSwitch(icon, label, sub, checked, action, id) {
  return `<label class="st-row">${_stIco(icon)}<span class="st-tx"><b>${label}</b><small>${sub}</small></span><input type="checkbox" role="switch" class="st-switch"${id ? ` id="${id}"` : ''} ${checked ? 'checked' : ''} onchange="${action}"></label>`;
}
function _stRow(icon, label, sub, action, end, cls) {
  return `<button type="button" class="st-row st-row--tap${cls ? ` ${cls}` : ''}" onclick="${action}">${_stIco(icon)}<span class="st-tx"><b>${label}</b><small>${sub}</small></span><span class="st-end">${end || _v3Icon('chev')}</span></button>`;
}
function _stSeg(items, current, fn, label) {
  return `<div class="st-seg" role="radiogroup" aria-label="${label}">${items.map(i => `<button type="button" role="radio" aria-checked="${i.id === current}" class="${i.id === current ? 'on' : ''}" onclick="${fn}('${i.id}')">${i.title}</button>`).join('')}</div>`;
}

function openSettingsModal() {
  switchPage('settings');
  _stRender();
  ['presence', 'notif', 'warps', 'account'].forEach(key => { if (!_ST[key]) _stLoad(key); });
}
function _stLoad(key) {
  const calls = { presence: ['/presence-v1/settings', 'Настройки приватности'], notif: ['/profile/notification-prefs', 'Уведомления'], warps: ['/profile/warp-prefs', 'Варпы'], account: ['/account/deletion-status', 'Настройки аккаунта'] };
  _ST.failed[key] = false; _stRender();
  return api(calls[key][0]).then(d => { _ST[key] = d; }).catch(() => { _ST.failed[key] = true; }).finally(_stRender);
}

function _stLook() {
  const look = _profileData?.look;
  return look ? `${_profileEsc(look.name)} · тир ${_profileEsc(look.tier)}` : 'Скин не надет, откройте витрину';
}
function _stPresence() {
  const p = _ST.presence;
  if (_ST.failed.presence) return _stFail('presence', 'Настройки приватности');
  if (!p) return _stLine(2);
  const cur = p.levels.find(l => l.id === p.visibility);
  const now = p.preview ? `Сейчас другие видят: «${_profileEsc(p.preview.label)}».` : 'Сейчас другие не видят ничего.';
  return `<div class="st-field">${_stIco('eye')}<span class="st-tx"><b>Кто видит, когда вы были в сети</b><small>${_profileEsc(cur?.hint || '')}</small></span></div>${_stSeg(p.levels, p.visibility, '_stSetPresence', 'Кто видит, когда вы были в сети')}
    <p class="st-hint st-hint--in">${now} Чужое время вы видите с той же точностью, какую даёте сами.</p>`;
}
function _stNotif() {
  if (_ST.failed.notif) return _stFail('notif', 'Уведомления');
  if (!_ST.notif) return _stLine(3);
  const list = _ST.notif.categories || [];
  return list.length ? list.map(c => _stSwitch('bell', _profileEsc(String(c.label).replace(/^[^\p{L}\p{N}]+/u, '')), 'Личные сообщения от бота', !!c.enabled, `_stNotifSet('${_profileEsc(c.key)}',this.checked)`)).join('') : '<div class="v3-empty">Категорий уведомлений пока нет.</div>';
}
function _stWarps() {
  if (_ST.failed.warps) return _stFail('warps', 'Варпы');
  if (!_ST.warps) return _stLine(1);
  return _stSwitch('warp', '18+ варпы в мой адрес', 'Разрешить другим игрокам взрослые варп-команды на вас. В чате: «бот 18+ вкл» / «бот 18+ выкл».', !!_ST.warps.adult, '_stWarpsSet(this.checked)');
}
function _stWarpsSet(on) {
  const before = _ST.warps; _ST.warps = { adult: on }; _haptic('select');
  api('/profile/warp-prefs', { method: 'POST', body: JSON.stringify({ enabled: on }) })
    .then(d => { _ST.warps = d; toast('Сохранено'); })
    .catch(e => { _ST.warps = before; toast(e, false); _stRender(); });
}
function _stAccount() {
  if (_ST.failed.account) return _stFail('account', 'Настройки аккаунта');
  const d = _ST.account; if (!d) return _stLine(2);
  const days = d.delete_after_days || 365, proc = d.process_status;
  const state = proc === 'confirming' ? '<p class="st-note">Ожидается код из ЛС бота.</p>' + _stRow('shield', 'Отменить процесс', 'Ничего не будет удалено', '_accCancel()')
    : proc === 'cooling' ? '<p class="st-note st-note--warn">Удаление запланировано, идёт период «остывания».</p>' + _stRow('shield', 'Отменить удаление', 'Аккаунт останется как был', '_accCancel()')
    : _stRow('trash', 'Удалить аккаунт…', 'Три шага защиты, 14 дней на возврат', '_accDeleteStart()', '', 'st-danger');
  return `<div class="st-field">${_stIco('clock')}<span class="st-tx"><b>Удалять аккаунт после неактивности</b><small>Предупредим в ЛС бота за 14 дней</small></span></div>${_stSeg([{ id: '180', title: '6 месяцев' }, { id: '365', title: '1 год' }, { id: '730', title: '2 года' }], String(days), '_stInactivity', 'Срок неактивности')}
    <p class="st-hint st-hint--in">Любое ваше сообщение в чате отменяет отсчёт.</p></div><div class="st-card st-card--danger">${state}`;
}
function _stRender() {
  const root = el('pg-settings'); if (!root) return;
  const calm = document.body.classList.contains('no-fx'), user = _profileData || {};
  const login = !INIT_DATA ? _stSec('Вход', `${_stRow('key', 'Войти другим аккаунтом', `Сейчас: @${_profileEsc(user.username || '—')}`, 'switchTgAccount()')}`, 'Сменили аккаунт в приложении Telegram — обновите вход здесь.') : '';
  root.innerHTML = `<div class="eyebrow-row"><button type="button" class="v3-link" onclick="navBack()" aria-label="Назад">‹ Назад</button></div>
    <header class="v3-hero">${typeof V3_SKY === 'string' ? V3_SKY : ''}${typeof v3Emblem === 'function' ? v3Emblem('gear') : ''}<div class="v3-hero-tx"><h1 class="v3-title">Настройки${v3GlintMark('Настройки')}</h1><p class="v3-sub">Всё под себя. Изменения сохраняются сразу.</p></div>${v3GuideIcon('settings')}</header>
    ${_stSec('Внешний вид', _stRow('look', 'Образы и скины', _stLook(), 'openLooksModal()') + _stSwitch('calm', 'Спокойный режим', 'Без анимаций: рамки, ореолы и частицы замирают. Телефон скажет спасибо.', calm, '_toggleNoFx(this.checked)') + _stSwitch('easy', 'Упрощённый ввод', 'Мягче таймеры в играх, спин тапом вместо удержания.', _easyInput(), '_toggleEasyInput(this.checked)') + _stSwitch('oled', 'Чёрный фон', 'Для OLED-экранов: фон полностью чёрный, цвета образа остаются.', _dispGet('pv_oled'), '_toggleOled(this.checked)') + _stSwitch('big', 'Крупный текст', 'Весь текст и элементы на экранах чуть крупнее.', _dispGet('pv_big'), '_toggleBig(this.checked)'))}
    ${_stSec('Приватность', _stPresence() + _stWarps(), 'Обычные варпы (обнять, погладить) работают всегда. Админы чата могут выключить 18+ во всём чате.')}
    ${_stSec('Уведомления', _stNotif(), 'Здесь только личные сообщения от бота.')}
    ${_stSec('Промокоды и документы', _stRow('promo', 'Промокоды', 'Ввести код, забрать доступные, история', 'openPromoSheet()') + _stRow('doc', 'Пользовательское соглашение', 'Откроется прямо здесь', "openLegalDoc('tos')") + _stRow('shield', 'Политика конфиденциальности', 'Откроется прямо здесь', "openLegalDoc('privacy')"))}
    ${login}
    ${_stSec('Аккаунт', _stAccount())}
    ${user.user_id ? `<button type="button" class="st-id" onclick="_stCopyId(${Number(user.user_id)})" aria-label="Скопировать ID игрока">ID игрока ${Number(user.user_id)} · нажмите, чтобы скопировать</button>` : ''}`;
}

// ── Действия ─────────────────────────────────────────────────────────────────────
function _stSetPresence(level) {
  if (_ST.busy || _ST.presence?.visibility === level) return;
  const before = _ST.presence; _ST.busy = 'presence'; _haptic('select');
  if (before) { _ST.presence = { ...before, visibility: level }; _stRender(); }     // сразу, откат только при ошибке
  api('/presence-v1/settings', { method: 'POST', body: JSON.stringify({ visibility: level }) })
    .then(d => { _ST.presence = d; toast('Сохранено'); })
    .catch(e => { _ST.presence = before; toast(e, false); })
    .finally(() => { _ST.busy = ''; _stRender(); });
}
function _stNotifSet(key, on) {
  _haptic('select');
  api('/profile/notification-prefs', { method: 'POST', body: JSON.stringify({ category: key, enabled: on }) })
    .then(() => { const row = (_ST.notif?.categories || []).find(c => c.key === key); if (row) row.enabled = on; toast(on ? 'Включено' : 'Выключено'); })
    .catch(e => { toast(e, false); _stLoad('notif'); });
}
function _stInactivity(days) {
  _haptic('select');
  if (_ST.account) { _ST.account.delete_after_days = Number(days); _stRender(); }
  _accSetInactivity(days);
}
function _stCopyId(id) {
  const done = () => { _haptic('success'); toast('ID скопирован'); };
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(String(id)).then(done).catch(() => toast('Не получилось скопировать', false)); else toast(`ID: ${id}`);
}

// ── Отображение: чёрный фон для OLED и крупный текст (хранится на устройстве) ─────────
const _dispGet = key => _lsGet(key) === '1';
function _dispApply() { document.body.classList.toggle('pv-oled', _dispGet('pv_oled')); document.body.classList.toggle('pv-big', _dispGet('pv_big')); }
function _toggleOled(on) { _lsSet('pv_oled', on ? '1' : '0'); _dispApply(); _haptic('select'); }
function _toggleBig(on) { _lsSet('pv_big', on ? '1' : '0'); _dispApply(); _haptic('select'); }
_dispApply();
