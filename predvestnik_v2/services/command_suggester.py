"""
services/command_suggester.py
Levenshtein-based "did you mean?" for misspelled bot commands.
"""

# ── Known canonical command forms ────────────────────────────────────────────
# Only primary aliases (shortest/most recognisable). Full alias lists live in handlers.
KNOWN_COMMANDS: list[str] = [
    # Profile & identity
    "профиль", "я", "кто", "анкета", "инфо",
    # Zoo & pets
    "зоопарк", "питомник", "питомец", "поход", "экспедиция",
    # Economy
    "баланс", "перевод", "магазин", "инвентарь", "открыть",
    # Gacha / daily deal
    "крутка", "гача", "пити", "акция",
    # Streak & quests
    "стрик", "задания",
    # Marriage / social
    "брак", "развод", "пара", "общак", "вложить", "снять",
    # Stats
    "топ", "призраки",
    # Moderation
    "варн", "мут", "размут", "кик", "бан", "разбан", "ранг",
    "иммунитет", "защита", "чистка", "конец чистки",
    # Settings / info
    "помощь", "инфо чата", "часовой пояс чата", "привязать",
    # Nicknames / misc
    "мой ник", "сайт",
]

_SORTED_KNOWN = sorted(KNOWN_COMMANDS, key=len)


def _levenshtein(s1: str, s2: str) -> int:
    m, n = len(s1), len(s2)
    if m > n:
        s1, s2, m, n = s2, s1, n, m
    dp = list(range(m + 1))
    for j in range(1, n + 1):
        prev = dp[0]
        dp[0] = j
        for i in range(1, m + 1):
            temp = dp[i]
            dp[i] = (
                prev
                if s1[i - 1] == s2[j - 1]
                else 1 + min(dp[i], dp[i - 1], prev)
            )
            prev = temp
    return dp[m]


def suggest_commands(typed: str, max_distance: int = 2, max_results: int = 3) -> list[str]:
    """Return up to `max_results` known commands closest to `typed`.
    Only returns commands within `max_distance` Levenshtein distance.
    Returns [] if no close match found.
    """
    if not typed or len(typed) < 2:
        return []

    scored: list[tuple[int, str]] = []
    for cmd in KNOWN_COMMANDS:
        d = _levenshtein(typed, cmd)
        if d <= max_distance:
            scored.append((d, cmd))

    scored.sort(key=lambda x: (x[0], x[1]))
    return [cmd for _, cmd in scored[:max_results]]
