"""Owner-designated official community destination and editorial constraints."""
CHAT_ID = -1003939897421
THREAD_ID = 4
BOT_USERNAME = "IIIPredvestnikIIIBot"
GROUP_URL = "https://t.me/predvestnik_official"
UPDATES_URL = GROUP_URL + "/4"
MAX_CAPTION = 900
COOLDOWN_HOURS = 24
DESTINATIONS = {"pets": ("Открыть питомцев", "pets", "pets_v2"),
                "rhythm": ("Открыть игры", "game", "game_rhythm_v2"),
                "mafia": ("История Мафии", "game", "game_mafia_v1"),
                "family": ("Моя родословная", "family", None),
                "purge": ("Чистка чатов", "purge", None)}


def action(kind: str) -> tuple[str, str]:
    label, section, _ = DESTINATIONS[kind]
    return label, f"https://t.me/{BOT_USERNAME}?startapp={section}"
