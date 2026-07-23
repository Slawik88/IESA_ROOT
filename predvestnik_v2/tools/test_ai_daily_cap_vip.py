"""Block 8: дневной лимит вопросов к ИИ-помощнику зависит от VIP.
Без VIP — базовый (5), VIP-1М — 7, VIP-2М и любой более длинный пак — 10.

Тест бьёт по логике выбора лимита в answer_question через мок get_vip_info и
repo.get_usage_today: разные тиры дают разный порог отказа и разный остаток.
GEMINI_API_KEY специально НЕ задаём? — нет, наоборот: чтобы дойти до проверки
лимита, ключ должен быть; но реальный Gemini не вызываем — упираемся в лимит
ДО сети (count_today >= cap возвращает раньше любого HTTP)."""
import sys
import pathlib
import asyncio

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import os
os.environ["GEMINI_API_KEY"] = "test-key-not-used"  # чтобы пройти ранний гейт ключа

from services import ai_assistant
from core.constants import AI_ASSISTANT_DAILY_CAP, AI_ASSISTANT_DAILY_CAP_BY_VIP


async def run_case(tier, count_today):
    """Возвращает (текст, remaining) при данном VIP-тире и уже потраченных вопросах."""
    async def fake_vip(db, uid):
        return {"tier": tier} if tier else None

    async def fake_usage(db, uid):
        return count_today, None  # last_at=None → кулдаун не мешает

    async def fake_register(db, uid):
        return None

    ai_assistant.get_vip_info = None  # не используется напрямую (импорт внутри), см. ниже
    # Патчим точки, которые реально вызываются внутри answer_question:
    import services.vip as vip_mod
    vip_mod.get_vip_info = fake_vip
    ai_assistant.repo.get_usage_today = fake_usage
    ai_assistant.repo.register_query = fake_register
    # _converse не должен вызываться, если лимит исчерпан; если НЕ исчерпан —
    # подменяем на короткий ответ, чтобы не ходить в сеть.
    async def fake_converse(*a, **k):
        return "ответ"
    ai_assistant._converse = fake_converse

    text, remaining, _ = await ai_assistant.answer_question(
        db=None, user_id=1, chat_id=-100, question="как отправить питомца в поход",
        system_knowledge="", user_name="тест")
    return text, remaining


async def main():
    base = AI_ASSISTANT_DAILY_CAP
    assert base == 5, f"ожидали базовый лимит 5, в конфиге {base}"
    assert AI_ASSISTANT_DAILY_CAP_BY_VIP["1m"] == 7
    assert AI_ASSISTANT_DAILY_CAP_BY_VIP["2m"] == 10

    # На пороге-1 запрос ещё проходит, remaining = cap - count - 1
    for tier, cap in [(None, 5), ("1m", 7), ("2m", 10), ("12m", 10)]:
        text, remaining = await run_case(tier, cap - 1)
        assert remaining == 0, f"{tier}: на последнем вопросе remaining ожидали 0, получили {remaining}"
        assert "закончились" not in text, f"{tier}: последний вопрос не должен отбиваться ({text!r})"

    # На пороге запрос отбивается сообщением про лимит
    for tier, cap in [(None, 5), ("1m", 7), ("2m", 10)]:
        text, remaining = await run_case(tier, cap)
        assert remaining is None and "закончились" in text, \
            f"{tier}: на лимите {cap} ожидали отказ, получили {text!r}"
        assert f"{cap}/день" in text, f"{tier}: в тексте нет актуального лимита {cap}/день: {text!r}"

    # Базовый и VIP-1М видят подсказку про VIP, максимум (10) — нет
    text_base, _ = await run_case(None, 5)
    assert "С VIP лимит больше" in text_base, "без VIP должна быть подсказка про VIP"
    text_max, _ = await run_case("2m", 10)
    assert "С VIP лимит больше" not in text_max, "на максимуме подсказки про VIP быть не должно"

    print("OK: лимит ИИ 5(база)/7(VIP-1М)/10(VIP-2М+) — порог и остаток считаются по тиру, "
          "подсказка про VIP только у не-максимальных")


asyncio.run(main())
