"""services/shadow_merchant.py — чистая логика ивента «Теневой Торговец» (БЛОК 13.X/24.A).

Только генерация слова/пророчества и тексты — без bot.* / FastAPI.* импортов.
Раздача/приём ответов: services/scheduler.py (спавн) + bot/handlers/dark_mora.py («бот слово»).
"""
import random

# Лорные слова-ключи. Только кириллица, без пробелов/дефисов — игрок отвечает
# одним словом: «бот слово, морок».
KEYWORDS: tuple = (
    "морок", "бездна", "сумрак", "пепел", "затмение",
    "пустота", "шёпот", "тлен", "мгла", "разлом",
    "омут", "клинок", "зарница", "прах", "полынь",
    "жатва", "клеймо", "оковы", "морена", "стужа",
    "навь", "тризна", "перун", "волхв",
)


def pick_keyword(rng: random.Random | None = None) -> str:
    return (rng or random).choice(KEYWORDS)


def mask_keyword(word: str, seed: str) -> str:
    """Маска-«пророчество»: первая буква открыта, ~половина остальных скрыта ▮.
    Детерминирована seed'ом (id ивента) — все видят одинаковую маску."""
    rng = random.Random(seed)
    chars = list(word.upper())
    hidden_idx = rng.sample(range(1, len(chars)), k=max(1, (len(chars) - 1) // 2 + 1))
    for i in hidden_idx:
        chars[i] = "▮"
    return " ".join(chars)


def prophecy_text(masked: str, minutes: int, winners: int) -> str:
    return (
        "🕴 <b>ТЕНЕВОЙ ТОРГОВЕЦ ЯВИЛСЯ</b>\n\n"
        "<i>Он не продаёт за золото. Он продаёт за понимание.\n"
        "Разгадайте слово из пророчества:</i>\n\n"
        f"    <code>{masked}</code>\n\n"
        f"Ответ: <code>бот слово, [догадка]</code>\n"
        f"⏳ Окно: <b>{minutes} минут</b>. Победители — первые <b>{winners}</b> угадавших.\n"
        "🏆 Приз: 🌑 Тёмная Мора + <b>право купить Теневую реликвию</b> "
        "(<code>бот теневые реликвии</code>)."
    )


def expired_text(word: str, n_winners: int) -> str:
    if n_winners:
        return (
            f"🕴 <i>Теневой Торговец растворился во мгле.</i>\n"
            f"Слово было: <b>{word.upper()}</b>. Победителей: {n_winners}."
        )
    return (
        f"🕴 <i>Теневой Торговец ушёл ни с чем — никто не разгадал пророчество.</i>\n"
        f"Слово было: <b>{word.upper()}</b>."
    )


def normalize_guess(raw: str) -> str:
    return (raw or "").strip().lower().replace("ё", "е")


def keywords_match(guess: str, keyword: str) -> bool:
    return normalize_guess(guess) == normalize_guess(keyword)
