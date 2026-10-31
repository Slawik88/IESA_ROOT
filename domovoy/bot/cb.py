"""
bot/cb.py — коды inline-кнопок.

Схема: "<префикс>:<арг1>:<арг2>". Все аргументы — числа или короткие токены;
парсинг строгий, чужие callback_data просто не совпадут с хендлерами.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Cb:
    data: str


def menu() -> str:
    return "menu"

def today() -> str:
    return "today"

def done(actual: str) -> str:
    return f"done:{actual}"

def schedule_view() -> str:
    return "sched"

def schedule_edit() -> str:
    return "sched_edit"

def schedule_pick(tg_id: int, weekday: int | None) -> str:
    return f"sched_pick:{tg_id}:{weekday if weekday is not None else 'x'}"

def schedule_member(tg_id: int) -> str:
    return f"sched_m:{tg_id}"

def house_create() -> str:
    return "house_new"

def category_add() -> str:
    return "cat_new"

def schedule_save() -> str:
    return "sched_save"

def schedule_cancel() -> str:
    return "sched_cancel"

def day_close(day_id: int) -> str:
    return f"day_close:{day_id}"

def day_cancel(day_id: int) -> str:
    return f"day_cancel:{day_id}"

def balance() -> str:
    return "bal"

def pending() -> str:
    return "pend"

def contribution_resolve(contribution_id: int, confirm: bool) -> str:
    return f"cres:{contribution_id}:{1 if confirm else 0}"

def expenses_list() -> str:
    return "exps"

def expense_card(expense_id: int) -> str:
    return f"exp:{expense_id}"

def expense_photos(expense_id: int) -> str:
    return f"exp_photos:{expense_id}"

def expense_reimburse(expense_id: int) -> str:
    return f"exp_reimb:{expense_id}"

def expense_delete(expense_id: int) -> str:
    return f"exp_del:{expense_id}"

def expense_new() -> str:
    return "exp_new"

def expense_category(category_id: int) -> str:
    return f"exp_cat:{category_id}"

def expense_mode(mode: str) -> str:
    return f"exp_mode:{mode}"

def expense_photos_done() -> str:
    return "exp_photos_done"

def expense_desc_skip() -> str:
    return "exp_desc_skip"

def contribute() -> str:
    return "skid"

def history(month: str) -> str:
    return f"hist:{month}"

def settings_root() -> str:
    return "st"

def settings_house() -> str:
    return "st_house"

def settings_house_set(key: str) -> str:
    return f"st_h:{key}"

def settings_house_value(key: str, index: int) -> str:
    return f"st_hv:{key}:{index}"

def settings_notify() -> str:
    return "st_notify"

def settings_notify_cycle(key: str) -> str:
    return f"st_n:{key}"

def settings_perms() -> str:
    return "st_perm"

def settings_perm_member(tg_id: int) -> str:
    return f"st_perm_m:{tg_id}"

def settings_perm_toggle(tg_id: int, code: str) -> str:
    return f"st_perm_t:{tg_id}:{code}"

def settings_categories() -> str:
    return "st_cat"

def settings_category_delete(category_id: int) -> str:
    return f"st_cat_del:{category_id}"

def settings_bind_chat() -> str:
    return "st_chat"

def settings_invite() -> str:
    return "st_invite"

def houses_list() -> str:
    return "houses"

def house_select(house_id: int) -> str:
    return f"house:{house_id}"

def noop() -> str:
    return "noop"


def parse(data: str) -> list[str]:
    """Разобрать callback_data на части; пустых частей не бывает."""
    parts = data.split(":")
    if not parts or not parts[0]:
        raise ValueError("Пустой callback_data")
    return parts
