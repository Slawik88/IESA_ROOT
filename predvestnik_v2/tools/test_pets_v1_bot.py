#!/usr/bin/env python3
"""Contract proof for the chat pet hub: escaping, buttons, tokens, ownership."""
from pathlib import Path
import asyncio
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from bot.filters.text_commands import TextCmd
from bot.handlers import _pets_ui as ui
from bot.handlers import pets_v1_callbacks as pvc
from bot.handlers.pets_v1 import (
    EXPEDITION_ALIASES, HUB_ALIASES, TREK_ALIASES, cmd_pets_v1,
    parse_activity_hours, parse_expedition_route, render_pet_overview,
)
from core.chests_v1 import PET_SPECIES
from services import pets_v1 as pets_service

empty = render_pet_overview({"pets": []})
assert "пока нет питомцев" in empty and "одному ключу" in empty
text = render_pet_overview({"pets": [{
    "name": "<Лис>", "level": 4, "endurance": 95, "active": True,
    "effects": {"visual_stage": "Развитый облик"},
}]})
assert "&lt;Лис&gt;" in text
assert "4" in text and "95/100" in text and "активный" in text
assert "select_active_pet" not in text
active_text = render_pet_overview({"pets": [], "activity": {"kind": "trek", "status": "active", "ends_at": "2026-09-05T18:00:00+00:00"}})
assert "Поход идёт" in active_text and "2026-09-05 18:00" in active_text
ready_text = render_pet_overview({"pets": [], "activity": {"kind": "expedition", "status": "ready"}})
assert "Экспедиция: таймер завершён" in ready_text and "бот маршрут, осторожный" in ready_text
chosen_text = render_pet_overview({"pets": [], "activity": {"kind": "expedition", "status": "ready", "decision": "bold"}})
assert "выбран рискованный маршрут" in chosen_text
assert "Ключ уже зачислен" in chosen_text
assert parse_activity_hours("3") == 3 and parse_activity_hours(" 9 ") == 9
for invalid in ("", "4", "03", "три"):
    try: parse_activity_hours(invalid)
    except ValueError: pass
    else: raise AssertionError(f"invalid chat duration accepted: {invalid!r}")
assert parse_expedition_route(" осторожный ") == "careful"
assert parse_expedition_route("ровный") == "steady"
assert parse_expedition_route("рискованный") == "bold"
for invalid in ("", "смелый", "careful", "осторожный маршрут"):
    try: parse_expedition_route(invalid)
    except ValueError: pass
    else: raise AssertionError(f"invalid chat route accepted: {invalid!r}")

# ── Button views: navigation, per-render tokens and owner payloads ────────────
PACK = ui.pack_pet_callback
TOKEN_RE = re.compile(r"^[0-9a-f]{12}$")


def callbacks_of(markup):
    return [ui.PetsCB.unpack(button.callback_data) for row in markup.inline_keyboard for button in row if button.callback_data]


