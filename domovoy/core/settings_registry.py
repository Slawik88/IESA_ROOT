"""
core/settings_registry.py
Реестры настроек — основа «каждый дом настраивает всё под себя».

Настройка описывается один раз здесь (тип, значение по умолчанию, допустимые
значения, кому видна) — бот строит меню настроек и валидацию автоматически.
Значения хранятся в БД строками (house_settings / user_notify_settings);
чтение всегда идёт через get_house_setting / get_notify_setting, которые
подставляют значение по умолчанию из реестра.
"""
from dataclasses import dataclass
from typing import Any

from core.constants import DEFAULT_CURRENCY

# Куда доставать уведомление
NOTIFY_PRIVATE = "private"   # в личку
NOTIFY_CHAT = "chat"         # в привязанный чат дома
NOTIFY_OFF = "off"
NOTIFY_CHANNELS = (NOTIFY_PRIVATE, NOTIFY_CHAT, NOTIFY_OFF)


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str          # как называется в меню
    kind: str           # "bool" | "choice"
    default: Any
    choices: tuple[str, ...] | tuple[int, ...] | None = None
    choice_labels: dict | None = None   # подписи значений choice
    for_owner_only: bool = False        # настраивается только владельцем/правом


# ── Настройки дома (уровень всего дома) ──────────────────────────────────────
HOUSE_SETTINGS: tuple[SettingDef, ...] = (
    SettingDef("confirm_contributions", "Подтверждение взносов владельцем", "bool", True),
    SettingDef("morning_hour", "Час утреннего напоминания", "choice", 9,
               choices=tuple(range(6, 13))),
    SettingDef("evening_hour", "Час вечернего напоминания", "choice", 20,
               choices=tuple(range(18, 24))),
    SettingDef("evening_repeat", "Напоминать о пропущенном дне каждый вечер", "bool", True),
    SettingDef("monthly_report", "Ежемесячный отчёт по балансу", "bool", True),
    SettingDef("currency", "Валюта дома", "choice", DEFAULT_CURRENCY,
               choices=("CHF", "₽", "₴", "$", "€", "Br", "тг"),
               choice_labels={"CHF": "CHF — швейцарский франк"}),
    SettingDef("tz_offset_hours", "Часовой пояс дома (UTC+)", "choice", 3,
               choices=tuple(range(-10, 13))),
)

HOUSE_SETTING_BY_KEY = {s.key: s for s in HOUSE_SETTINGS}


# ── Персональные уведомления (каждый участник настраивает для себя) ──────────
NOTIFY_SETTINGS: tuple[SettingDef, ...] = (
    SettingDef("morning_reminder", "Утром: «сегодня твой день уборки»", "choice", NOTIFY_PRIVATE,
               choices=NOTIFY_CHANNELS),
    SettingDef("evening_reminder", "Вечером: «день не закрыт»", "choice", NOTIFY_PRIVATE,
               choices=NOTIFY_CHANNELS),
    SettingDef("cleaning_marked", "Кто-то отметил/пропустил уборку", "choice", NOTIFY_CHAT,
               choices=NOTIFY_CHANNELS),
    SettingDef("expense_added", "Кто-то добавил трату", "choice", NOTIFY_CHAT,
               choices=NOTIFY_CHANNELS),
    SettingDef("contribution_declared", "Жилец заявил взнос (для подтвердившего право)",
               "choice", NOTIFY_PRIVATE, choices=NOTIFY_CHANNELS, for_owner_only=True),
    SettingDef("contribution_confirmed", "Мой взнос подтверждён/отклонён", "choice", NOTIFY_PRIVATE,
               choices=NOTIFY_CHANNELS),
    SettingDef("monthly_report", "Ежемесячный отчёт", "choice", NOTIFY_PRIVATE,
               choices=NOTIFY_CHANNELS),
)

NOTIFY_SETTING_BY_KEY = {s.key: s for s in NOTIFY_SETTINGS}


def channel_label(value: str) -> str:
    return {NOTIFY_PRIVATE: "личка", NOTIFY_CHAT: "чат", NOTIFY_OFF: "выкл"}.get(value, value)
