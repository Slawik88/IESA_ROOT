#!/usr/bin/env python3
"""Dependency-free contract checks for Mafia v1 rules, command parsing and player-facing copy."""
from core import mafia_command, mafia_copy as copy
from core import mafia_v1 as rules


# ── decks, winner, votes ────────────────────────────────────────────────────
assert rules.mafia_slots(4) == 1 and rules.mafia_slots(8) == 2
assert len(rules.role_deck(player_count=4, enabled_roles=())) == 4
deck = rules.role_deck(player_count=8, enabled_roles=("don", "doctor", "detective"))
assert deck.count("mafia") == 1 and deck.count("don") == 1 and deck.count("doctor") == deck.count("detective") == 1
assert rules.resolve_vote([1, 1, 2]) == 1 and rules.resolve_vote([1, 2]) is None and rules.resolve_vote([None, None]) is None
assert rules.winner(["citizen", "mafia"]) == "mafia" and rules.winner(["citizen", "doctor"]) == "town"
assert rules.winner(["citizen", "mafia", "doctor"]) is None

for kwargs in (
    {"max_players": 3, "enabled_roles": (), "vote_mode": "secret"},
    {"max_players": 4, "enabled_roles": ("don",), "vote_mode": "secret"},
    {"max_players": 8, "enabled_roles": ("alien",), "vote_mode": "secret"},
):
    try:
        rules.validate_settings(**kwargs)
    except rules.MafiaRuleError:
        pass
    else:
        raise AssertionError("invalid Mafia settings must fail closed")

# ── «авто» roles always make a legal deck, for every table size ─────────────
for players in range(rules.MIN_PLAYERS, rules.MAX_PLAYERS + 1):
    roles = rules.auto_roles(players)
    assert len(rules.role_deck(player_count=players, enabled_roles=roles)) == players, players
assert rules.auto_roles(5) == () and "don" not in rules.auto_roles(7) and "don" in rules.auto_roles(8)
assert rules.DEFAULT_SEATS >= 8, "a fresh lobby must hold a typical table of friends"

# ── day vote: «Никого» counts, one vote cannot beat the abstainers ───────────
day = rules.resolve_day_vote
assert day([1, 1, 2]) == 1 and day([1, None]) is None and day([None, None, 3]) is None
assert day([3, None, None, None, None, None]) is None, "five abstentions beat one accusation"
assert day([3, 3, None]) == 3 and day([3, 3, None, None]) is None and day([]) is None

# ── night kill: plurality, then the Don, then the earliest choice ───────────
vote = rules.NightVote
assert rules.resolve_night_kill([]) is None and rules.resolve_night_kill([vote("mafia", None, 1)]) is None
assert rules.resolve_night_kill([vote("mafia", 5, 1)]) == 5
assert rules.resolve_night_kill([vote("mafia", 5, 1), vote("mafia", 5, 2), vote("don", 6, 3)]) == 5, "majority beats the Don"
assert rules.resolve_night_kill([vote("mafia", 5, 1), vote("don", 6, 2)]) == 6, "a tie goes to the Don"
assert rules.resolve_night_kill([vote("mafia", 5, 2), vote("mafia", 6, 1)]) == 6, "without a Don the earlier choice wins"
assert rules.resolve_night_kill([vote("mafia", 5, 1), vote("mafia", 6, 2), vote("don", 7, 3)]) == 7, "a three-way tie includes the Don's pick"
assert rules.resolve_night_kill([vote("mafia", 5, 1), vote("mafia", 5, 2), vote("mafia", 6, 3), vote("mafia", 6, 4), vote("don", 7, 5)]) == 5, \
    "a Don outside the tie does not decide; the earliest tied choice does"

# ── a phase ends early only when everybody it waits for has moved ───────────
cast = [(1, "citizen", True), (2, "mafia", True), (3, "doctor", True), (4, "detective", False)]
assert not rules.is_phase_complete("night", cast, [(2, "mafia_target")])
assert rules.is_phase_complete("night", cast, [(2, "mafia_target"), (3, "doctor_save")]), "a dead detective is not awaited"
assert not rules.is_phase_complete("night", [(1, "citizen", True)], []), "no actors: nothing to wait for, never 'complete'"
assert rules.is_phase_complete("voting", cast, [(1, "vote"), (2, "vote"), (3, "vote")])
assert not rules.is_phase_complete("voting", cast, [(1, "vote")]) and not rules.is_phase_complete("discussion", cast, [])
assert rules.round_number(1) == rules.round_number(3) == 1 and rules.round_number(4) == 2
assert rules.phase_seconds("normal", "night") == rules.NIGHT_SECONDS and rules.phase_seconds("fast", "voting") < rules.VOTING_SECONDS

# ── commands: natural spellings, never a stray word ─────────────────────────
parse = mafia_command.parse
for text in ("бот мафия", "Бот Мафия!", "бот, мафия", "/mafia", "/mafia@some_bot", "бот мафия, 8 доктор", "бот мафия 8 доктор"):
    assert parse(text).kind == "create", text
for text, kind in (("бот мафия стоп", "stop"), ("бот мафия, стоп", "stop"), ("бот мафия отмена", "stop"), ("/mafia stop", "stop"),
                   ("бот мафия правила", "rules"), ("бот мафия как играть", "rules"), ("бот мафия статус", "status"),
                   ("бот мафия продолжить", "resume"), ("бот мафия готов", "ready")):
    assert parse(text).kind == kind, text
for text in ("мафия", "бот мафиози", "ботмафия", "привет бот мафия", "бот баланс", "", None):
    assert parse(text) is None, text
assert parse("бот мафия 8 доктор открытое быстро").args == "8 доктор открытое быстро"
assert {"stop", "resume", "rules", "status"} == set(mafia_command.GATE_BYPASS_KINDS)

# ── copy: plain words, popups fit Telegram's 200 characters ─────────────────
for role in rules.ALL_ROLES:
    assert len(copy.role_alert(role, ["Очень Длинное Имя Игрока"] * 5)) <= copy.ALERT_LIMIT, role
    card = copy.role_card(role, [("Имя", "mafia")])
    assert "Цель" in card and "Что делать" in card and copy.ROLE_NAME[role] in card, role
assert "<script>" not in copy.role_card("mafia", [("<script>", "mafia")]), "names must be escaped"
assert len(copy.rules_alert()) <= copy.ALERT_LIMIT
for key, _title in copy.RULES_TITLES:
    assert 100 < len(copy.rules_page(key)) < 1500, key
banned = ("фракци", "тай-брейк", "state_version", "callback", "phase")
assert not [w for page in copy._RULES.values() for w in banned if w in page.lower()], "jargon in the rules"

print("mafia_v1_rules: decks, auto roles, night tie-break, early close, commands and copy OK")
