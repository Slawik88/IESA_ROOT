(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const initData = tg?.initData || '';
  const app = {
    state: null, house: null, month: '', page: 0, allMonths: false,
    draft: null, drafts: new Map(), saving: false, importPayload: null,
    importVersion: 0, loadVersion: 0, houseListVersion: 0, searchTimer: null, noticeTimer: null,
    showAllChores: false, view: 'home', filterSnapshot: null,
    filters: { kind: 'all', member: '', category: '', mode: 'all', sort: 'newest' },
  };
  const houseUI = window.createHouseWorkspace({ api, post, notice, refresh, onHouseChanged: loadHouses, showView,
    initialName: tg?.initDataUnsafe?.user?.first_name || '' });
  const receiptUI = window.createReceiptWorkspace({ api, post, notice, refresh });

  function icon(name) {
    const element = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    element.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `#i-${name}`);
    element.append(use);
    return element;
  }

  function categoryIcon(name = '') {
    const text = (name || '').toLowerCase();
    if (text.includes('продукт')) return 'bag';
    if (text.includes('хими') || text.includes('уборк')) return 'spark';
    if (text.includes('коммун')) return 'bulb';
    if (text.includes('ремонт')) return 'tool';
    return 'tag';
  }

  function emptyState(title, description, name = 'receipt') {
    const box = node('div', undefined, 'empty-state');
    box.append(icon(name), node('h3', title), node('p', description));
    return box;
  }

  function node(tag, text, cls) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  }

  function amount(kop, withCurrency = true) {
    const value = Math.abs(kop);
    const fraction = value % 100 || app.state?.currency === 'CHF' ? `,${String(value % 100).padStart(2, '0')}` : '';
    return `${kop < 0 ? '−' : ''}${Math.floor(value / 100).toLocaleString('ru-RU')}${fraction}${withCurrency ? ` ${app.state?.currency || ''}` : ''}`;
  }

  function decimal(kop) {
    return `${Math.floor(kop / 100)}.${String(kop % 100).padStart(2, '0')}`;
  }

  function dateLabel(value, options = { day: 'numeric', month: 'short' }) {
    return new Date(`${value}T12:00:00Z`).toLocaleDateString('ru-RU', { ...options, timeZone: 'UTC' });
  }

  function showView(view, focus = true) {
    app.view = view;
    for (const name of ['home', 'journal', 'more']) $(`${name}-view`).hidden = name !== view;
    document.querySelectorAll('.bottom-nav [data-view]').forEach(button => {
      if (button.dataset.view === view) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (focus) $(view === 'more' && !$('house-detail').hidden ? 'house-panel-title' : `${view}-title`).focus({ preventScroll: true });
    syncBackButton();
  }

  function syncBackButton() {
    if (document.querySelector('dialog[open]') || app.view !== 'home') tg?.BackButton?.show();
    else tg?.BackButton?.hide();
  }

  function updateDateSummary() {
    $('payment-hint').hidden = $('tx-mode').value !== 'personal';
    document.querySelectorAll('[data-payment]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.payment === $('tx-mode').value)));
    const date = $('tx-date').value;
    const label = date === app.state.today ? 'Сегодня' : date ? dateLabel(date, { day: 'numeric', month: 'long', year: 'numeric' }) : 'Указать дату';
    const month = app.draft?.kind === 'contribution' && $('tx-month').value
      ? ` · за ${dateLabel(`${$('tx-month').value}-01`, { month: 'long' })}` : '';
    $('date-summary').textContent = `${label}${month} · изменить дату`;
  }

  function saveLabel() {
    return app.draft?.editId ? 'Сохранить изменения' : app.draft?.kind === 'contribution' ? 'Внести деньги' : 'Записать расход';
  }

  function notice(text) {
    $('notice').textContent = text;
    $('notice').hidden = false;
    clearTimeout(app.noticeTimer);
    app.noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 6000);
  }

  async function api(path, options = {}) {
    const response = await fetch(`./api/${path}`, {
      ...options, credentials: 'omit', cache: 'no-store',
      headers: { Authorization: `tma ${initData}`, ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
      signal: AbortSignal.timeout(25000),
    });
    if (!response.ok) {
      let text = 'Не удалось выполнить действие. Попробуйте ещё раз.';
      try {
        const data = await response.json();
        if (typeof data.detail === 'string') text = data.detail;
      } catch { /* Сеть может вернуть HTML вместо ответа API. */ }
      if (response.status === 404) text = 'Вход недоступен. Откройте приложение заново из личного чата.';
      throw new Error(text);
    }
    return options.raw ? response : response.json();
  }

  async function busy(button, work) {
    if (button.disabled) return;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    try { await work(); }
    catch (error) { notice(error.message || 'Нет соединения. Введённые данные сохранены в форме.'); }
    finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      if (app.state && ['previous', 'next'].includes(button.id)) renderPager();
    }
  }

  function post(path, data) {
    return api(path, { method: 'POST', ...(data ? { body: JSON.stringify(data) } : {}) });
  }

  function selectionParams() {
    const params = new URLSearchParams();
    if (app.allMonths) params.set('all_months', 'true');
    else if (app.month) params.set('month', app.month);
    if ($('search').value.trim()) params.set('q', $('search').value.trim());
    for (const [key, value] of Object.entries(app.filters)) {
      if (value && value !== 'all') params.set(key, value);
    }
    return params;
  }

  async function refresh() {
    const house = app.house, version = ++app.loadVersion;
    const params = selectionParams();
    params.set('page', app.page);
    const data = await api(`houses/${house}?${params}`);
    if (house !== app.house || version !== app.loadVersion) return;
    app.state = data;
    app.month = data.month;
    app.page = data.page;
    render();
  }

  function row(title, meta, sum) {
    const wrapper = node('div', undefined, 'row'), left = node('div', undefined, 'row-content');
    left.append(node('div', title), node('div', meta, 'meta'));
    wrapper.append(left);
    if (sum !== undefined) wrapper.append(node('div', sum, 'sum'));
    return wrapper;
  }

  function action(label, work) {
    const button = node('button', label, 'quiet');
    button.type = 'button';
    button.onclick = () => busy(button, work);
    return button;
  }

  function syncOptions(id, options, title) {
    const selected = $(id).value;
    $(id).replaceChildren(new Option(title, ''));
    for (const option of options) $(id).add(new Option(option.name, option.id));
    if ([...$(id).options].some(option => option.value === selected)) $(id).value = selected;
  }

  function renderChores() {
    $('chores').replaceChildren();
    const own = app.state.cleaning.filter(day => day.tg_id === app.state.actor);
    $('cleaning-status').textContent = own.length ? 'К отметке' : 'Свободны';
    if (!own.length) $('chores').append(node('p', 'Сегодня можно выдохнуть. Незакрытых дней нет.', 'subtle'));
    const days = app.showAllChores ? own : own.slice(0, 1);
    for (const day of days) {
      const item = row(day.planned_date === app.state.today ? 'Сегодня ваша очередь' : `За ${dateLabel(day.planned_date)}`, day.planned_date === app.state.today ? 'Когда закончите — отметьте здесь' : 'Ещё не отмечено');
      item.append(action('Готово', async () => {
        await post(`houses/${app.house}/clean/${day.id}`);
        await refresh();
        notice('Уборка отмечена');
      }));
      $('chores').append(item);
    }
    if (own.length > 1) $('chores').append(action(app.showAllChores ? 'Свернуть' : `Ещё дней: ${own.length - 1}`, () => {
      app.showAllChores = !app.showAllChores;
      renderChores();
    }));
  }

  function renderPending() {
    $('pending-card').hidden = !app.state.pending.length;
    $('pending-count').textContent = app.state.pending.length;
    $('pending').replaceChildren();
    for (const entry of app.state.pending) {
      const item = row(entry.display_name, `За ${dateLabel(`${entry.month}-01`, { month: 'long', year: 'numeric' })}`, amount(entry.amount_kop));
      for (const [label, confirm] of [['Принять', true], ['Отклонить', false]]) item.append(action(label, async () => {
        await post(`houses/${app.house}/contributions/${entry.id}`, { confirm });
        await refresh();
      }));
      $('pending').append(item);
    }
  }

  function renderJournal() {
    const data = app.state;
    $('results-count').textContent = `Записей: ${data.total}${app.allMonths ? ' · за всё время' : ''}`;
    const filters = Object.values(app.filters).filter(value => !['', 'all', 'newest'].includes(value)).length + Number(app.allMonths);
    $('filter-label').textContent = `Фильтры${filters ? ` · ${filters}` : ''}`;
    $('clear-filters').hidden = !filters && !$('search').value;
    $('export-context').textContent = `${app.allMonths ? 'Всё время' : dateLabel(`${app.month}-01`, { month: 'long', year: 'numeric' })} · записей в выборке: ${data.total}`;
    $('summary').replaceChildren();
    for (const [key, label] of [['expenses', 'Траты'], ['contributions', 'Зачтённые взносы'],
      ['pending', 'Ждут подтверждения'], ['waiting_return', 'Ждут возврата']]) {
      const card = node('div');
      card.append(node('span', label, 'subtle'), node('strong', amount(data.summary[key])));
      $('summary').append(card);
    }
    $('history').replaceChildren();
    if (!data.rows.length) {
      const empty = emptyState('Пока ничего не нашли', 'Попробуйте другую дату или поиск по всей истории.', 'search');
      empty.append(action('Искать за всё время', async () => {
        app.allMonths = true;
        app.page = 0;
        await refresh();
      }));
      $('history').append(empty);
    }
    let previousDate = '';
    for (const entry of data.rows) {
      if (['newest', 'oldest'].includes(app.filters.sort) && entry.date !== previousDate) {
        $('history').append(node('h3', entry.date === data.today ? 'Сегодня' : dateLabel(entry.date, { day: 'numeric', month: 'long', year: 'numeric' }), 'day-heading'));
        previousDate = entry.date;
      }
      $('history').append(transactionRow(entry));
    }
    $('recent').replaceChildren();
    const recent = data.recent || [];
    for (const entry of recent) $('recent').append(transactionRow(entry));
    if (!recent.length) $('recent').append(emptyState('Здесь начнётся ваша история', 'Первая покупка или взнос появится здесь. Всё остальное уже готово.', 'wallet'));
    renderPager();
  }

  function transactionRow(entry) {
    const contribution = entry.kind === 'contribution';
    const status = { declared: 'ждёт подтверждения', rejected: 'отклонён', confirmed: 'зачтён' }[entry.status];
    const title = contribution ? 'Взнос' : entry.description || entry.category || 'Расход';
    const detail = contribution ? status : entry.mode === 'personal'
      ? (entry.reimbursed ? 'за свои · возвращено' : 'за свои · ждёт возврата') : 'из котла';
    const item = node('details', undefined, `entry${contribution ? ' incoming' : ''}`);
    const heading = node('summary');
    const content = node('span', undefined, 'row-content');
    const shortStatus = contribution && entry.status !== 'confirmed' ? `${status} · `
      : !contribution && entry.mode === 'personal' ? 'за свои · ' : '';
    content.append(node('span', title, 'entry-title'), node('span', `${shortStatus}${dateLabel(entry.date)} · ${entry.display_name || 'Жилец'}`, 'meta'));
    const glyph = node('span', undefined, 'entry-icon');
    glyph.append(icon(contribution ? 'wallet' : categoryIcon(entry.category)));
    heading.append(glyph, content,
      node('span', `${contribution ? entry.status === 'confirmed' ? '+' : '' : '−'}${amount(entry.amount_kop)}`, 'sum'));
    const expanded = node('div', undefined, 'entry-detail');
    expanded.append(node('p', `${entry.category ? `${entry.category} · ` : ''}${detail}${contribution ? ` · за ${entry.month}` : ''}`));
    if (entry.description) expanded.append(node('p', entry.description));
    const actions = node('div', undefined, 'row-actions');
    actions.append(action('Повторить', () => openForm(entry.kind, entry)));
    if (entry.can_edit) actions.append(action('Изменить', () => openForm('expense', entry, true)));
    if (!contribution) actions.append(action('Чеки', async () => { const loading = receiptUI.open(app.house, entry); syncBackButton(); await loading; }));
    if (!contribution && entry.mode === 'personal' && !entry.reimbursed && app.state.permissions.confirm_contributions) {
      actions.append(action('Вернуть из котла', async () => {
        if (!window.confirm(`Отметить возврат ${amount(entry.amount_kop)} для ${entry.display_name}? Сумма спишется из котла.`)) return;
        await post(`houses/${app.house}/expenses/${entry.id}/reimburse`, { version: entry.version });
        await refresh();
        notice('Возврат отмечен');
      }));
    }
    if (entry.can_edit) {
      const remove = action('Удалить', async () => {
        if (!window.confirm(`Удалить расход ${amount(entry.amount_kop)} за ${dateLabel(entry.date)}? Остаток пересчитается. Вернуть запись кнопкой отмены будет нельзя.`)) return;
        await post(`houses/${app.house}/expenses/${entry.id}/delete`, { version: entry.version });
        await refresh();
        notice('Расход удалён');
      });
      remove.classList.add('danger');
      actions.append(remove);
    }
    expanded.append(actions);
    item.append(heading, expanded);
    return item;
  }

  function renderPager() {
    const size = app.state.page_size;
    $('page').textContent = `${app.page + 1} / ${Math.max(1, Math.ceil(app.state.total / size))}`;
    $('previous').disabled = app.page === 0;
    $('next').disabled = (app.page + 1) * size >= app.state.total;
    $('page').parentElement.hidden = app.state.total <= size;
  }

  function renderDrafts() {
    $('drafts').replaceChildren();
    const drafts = [...app.drafts.values()].filter(draft => draft.house === app.house);
    $('drafts').hidden = !drafts.length;
    if (drafts.length) $('drafts').append(node('p', 'Вы не закончили запись', 'subtle'));
    for (const draft of drafts) $('drafts').append(action(
      draft.editId ? 'Продолжить правку' : draft.kind === 'expense' ? 'Продолжить расход' : 'Продолжить взнос',
      () => showDraft(draft),
    ));
  }

  function render() {
    const data = app.state;
    document.title = data.title;
    $('brand').textContent = data.title;
    $('house-name').textContent = data.house.name;
    $('gate').hidden = true;
    $('workspace').hidden = false;
    $('onboarding').replaceChildren();
    $('balance').textContent = amount(data.balance.balance, false);
    $('balance-currency').textContent = data.currency;
    $('balance-detail').textContent = `Внесено ${amount(data.balance.confirmed_total)} · потрачено и возвращено ${amount(data.balance.house_spent + data.balance.reimbursed)}`;
    $('today').textContent = dateLabel(data.today, { weekday: 'long', day: 'numeric', month: 'long' });
    $('month').value = app.month;
    $('month').disabled = app.allMonths;
    if (!$('filter-dialog').open) $('all-months').checked = app.allMonths;
    const people = new Map(data.members.map(member => [member.tg_id, { id: member.tg_id, name: member.display_name }]));
    for (const person of data.filter_members || []) people.set(person.id, person);
    if (!$('filter-dialog').open) {
      syncOptions('filter-member', [...people.values()], 'Все жильцы');
      syncOptions('filter-category', data.categories, 'Все категории');
    }
    $('import-area').hidden = !data.permissions.import_transactions;
    $('import-members').replaceChildren(...data.members.map(member => node('li', `${member.display_name}: ${member.tg_id}`)));
    renderChores();
    renderPending();
    renderJournal();
    renderDrafts();
    houseUI.setContext(data);
    $('quick-repeat').replaceChildren();
    $('quick-repeat').hidden = !data.templates.length;
    if (data.templates.length) $('quick-repeat').append(node('span', 'Повторить недавнее: ', 'subtle'));
    for (const entry of data.templates) $('quick-repeat').append(action(
      `${entry.kind === 'expense' ? entry.category || 'Трата' : 'Взнос'} · ${amount(entry.amount_kop)}`,
      () => openForm(entry.kind, entry),
    ));
  }

  function rememberDraft() {
    if (!app.draft) return;
    Object.assign(app.draft, {
      amount: $('tx-amount').value, date: $('tx-date').value, month: $('tx-month').value,
      category_id: $('tx-category').value ? Number($('tx-category').value) : null,
      mode: $('tx-mode').value, description: $('tx-description').value,
    });
    const hasContent = app.draft.amount.trim() || app.draft.description.trim() || app.draft.category_id
      || app.draft.mode === 'personal' || app.draft.date !== app.state.today;
    if (hasContent) app.drafts.set(app.draft.request_id, { ...app.draft });
    else app.drafts.delete(app.draft.request_id);
    updateDateSummary();
    if (app.drafts.size) tg?.enableClosingConfirmation?.();
    else tg?.disableClosingConfirmation?.();
  }

  function showDraft(draft) {
    app.draft = { ...draft };
    $('transaction-form').reset();
    $('form-error').textContent = '';
    $('form-title').textContent = draft.editId ? 'Изменить расход' : draft.kind === 'expense' ? 'Записать расход' : 'Внести деньги';
    $('form-currency').textContent = app.state.currency;
    $('save-transaction').textContent = saveLabel();
    $('date-details').open = draft.date !== app.state.today || (draft.kind === 'contribution' && draft.month !== app.state.today.slice(0, 7));
    document.querySelector('.form-extras').open = false;
    $('expense-fields').hidden = draft.kind !== 'expense';
    $('tx-month-label').hidden = draft.kind !== 'contribution';
    $('tx-month').required = draft.kind === 'contribution';
    $('tx-date').max = app.state.today;
    $('tx-amount').value = draft.amount || '';
    $('tx-date').value = draft.date;
    $('tx-month').value = draft.month;
    $('tx-mode').value = draft.mode;
    $('tx-description').value = draft.description;
    $('tx-category').value = draft.category_id || '';
    $('category-picker').open = false;
    renderCategoryPicker();
    $('save-another').hidden = !!draft.editId;
    $('save-hint').textContent = draft.editId
      ? 'Правка сохранит историю изменений. Если запись уже изменили, она не будет перезаписана.'
      : draft.kind === 'contribution' ? 'Взнос будет зачтён по правилам дома.' : '«За свои» ждёт возврата, «Из котла» уменьшает общий остаток.';
    $('quick-amounts').replaceChildren();
    const amounts = [...new Set(app.state.templates.filter(entry => entry.kind === draft.kind).map(entry => entry.amount_kop))];
    for (const kop of amounts.slice(0, 4)) $('quick-amounts').append(action(amount(kop), () => {
      $('tx-amount').value = decimal(kop);
      rememberDraft();
    }));
    rememberDraft();
    if (!$('transaction-dialog').open) $('transaction-dialog').showModal();
    $('tx-amount').focus();
    tg?.BackButton?.show();
  }

  function renderCategoryPicker() {
    const selected = $('tx-category').value;
    const choices = [{ id: '', name: 'Без категории' }, ...app.state.categories];
    $('category-label').textContent = choices.find(category => String(category.id) === selected)?.name || 'Без категории';
    $('category-options').replaceChildren();
    for (const category of choices) {
      const button = action(category.name, () => {
        $('tx-category').value = category.id;
        $('category-picker').open = false;
        renderCategoryPicker();
        rememberDraft();
      });
      button.prepend(icon(categoryIcon(category.name)));
      button.setAttribute('aria-pressed', String(String(category.id) === selected));
      $('category-options').append(button);
    }
  }

  function openForm(kind, seed = null, edit = false) {
    if (!seed) {
      const unfinished = [...app.drafts.values()].find(draft => draft.house === app.house && draft.kind === kind && !draft.editId);
      if (unfinished) return showDraft(unfinished);
    }
    if (edit) {
      const unfinished = [...app.drafts.values()].find(draft => draft.house === app.house && draft.editId === seed.id);
      if (unfinished) return showDraft(unfinished);
    }
    showDraft({ request_id: crypto.randomUUID(), house: app.house, kind,
      amount: seed ? decimal(seed.amount_kop) : '', date: edit ? seed.date : app.state.today,
      month: edit ? seed.month : app.state.today.slice(0, 7), mode: seed?.mode || 'house',
      category_id: seed?.category_id || null, description: seed?.description || '',
      editId: edit ? seed.id : null, version: edit ? seed.version : null });
  }

  function closeForm(discard = false) {
    if (app.saving) return;
    if (discard) app.drafts.delete(app.draft?.request_id);
    else rememberDraft();
    $('transaction-dialog').close();
    app.draft = null;
    syncBackButton();
    if (!app.drafts.size) tg?.disableClosingConfirmation?.();
    renderDrafts();
  }

  async function submit(event) {
    event.preventDefault();
    if (app.saving) return;
    app.saving = true;
    $('transaction-fields').disabled = true;
    $('transaction-form').setAttribute('aria-busy', 'true');
    $('save-transaction').textContent = 'Сохраняю…';
    $('save-transaction').disabled = $('save-another').disabled = true;
    $('form-error').textContent = '';
    rememberDraft();
    const saved = { ...app.draft }, another = event.submitter?.id === 'save-another';
    const payload = { ...saved, month: saved.kind === 'expense' ? saved.date.slice(0, 7) : saved.month,
      description: saved.kind === 'expense' ? saved.description : '' };
    try {
      const path = saved.editId ? `houses/${saved.house}/expenses/${saved.editId}/edit` : `houses/${saved.house}/transactions`;
      const result = await post(path, payload);
      app.drafts.delete(saved.request_id);
      app.draft = null;
      $('transaction-dialog').close();
      syncBackButton();
      if (!app.drafts.size) tg?.disableClosingConfirmation?.();
      renderDrafts();
      let refreshed = true;
      try { await refresh(); }
      catch { refreshed = false; }
      if (another && app.house === saved.house && app.state?.house.id === saved.house) {
        showDraft({ ...saved, request_id: crypto.randomUUID(), amount: '', date: app.state.today,
          month: app.state.today.slice(0, 7), editId: null, version: null });
      }
      notice(refreshed ? (saved.editId ? 'Изменения сохранены' : result.status === 'declared' ? 'Взнос ждёт подтверждения' : 'Запись сохранена')
        : 'Запись сохранена. Список пока не обновился — нажмите «Обновить».');
    } catch (error) {
      $('form-error').textContent = error.message || 'Нет соединения. Поля сохранены; можно повторить отправку.';
      $('form-error').focus();
    } finally {
      app.saving = false;
      $('transaction-fields').disabled = false;
      $('transaction-form').removeAttribute('aria-busy');
      $('save-transaction').textContent = saveLabel();
      $('save-transaction').disabled = $('save-another').disabled = false;
      if (another && app.draft) $('tx-amount').focus();
    }
  }

  function resetFilters() {
    $('search').value = '';
    for (const [id, value] of [['filter-kind', 'all'], ['filter-member', ''], ['filter-category', ''],
      ['filter-mode', 'all'], ['filter-sort', 'newest']]) $(id).value = value;
    app.filters = { kind: 'all', member: '', category: '', mode: 'all', sort: 'newest' };
  }

  function commitFilters() {
    for (const key of Object.keys(app.filters)) app.filters[key] = $(`filter-${key}`).value;
    app.filterSnapshot = null;
  }

  async function filterChanged() {
    app.page = 0;
    try { await refresh(); } catch (error) { notice(error.message); }
  }

  function shiftMonth(delta) {
    const [year, month] = (app.month || app.state.today.slice(0, 7)).split('-').map(Number);
    const date = new Date(Date.UTC(year, month - 1 + delta, 1));
    if (!Number.isFinite(date.getTime()) || date.getUTCFullYear() < 1 || date.getUTCFullYear() > 9999) return notice('Выберите месяц от 0001 до 9999 года');
    app.month = date.toISOString().slice(0, 7);
    app.allMonths = false;
    return filterChanged();
  }

  async function changeHouse() {
    app.houseListVersion++;
    $('house-switch-dialog').close();
    app.house = Number($('house').value);
    app.importVersion++;
    app.importPayload = null;
    app.page = 0;
    app.month = '';
    app.allMonths = false;
    app.showAllChores = false;
    showView('home', false);
    resetFilters();
    $('workspace').hidden = true;
    $('gate').hidden = false;
    $('gate-text').textContent = 'Открываю выбранный дом…';
    $('import-preview').hidden = true;
    $('import-file').value = '';
    try { await refresh(); }
    catch (error) { $('gate-text').textContent = error.message; }
  }

  async function loadHouses(selected) {
    const version = ++app.houseListVersion;
    const data = await api('houses');
    if (version !== app.houseListVersion) return;
    $('house').replaceChildren();
    for (const house of data.houses) $('house').add(new Option(house.name, house.id));
    if (!data.houses.length) {
      app.house = null;
      app.state = null;
      $('workspace').hidden = true;
      $('gate').hidden = false;
      $('gate-text').textContent = 'Создайте пространство для своего дома или присоединитесь к соседям.';
      houseUI.reset();
      houseUI.showOnboarding();
      return;
    }
    if (data.houses.some(house => house.id === selected)) $('house').value = selected;
    await changeHouse();
  }

  async function exportFile(button) {
    const format = button.dataset.export, period = $('export-period').value;
    const params = period === 'selection' ? selectionParams() : new URLSearchParams();
    if (period === 'month') params.set('month', app.month);
    const response = await api(`houses/${app.house}/export/${format}?${params}`, { raw: true });
    await downloadFile(response, `operations-${period === 'all' || app.allMonths ? 'all' : app.month}.${format}`);
  }

  async function downloadFile(response, filename) {
    const url = URL.createObjectURL(await response.blob()), link = node('a');
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    notice('Файл подготовлен');
  }

  function cancelImport() {
    app.importVersion++;
    app.importPayload = null;
    $('import-preview').hidden = true;
    $('import-file').value = '';
  }

  async function importSelected() {
    const version = ++app.importVersion, house = app.house;
    app.importPayload = null;
    $('import-preview').hidden = true;
    const file = $('import-file').files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) return notice('Максимальный размер — 2 МБ');
    const extension = file.name.split('.').pop().toLowerCase();
    if (!['csv', 'tsv', 'json'].includes(extension)) return notice('Выберите CSV, TSV или JSON');
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 16384) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
      }
      if (house !== app.house || version !== app.importVersion) return;
      const payload = { extension, content: btoa(binary) };
      const preview = await post(`houses/${house}/import/preview`, payload);
      if (house !== app.house || version !== app.importVersion) return;
      $('import-summary').textContent = `Новых: ${preview.new} · дублей: ${preview.duplicates} · ошибок: ${preview.error_count}. Изменение котла: ${amount(preview.balance_delta)}`;
      $('import-errors').textContent = preview.errors.join('\n');
      $('import-preview').hidden = false;
      $('import-confirm').disabled = preview.error_count > 0 || preview.new === 0;
      if (!preview.error_count && preview.new) app.importPayload = payload;
    } catch (error) {
      if (version === app.importVersion) notice(error.message);
    }
  }

  async function confirmImport() {
    if (!app.importPayload) return;
    $('import-file').disabled = $('house').disabled = $('import-cancel').disabled = true;
    try {
      const result = await post(`houses/${app.house}/import/confirm`, app.importPayload);
      cancelImport();
      await refresh();
      notice(`Добавлено: ${result.added}, дублей: ${result.duplicates}`);
    } finally {
      $('import-file').disabled = $('house').disabled = $('import-cancel').disabled = false;
    }
  }

  $('close-form').onclick = () => closeForm();
  $('discard-draft').onclick = () => closeForm(true);
  $('transaction-dialog').addEventListener('cancel', event => { event.preventDefault(); closeForm(); });
  $('transaction-form').oninput = rememberDraft;
  $('transaction-form').onsubmit = submit;
  tg?.BackButton?.onClick(() => {
    if ($('transaction-dialog').open) closeForm();
    else if (document.querySelector('dialog[open]')) { document.querySelector('dialog[open]').close(); syncBackButton(); }
    else if (app.view === 'more' && houseUI.back()) $('more-title').focus();
    else showView('home');
  });
  document.querySelectorAll('[data-close]').forEach(button => { button.onclick = () => $(button.dataset.close).close(); });
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('close', syncBackButton));
  $('balance-info').onclick = () => { $('balance-dialog').showModal(); syncBackButton(); };
  $('open-house').onclick = () => { $('house-switch-dialog').showModal(); syncBackButton(); };
  document.querySelectorAll('[data-payment]').forEach(button => { button.onclick = () => { $('tx-mode').value = button.dataset.payment; rememberDraft(); }; });
  document.querySelectorAll('[data-view]').forEach(button => { button.onclick = () => showView(button.dataset.view); });
  $('journal-add').onclick = () => openForm('expense');
  $('journal-files').onclick = () => {
    showView('more');
    houseUI.open('files');
    $('export-details').open = true;
    $('files-card').scrollIntoView({ block: 'start' });
  };
  $('open-filters').onclick = () => {
    app.filterSnapshot = Object.fromEntries(['filter-kind', 'filter-member', 'filter-category', 'filter-mode', 'filter-sort']
      .map(id => [id, $(id).value]));
    $('all-months').checked = app.allMonths;
    $('filter-dialog').showModal();
    syncBackButton();
  };
  $('close-filters').onclick = () => { $('filter-dialog').close(); syncBackButton(); };
  $('filter-dialog').addEventListener('close', () => {
    if (app.filterSnapshot) {
      for (const [id, value] of Object.entries(app.filterSnapshot)) $(id).value = value;
      $('all-months').checked = app.allMonths;
      app.filterSnapshot = null;
    }
    syncBackButton();
  });
  $('apply-filters').onclick = async () => {
    commitFilters();
    app.allMonths = $('all-months').checked;
    $('filter-dialog').close();
    syncBackButton();
    await filterChanged();
  };
  $('add-expense').onclick = () => openForm('expense');
  $('add-contribution').onclick = () => openForm('contribution');
  $('date-today').onclick = () => { $('tx-date').value = app.state.today; rememberDraft(); };
  $('date-yesterday').onclick = () => {
    const day = new Date(`${app.state.today}T12:00:00Z`);
    day.setUTCDate(day.getUTCDate() - 1);
    $('tx-date').value = day.toISOString().slice(0, 10);
    rememberDraft();
  };
  $('house').onchange = changeHouse;
  $('month').onchange = () => { app.month = $('month').value || app.state.today.slice(0, 7); filterChanged(); };
  $('month-back').onclick = () => shiftMonth(-1);
  $('month-next').onclick = () => shiftMonth(1);
  $('month-today').onclick = () => {
    commitFilters();
    app.month = app.state.today.slice(0, 7);
    app.allMonths = false;
    $('filter-dialog').close();
    filterChanged();
  };
  $('search').oninput = () => { clearTimeout(app.searchTimer); app.searchTimer = setTimeout(filterChanged, 250); };
  $('clear-filters').onclick = () => { resetFilters(); app.allMonths = false; filterChanged(); };
  $('tx-date').onchange = rememberDraft;
  $('tx-month').onchange = rememberDraft;
  for (const id of ['tx-date', 'tx-month']) $(id).addEventListener('invalid', () => { $('date-details').open = true; });
  $('previous').onclick = () => busy($('previous'), async () => { app.page = Math.max(0, app.page - 1); await refresh(); });
  $('next').onclick = () => busy($('next'), async () => { app.page++; await refresh(); });
  $('reload').onclick = () => busy($('reload'), refresh);
  document.querySelectorAll('[data-export]').forEach(button => { button.onclick = () => busy(button, () => exportFile(button)); });
  document.querySelectorAll('[data-template]').forEach(button => {
    button.onclick = () => busy(button, async () => downloadFile(
      await api(`houses/${app.house}/template/${button.dataset.template}`, { raw: true }), `template.${button.dataset.template}`,
    ));
  });
  $('import-file').onchange = importSelected;
  $('import-cancel').onclick = cancelImport;
  $('import-confirm').onclick = () => busy($('import-confirm'), confirmImport);
  const connection = () => { $('connection').hidden = navigator.onLine; };
  window.addEventListener('online', connection);
  window.addEventListener('offline', connection);
  connection();

  (async () => {
    if (!initData) return;
    tg?.ready();
    tg?.expand();
    try {
      await loadHouses();
    } catch (error) { $('gate-text').textContent = error.message; }
  })();
})();
