// A report can be opened even when no exception or error message appeared.
(() => {
  'use strict';
  const diag = window.PVDiagnostics;
  if (!diag || window.PVSupport) return;
  const categories = {avatar:'Не видно фото',mafia:'Мафия и чат',games:'Другие игры',purchase:'Покупка или награда',display:'Внешний вид',other:'Другая проблема'};
  const MAX_AGE = 86400000, pending = new Map(), flights = new Map();
  let dialog = null, previousFocus = null, formOwner = '', lastNotice = 0, noticeTimer = null;
  const key = owner => `pv_support_pending_v1:${owner}`;
  const draftKey = owner => `pv_support_draft_v1:${owner}`;
  const receiptKey = owner => `pv_support_receipt_v1:${owner}`;
  function saveDraft() {
    if (!dialog || dialog.dataset.delivered === '1' || dialog.dataset.reportId) return;
    const draft = {saved_at:Date.now(),category:dialog.querySelector('select').value,
      comment:diag.safeText(dialog.querySelector('textarea').value,2000),include:dialog.querySelector('input').checked};
    if (!draft.comment.trim()) { if (formOwner) { try { localStorage.removeItem(draftKey(formOwner)); } catch (_) {} } return; }
    if (formOwner) { try { localStorage.setItem(draftKey(formOwner),JSON.stringify(draft)); } catch (_) {} }
  }
  function load(owner) {
    if (pending.has(owner)) return pending.get(owner);
    if (!owner) return null;
    try {
      const raw = localStorage.getItem(key(owner));
      if (!raw || raw.length > 1000000) return null;
      const saved = JSON.parse(raw);
      if (saved.owner === owner && saved.payload?.client_report_id && Date.now()-saved.saved_at < MAX_AGE) { pending.set(owner,saved); return saved; }
      localStorage.removeItem(key(owner));
    } catch (_) {}
    return null;
  }
  function save(report) {
    pending.set(report.owner,report);
    report.durable = false;
    if (!report.owner) return false;
    try {
      const raw = localStorage.getItem(key(report.owner));
      const existing = raw && raw.length < 1000000 ? JSON.parse(raw) : null;
      if (existing?.owner === report.owner && existing.payload?.client_report_id !== report.payload.client_report_id && Date.now()-existing.saved_at < MAX_AGE) return false;
      report.durable = true; localStorage.setItem(key(report.owner),JSON.stringify(report)); return true;
    } catch (_) { report.durable = false; return false; }
  }
  function remove(owner, id) {
    const saved = load(owner);
    if (id && saved?.payload.client_report_id !== id) return;
    pending.delete(owner);
    if (owner) { try {
      const disk = JSON.parse(localStorage.getItem(key(owner))||'null');
      if (!id || disk?.payload?.client_report_id === id) localStorage.removeItem(key(owner));
    } catch (_) {} }
  }
  function tell(message, bad = false) {
    if (!dialog) return;
    const output = dialog.querySelector('[data-support-status]');
    output.textContent = message; output.dataset.bad = String(bad);
  }
  function lock(report) {
    if (!dialog) return;
    if (report) dialog.dataset.reportId = report.payload.client_report_id;
    for (const input of dialog.querySelectorAll('textarea,select,input')) input.disabled = true;
    dialog.querySelector('[data-support-send]').textContent = 'Повторить отправку';
    dialog.querySelector('[data-support-delete]').hidden = false;
    if (report) {
      dialog.querySelector('textarea').value = report.payload.comment;
      dialog.querySelector('select').value = report.payload.category;
      dialog.querySelector('input').checked = report.payload.include_diagnostics;
    }
  }
  function close() {
    if (!dialog) return;
    saveDraft();
    const node = dialog; dialog = null;
    if (node.open && typeof node.close === 'function') node.close();
    node.remove(); previousFocus?.focus?.({preventScroll:true});
  }
  const uuid = () => globalThis.crypto?.randomUUID?.() || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c => {
    const r = globalThis.crypto?.getRandomValues ? crypto.getRandomValues(new Uint8Array(1))[0]&15 : Math.floor(Math.random()*16);
    return (c === 'x' ? r : (r&3)|8).toString(16);
  });
  async function transmit(report) {
    if (!report.owner || diag.owner() !== report.owner) throw new Error('Открой приложение через бота под тем же аккаунтом и повтори отправку.');
    if (Date.now()-report.saved_at >= MAX_AGE) throw new Error('Снимок старше суток. Удали его с устройства и создай новый отчёт.');
    const flightKey = `${report.owner}:${report.payload.client_report_id}`;
    if (flights.has(flightKey)) return flights.get(flightKey);
    const task = (async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(),12000);
      try {
        const response = await diag.nativeFetch(`${diag.base}/support/reports`,{method:'POST',headers:diag.credentials(),body:JSON.stringify(report.payload),signal:controller.signal});
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) throw new Error('Отчёт не отправлен. Открой приложение заново через бота и повтори отправку.');
          if (response.status === 429) throw new Error('Отчёт не отправлен: за час уже отправлено 6. Снимок сохранён, повтори позже.');
          if (response.status === 409) throw new Error('Аккаунт не совпал с автором отчёта. Снимок сохранён: открой приложение под нужным аккаунтом.');
          if (response.status === 400 || response.status === 413) throw new Error('Не удалось прочитать снимок. Удали его с устройства кнопкой ниже и создай новый отчёт.');
          throw new Error('Пока не удалось доставить отчёт. Снимок сохранён, можно повторить отправку.');
        }
        if (!result.code || !result.id || result.client_report_id !== report.payload.client_report_id) throw new Error('Ответ не подтвердил доставку. Повтори отправку — дубликата не будет.');
        remove(report.owner,report.payload.client_report_id);
        try { localStorage.setItem(receiptKey(report.owner),JSON.stringify({code:result.code,saved_at:Date.now()})); } catch (_) {}
        return result;
      } catch (error) {
        if (error instanceof TypeError) throw new Error('Нет связи. Повтори отправку после подключения — снимок не изменится.');
        throw error;
      } finally { clearTimeout(timer); }
    })();
    flights.set(flightKey,task);
    try { return await task; } finally { flights.delete(flightKey); }
  }
  async function send() {
    const node = dialog;
    if (!node) return;
    const owner = diag.owner();
    if (owner !== formOwner) { tell('Аккаунт изменился. Закрой форму и открой её заново.',true); return; }
    const button = node.querySelector('[data-support-send]');
    if (button.disabled) return;
    button.disabled = true; tell('Собираем отчёт…');
    let report = load(owner), durable = report?.durable !== false;
    try {
      if (report && node.dataset.reportId !== report.payload.client_report_id) {
        saveDraft(); lock(report);
        tell('Есть ранее сохранённый отчёт. Проверь его перед повтором. Новое описание осталось в черновике.');
        return;
      }
      if (!report) {
        const include = node.querySelector('input').checked;
        const snapshot = include ? await diag.snapshot() : {captured_at:Date.now(),environment:{},events:[],dropped_events:0};
        if (diag.owner() !== owner) throw new Error('Аккаунт изменился. Закрой форму и открой её заново.');
        report = {owner,saved_at:Date.now(),payload:{expected_user_id:owner,client_report_id:uuid(),category:node.querySelector('select').value,
          comment:diag.safeText(node.querySelector('textarea').value,2000),include_diagnostics:include,...snapshot}};
        durable = save(report); lock(report);
        try { localStorage.removeItem(draftKey(owner)); } catch (_) {}
      }
      tell(navigator.onLine ? 'Отправляем…' : 'Нет сети. Снимок сохранён, отправим после подключения.');
      if (!navigator.onLine) {
        if (!durable) tell('Нет сети. Снимок хранится только в этой вкладке — не закрывай её до отправки.',true);
        return;
      }
      const result = await transmit(report);
      if (dialog !== node || diag.owner() !== owner) return;
      tell(`Отчёт доставлен · ${result.code}. Спасибо!`);
      node.dataset.delivered = '1';
      button.hidden = true; node.querySelector('[data-support-delete]').hidden = true;
      node.querySelector('[data-support-close]').textContent = 'Готово';
    } catch (error) {
      if (dialog === node && diag.owner() === owner) {
        const message = error?.name === 'AbortError' ? 'Ответ задержался. Повтори отправку — уже доставленный отчёт не продублируется.' : diag.safeText(error.message,240);
        tell(message + (!durable ? ' Не закрывай вкладку: хранилище устройства недоступно.' : ''),true);
      }
    } finally { button.disabled = false; }
  }
  function open(category) {
    if (dialog) return;
    previousFocus = document.activeElement; formOwner = diag.owner();
    const saved = load(formOwner), node = document.createElement('dialog');
    dialog = node; node.className = 'pv-support'; node.setAttribute('aria-labelledby','pv-support-title');
    node.innerHTML = `<form method="dialog" class="pv-support-card">
      <header><div><small>Поможем разобраться</small><h2 id="pv-support-title">Сообщить о проблеме</h2></div><button type="button" data-support-x aria-label="Закрыть форму">×</button></header>
      <p>Что-то работает не так? Сообщи нам, даже если ошибки на экране нет.</p>
      <label>Что случилось?<select name="category">${Object.entries(categories).map(([value,label]) => `<option value="${value}">${label}</option>`).join('')}</select></label>
      <label>Пару слов о проблеме <small>Необязательно</small><textarea name="comment" maxlength="2000" rows="3" placeholder="Например: у меня VIP, но фото не появилось"></textarea></label>
      <label class="pv-support-consent"><input type="checkbox" checked/><span>Приложить сведения для проверки<small>Устройство, Telegram, соединение и история работы за последний час, пока приложение было открыто. Без переписки и секретных данных входа.</small></span></label>
      <details><summary>Что будет отправлено</summary><p>Язык и часовой пояс, доступные сведения об устройстве, версия приложения, результаты загрузки и ошибки. Точный регион и модель могут быть недоступны.</p><p>Данные хранятся до 30 дней. Отчёт видят разработчики и создатель.</p><button type="button" data-support-preview>Посмотреть сведения</button><pre data-support-details hidden></pre></details>
      <p class="pv-support-status" data-support-status role="status" aria-live="polite"></p>
      <footer><button type="button" data-support-close>Закрыть</button><button type="button" class="pv-support-primary" data-support-send>Отправить</button></footer>
      <button type="button" class="pv-support-delete" data-support-delete hidden>Удалить снимок с устройства</button>
    </form>`;
    node.querySelector('select').value = categories[category] ? category : location.pathname.includes('rhythm') || location.pathname.includes('minesweeper') || location.pathname.includes('league') ? 'games' : 'other';
    if (!saved && formOwner) {
      try {
        const draft = JSON.parse(localStorage.getItem(draftKey(formOwner))||'null');
        if (draft?.comment?.trim() && Date.now()-draft.saved_at < MAX_AGE) {
          node.querySelector('textarea').value = diag.safeText(draft.comment,2000);
          if (categories[draft.category]) node.querySelector('select').value = draft.category;
          node.querySelector('input').checked = draft.include !== false;
        }
      } catch (_) {}
    }
    node.addEventListener('input',saveDraft);
    node.querySelector('form').onsubmit = event => { event.preventDefault(); send(); };
    node.querySelector('[data-support-send]').onclick = send;
    node.querySelector('[data-support-close]').onclick = close; node.querySelector('[data-support-x]').onclick = close;
    node.addEventListener('cancel',event => { event.preventDefault(); close(); });
    node.addEventListener('keydown',event => {
      event.stopPropagation();
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key !== 'Tab') return;
      const focusable = [...node.querySelectorAll('button,input,textarea,select,summary')].filter(el => !el.disabled && !el.hidden && el.getClientRects().length);
      const first = focusable[0], last = focusable[focusable.length-1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    node.querySelector('[data-support-delete]').onclick = () => {
      remove(formOwner,dialog.dataset.reportId); try { localStorage.removeItem(draftKey(formOwner)); } catch (_) {}
      const removed = dialog; dialog = null; if (removed.open && removed.close) removed.close(); removed.remove(); open(category);
    };
    node.querySelector('[data-support-preview]').onclick = async () => {
      const button = node.querySelector('[data-support-preview]'); button.disabled = true;
      try {
        const snapshot = load(formOwner)?.payload || (node.querySelector('input').checked ? await diag.snapshot() : {environment:{},events:[],dropped_events:0});
        if (dialog !== node || formOwner !== diag.owner()) return;
        const output = node.querySelector('[data-support-details]');
        output.hidden = false; output.textContent = JSON.stringify({environment:snapshot.environment,events:snapshot.events,dropped_events:snapshot.dropped_events},null,2);
      } finally { button.disabled = false; }
    };
    document.body.append(node);
    if (typeof node.showModal === 'function') node.showModal(); else { node.setAttribute('open',''); node.setAttribute('role','dialog'); node.setAttribute('aria-modal','true'); }
    if (saved) { lock(saved); tell('Есть неотправленный снимок. Повторная отправка использует те же сведения и не создаст дубликат.'); }
    else if (formOwner) {
      try { const receipt = JSON.parse(localStorage.getItem(receiptKey(formOwner))||'null');
        if (receipt && Date.now()-receipt.saved_at < MAX_AGE) tell(`Последний доставленный отчёт: ${diag.safeText(receipt.code,30)}.`);
      } catch (_) {}
    }
    node.querySelector('select').focus();
  }
  function showIssue() {
    if (!document.body || Date.now()-lastNotice < 60000 || dialog) return;
    lastNotice = Date.now();
    let notice = document.getElementById('pv-support-notice');
    if (!notice) {
      notice = document.createElement('aside'); notice.id = 'pv-support-notice'; notice.setAttribute('aria-label','Помощь при проблеме');
      notice.setAttribute('role','status'); notice.setAttribute('aria-live','polite');
      notice.innerHTML = '<button type="button" data-support-open>Проблема? Сообщить</button><button type="button" data-support-dismiss aria-label="Скрыть подсказку">×</button>';
      notice.querySelector('[data-support-dismiss]').onclick = () => notice.remove(); document.body.append(notice);
    }
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => notice.remove(),12000);
  }
  document.addEventListener('click',event => { if (event.target.closest?.('[data-support-open]')) { event.preventDefault(); open(event.target.closest('[data-support-open]').dataset.supportCategory); } });
  window.addEventListener('pv-support-issue',showIssue);
  async function retryPending() {
    if (!navigator.onLine) return;
    const owner = diag.owner(), report = load(owner);
    if (!owner || !report) return;
    try {
      const result = await transmit(report);
      if (dialog && dialog.dataset.reportId === report.payload.client_report_id && formOwner === owner && diag.owner() === owner) {
        tell(`Отчёт доставлен · ${result.code}. Спасибо!`);
        dialog.dataset.delivered = '1';
        dialog.querySelector('[data-support-send]').hidden = true; dialog.querySelector('[data-support-delete]').hidden = true;
      }
    } catch (error) { if (dialog && dialog.dataset.reportId === report.payload.client_report_id && formOwner === owner) tell(diag.safeText(error.message,240),true); }
  }
  window.addEventListener('pv-support-account',() => { close(); retryPending(); });
  window.addEventListener('online',retryPending);
  window.addEventListener('storage',event => {
    if (event.key?.startsWith('pv_support_pending_v1:')) pending.delete(event.key.slice('pv_support_pending_v1:'.length));
  });
  window.PVSupport = {open,close,isOpen:() => !!dialog};
  setTimeout(retryPending,0);
})();
