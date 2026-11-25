#!/usr/bin/env python3
"""Контракт чат-хаба питомцев и часового пояса: экранирование, кнопки, токены, права.

Без базы: проверяются рендеры (чистые функции), разборы команд, владелец в
колбэках, лимит длины callback_data и регистрация команд/разделов в каркасе.
"""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from bot.chat import chat_timezone as tz  # noqa: E402
from bot.chat import pets as pets_chat  # noqa: E402
from bot.chat import pets_activity_views as activity_ui  # noqa: E402
from bot.chat import pets_collection_views as collection_ui  # noqa: E402
from bot.chat import pets_views as ui  # noqa: E402
from core.chests_v1 import PET_SPECIES  # noqa: E402
from services import pets_v1  # noqa: E402

USER = 42

ROUTES_PAID = {
    "rewards_enabled": True, "hint": True, "weekly_remaining_mora": 320, "weekly_cap_mora": 400,
    "routes": [
        {"id": "careful", "chance_percent": 95, "reward_mora": 84},
        {"id": "steady", "chance_percent": 80, "reward_mora": 100},
        {"id": "scout", "chance_percent": 70, "reward_mora": 114},
        {"id": "bold", "chance_percent": 60, "reward_mora": 133},
    ],
}


def view(**over) -> dict:
    data = {
        "pets": [{
            "id": 7, "name": "<Лис>", "species_id": "star_dragon", "level": 13, "endurance": 95, "active": True,
            "effects": {"visual_stage": "Развитый облик", "expedition_route_bonus_percent": 10,
                        "expedition_hint_charges": 1, "expedition_extra_option": True},
        }],
        "food": [{"id": "food_basic", "icon": "🥕", "name": "Дорожный паёк", "restore": 15, "quantity": 2}],
        "bestiary": [
            {"id": "star_dragon", "name": "Звёздный дракон", "rarity": "legendary", "icon": "🐉", "owned": True},
            {"id": "void_lynx", "name": "Рысь", "rarity": "epic", "icon": "🐈‍⬛", "owned": False},
        ],
        "bestiary_owned": 1, "bestiary_total": 2,
        "activity": {"kind": "expedition", "status": "ready", "decision": None, "duration_hours": 6, "pet_id": 7},
        "route_options": ROUTES_PAID,
        "activity_costs": {3: 25, 6: 40, 9: 55},
        "durations": [3, 6, 9],
        "activity_key_counts": {"trek": 1, "expedition": 2},
        "features": {"route_rewards": True},
    }
    data.update(over)
    return data


def buttons(markup) -> list[tuple[str, str | None, str | None]]:
    return [(b.text, b.callback_data, getattr(b, "url", None)) for row in markup.inline_keyboard for b in row]


def pv_payloads(markup) -> list[ui.PetsCB]:
    out = []
    for text, data, url in buttons(markup):
        if url is None:
            assert len(str(data).encode()) <= 64, f"callback слишком длинный: {text} -> {data}"
            if str(data).startswith("pv:"):
                out.append(ui.PetsCB.unpack(str(data)))
    return out


# ── Хаб: текст, экранирование, подсказки ─────────────────────────────────────


empty = ui.render_pet_overview({"pets": []})
assert "пока нет питомцев" in empty and "ключи" in empty

text = ui.render_pet_overview(view())
assert "&lt;Лис&gt;" in text and "<Лис>" not in text          # имя экранировано
assert "нужен маршрут" in text and "осталось 320 из 400" in text
assert ui.pet_icon("нет_такого") == "🐾"
assert ui.pet_icon("star_dragon") == PET_SPECIES["star_dragon"]["icon"]

no_hint = view(route_options={**ROUTES_PAID, "hint": False})
assert "С 4 уровня питомец покажет шансы маршрутов" in ui.render_pet_overview(no_hint)
assert ui.route_meta_lines({"rewards_enabled": False, "routes": []}) == []

# ── Кнопки меню: маршруты, владелец, лимит длины ─────────────────────────────


text, markup = collection_ui.menu_view(view(), user_id=USER, pack=ui.pack_pet_callback)
labels = " · ".join(b[0] for b in buttons(markup))
assert "Мои питомцы · 1" in labels and "Бестиарий · 1/2" in labels and "Покормить" in labels
assert "🖼 Открыть в Mini App" in labels

