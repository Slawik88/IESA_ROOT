'use strict';

window.createHouseWorkspace = ({ api, post, notice, refresh, onHouseChanged, showView, initialName = '' }) => {
  const $ = id => document.getElementById(id);
  let context = null, panel = null, generation = 0;
  const titles = { people: 'Люди и приглашения', schedule: 'График уборки', money: 'Деньги и категории', notifications: 'Мои уведомления', settings: 'Настройки дома', add: 'Ещё один дом', files: 'Записи и файлы' };
  const weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
  const node = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  };
  const base = data => `houses/${data.house.id}`;
  const current = data => context?.house.id === data.house.id;

  function button(text, work, cls = 'secondary') {
    const item = node('button', text, cls);
    item.type = 'button';
    item.onclick = async () => {
      if (item.disabled) return;
      item.disabled = true;
      item.setAttribute('aria-busy', 'true');
      try { await work(); }
      catch (error) { notice(error.message || 'Нет соединения. Попробуйте ещё раз.'); }
      finally { item.disabled = false; item.removeAttribute('aria-busy'); }
    };
    return item;
  }

  function input(label, { value = '', type = 'text', maxLength, placeholder = '', required = true } = {}) {
    const wrapper = node('label', label), control = node('input');
    control.type = type;
    control.value = value;
    control.required = required;
    control.placeholder = placeholder;
    if (maxLength) control.maxLength = maxLength;
    wrapper.append(control);
    return { wrapper, control };
  }

  function select(label, choices, value) {
    const wrapper = node('label', label), control = node('select');
    for (const choice of choices) control.add(new Option(choice.label, choice.value));
    control.value = String(value ?? '');
    wrapper.append(control);
    return { wrapper, control };
  }

  function form(fields, label, work) {
    const element = node('form', undefined, 'panel-form'), group = node('fieldset');
    const submit = node('button', label), error = node('p', '', 'error');
    submit.type = 'submit';
    error.role = 'alert';
    error.tabIndex = -1;
    group.append(...fields, submit);
    element.append(group, error);
    element.onsubmit = async event => {
      event.preventDefault();
      if (group.disabled) return;
      group.disabled = true;
      submit.setAttribute('aria-busy', 'true');
      error.textContent = '';
      try { await work(); }
      catch (failure) {
        error.textContent = failure.message || 'Нет соединения. Введённые поля сохранены.';
        if (error.isConnected) error.focus();
      } finally { group.disabled = false; submit.removeAttribute('aria-busy'); }
    };
    return element;
  }

  function section(title, description) {
    const box = node('section', undefined, 'panel-section');
    if (title) box.append(node('h3', title));
    if (description) box.append(node('p', description, 'subtle'));
    return box;
  }

  function home() {
    panel = null;
    generation++;
    $('house-menu').hidden = false;
    $('house-detail').hidden = true;
    $('files-card').hidden = true;
    $('house-content').replaceChildren();
    $('more-view').classList.remove('has-panel');
  }

  async function open(name) {
    panel = name;
    const version = ++generation, house = context?.house.id;
    $('house-menu').hidden = true;
    $('house-detail').hidden = false;
    $('files-card').hidden = name !== 'files';
    $('house-panel-title').textContent = titles[name] || 'Ваш дом';
    $('more-view').classList.add('has-panel');
    $('house-panel-title').focus({ preventScroll: true });
    const content = $('house-content');
    content.replaceChildren();
    if (name === 'files') return;
    if (name === 'add') return renderMembership(content);
    content.append(node('p', 'Открываем…', 'subtle'));
    try {
      const data = await api(`houses/${house}/management`);
      if (version !== generation || house !== context?.house.id) return;
      content.replaceChildren();
      ({ people: renderPeople, schedule: renderSchedule, money: renderMoney, notifications: renderNotifications, settings: renderSettings })[name](content, data);
    } catch (error) {
      if (version !== generation) return;
      content.replaceChildren(node('p', error.message, 'error'), button('Попробовать ещё раз', () => open(name)));
    }
  }

  function renderMembership(container) {
    container.replaceChildren();
    const choice = section('Добавить дом', 'Создайте дом или войдите по приглашению. Данные разных домов не смешиваются.');
    const actions = node('div', undefined, 'payment-switch membership-choices');
    const target = node('div');
    const choose = joining => {
      [...actions.children].forEach((item, index) => item.setAttribute('aria-pressed', String(Boolean(index) === joining)));
      target.replaceChildren();
      const display = input('Ваше имя в доме', { value: context?.members.find(member => member.tg_id === context.actor)?.display_name || initialName, maxLength: 32 });
      const key = input(joining ? 'Код или ссылка приглашения' : 'Название дома', { maxLength: joining ? 2048 : 32, placeholder: joining ? 'Вставьте приглашение' : 'Например, Дом на Садовой' });
      target.append(form([key.wrapper, display.wrapper], joining ? 'Присоединиться' : 'Создать дом', async () => {
        const result = await post(joining ? 'houses/join' : 'houses', joining
          ? { invite_token: key.control.value.trim(), display_name: display.control.value.trim() }
          : { name: key.control.value.trim(), display_name: display.control.value.trim() });
        await onHouseChanged(result.house_id);
        notice(joining ? result.joined ? 'Вы вступили в дом' : 'Вы уже живёте в этом доме'
          : result.created ? 'Дом создан' : 'Открыли ваш существующий дом');
      }));
    };
    actions.append(button('Новый дом', () => choose(false)), button('Приглашение', () => choose(true)));
    choice.append(actions);
    container.append(choice, target);
    choose(false);
  }

  function renderPeople(container, data) {
    if (data.permissions.manage_members) {
      const invite = section('Пригласить соседей', 'Отправьте код человеку, с которым живёте. Он сможет вступить в этот дом на сайте.');
      invite.append(button('Показать приглашение', async () => {
        const result = await api(`${base(data)}/invite`);
        if (!current(data)) return;
        const field = input('Код приглашения', { value: result.invite_token, required: false });
        field.control.readOnly = true;
        const actions = node('div', undefined, 'file-row');
        actions.append(button('Скопировать код', async () => {
          try { await navigator.clipboard.writeText(field.control.value); notice('Код скопирован'); }
          catch { field.control.focus(); field.control.select(); notice('Выделили код — скопируйте его'); }
        }), button('Обновить код', async () => {
          if (!window.confirm('Создать новый код? Старые приглашения перестанут работать. Жильцы останутся в доме.')) return;
          const changed = await post(`${base(data)}/invite/rotate`);
          if (current(data)) field.control.value = changed.invite_token;
        }));
        invite.replaceChildren(node('h3', 'Приглашение в дом'), node('p', 'Делитесь только с будущими жильцами.', 'subtle'), field.wrapper, actions);
      }));
      container.append(invite);
    }
    const people = section('Жильцы');
    for (const member of data.members) {
      const person = node('div', undefined, 'person'), heading = node('div', undefined, 'section-title');
      const name = node('div');
      name.append(node('h3', member.display_name), node('p', member.role === 'owner' ? 'Владелец дома' : member.tg_id === data.actor ? 'Это вы' : 'Жилец', 'subtle'));
      heading.append(name);
      person.append(heading);
      if (member.can_manage) {
        const permissions = node('details'), title = node('summary', 'Доступ и права');
        permissions.append(title);
        for (const definition of data.permission_definitions) {
          const label = node('label', undefined, 'permission-row'), control = node('input');
          control.type = 'checkbox';
          control.checked = member.grants.includes(definition.code);
          const description = node('span', definition.label);
          description.append(node('small', definition.hint));
          label.append(control, description);
          control.onchange = async () => {
            const wanted = control.checked;
            if (!window.confirm(`${wanted ? 'Разрешить' : 'Запретить'} «${definition.label}» для ${member.display_name}?`)) { control.checked = !wanted; return; }
            control.disabled = true;
            try {
              await post(`${base(data)}/members/${member.tg_id}/permissions/${definition.code}`, { granted: wanted });
              notice('Права обновлены');
            } catch (error) { control.checked = !wanted; notice(error.message); }
            finally { control.disabled = false; }
          };
          permissions.append(label);
        }
        person.append(permissions);
      }
      people.append(person);
    }
    container.append(people);
  }

  function renderSchedule(container, data) {
    const panelVersion = generation;
    const schedule = section('Дни недели', 'Каждому жильцу можно выбрать день. Изменения касаются будущих открытых дней; прошлые отметки останутся в истории.');
    const fields = [];
    for (const member of data.members) {
      const item = select(member.display_name, [{ value: '', label: 'Без дня' }, ...weekdays.map((label, value) => ({ value, label }))], data.schedule.weekday_map[member.tg_id]);
      item.control.disabled = !data.permissions.manage_schedule;
      item.wrapper.classList.add('schedule-row');
      fields.push({ member, ...item });
    }
    if (data.permissions.manage_schedule) schedule.append(form(fields.map(item => item.wrapper), 'Сохранить график', async () => {
      const result = await post(`${base(data)}/schedule`, { version: data.schedule.version, weekday_map: Object.fromEntries(fields.map(item => [item.member.tg_id, item.control.value === '' ? null : Number(item.control.value)])) });
      data.schedule.version = result.version;
      await refresh();
      if (current(data) && generation === panelVersion) await loadDays();
      notice('График обновлён');
    }));
    else schedule.append(...fields.map(item => item.wrapper));
    container.append(schedule);
    const history = section('Дни и отметки', `Показан ${new Date(`${data.schedule.month}-01T12:00:00Z`).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' })}.`);
    const month = input('Месяц истории', { type: 'month', value: data.schedule.month });
    history.append(month.wrapper);
    const list = node('div', undefined, 'schedule-history');
    let historyGeneration = 0;
    const loadDays = async () => {
      if (!month.control.value) return;
      const request = ++historyGeneration;
      const snapshot = await api(`${base(data)}/management?month=${month.control.value}`);
      if (request === historyGeneration && current(data) && generation === panelVersion) renderDays(snapshot);
    };
    const renderDays = snapshot => {
      list.replaceChildren();
      if (!snapshot.schedule.history.length) list.append(node('p', 'Дней за этот месяц пока нет.', 'subtle'));
      for (const day of snapshot.schedule.history) {
        const item = node('div', undefined, 'row'), text = node('div', undefined, 'row-content');
        const date = new Date(`${day.planned_date}T12:00:00Z`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' });
        text.append(node('div', `${day.display_name} · ${date}`), node('span', { open: day.planned_date > snapshot.schedule.today ? 'Впереди' : 'Ждёт отметки', done: 'Убрано', canceled: 'Пропущено' }[day.status], 'meta'));
        item.append(text);
        if (day.status === 'open' && day.planned_date <= snapshot.schedule.today && (day.tg_id === data.actor || data.permissions.close_others_days)) {
          const actions = node('div', undefined, 'row-actions');
          actions.append(button('Отметить уборку', async () => {
            await post(`${base(data)}/cleaning/${day.id}/close`);
            await refresh();
            if (current(data) && generation === panelVersion) await loadDays();
          }));
          if (data.permissions.close_others_days) actions.append(button('Пропустить', async () => {
            if (!window.confirm(`Отметить день ${date} для ${day.display_name} как пропущенный?`)) return;
            await post(`${base(data)}/cleaning/${day.id}/cancel`);
            await refresh();
            if (current(data) && generation === panelVersion) await loadDays();
          }));
          item.append(actions);
        }
        list.append(item);
      }
    };
    month.control.onchange = async () => {
      try { await loadDays(); }
      catch (error) { notice(error.message); }
    };
    renderDays(data);
    history.append(list);
    container.append(history);
  }

  function settingControl(definition, value, notification = false) {
    if (definition.kind === 'bool') return select(definition.label, [{ value: 'true', label: 'Включено' }, { value: 'false', label: 'Выключено' }], String(value));
    const labels = notification ? { private: 'Личный чат', chat: 'Общий чат дома', off: 'Не присылать' } : definition.choice_labels;
    return select(definition.label, definition.choices.map(choice => ({ value: choice, label: labels?.[choice] ?? String(choice) })), value);
  }

  function settingRow(data, definition, value, notification = false) {
    let savedValue = value;
    const item = node('div', undefined, 'settings-row');
    const field = settingControl(definition, value, notification);
    const canEdit = notification || data.permissions.manage_house_settings;
    if (!canEdit) {
      const label = definition.kind === 'bool' ? value ? 'Включено' : 'Выключено' : definition.choice_labels?.[value] ?? String(value);
      item.append(node('h3', definition.label), node('p', label, 'subtle'));
      return item;
    }
    item.append(form([field.wrapper], 'Сохранить', async () => {
      const selected = definition.kind === 'bool' ? field.control.value === 'true'
        : typeof definition.default === 'number' ? Number(field.control.value) : field.control.value;
      if (definition.key === 'currency' && selected !== savedValue && !window.confirm('Изменить обозначение валюты у всех записей дома? Суммы останутся прежними — пересчёта по курсу не будет.')) return;
      await post(`${base(data)}/${notification ? 'notifications' : 'settings'}/${definition.key}`, { value: selected });
      savedValue = selected;
      await refresh();
      notice('Сохранено');
    }));
    return item;
  }

  function renderMoney(container, data) {
    const panelVersion = generation;
    const currency = data.house_setting_definitions.find(item => item.key === 'currency');
    container.append(settingRow(data, currency, data.house_settings.currency));
    const categories = section('Категории расходов', 'Названия помогают находить покупки в истории. Категория с расходами не удаляется.');
    const list = node('div');
    categories.append(list);
    const updateCategories = async () => {
      await refresh();
      const latest = await api(`${base(data)}/management`);
      if (current(data) && generation === panelVersion) renderCategories(latest.categories);
    };
    const renderCategories = rows => {
      list.replaceChildren();
      for (const category of rows) {
      const row = node('div', undefined, 'row');
      row.append(node('span', category.name));
      if (data.permissions.manage_categories) row.append(button('Убрать', async () => {
        if (!window.confirm(`Убрать категорию «${category.name}»?`)) return;
        await post(`${base(data)}/categories/${category.id}/delete`);
        await updateCategories();
      }, 'text-button'));
        list.append(row);
      }
    };
    renderCategories(data.categories);
    if (data.permissions.manage_categories) {
      const name = input('Новая категория', { maxLength: 24, placeholder: 'Например, Для кухни' });
      categories.append(form([name.wrapper], 'Добавить категорию', async () => {
        await post(`${base(data)}/categories`, { name: name.control.value.trim() });
        await updateCategories();
        name.control.value = '';
        notice('Категория добавлена');
      }));
    }
    container.append(categories);
  }

  function renderNotifications(container, data) {
    container.append(node('p', 'Это только ваши настройки. Уведомления приходят в личный чат или общий чат дома, если он подключён.', 'panel-note'));
    if (!data.house.chat_bound) container.append(node('p', 'Общий чат пока не подключён. Чтобы получать сообщения сейчас, выбирайте «Личный чат».', 'panel-note'));
    for (const definition of data.notify_setting_definitions) container.append(settingRow(data, definition, data.notify_settings[definition.key], true));
  }

  function renderSettings(container, data) {
    if (data.permissions.manage_house_settings) {
      const identity = section('Название дома');
      const houseName = input('Как называется ваш дом', { value: data.house.name, maxLength: 32 });
      identity.append(form([houseName.wrapper], 'Сохранить название', async () => {
        await post(`${base(data)}/name`, { name: houseName.control.value.trim() });
        data.house.name = houseName.control.value.trim();
        await refresh();
        notice('Название обновлено');
      }));
      container.append(identity);
    }
    const profile = section('Как к вам обращаться');
    const name = input('Ваше имя в этом доме', { value: data.profile.display_name, maxLength: 32 });
    profile.append(form([name.wrapper], 'Сохранить имя', async () => {
      await post(`${base(data)}/profile`, { display_name: name.control.value.trim() });
      await refresh();
      notice('Имя обновлено');
    }));
    container.append(profile);
    if (!data.permissions.manage_house_settings) container.append(node('p', 'Правила дома меняет владелец или участник с соответствующим доступом.', 'panel-note'));
    for (const definition of data.house_setting_definitions.filter(item => item.key !== 'currency')) container.append(settingRow(data, definition, data.house_settings[definition.key]));
    if (data.profile.can_leave) {
      const leave = node('div', undefined, 'danger-zone');
      leave.append(node('h3', 'Выйти из дома'), node('p', 'Доступ к данным этого дома закроется. Старые записи сохранятся у жильцов.', 'subtle'), button('Выйти из дома', async () => {
        if (!window.confirm(`Выйти из «${data.house.name}»? Вы потеряете доступ к этому дому.`)) return;
        await post(`${base(data)}/leave`);
        await onHouseChanged(null);
      }, 'danger'));
      container.append(leave);
    }
  }

  $('house-back').onclick = () => { home(); $('more-title').focus(); };
  document.querySelectorAll('[data-house-panel]').forEach(item => {
    item.onclick = () => {
      document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
      showView('more');
      open(item.dataset.housePanel);
    };
  });

  return {
    open, home,
    reset() { context = null; home(); },
    back() { if (!panel) return false; home(); return true; },
    showOnboarding() { renderMembership($('onboarding')); },
    setContext(data) {
      if (context && context.house.id !== data.house.id) home();
      context = data;
      $('more-title').textContent = 'Дом';
      $('members-count').textContent = `Жильцов: ${data.members.length}`;
      $('house-currency-label').textContent = `Валюта дома · ${data.currency}`;
    },
  };
};
