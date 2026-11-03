// Дом: список разделов и подэкраны (жильцы, график, деньги, уведомления, настройки, ещё один дом).
import { locale, t } from '../i18n.js';
import { formatMonth, shiftMonth, weekdayName } from '../format.js';
import { app, day, nav } from '../state.js';
import { loadHouses, refresh } from '../data.js';
import { telegram } from '../telegram.js';
import { avatar, busy, button, confirmSheet, emptyState, errorText, fail, h, icon, iconButton, openSheet, segmented, selectField,
  skeleton, switchRow, textField, toast } from '../ui.js';
import { renderMembership } from './onboarding.js';

const WEEK = [0, 1, 2, 3, 4, 5, 6];
const MEMBER_NAME_LIMIT = 32;
const HOUSE_NAME_LIMIT = 32;
const CATEGORY_LIMIT = 24;
let generation = 0;

const titles = () => ({
  people: t("Жильцы"), schedule: t("График уборки"), money: t("Деньги и категории"),
  notifications: t("Мои уведомления"), settings: t("Настройки дома"), add: t("Ещё один дом"),
});

const base = () => `houses/${app.houseId}`;

function linkRow({ iconName, title, meta, onClick }) {
  return h('button', { type: 'button', class: 'group-row', onClick },
    h('span', { class: 'row-icon' }, icon(iconName)),
    h('span', { class: 'row-main' }, h('span', { class: 'row-title' }, title), meta ? h('span', { class: 'row-meta' }, meta) : null),
    icon('chevron-right', 'row-chevron'));
}

function renderHub(root) {
  const { data } = app;
  const me = data.members.find(member => member.tg_id === data.actor);
  const open = name => () => nav.go('house', name);
  const reload = button({ label: t("Обновить данные"), variant: 'ghost', size: 'sm' });
  reload.onclick = () => busy(reload, async () => { await refresh(); toast(t("Данные обновлены")); });
  root.replaceChildren(
    h('header', { class: 'page-head' }, h('div', {}, h('p', { class: 'eyebrow' }, data.house.name), h('h1', { id: 'house-title', tabindex: '-1' }, t("Дом")))),
    h('section', { class: 'profile-card' }, avatar(me?.display_name, data.actor, 'lg'),
      h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, me?.display_name),
        h('div', { class: 'row-meta' }, me?.role === 'owner' ? t("Владелец дома") : t("Жилец")))),
    h('div', { class: 'group' },
      linkRow({ iconName: 'people', title: t("Жильцы"), meta: t("Жильцов: {0}", [data.members.length]), onClick: open('people') }),
      linkRow({ iconName: 'calendar', title: t("График уборки"), meta: t("Дни, отметки и история"), onClick: open('schedule') }),
      linkRow({ iconName: 'wallet', title: t("Деньги и категории"), meta: t("Валюта дома · {0}", [data.currency]), onClick: open('money') }),
      linkRow({ iconName: 'bell', title: t("Мои уведомления"), meta: t("Что и куда присылать"), onClick: open('notifications') }),
      linkRow({ iconName: 'sliders', title: t("Настройки дома"), meta: t("Название, правила и напоминания"), onClick: open('settings') })),
    h('div', { class: 'hub-footer' },
      button({ label: t("Другой дом"), icon: 'plus', variant: 'secondary', onClick: open('add') }), reload));
}

async function copyText(text, node) {
  try {
    await navigator.clipboard.writeText(text);
    toast(t("Скопировано"));
  } catch {
    const range = document.createRange();
    range.selectNodeContents(node);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    toast(t("Выделили текст — скопируйте его"));
  }
}

// ── Жильцы ──────────────────────────────────────────────────────────────────────────────────────

function inviteCard(initial, mgmt) {
  let info = initial;
  const code = h('p', { class: 'invite-code' });
  const paint = () => { code.textContent = info.link || info.invite_token; };
  paint();
  const share = button({ label: t("Поделиться"), icon: 'share', block: true, onClick: () => {
    if (info.link) telegram.share(info.link, t("Приглашаю вас в дом «{0}» в Домовом.", [mgmt.house.name]));
    else copyText(info.invite_token, code);
  } });
  const copy = button({ label: info.link ? t("Скопировать ссылку") : t("Скопировать код"), icon: 'copy', variant: 'secondary', block: true,
    onClick: () => copyText(info.link || info.invite_token, code) });
  const rotate = button({ label: t("Обновить код"), icon: 'refresh', variant: 'ghost', block: true });
  rotate.onclick = () => busy(rotate, async () => {
    const agreed = await confirmSheet({ title: t("Обновить код?"), confirmLabel: t("Обновить код"),
      text: t("Создать новый код? Старые приглашения перестанут работать. Жильцы останутся в доме.") });
    if (!agreed) return;
    info = await app.api.post(`${base()}/invite/rotate`);
    paint();
    toast(t("Код обновлён"));
  });
  return h('section', { class: 'card', 'aria-labelledby': 'invite-title' },
    h('div', { class: 'card-head' }, h('h2', { id: 'invite-title' }, t("Пригласить соседей"))),
    h('p', { class: 'row-meta' }, t("Отправьте приглашение человеку, с которым живёте — он вступит в дом по ссылке.")),
    code, h('div', { class: 'stack' }, share, copy, rotate));
}