routes = [p for p in pv_payloads(markup) if p.action == "route"]
assert {r.value for r in routes} == {"careful", "steady", "scout", "bold"}   # разведка с 12 ур. на месте
assert any("95%" in b[0] and "+84 🪙" in b[0] for b in buttons(markup))
assert all(r.user_id == USER for r in pv_payloads(markup) if r.action in ("route", "menu", "pets", "best", "act", "feed"))

# Без подсказок — без процентов; без наград — три классических маршрута.
_, markup = collection_ui.menu_view(no_hint, user_id=USER, pack=ui.pack_pet_callback)
assert not any("%" in b[0] for b in buttons(markup))
_, markup = collection_ui.menu_view(view(route_options={"rewards_enabled": False, "routes": []}),
                                    user_id=USER, pack=ui.pack_pet_callback)
assert {p.value for p in pv_payloads(markup) if p.action == "route"} == {"careful", "steady", "bold"}

# ── Коллекция: список, карточка, кормление, бестиарий ────────────────────────


_, markup = collection_ui.pets_view(view(), user_id=USER, pack=ui.pack_pet_callback)
payloads = pv_payloads(markup)
assert any(p.action == "pet" and p.pet_id == 7 for p in payloads)
assert "&lt;Лис&gt;" in buttons(markup)[0][0]

card_text, card_markup = collection_ui.pet_card_view(view(), 7, user_id=USER, pack=ui.pack_pet_callback)
assert "13</b>/16" in card_text and "Активный спутник" in card_text
assert not any(p.action == "activate" for p in pv_payloads(card_markup))       # уже активный
card_text, card_markup = collection_ui.pet_card_view(
    view(pets=[{**view()["pets"][0], "active": False}]), 7, user_id=USER, pack=ui.pack_pet_callback)
assert "Сделать активным" in " ".join(b[0] for b in buttons(card_markup))
activate = [p for p in pv_payloads(card_markup) if p.action == "activate"][0]
assert len(activate.token) == 12, activate.token

feed_text, feed_markup = collection_ui.feed_view(view(), 7, user_id=USER, pack=ui.pack_pet_callback)
assert "Дорожный паёк +15 · ×2" in " ".join(b[0] for b in buttons(feed_markup))
assert any(p.action == "food" and p.value == "food_basic" and len(p.token) == 12 for p in pv_payloads(feed_markup))

best_text, _ = collection_ui.bestiary_view(view(), user_id=USER, pack=ui.pack_pet_callback)
assert "Звёздный дракон" in best_text and "открыт" in best_text and "Неизвестный питомец" in best_text

# ── Активности: награды, статус, ускорение ───────────────────────────────────


trek_text, trek_markup = activity_ui.activity_view(
    view(activity=None), "trek", user_id=USER, pack=ui.pack_pet_callback)
assert "1 ключ" in trek_text and "6 ч · −40" in " ".join(b[0] for b in buttons(trek_markup))
exp_text, _ = activity_ui.activity_view(view(activity=None), "expedition", user_id=USER, pack=ui.pack_pet_callback)
assert "2 ключа" in exp_text and "маршрут" in exp_text.lower()

route_text, route_markup = activity_ui.route_view(view(), user_id=USER, pack=ui.pack_pet_callback)
assert "ВЫБОР МАРШРУТА" in route_text
assert {p.value for p in pv_payloads(route_markup) if p.action == "route"} == {"careful", "steady", "scout", "bold"}

idle_route_text, idle_markup = activity_ui.route_view(view(activity=None, route_options=None),
                                                      user_id=USER, pack=ui.pack_pet_callback)
assert "Нет завершённой экспедиции" in idle_route_text

speed_text, _ = activity_ui.speedup_view(view(), user_id=USER, pack=ui.pack_pet_callback)
assert "УСКОРЕНИЕ" in speed_text and "Выбери маршрут" in speed_text

