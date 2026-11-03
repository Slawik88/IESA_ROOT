// Создание дома и вступление по приглашению: первый вход и экран «Другой дом».
import { t } from '../i18n.js';
import { app } from '../state.js';
import { busy, button, errorText, fail, h, icon, segmented, textField, toast } from '../ui.js';

const HOUSE_NAME_LIMIT = 32;
const MEMBER_NAME_LIMIT = 32;
const INVITE_LIMIT = 2048;

export function renderMembership(container, { initialName = '', onDone }) {
  const target = h('div', { class: 'stack' });
  const mode = segmented({
    label: t("Добавить дом"), value: 'create', onChange: () => paint(),
    options: [{ value: 'create', label: t("Новый дом") }, { value: 'join', label: t("Приглашение") }],
  });

  function paint() {
    const joining = mode.value === 'join';
    const key = textField({
      label: joining ? t("Код или ссылка приглашения") : t("Название дома"), maxLength: joining ? INVITE_LIMIT : HOUSE_NAME_LIMIT,
      placeholder: joining ? t("Вставьте приглашение") : t("Например, Дом на Садовой"), enterKeyHint: 'next',
    });
    const name = textField({ label: t("Ваше имя в доме"), value: initialName, maxLength: MEMBER_NAME_LIMIT, enterKeyHint: 'done' });
    const submit = button({ label: joining ? t("Присоединиться") : t("Создать дом"), type: 'submit', block: true });
    const form = h('form', { class: 'stack', novalidate: true }, key.el, name.el, submit);
    form.onsubmit = async event => {
      event.preventDefault();
      key.clearError();
      name.clearError();
      const keyValue = key.input.value.trim();
      const nameValue = name.input.value.trim();
      if (!keyValue) { key.setError(t("Заполните поле")); key.input.focus(); return; }
      if (!nameValue) { name.setError(t("Заполните поле")); name.input.focus(); return; }
      await busy(submit, async () => {
        try {
          const result = await app.api.post(joining ? 'houses/join' : 'houses', joining
            ? { invite_token: keyValue, display_name: nameValue } : { name: keyValue, display_name: nameValue });
          await onDone(result.house_id);
          toast(joining ? result.joined ? t("Вы вступили в дом") : t("Вы уже живёте в этом доме")
            : result.created ? t("Дом создан") : t("Открыли ваш существующий дом"));
        } catch (error) {
          if (error.kind === 'session') fail(error);
          else key.setError(errorText(error));
        }
      });
    };
    target.replaceChildren(form);
  }

  paint();
  container.replaceChildren(mode.el, target);
}

export function renderOnboarding(root, options) {
  const body = h('div', { class: 'stack' });
  root.replaceChildren(h('section', { class: 'welcome' },
    h('span', { class: 'welcome-mark', 'aria-hidden': 'true' }, icon('brand')),
    h('h1', { id: 'welcome-title', tabindex: '-1' }, t("Добро пожаловать в Домовой")),
    h('p', { class: 'welcome-text' }, t("Уборка по графику и общие деньги дома — в одном месте. Создайте дом или вступите по приглашению.")),
    body));
  renderMembership(body, options);
}
