#!/usr/bin/env python3
"""Dependency-free contract checks for approved Mafia v1 rules."""
from core import mafia_v1 as rules


assert rules.mafia_slots(4) == 1
assert rules.mafia_slots(8) == 2
assert len(rules.role_deck(player_count=4, enabled_roles=())) == 4
deck = rules.role_deck(player_count=8, enabled_roles=("don", "doctor", "detective"))
assert deck.count("mafia") == 1 and deck.count("don") == 1
assert deck.count("doctor") == deck.count("detective") == 1
assert rules.resolve_vote([1, 1, 2]) == 1
assert rules.resolve_vote([1, 2]) is None
assert rules.winner(["citizen", "mafia"]) == "mafia"
assert rules.winner(["citizen", "doctor"]) == "town"
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

print("mafia_v1_rules: decks, winner, ties and invalid settings OK")