# Итог выбора маршрута: успех, провал, лимит недели.
win = pets_chat._route_result_text("steady", {"route": {"success": True, "paid_mora": 80, "reward_mora": 80}, "amount_keys": 2})
assert "+80 🪙" in win and "+2 🗝" in win
fail = pets_chat._route_result_text("bold", {"route": {"success": False}, "amount_keys": 1})
assert "ничего не потеряно" in fail
capped = pets_chat._route_result_text("careful", {"route": {"success": True, "paid_mora": 40, "reward_mora": 84,
                                                           "capped": True}, "amount_keys": 0})
assert "начислено 40 из 84 🪙" in capped

# ── Разборы команд и токены ──────────────────────────────────────────────────


assert pets_chat.parse_hours("6") == 6
try:
    pets_chat.parse_hours("5")
except ValueError:
    pass
else:
    raise AssertionError("часы 5 должны быть отклонены")

assert pets_chat.parse_route("Осторожный") == "careful"
assert pets_chat.parse_route(" ровный ") == "steady"
assert pets_chat.parse_route("разведка") == "scout"
assert pets_chat.parse_route("РАЗВЕДАТЬ") == "scout"
try:
    pets_chat.parse_route("быстрый")
except ValueError:
    pass
else:
    raise AssertionError("неизвестный маршрут должен быть отклонён")

token = "a" * 12
assert pets_chat._action_id("start", token) == f"chat:start:{token}"
for bad in ("", "zz", "A" * 12, token + "\n1"):
    try:
        pets_chat._action_id("start", bad)
    except pets_v1.PetPolicyError:
        continue
    raise AssertionError(f"плохой токен принят: {bad!r}")

# ── Часовой пояс ─────────────────────────────────────────────────────────────


assert tz.parse_offset("+3") == 3 and tz.parse_offset("UTC-5") == -5
assert tz.parse_offset(" 3 ") == 3 and tz.parse_offset("utc+14") == 14
for bad in ("", "+3.5", "москва", "12ч"):
    try:
        tz.parse_offset(bad)
    except ValueError:
        continue
    raise AssertionError(f"плохой пояс принят: {bad!r}")

assert tz.label(0) == "UTC+0" and tz.label(-5) == "UTC-5" and tz.label(3) == "UTC+3"
assert "UTC+3" in tz.view_text(3)
assert len(tz.view_keyboard(-100, 0).inline_keyboard) == 1      # на UTC+0 кнопки сброса нет
kb = tz.view_keyboard(-100, 3)
assert len(kb.inline_keyboard) == 2
assert tz.TimezoneCB.unpack(kb.inline_keyboard[0][0].callback_data).delta == -1
assert tz.TimezoneCB.unpack(kb.inline_keyboard[1][0].callback_data).delta == 0

# ── Регистрация в каркасе: команды, справка, выключатели ─────────────────────


import bot.chat  # noqa: E402  реальный реестр команд
from bot.chat import help as chat_help  # noqa: E402
from bot.chat.framework import parse  # noqa: E402
from bot.chat.framework import registry as real  # noqa: E402
from services import feature_switches as fs  # noqa: E402

hub = real.get("питомцы")
assert hub is not None and hub.section == "pets"
assert {"мои питомцы", "питомец", "зоопарк", "питомник"} <= set(hub.aliases)
for name in ("поход", "экспедиция", "маршрут", "бестиарий", "ускорить поход"):
    assert real.get(name) is not None, name
assert real.get("ускорить") is real.get("ускорить поход")

parsed = parse(real, "бот поход, 6")
assert parsed.command.name == "поход" and parsed.args == "6"
parsed = parse(real, "бот маршрут, разведка")
assert parsed.command.name == "маршрут" and parsed.args == "разведка"

clock = real.get("часовой пояс")
assert clock is not None and clock.section == "settings" and not clock.private
assert real.get("timezone") is clock and real.get("пояс чата") is clock

assert "section:pets" in fs.command_features("поход", "pets", "")
assert "pets" in chat_help.SECTIONS
assert "бот поход" in chat_help.section_text("pets")
assert "бот часовой пояс" in chat_help.section_text("settings")
assert "🐾 Питомцы" in " ".join(b.text for row in chat_help.main_keyboard(1).inline_keyboard for b in row)

print("OK: чат-хаб питомцев и часовой пояс")
