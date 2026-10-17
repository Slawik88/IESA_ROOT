"""Дефолты и подписи «скалярных» настроек чата (вне реестра модулей).

core.chat_modules отвечает за модули-механики; здесь — остальные настройки
chat_settings, которые меняются из бота и панели модератора: пороги рангов,
пороги чистки и чатовые тумблеры. Значения синхронизированы с fallback-словарём
get_chat_settings (infrastructure/repositories/moderation.py) и DDL chat_settings
(bot/core/database.py); для отката «к стандарту» источник истины — этот словарь.
"""
from __future__ import annotations

from typing import Final

# Только настройки, видимые в интерфейсах бота и сайта. Скрытые служебные
# колонки (shield_duration_days, max_warnings, notif_* и т.п.) сброс не трогает.
# rank_mute/rank_kick/rank_ban = 1/1/2 — дефолты из коммита 42e31338 («выровнены
# на фактическое поведение бота до фикса»); DDL chat_settings выровнен на те же
# значения (ALTER COLUMN SET DEFAULT в _init_users_and_chats — новые строки,
# старые значения чатов не переписываются).
CHAT_SETTING_DEFAULTS: Final = {
    "rank_warn": 2,
    "rank_mute": 1,
    "rank_kick": 1,
    "rank_ban": 2,
    "rank_shield": 4,
    "rank_immune": 5,
    "rank_marriage": 0,
    "rank_give": 0,
    "purge_min_rank": 4,
    "purge_action_rank": 2,
    "purge_write_rank": 0,
    "rank_chat_lock": 4,
    "nsfw_warps_allowed": 1,
    "include_in_global_top": 1,
}

# Подписи для журнала изменений (единый вид в боте и мини-аппе).
CHAT_SETTING_LABELS: Final = {
    "rank_warn": "⚠️ Выдавать варны",
    "rank_mute": "🔇 Ставить мут",
    "rank_kick": "👢 Кикнуть из чата",
    "rank_ban": "🔨 Забанить навсегда",
    "rank_shield": "🛡 Выдавать щит",
    "rank_immune": "🔰 Давать иммунитет",
    "rank_marriage": "💍 Предлагать брак",
    "rank_give": "💸 Переводить мору/алмазы",
    "purge_min_rank": "🧹 Освобождены от чистки",
    "purge_action_rank": "⚖️ Кнопки вердикта в сводке",
    "purge_write_rank": "✍️ Пишут во время чистки",
    "rank_chat_lock": "🔒 Открывать/закрывать чат",
    "nsfw_warps_allowed": "🔞 18+ варп-команды",
    "include_in_global_top": "🏆 Участие в глобальном топе",
    "timezone": "🕓 Часовой пояс",
    "admin_chat": "🔗 Админ-чат",
}


def chat_setting_label(key: str) -> str:
    """Человеческая подпись настройки; модули — по реестру, иначе сам ключ."""
    from core.chat_modules import CHAT_MODULES

    if key in CHAT_SETTING_LABELS:
        return CHAT_SETTING_LABELS[key]
    spec = CHAT_MODULES.get(key)
    if spec:
        return f"{spec['icon']} {spec['name']}"
    return key
