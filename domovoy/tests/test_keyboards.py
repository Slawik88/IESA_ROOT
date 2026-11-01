"""
tests/test_keyboards.py — регрессия: все inline-кнопки строятся без ошибок.

Прод-инцидент 2026-11-01: InlineKeyboardButton в aiogram 3 — pydantic-модель,
позиционные аргументы падают только при первом реальном обновлении. Тест
строит основные клавиатуры — позиционный Btn(...) не пройдёт здесь.
"""
from aiogram.types import InlineKeyboardButton

from bot import cb, keyboards as kb


def test_all_buttons_are_keyword_only():
    """Ни одна кнопка в меню не должна строиться позиционными аргументами."""
    for markup in (
        kb.onboarding(),
        kb.main_menu(can_switch_house=True),
        kb.back_to_menu(),
        kb.bind_chat_keyboard(),
        kb.today_keyboard([], "2026-11-01", "2026-10-31", []),
        kb.schedule_keyboard(can_edit=True),
        kb.balance_keyboard(0, False),
        kb.mode_keyboard(),
        kb.photos_keyboard(),
        kb.description_keyboard(),
        kb.expenses_list_keyboard([]),
        kb.settings_root_keyboard(is_owner=True, chat_bound=False),
        kb.categories_manage_keyboard([]),
    ):
        for row in markup.inline_keyboard:
            for button in row:
                assert isinstance(button, InlineKeyboardButton)
                assert button.text and button.callback_data


def test_keyboards_with_data():
    markup = kb.schedule_editor_keyboard(
        [{"tg_id": 1, "display_name": "Аня"}], {1: None}, picked_tg=1)
    assert any(b.callback_data == cb.schedule_pick(1, 3) for row in markup.inline_keyboard for b in row)

    pending = kb.pending_keyboard(
        [{"id": 5, "display_name": "Борис", "amount_kop": 300000}], "₽")
    assert any("Борис" in b.text for row in pending.inline_keyboard for b in row)
