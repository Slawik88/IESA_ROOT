// ── Настройки: полноэкранная страница в стиле каркаса v3 ─────────────────────────
// Секции без карточек: внешний вид, приватность («был(а) в сети»), уведомления, документы, вход, аккаунт.
// Всё сохраняется сразу; опасное (удаление аккаунта) вынесено вниз и идёт через подтверждения (_acc* в app.02.js).
const _ST = { presence: null, notif: null, account: null, failed: {}, busy: '' };
const _stSec = (title, body, hint) => `<section class="st-sec"><div class="v3-sec"><span class="v3-eyebrow">${title}</span></div>${body}${hint ? `<p class="st-hint">${hint}</p>` : ''}</section>`;
const _stLine = (n = 3) => Array.from({ length: n }, () => '<div class="sk" style="height:44px;border-radius:12px;margin-top:8px"></div>').join('');
const _stFail = (key, what) => `<div class="v3-empty">${what} не загрузились. <button type="button" class="v3-link" onclick="_stLoad('${key}')">Повторить</button></div>`;
function _stSwitch(label, sub, checked, action, id) {
  return `<label class="st-row"><span><b>${label}</b><small>${sub}</small></span><input type="checkbox" role="switch" class="st-switch"${id ? ` id="${id}"` : ''} ${checked ? 'checked' : ''} onchange="${action}"></label>`;
}
function _stRow(label, sub, action, end) {
  return `<button type="button" class="st-row st-row--tap" onclick="${action}"><span><b>${label}</b><small>${sub}</small></span><span class="st-end">${end || _v3Icon('chev')}</span></button>`;
}
function _stSeg(items, current, fn, label) {
  return `<div class="st-seg" role="radiogroup" aria-label="${label}">${items.map(i => `<button type="button" role="radio" aria-checked="${i.id === current}" class="${i.id === current ? 'on' : ''}" onclick="${fn}('${i.id}')">${i.title}</button>`).join('')}</div>`;
}

function openSettingsModal() {
  switchPage('settings');
  _stRender();
  ['presence', 'notif', 'account'].forEach(key => { if (!_ST[key]) _stLoad(key); });
}
function _stLoad(key) {
  const calls = { presence: ['/presence-v1/settings', 'Настройки приватности'], notif: ['/profile/notification-prefs', 'Уведомления'], account: ['/account/deletion-status', 'Настройки аккаунта'] };
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
  return `<div class="st-field"><b>Кто видит, когда вы были в сети</b></div>${_stSeg(p.levels, p.visibility, '_stSetPresence', 'Кто видит, когда вы были в сети')}
    <p class="st-hint st-hint--on">${_profileEsc(cur?.hint || '')}</p><p class="st-hint">${now} Чужое время вы видите с той же точностью, какую даёте сами.</p>`;
}
function _stNotif() {
  if (_ST.failed.notif) return _stFail('notif', 'Уведомления');
  if (!_ST.notif) return _stLine(3);
  const list = _ST.notif.categories || [];
  return list.length ? list.map(c => _stSwitch(_profileEsc(c.label), 'Личные сообщения от бота', !!c.enabled, `_stNotifSet('${_profileEsc(c.key)}',this.checked)`)).join('') : '<div class="v3-empty">Категорий уведомлений пока нет.</div>';
}
function _stAccount() {
  if (_ST.failed.account) return _stFail('account', 'Настройки аккаунта');
  const d = _ST.account; if (!d) return _stLine(2);
  const days = d.delete_after_days || 365, proc = d.process_status;
  const state = proc === 'confirming' ? '<p class="st-note">Ожидается код из ЛС бота.</p>' + _stRow('Отменить процесс', 'Ничего не будет удалено', '_accCancel()')
    : proc === 'cooling' ? '<p class="st-note st-note--warn">Удаление запланировано, идёт период «остывания».</p>' + _stRow('Отменить удаление', 'Аккаунт останется как был', '_accCancel()')
    : `<button type="button" class="st-row st-row--tap st-danger" onclick="_accDeleteStart()"><span><b>Удалить аккаунт…</b><small>Три шага защиты, 14 дней на возврат</small></span><span class="st-end">${_v3Icon('chev')}</span></button>`;
  return `<div class="st-field"><b>Удалять аккаунт после неактивности</b></div>${_stSeg([{ id: '180', title: '6 месяцев' }, { id: '365', title: '1 год' }, { id: '730', title: '2 года' }], String(days), '_stInactivity', 'Срок неактивности')}
    <p class="st-hint">За 14 дней до срока придёт предупреждение в ЛС бота. Любое сообщение в чате отменяет отсчёт.</p>${state}`;
}
function _stRender() {
  const root = el('pg-settings'); if (!root) return;
  const calm = document.body.classList.contains('no-fx'), user = _profileData || {};
  const login = !INIT_DATA ? _stSec('Вход', `<p class="st-hint">Сейчас: Telegram @${_profileEsc(user.username || '—')}. Если вы сменили аккаунт в приложении Telegram, обновите вход.</p>${_stRow('Войти другим аккаунтом', 'Откроется вход через Telegram', 'switchTgAccount()')}`) : '';
  root.innerHTML = `<div class="eyebrow-row"><button type="button" class="v3-link" onclick="navBack()" aria-label="Назад">‹ Назад</button></div>
    <h1 class="v3-title">Настройки</h1><p class="v3-sub">Всё под себя. Изменения сохраняются сразу.</p>
    ${_stSec('Внешний вид', _stRow('Образы и скины', _stLook(), 'openLooksModal()') + _stSwitch('Спокойный режим', 'Без анимаций: рамки, ореолы и частицы замирают. Телефон скажет спасибо.', calm, '_toggleNoFx(this.checked)') + _stSwitch('Упрощённый ввод', 'Мягче таймеры в играх, спин тапом вместо удержания.', _easyInput(), '_toggleEasyInput(this.checked)'))}
    ${_stSec('Приватность', _stPresence())}
    ${_stSec('Уведомления', _stNotif(), 'Здесь настраиваются только личные сообщения от бота.')}
    ${_stSec('Документы', _stRow('Пользовательское соглашение', 'Откроется прямо здесь', "openLegalDoc('tos')") + _stRow('Политика конфиденциальности', 'Откроется прямо здесь', "openLegalDoc('privacy')"))}
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
