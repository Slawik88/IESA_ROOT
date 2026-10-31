"""
bot/keyboards.py — все inline-клавиатуры бота. Только кнопки; правила — в services.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import cb
from core import settings_registry as reg
from core.constants import WEEKDAY_SHORT

Btn = InlineKeyboardButton


def _kb(rows: list[list[Btn]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Главное меню ─────────────────────────────────────────────────────────────

def main_menu(can_switch_house: bool) -> InlineKeyboardMarkup:
    rows = [
        [Btn("🧹 Сегодня", cb.today()), Btn("📅 График", cb.schedule_view())],
        [Btn("💰 Баланс", cb.balance()), Btn("🧾 Траты", cb.expenses_list())],
        [Btn("💸 Скинулся", cb.contribute()), Btn("➕ Трата", cb.expense_new())],
        [Btn("⚙️ Настройки", cb.settings_root())],
    ]
    if can_switch_house:
        rows.append([Btn("🏠 Сменить дом", cb.houses_list())])
    return _kb(rows)


def onboarding() -> InlineKeyboardMarkup:
    return _kb([[Btn("🏠 Создать дом", cb.house_create())]])


def house_selector(houses: list) -> InlineKeyboardMarkup:
    rows = [[Btn(f"«{h['name']}»", cb.house_select(h["id"]))] for h in houses]
    rows.append([Btn("🏠 Создать новый дом", cb.house_create())])
    return _kb(rows)


def back_to_menu() -> InlineKeyboardMarkup:
    return _kb([[Btn("← Меню", cb.menu())]])


def bind_chat_keyboard() -> InlineKeyboardMarkup:
    return _kb([[Btn("🔗 Привязать этот чат", cb.settings_bind_chat())]])


# ── Сегодня / дни ────────────────────────────────────────────────────────────

def today_keyboard(
    my_open_dates: list[str], today_iso: str, yesterday_iso: str,
    owner_days: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    rows = []
    if today_iso in my_open_dates:
        rows.append([Btn("✅ Убрался", cb.done(today_iso))])
    elif my_open_dates:
        rows.append([Btn("✅ Убрался (закрыть пропуск)", cb.done(today_iso))])
    if yesterday_iso in my_open_dates:
        rows.append([Btn("✅ Убрался вчера", cb.done(yesterday_iso))])
    for day_id, name in owner_days:
        rows.append([
            Btn(f"🧹 {name}: закрыть за него", cb.day_close(day_id)),
            Btn("⛔", cb.day_cancel(day_id)),
        ])
    rows.append([Btn("🔄 Обновить", cb.today()), Btn("← Меню", cb.menu())])
    return _kb(rows)


def day_owner_keyboard(day_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [Btn("✅ Закрыть за него", cb.day_close(day_id)), Btn("⛔ Отменить день", cb.day_cancel(day_id))],
    ])


# ── График ───────────────────────────────────────────────────────────────────

def schedule_keyboard(can_edit: bool) -> InlineKeyboardMarkup:
    rows = [[Btn("🗓 Уборка за месяц", cb.history("current"))]]
    if can_edit:
        rows.append([Btn("✏️ Изменить график", cb.schedule_edit())])
    rows.append([Btn("← Меню", cb.menu())])
    return _kb(rows)


def schedule_editor_keyboard(members: list, draft: dict[int, int | None], picked_tg: int | None = None):
    """Черновик графика: строка на жильца; выбранный жилец раскрывается в дни недели."""
    rows = []
    for member in members:
        tg_id = member["tg_id"]
        weekday = draft.get(tg_id)
        value = WEEKDAY_SHORT[weekday] if weekday is not None else "—"
        prefix = "▸ " if tg_id == picked_tg else ""
        rows.append([Btn(f"{prefix}{member['display_name']}: {value}", cb.schedule_member(tg_id))])
    if picked_tg is not None:
        day_rows = []
        row = []
        for weekday in range(7):
            row.append(Btn(WEEKDAY_SHORT[weekday], cb.schedule_pick(picked_tg, weekday)))
            if len(row) == 4:
                day_rows.append(row)
                row = []
        row.append(Btn("—", cb.schedule_pick(picked_tg, None)))
        day_rows.append(row)
        rows.extend(day_rows)
    rows.append([Btn("💾 Сохранить", cb.schedule_save()), Btn("✖️ Отмена", cb.schedule_cancel())])
    return _kb(rows)


# ── Деньги ───────────────────────────────────────────────────────────────────

def balance_keyboard(pending_count: int, can_confirm: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_confirm and pending_count:
        rows.append([Btn(f"⏳ Подтвердить взносы ({pending_count})", cb.pending())])
    rows.append([Btn("🧾 Последние траты", cb.expenses_list()), Btn("← Меню", cb.menu())])
    return _kb(rows)


def pending_keyboard(pending_rows: list, currency: str) -> InlineKeyboardMarkup:
    from core.money import format_amount

    rows = []
    for row in pending_rows:
        who = row["display_name"] or "?"
        label = f"{who} · {format_amount(row['amount_kop'], currency)}"[:24]
        rows.append([
            Btn(f"✅ {label}", cb.contribution_resolve(row["id"], True)),
            Btn("❌", cb.contribution_resolve(row["id"], False)),
        ])
    rows.append([Btn("← Баланс", cb.balance())])
    return _kb(rows)


def contribution_decision_keyboard(contribution_id: int) -> InlineKeyboardMarkup:
    return _kb([[
        Btn("✅ Подтвердить", cb.contribution_resolve(contribution_id, True)),
        Btn("❌ Отклонить", cb.contribution_resolve(contribution_id, False)),
    ]])


def categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for category in categories:
        row.append(Btn(category["name"], cb.expense_category(category["id"])))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Btn("✖️ Отмена", cb.menu())])
    return _kb(rows)


def mode_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [Btn("🏦 Из котла", cb.expense_mode("house"))],
        [Btn("👛 За свои (ждёт возврата)", cb.expense_mode("personal"))],
        [Btn("✖️ Отмена", cb.menu())],
    ])


def photos_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [Btn("📸 Готово, сохранить", cb.expense_photos_done())],
        [Btn("✖️ Отмена", cb.menu())],
    ])


def description_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [Btn("Без описания", cb.expense_desc_skip())],
    ])


def expenses_list_keyboard(expenses: list) -> InlineKeyboardMarkup:
    rows = [[Btn(f"{row['spent_on'][8:10]}.{row['spent_on'][5:7]} · {row['display_name'] or '?'} · "
                 f"{row['category_name'] or '—'}", cb.expense_card(row["id"]))]
            for row in expenses]
    rows.append([Btn("← Меню", cb.menu())])
    return _kb(rows)


def expense_card_keyboard(expense, photos_count: int, can_manage: bool, can_reimburse: bool) -> InlineKeyboardMarkup:
    rows = []
    if photos_count:
        rows.append([Btn(f"📎 Чеки ({photos_count})", cb.expense_photos(expense["id"]))])
    if can_reimburse and expense["mode"] == "personal" and not expense["reimbursed"]:
        rows.append([Btn("↩️ Вернуть из котла", cb.expense_reimburse(expense["id"]))])
    if can_manage:
        rows.append([Btn("🗑 Удалить трату", cb.expense_delete(expense["id"]))])
    rows.append([Btn("← Траты", cb.expenses_list())])
    return _kb(rows)


def history_keyboard(month: str, prev_month: str, next_month: str, can_nav_next: bool) -> InlineKeyboardMarkup:
    rows = [[Btn("‹", cb.history(prev_month)), Btn("›", cb.history(next_month) if can_nav_next else cb.noop())]]
    rows.append([Btn("← Меню", cb.menu())])
    return _kb(rows)


# ── Настройки ────────────────────────────────────────────────────────────────

def settings_root_keyboard(is_owner: bool, chat_bound: bool) -> InlineKeyboardMarkup:
    rows = [
        [Btn("🔔 Мои уведомления", cb.settings_notify())],
    ]
    if is_owner:
        rows.append([Btn("🏠 Настройки дома", cb.settings_house())])
        rows.append([Btn("👥 Права участников", cb.settings_perms())])
        rows.append([Btn("🏷 Категории трат", cb.settings_categories())])
        rows.append([Btn("🔗 Привязать этот чат" if not chat_bound else "🔗 Чат привязан ✓",
                         cb.settings_bind_chat())])
        rows.append([Btn("💌 Ссылка-приглашение", cb.settings_invite())])
    rows.append([Btn("← Меню", cb.menu())])
    return _kb(rows)


def house_settings_keyboard(values: dict) -> InlineKeyboardMarkup:
    rows = []
    for definition in reg.HOUSE_SETTINGS:
        value = values[definition.key]
        if definition.kind == "bool":
            shown = "вкл" if value else "выкл"
        else:
            shown = definition.choice_labels.get(value, value) if definition.choice_labels else value
        rows.append([Btn(f"{definition.label}: {shown}", cb.settings_house_set(definition.key))])
    rows.append([Btn("← Настройки", cb.settings_root())])
    return _kb(rows)


def house_setting_choices_keyboard(key: str, choices: tuple) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for index, value in enumerate(choices):
        row.append(Btn(str(value), cb.settings_house_value(key, index)))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Btn("← Настройки дома", cb.settings_house())])
    return _kb(rows)


def notify_settings_keyboard(values: dict, is_owner: bool) -> InlineKeyboardMarkup:
    rows = []
    for definition in reg.NOTIFY_SETTINGS:
        if definition.for_owner_only and not is_owner:
            continue
        channel = reg.channel_label(values[definition.key])
        rows.append([Btn(f"{definition.label}: {channel}", cb.settings_notify_cycle(definition.key))])
    rows.append([Btn("← Настройки", cb.settings_root())])
    return _kb(rows)


def perm_members_keyboard(members: list) -> InlineKeyboardMarkup:
    rows = [[Btn(member["display_name"], cb.settings_perm_member(member["tg_id"]))]
            for member in members]
    rows.append([Btn("← Настройки", cb.settings_root())])
    return _kb(rows)


def perm_toggle_keyboard(member, grants: frozenset[str]) -> InlineKeyboardMarkup:
    from core import permissions as perms

    rows = []
    for permission in perms.PERMISSIONS:
        mark = "✅" if permission.code in grants else "❌"
        rows.append([Btn(f"{mark} {permission.label}", cb.settings_perm_toggle(member["tg_id"], permission.code))])
    rows.append([Btn("← Участники", cb.settings_perms())])
    return _kb(rows)


def categories_manage_keyboard(categories: list) -> InlineKeyboardMarkup:
    rows = [[Btn(f"🗑 {category['name']}", cb.settings_category_delete(category["id"]))]
            for category in categories]
    rows.append([Btn("➕ Добавить категорию", cb.category_add())])
    rows.append([Btn("← Настройки", cb.settings_root())])
    return _kb(rows)


def invite_keyboard(link: str) -> InlineKeyboardMarkup:
    return _kb([
        [Btn("🔄 Обновить ссылку", cb.settings_invite())],
        [Btn("← Настройки", cb.settings_root())],
    ])
