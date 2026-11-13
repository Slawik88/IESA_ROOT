"""
bot/keyboards.py — все inline-клавиатуры бота. Только кнопки; правила — в services.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot import cb
from core import settings_registry as reg
from core.constants import WEEKDAY_SHORT

Btn = InlineKeyboardButton


def _kb(rows: list[list[Btn]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Главное меню ─────────────────────────────────────────────────────────────

def main_menu(can_switch_house: bool, web_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [Btn(text="🧹 Сегодня", callback_data=cb.today()), Btn(text="📅 График", callback_data=cb.schedule_view())],
        [Btn(text="💰 Деньги и операции", callback_data=cb.balance())],
        [Btn(text="💸 Скинулся", callback_data=cb.contribute()), Btn(text="➕ Трата", callback_data=cb.expense_new())],
        [Btn(text="⚙️ Настройки", callback_data=cb.settings_root())],
    ]
    if can_switch_house:
        rows.append([Btn(text="🏠 Сменить дом", callback_data=cb.houses_list())])
    if web_url:
        rows.insert(0, [Btn(text="Открыть домашний кабинет", web_app=WebAppInfo(url=web_url))])
    return _kb(rows)


def onboarding() -> InlineKeyboardMarkup:
    return _kb([[Btn(text="🏠 Создать дом", callback_data=cb.house_create())]])


def house_selector(houses: list) -> InlineKeyboardMarkup:
    rows = [[Btn(text=f"«{h['name']}»", callback_data=cb.house_select(h["id"]))] for h in houses]
    rows.append([Btn(text="🏠 Создать новый дом", callback_data=cb.house_create())])
    return _kb(rows)


def back_to_menu() -> InlineKeyboardMarkup:
    return _kb([[Btn(text="← Меню", callback_data=cb.menu())]])


def bind_chat_keyboard() -> InlineKeyboardMarkup:
    return _kb([[Btn(text="🔗 Привязать этот чат", callback_data=cb.settings_bind_chat())]])


# ── Сегодня / дни ────────────────────────────────────────────────────────────

def today_keyboard(
    my_open_dates: list[str], today_iso: str, yesterday_iso: str,
    owner_days: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    rows = []
    if today_iso in my_open_dates:
        rows.append([Btn(text="✅ Убрался", callback_data=cb.done(today_iso))])
    elif my_open_dates:
        rows.append([Btn(text="✅ Убрался (закрыть пропуск)", callback_data=cb.done(today_iso))])
    if yesterday_iso in my_open_dates:
        rows.append([Btn(text="✅ Убрался вчера", callback_data=cb.done(yesterday_iso))])
    for day_id, name in owner_days:
        rows.append([
            Btn(text=f"🧹 {name}: закрыть за него", callback_data=cb.day_close(day_id)),
            Btn(text="⛔", callback_data=cb.day_cancel(day_id)),
        ])
    rows.append([Btn(text="🔄 Обновить", callback_data=cb.today()), Btn(text="← Меню", callback_data=cb.menu())])
    return _kb(rows)


def day_owner_keyboard(day_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [Btn(text="✅ Закрыть за него", callback_data=cb.day_close(day_id)),
         Btn(text="⛔ Отменить день", callback_data=cb.day_cancel(day_id))],
    ])


# ── График ───────────────────────────────────────────────────────────────────

def schedule_keyboard(can_edit: bool) -> InlineKeyboardMarkup:
    rows = [[Btn(text="🗓 Уборка за месяц", callback_data=cb.history("current"))]]
    if can_edit:
        rows.append([Btn(text="✏️ Изменить график", callback_data=cb.schedule_edit())])
    rows.append([Btn(text="← Меню", callback_data=cb.menu())])
    return _kb(rows)


def schedule_editor_keyboard(members: list, draft: dict[int, int | None], picked_tg: int | None = None):
    """Черновик графика: строка на жильца; выбранный жилец раскрывается в дни недели."""
    rows = []
    for member in members:
        tg_id = member["tg_id"]
        weekday = draft.get(tg_id)
        value = WEEKDAY_SHORT[weekday] if weekday is not None else "—"
        prefix = "▸ " if tg_id == picked_tg else ""
        rows.append([Btn(text=f"{prefix}{member['display_name']}: {value}", callback_data=cb.schedule_member(tg_id))])
    if picked_tg is not None:
        day_rows = []
        row = []
        for weekday in range(7):
            row.append(Btn(text=WEEKDAY_SHORT[weekday], callback_data=cb.schedule_pick(picked_tg, weekday)))
            if len(row) == 4:
                day_rows.append(row)
                row = []
        row.append(Btn(text="—", callback_data=cb.schedule_pick(picked_tg, None)))
        day_rows.append(row)
        rows.extend(day_rows)
    rows.append([Btn(text="💾 Сохранить", callback_data=cb.schedule_save()),
                 Btn(text="✖️ Отмена", callback_data=cb.schedule_cancel())])
    return _kb(rows)


# ── Деньги ───────────────────────────────────────────────────────────────────

def balance_keyboard(pending_count: int, can_confirm: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_confirm and pending_count:
        rows.append([Btn(text=f"⏳ Подтвердить взносы ({pending_count})", callback_data=cb.pending())])
    rows.extend([
        [Btn(text="➕ Трата", callback_data=cb.expense_new()),
         Btn(text="💸 Внести деньги", callback_data=cb.contribute())],
        [Btn(text="📋 Все операции", callback_data=cb.money_history())],
        [Btn(text="📁 Экспорт и импорт", callback_data=cb.money_files())],
        [Btn(text="← Меню", callback_data=cb.menu())],
    ])
    return _kb(rows)


def pending_keyboard(pending_rows: list, currency: str) -> InlineKeyboardMarkup:
    from core.money import format_amount

    rows = []
    for row in pending_rows:
        who = row["display_name"] or "?"
        label = f"{who} · {format_amount(row['amount_kop'], currency)}"[:24]
        rows.append([
            Btn(text=f"✅ {label}", callback_data=cb.contribution_resolve(row["id"], True)),
            Btn(text="❌", callback_data=cb.contribution_resolve(row["id"], False)),
        ])
    rows.append([Btn(text="← Баланс", callback_data=cb.balance())])
    return _kb(rows)


def contribution_decision_keyboard(contribution_id: int) -> InlineKeyboardMarkup:
    return _kb([[
        Btn(text="✅ Подтвердить", callback_data=cb.contribution_resolve(contribution_id, True)),
        Btn(text="❌ Отклонить", callback_data=cb.contribution_resolve(contribution_id, False)),
    ]])


def categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for category in categories:
        row.append(Btn(text=category["name"], callback_data=cb.expense_category(category["id"])))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Btn(text="✖️ Отмена", callback_data=cb.menu())])
    return _kb(rows)


def mode_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [Btn(text="🏦 Из котла", callback_data=cb.expense_mode("house"))],
        [Btn(text="👛 За свои (ждёт возврата)", callback_data=cb.expense_mode("personal"))],
        [Btn(text="✖️ Отмена", callback_data=cb.menu())],
    ])


def photos_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [Btn(text="📸 Готово, сохранить", callback_data=cb.expense_photos_done())],
        [Btn(text="✖️ Отмена", callback_data=cb.menu())],
    ])


def description_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [Btn(text="Без описания", callback_data=cb.expense_desc_skip())],
    ])


def expenses_list_keyboard(expenses: list) -> InlineKeyboardMarkup:
    rows = [[Btn(text=f"{row['spent_on'][8:10]}.{row['spent_on'][5:7]} · {row['display_name'] or '?'} · "
                 f"{row['category_name'] or '—'}", callback_data=cb.expense_card(row["id"]))]
            for row in expenses]
    rows.extend([
        [Btn(text="➕ Трата", callback_data=cb.expense_new()),
         Btn(text="💸 Внести деньги", callback_data=cb.contribute())],
        [Btn(text="📋 Все операции", callback_data=cb.money_history())],
        [Btn(text="📁 Экспорт и импорт", callback_data=cb.money_files())],
        [Btn(text="← Меню", callback_data=cb.menu())],
    ])
    return _kb(rows)


def expense_card_keyboard(expense, photos_count: int, can_manage: bool, can_reimburse: bool) -> InlineKeyboardMarkup:
    rows = []
    if photos_count:
        rows.append([Btn(text=f"📎 Чеки ({photos_count})", callback_data=cb.expense_photos(expense["id"]))])
    if can_reimburse and expense["mode"] == "personal" and not expense["reimbursed"]:
        rows.append([Btn(text="↩️ Вернуть из котла", callback_data=cb.expense_reimburse(expense["id"]))])
    if can_manage:
        rows.append([Btn(text="🗑 Удалить трату", callback_data=cb.expense_delete(expense["id"]))])
    rows.append([Btn(text="← Траты", callback_data=cb.expenses_list())])
    return _kb(rows)


def history_keyboard(month: str, prev_month: str, next_month: str, can_nav_next: bool) -> InlineKeyboardMarkup:
    rows = [[
        Btn(text="‹", callback_data=cb.history(prev_month)),
        Btn(text="›", callback_data=cb.history(next_month) if can_nav_next else cb.noop()),
    ]]
    rows.append([Btn(text="← Меню", callback_data=cb.menu())])
    return _kb(rows)


# ── Настройки ────────────────────────────────────────────────────────────────

def settings_root_keyboard(
    is_owner: bool, chat_bound: bool, *, can_manage_members: bool | None = None,
    can_manage_categories: bool | None = None,
) -> InlineKeyboardMarkup:
    members_allowed = is_owner if can_manage_members is None else can_manage_members
    categories_allowed = is_owner if can_manage_categories is None else can_manage_categories
    rows = [
        [Btn(text="🔔 Мои уведомления", callback_data=cb.settings_notify())],
    ]
    if is_owner:
        rows.append([Btn(text="🏠 Настройки дома", callback_data=cb.settings_house())])
    if members_allowed:
        rows.append([Btn(text="👥 Права участников", callback_data=cb.settings_perms())])
        rows.append([Btn(text="💌 Ссылка-приглашение", callback_data=cb.settings_invite())])
    if categories_allowed:
        rows.append([Btn(text="🏷 Категории трат", callback_data=cb.settings_categories())])
    if is_owner:
        rows.append([Btn(text="🔗 Привязать этот чат" if not chat_bound else "🔗 Чат привязан ✓",
                         callback_data=cb.settings_bind_chat())])
    rows.append([Btn(text="← Меню", callback_data=cb.menu())])
    return _kb(rows)


def house_settings_keyboard(values: dict) -> InlineKeyboardMarkup:
    rows = []
    for definition in reg.HOUSE_SETTINGS:
        value = values[definition.key]
        if definition.kind == "bool":
            shown = "вкл" if value else "выкл"
        else:
            shown = definition.choice_labels.get(value, value) if definition.choice_labels else value
        rows.append([Btn(text=f"{definition.label}: {shown}", callback_data=cb.settings_house_set(definition.key))])
    rows.append([Btn(text="← Настройки", callback_data=cb.settings_root())])
    return _kb(rows)


def house_setting_choices_keyboard(key: str, choices: tuple) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for index, value in enumerate(choices):
        row.append(Btn(text=str(value), callback_data=cb.settings_house_value(key, index)))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Btn(text="← Настройки дома", callback_data=cb.settings_house())])
    return _kb(rows)


def notify_settings_keyboard(values: dict, is_owner: bool) -> InlineKeyboardMarkup:
    rows = []
    for definition in reg.NOTIFY_SETTINGS:
        if definition.for_owner_only and not is_owner:
            continue
        channel = reg.channel_label(values[definition.key])
        rows.append([Btn(text=f"{definition.label}: {channel}",
                         callback_data=cb.settings_notify_cycle(definition.key))])
    rows.append([Btn(text="← Настройки", callback_data=cb.settings_root())])
    return _kb(rows)


def perm_members_keyboard(members: list) -> InlineKeyboardMarkup:
    rows = [[Btn(text=member["display_name"], callback_data=cb.settings_perm_member(member["tg_id"]))]
            for member in members]
    rows.append([Btn(text="← Настройки", callback_data=cb.settings_root())])
    return _kb(rows)


def perm_toggle_keyboard(member, grants: frozenset[str]) -> InlineKeyboardMarkup:
    from core import permissions as perms

    rows = []
    for permission in perms.PERMISSIONS:
        mark = "✅" if permission.code in grants else "❌"
        rows.append([Btn(text=f"{mark} {permission.label}",
                         callback_data=cb.settings_perm_toggle(member["tg_id"], permission.code))])
    rows.append([Btn(text="← Участники", callback_data=cb.settings_perms())])
    return _kb(rows)


def categories_manage_keyboard(categories: list) -> InlineKeyboardMarkup:
    rows = [[Btn(text=f"🗑 {category['name']}", callback_data=cb.settings_category_delete(category["id"]))]
            for category in categories]
    rows.append([Btn(text="➕ Добавить категорию", callback_data=cb.category_add())])
    rows.append([Btn(text="← Настройки", callback_data=cb.settings_root())])
    return _kb(rows)


def invite_keyboard(link: str) -> InlineKeyboardMarkup:
    return _kb([
        [Btn(text="🔄 Обновить ссылку", callback_data=cb.settings_invite_refresh())],
        [Btn(text="← Настройки", callback_data=cb.settings_root())],
    ])


def transaction_cancel_keyboard() -> InlineKeyboardMarkup:
    return _kb([[Btn(text="Отмена → деньги", callback_data=cb.balance())]])


def transaction_back_keyboard() -> InlineKeyboardMarkup:
    return _kb([[Btn(text="← К записи", callback_data="tx_back")],
                [Btn(text="Отмена → деньги", callback_data=cb.balance())]])


def transaction_review_keyboard(kind: str, token: str) -> InlineKeyboardMarkup:
    rows = [
        [Btn(text="✅ Сохранить", callback_data=cb.transaction_save(token))],
        [Btn(text="Изменить сумму", callback_data=cb.transaction_field("amount")),
         Btn(text="Дата", callback_data=cb.transaction_field("date"))],
    ]
    if kind == "expense":
        rows += [
            [Btn(text="Категория", callback_data=cb.transaction_field("category")),
             Btn(text="Из котла / за свои", callback_data=cb.transaction_field("mode"))],
            [Btn(text="Описание", callback_data=cb.transaction_field("description")),
             Btn(text="Прикрепить чеки", callback_data=cb.transaction_field("photos"))],
        ]
    else:
        rows.append([Btn(text="За какой месяц", callback_data=cb.transaction_field("month"))])
    rows.append([Btn(text="Отмена → деньги", callback_data=cb.balance())])
    return _kb(rows)


def transaction_date_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [Btn(text="Сегодня", callback_data="tx_date:today"), Btn(text="Вчера", callback_data="tx_date:yesterday")],
        [Btn(text="← К записи", callback_data="tx_back")],
    ])


def transaction_categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    rows = [[Btn(text=row["name"], callback_data=f"tx_cat:{row['id']}")] for row in categories]
    rows += [[Btn(text="Без категории", callback_data="tx_cat:0")],
             [Btn(text="← К записи", callback_data="tx_back")]]
    return _kb(rows)


def transaction_success_keyboard(kind: str) -> InlineKeyboardMarkup:
    return _kb([
        [Btn(text="Добавить ещё", callback_data=cb.expense_new() if kind == "expense" else cb.contribute())],
        [Btn(text="📋 Все операции", callback_data=cb.money_history())],
        [Btn(text="← Деньги", callback_data=cb.balance())],
    ])


def money_files_keyboard(month: str, can_import: bool) -> InlineKeyboardMarkup:
    rows = [
        [Btn(text="Текущий месяц", callback_data="files_period:current"),
         Btn(text="Вся история", callback_data="files_period:all")],
        [Btn(text="Другой месяц", callback_data="files_period:custom")],
        [Btn(text=f"Скачать {fmt.upper()}", callback_data=f"file_export:{fmt}:{month}")
         for fmt in ("xlsx", "csv")],
        [Btn(text=f"Скачать {fmt.upper()}", callback_data=f"file_export:{fmt}:{month}")
         for fmt in ("tsv", "json")],
    ]
    if can_import:
        rows += [[Btn(text="📥 Загрузить операции", callback_data="file_import")],
                 [Btn(text="Шаблон Excel", callback_data="file_template:xlsx"),
                  Btn(text="Шаблон CSV", callback_data="file_template:csv"),
                  Btn(text="Шаблон JSON", callback_data="file_template:json")]]
    rows.append([Btn(text="← Деньги", callback_data=cb.balance())])
    return _kb(rows)


def import_review_keyboard(token: str | None) -> InlineKeyboardMarkup:
    rows = []
    if token:
        rows.append([Btn(text="✅ Подтвердить импорт", callback_data=f"file_apply:{token}")])
    rows += [[Btn(text="Загрузить другой файл", callback_data="file_import")],
             [Btn(text="← Файлы / отмена", callback_data=cb.money_files())]]
    return _kb(rows)
