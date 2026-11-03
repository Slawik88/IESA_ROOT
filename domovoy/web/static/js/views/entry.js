// Карточка записи: все поля и действия в одном месте; опасное отделено и требует подтверждения.
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

export function openEntry(entry) {
  const contribution = entry.kind === 'contribution';
  const { permissions } = app.data;
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

  function decision(confirm) {
    const control = button({ label: confirm ? t("Принять") : t("Отклонить"), variant: confirm ? 'primary' : 'secondary' });
    control.onclick = () => busy(control, async () => {
      await app.api.post(`houses/${app.houseId}/contributions/${entry.id}`, { confirm });
      sheet.close();
      await refresh();
      toast(confirm ? t("Взнос принят") : t("Взнос отклонён"));
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
      await app.api.post(`houses/${app.houseId}/expenses/${entry.id}/reimburse`, { version: entry.version });
      sheet.close();
      await refresh();
      toast(t("Возврат отмечен"));
    });
    return control;
  }

  function remove() {
    const control = button({ label: t("Удалить"), icon: 'trash', variant: 'danger-soft', block: true });
    control.onclick = () => busy(control, async () => {
      const agreed = await confirmSheet({
        title: t("Удалить расход?"), confirmLabel: t("Удалить"), danger: true,
        text: t("Удалить расход {0} за {1}? Остаток пересчитается. Вернуть запись кнопкой отмены будет нельзя.",
          [money(entry.amount_kop), day(entry.date)]),
      });
      if (!agreed) return;
      await app.api.post(`houses/${app.houseId}/expenses/${entry.id}/delete`, { version: entry.version });
      sheet.close();
      await refresh();
      toast(t("Расход удалён"));
    });
    return control;
  }

  function actions() {
    const waiting = contribution && entry.status === 'declared' && permissions.confirm_contributions;
    const canReimburse = !contribution && entry.mode === 'personal' && !entry.reimbursed && permissions.confirm_contributions;
    return h('div', { class: 'entry-actions' },
      waiting ? h('div', { class: 'button-row' }, decision(true), decision(false)) : null,
      canReimburse ? reimburse() : null,
      h('div', { class: 'button-row' },
        button({ label: t("Повторить"), icon: 'repeat', variant: 'secondary', onClick: () => { sheet.close(); openForm({ kind: entry.kind, seed: entry }); } }),
        entry.can_edit ? button({ label: t("Изменить"), icon: 'edit', variant: 'secondary', onClick: () => { sheet.close(); openForm({ kind: 'expense', seed: entry, edit: true }); } }) : null,
        contribution ? null : button({ label: t("Чеки"), icon: 'receipt', variant: 'secondary', onClick: () => { sheet.close(); openReceipts(entry); } })),
      entry.can_edit ? remove() : null);
  }
}
