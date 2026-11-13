// Карточка записи: все поля и действия в одном месте. Недоступное действие не прячется — рядом сказано, почему и что делать.
import { locale, t } from '../i18n.js';
import { formatMonth } from '../format.js';
import { app, day, money } from '../state.js';
import { refresh } from '../data.js';
import { avatar, busy, button, confirmSheet, h, icon, openSheet, toast } from '../ui.js';
import { entryAmount, entryBadge, entryIconName } from './entries.js';
import { openForm } from './form.js';
import { openReceipts } from './receipts.js';

function facts(entry) {
  const contribution = entry.kind === 'contribution';
  const rows = [
    [t("Кто"), h('span', { class: 'who' }, avatar(entry.display_name, entry.tg_id, 'sm'), entry.display_name || t("Жилец"))],
    [t("Дата"), day(entry.date, { day: 'numeric', month: 'long', year: 'numeric' })],
  ];
  if (contribution) rows.push([t("За какой месяц взнос"), formatMonth(entry.month, locale)]);
  else rows.push([t("Категория"), entry.category || t("Без категории")], [t("Откуда деньги"), entry.mode === 'personal' ? t("За свои") : t("Из котла")]);
  if (entry.description) rows.push([t("На что"), h('span', { class: 'multiline' }, entry.description)]);
  return h('dl', { class: 'facts facts-list' }, rows.map(([label, value]) => h('div', {}, h('dt', {}, label), h('dd', {}, value))));
}

// Почему запись нельзя изменить: короткая причина вместо исчезнувшей кнопки.
function lockedReason(entry, approver) {
  if (entry.kind === 'contribution') return t("Взнос меняет его автор, пока он не подтверждён, а потом — владелец дома или жилец с правом «Взносы».");
  if (entry.reimbursed) {
    return approver ? t("Расход уже возвращён из котла, поэтому он закрыт для правок. Чтобы изменить или удалить его, сначала отмените возврат.")
      : t("Расход уже возвращён из котла, поэтому он закрыт для правок. Отменить возврат может владелец дома или жилец с правом «Взносы».");
  }
  return t("Эту запись меняет её автор, владелец дома или жилец с правом «Чужие траты».");
}

export function openEntry(entry) {
  const contribution = entry.kind === 'contribution';
  const approver = app.data.permissions.confirm_contributions;
  const amount = entryAmount(entry);
  const sheet = openSheet({
    title: contribution ? t("Взнос") : t("Расход"),
    body: [
      h('div', { class: 'entry-hero' },
        h('span', { class: 'row-icon row-icon-lg' }, icon(entryIconName(entry))),
        h('p', { class: `entry-amount ${amount.className}` }, amount.text),
        entryBadge(entry)),
      facts(entry),
      actions(),
    ],
  });
  const base = () => `houses/${app.houseId}`;

  // Общий порядок для действий, которые меняют запись: запрос, закрытие карточки, обновление списка, уведомление.
  const finish = async message => {
    sheet.close();
    await refresh();
    toast(message);
  };

  function decision(confirm) {
    const control = button({ label: confirm ? t("Принять") : t("Отклонить"), variant: confirm ? 'primary' : 'secondary' });
    control.onclick = () => busy(control, async () => {
      await app.api.post(`${base()}/contributions/${entry.id}`, { confirm });
      await finish(confirm ? t("Взнос принят") : t("Взнос отклонён"));
    });
    return control;
  }

  function reimburse() {
    const control = button({ label: t("Вернуть из котла"), icon: 'wallet', block: true });
    control.onclick = () => busy(control, async () => {
      const agreed = await confirmSheet({
        title: t("Вернуть из котла?"), confirmLabel: t("Вернуть из котла"),
        text: t("Отметить возврат {0} для {1}? Сумма спишется из котла.", [money(entry.amount_kop), entry.display_name]),
      });
      if (!agreed) return;
      await app.api.post(`${base()}/expenses/${entry.id}/reimburse`, { version: entry.version });
      await finish(t("Возврат отмечен"));
    });
    return control;
  }

  function undoReimburse() {
    const control = button({ label: t("Отменить возврат"), icon: 'undo', variant: 'secondary', block: true });
    control.onclick = () => busy(control, async () => {
      const agreed = await confirmSheet({
        title: t("Отменить возврат?"), confirmLabel: t("Отменить возврат"),
        text: t("Сумма {0} снова будет числиться за домом и вернётся в остаток котла. Запись можно будет изменить.", [money(entry.amount_kop)]),
      });
      if (!agreed) return;
      await app.api.post(`${base()}/expenses/${entry.id}/unreimburse`, { version: entry.version });
      await finish(t("Возврат отменён"));
    });
    return control;
  }

  function edit() {
    return button({ label: t("Изменить"), icon: 'edit', variant: 'secondary', block: true,
      onClick: () => { sheet.close(); openForm({ kind: entry.kind, seed: entry, edit: true }); } });
  }

  function remove() {
    const control = button({ label: contribution ? t("Удалить взнос") : t("Удалить расход"), icon: 'trash', variant: 'danger-soft', block: true });
    control.onclick = () => busy(control, async () => {
      const agreed = await confirmSheet({
        title: contribution ? t("Удалить взнос?") : t("Удалить расход?"), confirmLabel: t("Удалить"), danger: true,
        text: contribution
          ? t("Удалить взнос {0} за {1}? Остаток котла пересчитается. Вернуть запись кнопкой отмены будет нельзя.", [money(entry.amount_kop), formatMonth(entry.month, locale)])
          : t("Удалить расход {0} за {1}? Остаток пересчитается. Вернуть запись кнопкой отмены будет нельзя.", [money(entry.amount_kop), day(entry.date)]),
      });
      if (!agreed) return;
      await app.api.post(`${base()}/${contribution ? 'contributions' : 'expenses'}/${entry.id}/delete`, { version: entry.version });
      await finish(contribution ? t("Взнос удалён") : t("Расход удалён"));
    });
    return control;
  }

  function actions() {
    const waiting = contribution && entry.status === 'declared' && approver;
    const personal = !contribution && entry.mode === 'personal';
    return h('div', { class: 'entry-actions' },
      waiting ? h('div', { class: 'button-row' }, decision(true), decision(false)) : null,
      personal && !entry.reimbursed && approver ? reimburse() : null,
      entry.can_edit ? edit() : h('p', { class: 'panel-note locked-note' }, icon('info'), h('span', {}, lockedReason(entry, approver))),
      personal && entry.reimbursed && approver ? undoReimburse() : null,
      h('div', { class: 'button-row' },
        button({ label: t("Повторить"), icon: 'repeat', variant: 'secondary', onClick: () => { sheet.close(); openForm({ kind: entry.kind, seed: entry }); } }),
        contribution ? null : button({ label: t("Чеки"), icon: 'receipt', variant: 'secondary', onClick: () => { sheet.close(); openReceipts(entry); } })),
      entry.can_edit ? remove() : null);
  }
}
