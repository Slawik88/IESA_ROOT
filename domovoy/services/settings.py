"""
services/settings.py — чтение/запись настроек по реестрам.

Источник значений — core/settings_registry. Всё, что не переопределено в БД,
берётся из реестра: новый дом сразу работает на разумных дефолтах.
"""
import json
from datetime import datetime, timedelta
from typing import Any

from core import settings_registry as reg
from infrastructure import repositories as repo
from services.households import DomainError


async def house_settings(house_id: int) -> dict[str, Any]:
    """Все настройки дома уже приведёнными к типу значениями."""
    raw = await repo.settings.house_settings_all(house_id)
    result: dict[str, Any] = {}
    for definition in reg.HOUSE_SETTINGS:
        if definition.key in raw:
            result[definition.key] = json.loads(raw[definition.key])
        else:
            result[definition.key] = definition.default
    return result


async def house_setting(house_id: int, key: str) -> Any:
    definition = reg.HOUSE_SETTING_BY_KEY.get(key)
    if definition is None:
        raise ValueError(f"Неизвестная настройка дома: {key}")
    raw = await repo.settings.house_settings_all(house_id)
    return json.loads(raw[key]) if key in raw else definition.default


async def set_house_setting(house_id: int, key: str, value: Any) -> None:
    definition = reg.HOUSE_SETTING_BY_KEY.get(key)
    if definition is None:
        raise DomainError("Неизвестная настройка")
    if definition.kind == "bool":
        if not isinstance(value, bool):
            raise DomainError("Ожидалось вкл/выкл")
    elif definition.kind == "choice":
        if value not in (definition.choices or ()):
            raise DomainError("Недопустимое значение настройки")
    await repo.settings.set_house_setting(house_id, key, value)


async def notify_settings(house_id: int, tg_id: int) -> dict[str, str]:
    raw = await repo.settings.notify_settings_all(house_id, tg_id)
    return {
        definition.key: raw.get(definition.key, definition.default)
        for definition in reg.NOTIFY_SETTINGS
    }


async def set_notify_setting(house_id: int, tg_id: int, key: str, value: str) -> None:
    definition = reg.NOTIFY_SETTING_BY_KEY.get(key)
    if definition is None or value not in reg.NOTIFY_CHANNELS:
        raise DomainError("Неизвестная настройка уведомлений")
    await repo.settings.set_notify_setting(house_id, tg_id, key, value)


# ── Локальное время дома ─────────────────────────────────────────────────────

def house_now(settings: dict[str, Any]) -> datetime:
    """Сейчас в доме: UTC + смещение из настроек. Наивные часы локального дня."""
    offset = int(settings.get("tz_offset_hours", 0))
    return datetime.utcnow() + timedelta(hours=offset)


def house_today(settings: dict[str, Any]) -> str:
    return house_now(settings).strftime("%Y-%m-%d")