function openRights(mgmt, member) {
  openSheet({
    title: member.display_name,
    body: [
      h('p', { class: 'row-meta' }, t("Что этот жилец может делать в доме. Изменения действуют сразу.")),
      h('div', { class: 'group' }, mgmt.permission_definitions.map(definition => switchRow({
        title: t(definition.label), hint: t(definition.hint), checked: member.grants.includes(definition.code),
        onChange: async granted => {
          await app.api.post(`${base()}/members/${member.tg_id}/permissions/${definition.code}`, { granted });
          member.grants = granted ? [...member.grants, definition.code] : member.grants.filter(code => code !== definition.code);
          toast(t("Права обновлены"));
        },
      }))),
    ],
  });
}

function peoplePanel(mgmt, invite) {
  return [
    mgmt.permissions.manage_members && invite ? inviteCard(invite, mgmt) : null,
    h('section', { class: 'card', 'aria-labelledby': 'people-title' },
      h('div', { class: 'card-head' }, h('h2', { id: 'people-title' }, t("Жильцы"))),
      mgmt.members.map(member => {
        const role = member.role === 'owner' ? t("Владелец дома") : member.tg_id === mgmt.actor ? t("Это вы") : t("Жилец");
        const content = [avatar(member.display_name, member.tg_id),
          h('span', { class: 'row-main' }, h('span', { class: 'row-title' }, member.display_name), h('span', { class: 'row-meta' }, role)),
          member.can_manage ? h('span', { class: 'row-end' }, h('span', { class: 'row-meta' }, t("Права")), icon('chevron-right', 'row-chevron')) : null];
        return member.can_manage
          ? h('button', { type: 'button', class: 'row', onClick: () => openRights(mgmt, member) }, content)
          : h('div', { class: 'row' }, content);
      })),
  ];
}

// ── График уборки ───────────────────────────────────────────────────────────────────────────────

