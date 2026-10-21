"""Настоящие тексты бота для роликов: вызывает функции оформления из кода бота с демо-данными.

    cd predvestnik_v2 && BOT_TOKEN=0:promo DATABASE_URL=postgresql://none@127.0.0.1:1/none \
        python3 tools/promo_video/capture/real_texts.py

Пишет tools/promo_video/assets/texts.json: {имя: {"html": ..., "buttons": [[...]]}}. В сценарии сообщение
ссылается на текст так: {"from": "bot", "real": "top_chat"}. База и Telegram не нужны: функции только
форматируют. Имена и ники вымышленные.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from bot.chat import mafia_card_views, mafia_views, onboarding, profile_view, purge, site, top  # noqa: E402
from bot.chat.style import profile_link, quote, reason_quote  # noqa: E402
from core.skins_v3_chat import chat_look, glyph_of  # noqa: E402
from services import chat_setup as cs  # noqa: E402
from services.skin_chat_news import _one as skin_news  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "texts.json")
T: dict[str, dict] = {}


def put(name: str, html: str, buttons: list[list[str]] | None = None) -> None:
    T[name] = {"html": html, **({"buttons": buttons} if buttons else {})}


def kb_labels(markup) -> list[list[str]]:
    return [[b.text for b in row] for row in markup.inline_keyboard]


# ── Топ: игроки чата и топ чатов (bot/chat/top.py) ─────────────────────────────
players = [(1, profile_link(1, "liza", mark=glyph_of("starheart")), 1204), (2, profile_link(2, "tema_frog"), 1198),
           (3, profile_link(3, "kira_bloom", mark=glyph_of("sakura_storm")), 640), (4, profile_link(4, "mark_off"), 587),
           (5, profile_link(5, "sonya_cat"), 412)]
put("top_chat", top.render("Топ чата", players, 0, 3, "d", "c"), kb_labels(top.keyboard(1, "c", "d", 0, 3, -1)))
chats = [(1, "Флудилка 🌚", 7218), (2, "10Б 🔥 флуд", 5072), (3, "аниме и чай 🍵", 3230), (4, "ФЛУД 18:00 ☕", 2955),
         (5, "клуб полуночников 🌙", 1224)]
put("top_chats", top.render("Топ чатов", chats, 0, 12, "w", "k"), kb_labels(top.keyboard(1, "k", "w", 0, 12, -1)))
chats_up = [(1, "ФЛУД 18:00 ☕", 7390), (2, "Флудилка 🌚", 7218), (3, "10Б 🔥 флуд", 5072), (4, "аниме и чай 🍵", 3230),
            (5, "клуб полуночников 🌙", 1224)]
put("top_chats_first", top.render("Топ чатов", chats_up, 0, 12, "w", "k"), kb_labels(top.keyboard(1, "k", "w", 0, 12, -1)))

# ── Чистка (bot/chat/purge.py) ─────────────────────────────────────────────────
put("purge_start",
    "🧹 <b>Чистка началась</b>\n"
    + quote(["Период: 14.10.2026 – 20.10.2026 · норма 50", "Не набрали норму: <b>34</b>", "Боты не считаются: 2"])
    + "\n🔒 Чат закрыт до конца чистки.", [["Продолжить на сайте"]])
for i, (user, count, req, total, days, warns, note) in enumerate([
        ("ghost_228", 3, 50, 41, 214, 1, ""),
        ("nastya_new", 12, 21, 12, 3, 0, "в чате 3 дня — норма снижена"),
        ("sleepy_bear", 7, 50, 980, 400, 2, "")]):
    v = purge.Violator(user_id=500 + i, username=user, count=count, required=req, total=total, days_in_chat=days, warns=warns, note=note)
    put(f"dossier_{i}", purge.dossier_text(v, "ФЛУД 18:00 ☕"), kb_labels(purge.dossier_kb(1, 500 + i)))

# решение по досье: бот дописывает итог в то же сообщение (purge.on_verdict)
put("dossier_0_kick", T["dossier_0"]["html"] + "\n\n<b>👢 Кик</b> · Кира")

# ── «бот сайт» (bot/chat/site.py) ─────────────────────────────────────────────
put("site", site.SITE_TEXT, [["🔮 Открыть Предвестник"]])

# ── Брак (bot/chat/family.py): предложение и ответ «Да» правкой того же сообщения ──
put("proposal", "💍 <b>Марк</b> делает предложение <b>Лизе</b>!\n"
                "Ответить может только тот, кому предложили. Предложение действует сутки.",
    [["💍 Да", "💔 Нет"], ["✖️ Отозвать"]])
put("married", "💒 <b>Марк</b> и <b>Лиза</b> теперь семья! Брак действует во всех чатах.\n"
               "Карточка семьи: <code>бот семья</code>")

# ── Модерация (bot/chat/moderation.py): те же строки, что в ответах команд ─────
put("mute", "🔇 <b>@krypta_tut</b> не может писать на 2 ч." + reason_quote("спам"))
put("ban", "⛔ <b>@krypta_tut</b> забанен навсегда." + reason_quote("спам ссылками"))
put("warn", "⚠️ <b>@egor_zz</b> получает варн (3/3), на 7 д." + reason_quote("капс"))
put("warn_limit_kick", "🚨 <b>Лимит варнов превышен</b>\n@egor_zz — 3/3 в «ФЛУД 18:00 ☕».\nЧто сделать?\n\n<b>👢 Кикнут (Кира)</b>")
put("warn_limit", "🚨 <b>Лимит варнов превышен</b>\n@egor_zz — 3/3 в «ФЛУД 18:00 ☕».\nЧто сделать?",
    [["🕊 Простить", "🔇 Мут"], ["👢 Кик", "⛔ Бан"]])
put("close_chat", "🔒 Чат закрыт. Писать могут только те, кому это разрешено рангом.")
put("report", "📨 Жалоба на <b>@krypta_tut</b> принята · №128\n"
              "<i>Она анонимна: автора видит только персонал с доступом. Результат придёт сюда.</i>")

# ── Подключение к чату (bot/chat/onboarding.py) ────────────────────────────────
fresh = cs.Setup(chat_id=-1004, title="ФЛУД 18:00 ☕", present=True, admin=False, can_delete=False, can_restrict=False)
text, kb = onboarding.group_screen(fresh, "IIIPredvestnikIIIBot")
put("onboard_need", text, kb_labels(kb))
ready = cs.Setup(chat_id=-1004, title="ФЛУД 18:00 ☕", present=True, admin=True, can_delete=True, can_restrict=True, verified=True)
text, kb = onboarding.group_screen(ready, "IIIPredvestnikIIIBot")
put("onboard_ready", text, kb_labels(kb))
props = [cs.Proposal(user_id=10 + i, username=u, name=u, rank=r, current=0) for i, (u, r) in
         enumerate([("kira_bloom", 6), ("mark_off", 4), ("tema_frog", 3)])]
legend = onboarding.rank_legend({"warn": 2, "mute": 3, "kick": 4, "ban": 5, "close_chat": 4}, [p.rank for p in props])
text, kb = onboarding.staff_screen(ready, props, legend=legend)
put("staff", text, kb_labels(kb))

# ── Профиль, стрик, новости скинов в стиле скина ──────────────────────────────
look = chat_look("starheart", "SSS")
card = profile_view.CardData(title="Лиза", username="liza",
                             head=["✨ Активист", "👑 VIP"],
                             messages=[("сегодня", "214"), ("неделя", "1 204"), ("месяц", "4 395")],
                             totals=[("всего", "12 000")],
                             progress=[("серия", "41 день"), ("рекорд", "41 день"), ("место", "#1"), ("достижения", "38/869")],
                             personal=["💞 В браке с Марком"],
                             wallet=["мора <b>48 210</b> 🪙", "алмазы <b>120</b> 💎"])
put("profile_sss", profile_view.styled(card, look))
put("profile_plain", profile_view.plain(card))
put("streak_sss", profile_view.streak(look, "Ваш", 41, 41, "✅ Сегодня засчитан"))
put("skin_news_sss", skin_news(1, "liza", {"skin_id": "starheart", "kind": "sss"}), [["🎨 Образы"]])
put("skin_news_buy", skin_news(2, "mark_off", {"skin_id": "scarlet_star", "kind": "buy"}), [["🎨 Образы"]])

# ── Мафия (bot/chat/mafia_views.py, mafia_card_views.py) ──────────────────────
names = ["Кира", "Марк", "Лиза", "Тёма", "Соня", "Даня", "Вика", "Егор"]
plist = [{"user_id": i + 1, "display_name": n, "alive": n != "Марк"} for i, n in enumerate(names)]
view = {"match_id": 1, "players": plist, "initiator_id": 1, "host_name": "Кира", "max_players": 12, "vote_mode": "hidden",
        "roles_auto": True, "enabled_roles": [], "tempo": "normal"}
put("mafia_lobby", mafia_views.lobby_text(view), kb_labels(mafia_views.lobby_keyboard(view, "IIIPredvestnikIIIBot")))
from datetime import datetime, timedelta  # noqa: E402
now = datetime(2026, 10, 21, 21, 0)
players = [{**p, "join_order": i + 1, "alive": True} for i, p in enumerate(plist)]
night = {**view, "players": players, "phase": "night", "round_number": 1, "phase_deadline": now + timedelta(seconds=58), "server_time": now}
put("mafia_night", mafia_card_views.phase_text(night))
dead = [{**p, "alive": p["display_name"] != "Марк"} for p in players]
day = {**night, "players": dead, "phase": "discussion", "phase_deadline": now + timedelta(seconds=179)}
put("mafia_dawn_day", mafia_card_views.dawn_text(day, {"display_name": "Марк"}))
try:
    put("mafia_dawn", mafia_card_views.dawn_text({**view, "phase": "night"}, {"display_name": "Марк"}))
except Exception as exc:   # формат утра зависит от полей партии; без них — только заголовок
    print("mafia_dawn:", exc)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(T, f, ensure_ascii=False, indent=1)
print(f"{len(T)} текстов → {os.path.relpath(OUT, ROOT)}")
