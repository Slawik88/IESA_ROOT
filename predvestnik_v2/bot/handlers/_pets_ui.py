"""Chat-side pet views (façade): re-exports the split rendering modules.

Handlers import this module as the single entry point; the implementation lives
in ``_pets_ui_base`` (primitives and hub text), ``_pets_ui_pets`` (collection,
cards, feeding, bestiary) and ``_pets_ui_activity`` (timers and routes).
"""
from bot.handlers._pets_ui_activity import activity_view, route_view, speedup_view
from bot.handlers._pets_ui_base import (
    ACTIVITY_TITLES,
    DEFAULT_DURATIONS,
    Pack,
    PetsCB,
    RARITY_LABELS,
    ROUTE_LABELS,
    Row,
    active_pet,
    activity_sentence,
    find_pet,
    markup_rows,
    menu_button,
    needs_decision,
    new_token,
    pack_pet_callback,
    pet_endurance,
    pet_icon,
    pet_level,
    pet_name,
    render_pet_overview,
    route_button_row,
)
from bot.handlers._pets_ui_pets import bestiary_view, feed_view, menu_view, pet_card_view, pets_view