function schedulePanel(mgmt) {
  const editable = mgmt.permissions.manage_schedule;
  let version = mgmt.schedule.version;
  const chosen = new Map(mgmt.members.map(member => [member.tg_id, mgmt.schedule.weekday_map[member.tg_id] ?? null]));
  let saved = JSON.stringify([...chosen]);
  const save = button({ label: t("Сохранить график"), block: true });
  save.disabled = true;
  const sync = () => { save.disabled = JSON.stringify([...chosen]) === saved; };

  const rows = mgmt.members.map(member => {
    const buttons = WEEK.map(index => {
      const control = h('button', { type: 'button', class: 'day-pick', 'aria-pressed': String(chosen.get(member.tg_id) === index),
        'aria-label': `${member.display_name}: ${weekdayName(index, locale, 'long')}`, disabled: !editable }, weekdayName(index, locale));
      control.onclick = () => {
        chosen.set(member.tg_id, chosen.get(member.tg_id) === index ? null : index);
        buttons.forEach((node, position) => node.setAttribute('aria-pressed', String(chosen.get(member.tg_id) === position)));
        sync();
      };
      return control;
    });
    return h('div', { class: 'schedule-member' },
      h('div', { class: 'row' }, avatar(member.display_name, member.tg_id), h('span', { class: 'row-main' }, h('span', { class: 'row-title' }, member.display_name))),
      h('div', { class: 'days', role: 'group', 'aria-label': member.display_name }, buttons));
  });
  save.onclick = () => busy(save, async () => {
    const result = await app.api.post(`${base()}/schedule`, { version, weekday_map: Object.fromEntries(chosen) });
    version = result.version;
    saved = JSON.stringify([...chosen]);
    sync();
    await refresh();
    await loadDays();
    toast(t("График обновлён"));
  });

  // История дней месяца с отметками.
  let month = mgmt.schedule.month;
  let snapshot = mgmt.schedule;
  const monthLabel = h('span', { class: 'month-label' });
  const list = h('div', { class: 'list' });
  async function loadDays() {
    snapshot = (await app.api.get(`${base()}/management?month=${month}`)).schedule;
    paintDays();
  }
  const shift = async delta => {
    month = shiftMonth(month, delta) ?? month;
    try { await loadDays(); } catch (error) { fail(error); }
  };
  function paintDays() {
    monthLabel.textContent = formatMonth(month, locale);
    const status = { open: t("Ждёт отметки"), done: t("Убрано"), canceled: t("Пропущено") };
    list.replaceChildren(...(snapshot.history.length ? snapshot.history.map(entry => {
      const upcoming = entry.status === 'open' && entry.planned_date > snapshot.today;
      const canClose = entry.status === 'open' && !upcoming && (entry.tg_id === mgmt.actor || mgmt.permissions.close_others_days);
      const done = button({ label: t("Отметить уборку"), size: 'sm', variant: 'secondary' });
      done.onclick = () => busy(done, async () => { await app.api.post(`${base()}/cleaning/${entry.id}/close`); await refresh(); await loadDays(); });
      const skip = button({ label: t("Пропустить"), size: 'sm', variant: 'ghost' });
      skip.onclick = () => busy(skip, async () => {
        const agreed = await confirmSheet({ title: t("Пропустить день?"), confirmLabel: t("Пропустить"),
          text: t("Отметить день {0} для {1} как пропущенный?", [day(entry.planned_date), entry.display_name]) });
        if (!agreed) return;
        await app.api.post(`${base()}/cleaning/${entry.id}/cancel`);
        await refresh();
        await loadDays();
      });
      return h('div', { class: 'schedule-day' },
        h('div', { class: 'row' }, h('span', { class: 'row-main' },
          h('span', { class: 'row-title' }, `${entry.display_name} · ${day(entry.planned_date, { weekday: 'short', day: 'numeric', month: 'short' })}`),
          h('span', { class: 'row-meta' }, upcoming ? t("Впереди") : status[entry.status]))),
        canClose ? h('div', { class: 'button-row' }, done, mgmt.permissions.close_others_days ? skip : null) : null);
    }) : [h('p', { class: 'row-meta' }, t("Дней за этот месяц пока нет."))]));
  }
  paintDays();

  return [
    h('section', { class: 'card', 'aria-labelledby': 'week-title' },
      h('div', { class: 'card-head' }, h('h2', { id: 'week-title' }, t("Дни недели"))),
      h('p', { class: 'row-meta' }, editable
        ? t("Выберите каждому жильцу день уборки. Изменения касаются будущих открытых дней; прошлые отметки останутся в истории.")
        : t("График меняет владелец или жилец с соответствующим доступом.")),
      rows, editable ? save : null),
    h('section', { class: 'card', 'aria-labelledby': 'days-title' },
      h('div', { class: 'card-head' }, h('h2', { id: 'days-title' }, t("Дни и отметки"))),
      h('div', { class: 'month-bar' },
        iconButton({ icon: 'chevron-left', label: t("Предыдущий месяц"), onClick: () => shift(-1) }), monthLabel,
        iconButton({ icon: 'chevron-right', label: t("Следующий месяц"), onClick: () => shift(1) })),
      list),
  ];
}

// ── Деньги и категории ──────────────────────────────────────────────────────────────────────────

function choiceLabel(definition, choice) {
  if (definition.key.endsWith('_hour')) return `${choice}:00`;
  if (definition.key === 'tz_offset_hours') return `UTC${choice < 0 ? '−' : '+'}${Math.abs(choice)}`;
  return t(definition.choice_labels?.[choice] ?? String(choice));
}

async function saveSetting(key, value) {
  await app.api.post(`${base()}/settings/${key}`, { value });
  await refresh();
  toast(t("Сохранено"));
}