def labels_of(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


FOOD = {"id": "food_basic", "name": "Дорожный паёк", "restore": 15, "icon": "🥕", "quantity": 2}
PET_ONE = {
    "id": 7, "name": "<Лис>", "species_id": "salt_fox", "rarity": "uncommon", "level": 4,
    "endurance": 95, "active": False,
    "effects": {"visual_stage": "Развитый облик", "expedition_route_bonus_percent": 3,
                "expedition_hint_charges": 1, "expedition_risk_guard_percent": 0,
                "expedition_extra_option": False, "max_level_effect": False},
}
PET_TWO = {**PET_ONE, "id": 8, "name": "Моховой кот", "species_id": "moss_cat", "level": 1,
           "endurance": 100, "active": True, "effects": {"visual_stage": "Начальный облик"}}
BESTIARY = [{"id": key, **row, "owned": index < 3} for index, (key, row) in enumerate(PET_SPECIES.items())]
VIEW = {
    "active_pet_id": 8, "pets": [PET_ONE, PET_TWO],
    "bestiary": BESTIARY, "bestiary_owned": 3, "bestiary_total": 12,
    "durations": [3, 6, 9], "activity": None,
    "food": [FOOD], "activity_costs": {3: 25, 6: 40, 9: 55},
}
READY = {**VIEW, "activity": {"kind": "expedition", "status": "ready", "decision": None}}
RUNNING = {**VIEW, "activity": {"kind": "trek", "status": "active", "ends_at": "2026-09-05T18:00:00+00:00"}}

text, markup = ui.menu_view(VIEW, user_id=777, pack=PACK)
assert {"pets", "best", "act"} <= {c.action for c in callbacks_of(markup)}
assert all(c.user_id == 777 for c in callbacks_of(markup))
assert any(button.url for row in markup.inline_keyboard for button in row)
assert "&lt;Лис&gt;" in text and "95/100" in text

text, markup = ui.menu_view(READY, user_id=777, pack=PACK)
routes = [c for c in callbacks_of(markup) if c.action == "route"]
assert {c.value for c in routes} == {"careful", "steady", "bold"}
assert all(TOKEN_RE.fullmatch(c.token) for c in routes)
assert len({c.token for c in routes}) == 3, "each rendered route button needs its own token"
assert "Экспедиция: таймер завершён" in text
_, markup2 = ui.menu_view(READY, user_id=777, pack=PACK)
fresh = {c.token for c in callbacks_of(markup2) if c.action == "route"}
assert fresh.isdisjoint({c.token for c in routes}), "a re-render must mint fresh tokens"

text, markup = ui.pet_card_view(VIEW, 7, user_id=777, pack=PACK)
assert "&lt;Лис&gt;" in text and "Развитый облик" in text
activate = [c for c in callbacks_of(markup) if c.action == "activate"]
assert len(activate) == 1 and activate[0].pet_id == 7 and TOKEN_RE.fullmatch(activate[0].token)
text, markup = ui.pet_card_view(VIEW, 8, user_id=777, pack=PACK)
assert "Активный спутник" in text
assert not [c for c in callbacks_of(markup) if c.action == "activate"], "an active pet has nothing to activate"

text, markup = ui.feed_view(VIEW, 7, user_id=777, pack=PACK)
foods = [c for c in callbacks_of(markup) if c.action == "food"]
assert len(foods) == 1 and foods[0].value == "food_basic" and foods[0].pet_id == 7
assert {"🥕 Дорожный паёк +15 · ×2"} <= set(labels_of(markup)), "the button shows restore and stock"

text, markup = ui.activity_view(VIEW, "trek", user_id=777, pack=PACK)
starts = [c for c in callbacks_of(markup) if c.action == "start"]
assert {c.amount for c in starts} == {3, 6, 9} and all(c.value == "trek" for c in starts)
assert {"3 ч · −25", "6 ч · −40", "9 ч · −55"} <= set(labels_of(markup))
text, markup = ui.activity_view(RUNNING, "expedition", user_id=777, pack=PACK)
assert "идёт до" in text and "2026-09-05 18:00" in text
assert not [c for c in callbacks_of(markup) if c.action == "start"], "one shared timer blocks a second start"
lonely = {**VIEW, "active_pet_id": None, "pets": [{**PET_ONE, "active": False}]}
text, markup = ui.activity_view(lonely, "trek", user_id=777, pack=PACK)
assert "выбери активного питомца" in text.lower()
assert [c for c in callbacks_of(markup) if c.action == "pets"]

text, markup = ui.bestiary_view(VIEW, user_id=777, pack=PACK)
assert "3/12" in text and text.count("✅") == 3 and "Неизвестный питомец" in text

text, markup = ui.route_view(READY, user_id=777, pack=PACK)
assert {c.value for c in callbacks_of(markup) if c.action == "route"} == {"careful", "steady", "bold"}
text, markup = ui.route_view(VIEW, user_id=777, pack=PACK)
assert "Нет завершённой экспедиции" in text
text, markup = ui.speedup_view(RUNNING, user_id=777, pack=PACK)
assert "Ускорения нет" in text

payload = ui.pack_pet_callback("start", value="expedition", amount=6, token="a1b2c3d4e5f6", user_id=9_999_999_999)
parsed = ui.PetsCB.unpack(payload)
assert parsed.action == "start" and parsed.value == "expedition" and parsed.amount == 6
assert parsed.user_id == 9_999_999_999
worst = ui.pack_pet_callback("activate", pet_id=9_999_999_999, value="food_feast", amount=9, token="f" * 12, user_id=9_999_999_999)
assert len(worst.encode("utf-8")) <= 64, "callback payload must fit the Telegram limit"

# ── Handler contract: every callback guards the owner; actions use the token ──
callbacks_source = (ROOT / "bot/handlers/pets_v1_callbacks.py").read_text(encoding="utf-8")
assert callbacks_source.count("await _guard(query, callback_data)") == callbacks_source.count("@router.callback_query(")
assert "check_callback_owner" in callbacks_source


class _FakeUser:
    def __init__(self, user_id): self.id = user_id


class _FakeMessage:
    def __init__(self): self.edits = []

    async def edit_text(self, text, reply_markup=None, parse_mode=None):
        self.edits.append(text)


class _FakeQuery:
    def __init__(self, user_id):
        self.from_user = _FakeUser(user_id)
        self.message = _FakeMessage()
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


CALLS = {}


class _FakeOutMessage:
    def __init__(self, user_id=777):
        self.from_user = _FakeUser(user_id)
        self.sent = []

    async def answer(self, text, reply_markup=None, parse_mode=None):
        self.sent.append((text, reply_markup))


class _FakeTextMessage:
    def __init__(self, text): self.text = text


async def _fake_select(db, user_id, pet_id, action_id):
    CALLS["activate"] = (user_id, pet_id, action_id)
    return {"ok": True}


async def _fake_chat_overview(db, user_id):
    CALLS["view_user"] = user_id
    return VIEW


async def _fake_feed(db, *, user_id, pet_id, food_id, action_id):
    CALLS["feed"] = (user_id, pet_id, food_id, action_id)
    return {"endurance": 100, "remaining": 1}


async def _fake_start(db, *, user_id, kind, hours, action_id):
    CALLS["start"] = (user_id, kind, hours, action_id)
    return {"activity": {"ends_at": "2026-09-06T21:00:00+00:00"}, "endurance": 60}


# Alias wiring: the hub also answers «зоопарк»/«мои питомци», treks keep the comma form.
hub_filter = TextCmd(HUB_ALIASES)
assert asyncio.run(hub_filter(_FakeTextMessage("бот зоопарк"))) == {"text_args": ""}
assert asyncio.run(hub_filter(_FakeTextMessage("бот активный питомец"))) == {"text_args": ""}
assert asyncio.run(hub_filter(_FakeTextMessage("бот зоопарк закрыт"))) is False
assert asyncio.run(TextCmd(TREK_ALIASES)(_FakeTextMessage("бот походы"))) == {"text_args": ""}
assert asyncio.run(TextCmd(TREK_ALIASES)(_FakeTextMessage("бот поход, 6"))) == {"text_args": "6"}
assert asyncio.run(TextCmd(EXPEDITION_ALIASES)(_FakeTextMessage("бот экспедиции"))) == {"text_args": ""}

original_select = pets_service.select_active_pet
original_view = pets_service.chat_overview
original_feed = pets_service.feed_pet
original_start = pets_service.start_activity
try:
    pets_service.select_active_pet = _fake_select
    pets_service.chat_overview = _fake_chat_overview
    pets_service.feed_pet = _fake_feed
    pets_service.start_activity = _fake_start
    token = "0123456789ab"
    callback_data = ui.PetsCB(action="activate", pet_id=7, token=token, user_id=777)

    stranger = _FakeQuery(1)
    asyncio.run(pvc.cb_pet_activate(stranger, callback_data, None))
    assert "activate" not in CALLS and not stranger.message.edits, "a stranger must not touch the pet"
    assert stranger.answers and stranger.answers[-1][1] is True

    owner = _FakeQuery(777)
    asyncio.run(pvc.cb_pet_activate(owner, callback_data, None))
    assert CALLS["activate"] == (777, 7, f"chat:active:{token}")
    assert owner.answers and "активный" in str(owner.answers[-1][0])
    assert owner.message.edits and "&lt;Лис&gt;" in owner.message.edits[0], "the owner sees the refreshed card"

    feeder = _FakeQuery(777)
    asyncio.run(pvc.cb_pet_feed(feeder, ui.PetsCB(action="food", pet_id=7, value="food_basic", token=token, user_id=777), None))
    assert CALLS["feed"] == (777, 7, "food_basic", f"chat:feed:{token}")
    assert "+15" in str(feeder.answers[-1][0]) and "100/100" in str(feeder.answers[-1][0])

    starter = _FakeQuery(777)
    asyncio.run(pvc.cb_pet_start(starter, ui.PetsCB(action="start", value="expedition", amount=6, token=token, user_id=777), None))
    assert CALLS["start"] == (777, "expedition", 6, f"chat:start:{token}")
    assert "6 ч" in str(starter.answers[-1][0]) and "2026-09-06 21:00" in str(starter.answers[-1][0])

    hub = _FakeOutMessage(777)
    asyncio.run(cmd_pets_v1(hub, None, text_args=""))
    assert hub.sent and "ПИТОМЦЫ" in hub.sent[0][0] and hub.sent[0][1] is not None
finally:
    pets_service.select_active_pet = original_select
    pets_service.chat_overview = original_view
    pets_service.feed_pet = original_feed
    pets_service.start_activity = original_start

print("OK: chat pet hub is escaped, owner-locked, tokenized and legacy commands stay strict")
