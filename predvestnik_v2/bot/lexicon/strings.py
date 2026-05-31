# bot/lexicon/strings.py

LEXICON = {
    "wolf_shield_active": "🐺 <b>Снежный Волк</b> выскочил вперёд и защитил {name} (ID: {id}) от варна!",
}


def get_str(key: str, **kwargs) -> str:
    text = LEXICON.get(key, f"⚠️ Ошибка: ключ '{key}' не найден в LEXICON")
    try:
        return text.format(**kwargs)
    except KeyError as e:
        return f"⚠️ Ошибка форматирования строки '{key}': не хватает аргумента {e}"