function settingControl(mgmt, definition) {
  const value = mgmt.house_settings[definition.key];
  const canEdit = mgmt.permissions.manage_house_settings;
  if (!canEdit) {
    return h('div', { class: 'setting-row' }, h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, t(definition.label))),
      h('span', { class: 'row-meta' }, definition.kind === 'bool' ? (value ? t("Включено") : t("Выключено")) : choiceLabel(definition, value)));
  }
  if (definition.kind === 'bool') {
    return switchRow({ title: t(definition.label), checked: value, onChange: next => saveSetting(definition.key, next) });
  }
  let current = value;
  const numeric = typeof definition.default === 'number';
  const field = selectField({ label: t(definition.label), value: String(value),
    options: definition.choices.map(choice => ({ value: choice, label: choiceLabel(definition, choice) })) });
  field.input.addEventListener('change', async () => {
    const next = numeric ? Number(field.input.value) : field.input.value;
    if (definition.key === 'currency') {
      const agreed = await confirmSheet({ title: t("Сменить валюту?"), confirmLabel: t("Сменить"),
        text: t("Изменить обозначение валюты у всех записей дома? Суммы останутся прежними — пересчёта по курсу не будет.") });
      if (!agreed) { field.input.value = String(current); return; }
    }
    try {
      await saveSetting(definition.key, next);
      current = next;
    } catch (error) {
      field.input.value = String(current);
      fail(error);
    }
  });
  return field.el;
}

function moneyPanel(mgmt, reload) {
  const currency = mgmt.house_setting_definitions.find(definition => definition.key === 'currency');
  const canEdit = mgmt.permissions.manage_categories;
  const name = textField({ label: t("Новая категория"), maxLength: CATEGORY_LIMIT, placeholder: t("Например, Для кухни"), enterKeyHint: 'done' });
  const add = button({ label: t("Добавить категорию"), variant: 'secondary', block: true, type: 'submit' });
  const form = h('form', { class: 'stack', novalidate: true }, name.el, add);
  form.onsubmit = async event => {
    event.preventDefault();
    name.clearError();
    if (!name.input.value.trim()) { name.setError(t("Введите название")); name.input.focus(); return; }
    await busy(add, async () => {
      try {
        await app.api.post(`${base()}/categories`, { name: name.input.value.trim() });
        toast(t("Категория добавлена"));
        await refresh();
        reload();
      } catch (error) {
        if (error.kind === 'session') fail(error);
        else name.setError(errorText(error));
      }
    });
  };
  return [
    h('section', { class: 'card' }, settingControl(mgmt, currency)),
    h('section', { class: 'card', 'aria-labelledby': 'categories-title' },
      h('div', { class: 'card-head' }, h('h2', { id: 'categories-title' }, t("Категории расходов"))),
      h('p', { class: 'row-meta' }, t("Названия помогают находить покупки в истории. Категория с расходами не удаляется.")),
      mgmt.categories.map(category => {
        const remove = iconButton({ icon: 'trash', label: t("Убрать категорию «{0}»", [category.name]) });
        remove.onclick = () => busy(remove, async () => {
          const agreed = await confirmSheet({ title: t("Убрать категорию?"), confirmLabel: t("Убрать"), danger: true,
            text: t("Убрать категорию «{0}»?", [category.name]) });
          if (!agreed) return;
          await app.api.post(`${base()}/categories/${category.id}/delete`);
          await refresh();
          reload();
        });
        return h('div', { class: 'row' }, h('span', { class: 'row-main' }, h('span', { class: 'row-title' }, category.name)), canEdit ? remove : null);
      }),
      canEdit ? form : null),
  ];
}

// ── Уведомления ─────────────────────────────────────────────────────────────────────────────────

function notificationsPanel(mgmt) {
  const labels = { private: t("Личный чат"), chat: t("Общий чат дома"), off: t("Не присылать") };
  return [
    h('p', { class: 'panel-note' }, t("Это только ваши настройки. Уведомления приходят в личный чат или общий чат дома, если он подключён.")),
    mgmt.house.chat_bound ? null : h('p', { class: 'panel-note' }, t("Общий чат пока не подключён. Чтобы получать сообщения сейчас, выбирайте «Личный чат».")),
    h('div', { class: 'group' }, mgmt.notify_setting_definitions.map(definition => {
      let previous = mgmt.notify_settings[definition.key];
      const control = segmented({
        label: t(definition.label), value: previous,
        options: definition.choices.map(choice => ({ value: choice, label: labels[choice] })),
        onChange: async next => {
          try {
            await app.api.post(`${base()}/notifications/${definition.key}`, { value: next });
            previous = next;
            toast(t("Сохранено"));
          } catch (error) {
            control.set(previous);
            fail(error);
          }
        },
      });
      return h('div', { class: 'setting-block' }, h('p', { class: 'row-title' }, t(definition.label)), control.el);
    })),
  ];
}

// ── Настройки дома ──────────────────────────────────────────────────────────────────────────────

function saveCard({ title, field, label, request, done }) {
  const submit = button({ label, type: 'submit', variant: 'secondary', block: true });
  const form = h('form', { class: 'stack', novalidate: true }, field.el, submit);
  form.onsubmit = async event => {
    event.preventDefault();
    field.clearError();
    if (!field.input.value.trim()) { field.setError(t("Заполните поле")); field.input.focus(); return; }
    await busy(submit, async () => {
      try {
        await request(field.input.value.trim());
        await refresh();
        toast(done);
      } catch (error) {
        if (error.kind === 'session') fail(error);
        else field.setError(errorText(error));
      }
    });
  };
  return h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title)), form);
}

function settingsPanel(mgmt) {
  const manage = mgmt.permissions.manage_house_settings;
  const houseName = textField({ label: t("Как называется ваш дом"), value: mgmt.house.name, maxLength: HOUSE_NAME_LIMIT });
  const myName = textField({ label: t("Ваше имя в этом доме"), value: mgmt.profile.display_name, maxLength: MEMBER_NAME_LIMIT });
  const rules = mgmt.house_setting_definitions.filter(definition => definition.key !== 'currency');
  const leave = button({ label: t("Выйти из дома"), icon: 'logout', variant: 'danger-soft', block: true });
  leave.onclick = () => busy(leave, async () => {
    const agreed = await confirmSheet({ title: t("Выйти из дома?"), confirmLabel: t("Выйти"), danger: true,
      text: t("Выйти из «{0}»? Вы потеряете доступ к этому дому.", [mgmt.house.name]) });
    if (!agreed) return;
    await app.api.post(`${base()}/leave`);
    await loadHouses();
  });
  return [
    manage ? saveCard({ title: t("Название дома"), field: houseName, label: t("Сохранить название"), done: t("Название обновлено"),
      request: value => app.api.post(`${base()}/name`, { name: value }) }) : null,
    saveCard({ title: t("Как к вам обращаться"), field: myName, label: t("Сохранить имя"), done: t("Имя обновлено"),
      request: value => app.api.post(`${base()}/profile`, { display_name: value }) }),
    manage ? null : h('p', { class: 'panel-note' }, t("Правила дома меняет владелец или участник с соответствующим доступом.")),
    h('section', { class: 'card', 'aria-labelledby': 'rules-title' },
      h('div', { class: 'card-head' }, h('h2', { id: 'rules-title' }, t("Правила и напоминания"))),
      rules.map(definition => settingControl(mgmt, definition))),
    mgmt.profile.can_leave ? h('section', { class: 'card card-danger' },
      h('p', { class: 'row-meta' }, t("Доступ к данным этого дома закроется. Старые записи сохранятся у жильцов.")), leave) : null,
  ];
}

// ── Подэкраны ───────────────────────────────────────────────────────────────────────────────────

async function renderPanel(root, name) {
  const mine = ++generation;
  const body = h('div', { class: 'stack' }, skeleton('sk-card'), skeleton('sk-card'));
  root.replaceChildren(
    h('header', { class: 'page-head panel-head' },
      iconButton({ icon: 'chevron-left', label: t("К дому"), onClick: () => nav.go('house') }),
      h('h1', { id: 'house-title', tabindex: '-1' }, titles()[name])), body);
  if (name === 'add') {
    renderMembership(body, { initialName: app.data.members.find(member => member.tg_id === app.data.actor)?.display_name || telegram.user?.first_name || '',
      onDone: async houseId => { await loadHouses(houseId); nav.go('home'); } });
    return;
  }
  const reload = () => { if (app.sub === name) renderPanel(root, name); };
  try {
    const mgmt = await app.api.get(`${base()}/management`);
    const invite = name === 'people' && mgmt.permissions.manage_members ? await app.api.get(`${base()}/invite`) : null;
    if (mine !== generation || app.sub !== name) return;
    const builders = { people: () => peoplePanel(mgmt, invite), schedule: () => schedulePanel(mgmt), money: () => moneyPanel(mgmt, reload),
      notifications: () => notificationsPanel(mgmt), settings: () => settingsPanel(mgmt) };
    body.replaceChildren(...builders[name]().filter(Boolean));
  } catch (error) {
    if (mine !== generation) return;
    if (error.kind === 'session') { fail(error); return; }
    body.replaceChildren(emptyState({ icon: 'alert', title: errorText(error),
      action: button({ label: t("Попробовать ещё раз"), onClick: reload }) }));
  }
}

export function renderHouse(root) {
  if (app.sub) renderPanel(root, app.sub);
  else {
    generation += 1;
    renderHub(root);
  }
}
