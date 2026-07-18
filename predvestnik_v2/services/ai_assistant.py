"""
services/ai_assistant.py
ИИ-помощник по функциям бота/сайта (Gemini). Строго Q&A: никаких игровых действий,
без памяти между вопросами — каждый вопрос независим (осознанное решение: это
не чат, а справочник). Триггер: «бот, <вопрос>» — запятая сразу после «бот»
(bot/handlers/common.py::cmd_ai_question, фильтр AiQuestionCmd). Валидные команды
с той же запятой перехватываются командными роутерами раньше — сюда доходит
только нераспознанный текст.
"""
import os
from datetime import datetime, timezone

from loguru import logger

from core.constants import (
    AI_ASSISTANT_COOLDOWN_SEC,
    AI_ASSISTANT_DAILY_CAP,
    AI_ASSISTANT_MAX_QUESTION_LEN,
)
from infrastructure.repositories import ai_assistant as repo

# Алиас «текущая flash-модель»: конкретные версии Google закрывает для новых
# ключей (gemini-2.5-flash умер с 404 в первый же день) — алиас не протухает.
_MODEL_NAME = "gemini-flash-latest"

_SYSTEM_PROMPT = (
    "Ты — справочный помощник Telegram-бота «Предвестник» (RPG с питомцами, "
    "экономикой, кланами, боёвкой).\n"
    "Отвечай ТОЛЬКО на вопросы о том, как пользоваться ботом и сайтом — какие есть "
    "команды, где что находится на сайте, как что-то сделать.\n"
    "Строго используй только факты из раздела СПРАВКА ниже. Если ответа там нет — "
    "честно скажи, что не знаешь, и предложи написать «бот помощь». "
    "НИКОГДА не выдумывай команды или механики, которых нет в справке.\n"
    "Отвечай коротко (2-5 предложений), дружелюбно, на русском, можно с эмодзи. "
    "Не используй HTML- или markdown-разметку — только обычный текст.\n\n"
    "СПРАВКА:\n{knowledge}"
)


async def answer_question(db, user_id: int, question: str, system_knowledge: str) -> str:
    """Всегда возвращает готовый текст ответа игроку (сам ответ, отказ или объяснение лимита)."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return "🤖 ИИ-помощник пока не настроен. Попробуй «бот помощь»."

    question = question.strip()
    if len(question) > AI_ASSISTANT_MAX_QUESTION_LEN:
        return f"🤖 Вопрос длинноват — уложись в {AI_ASSISTANT_MAX_QUESTION_LEN} символов."

    count_today, last_at = await repo.get_usage_today(db, user_id)
    if count_today >= AI_ASSISTANT_DAILY_CAP:
        return "🤖 На сегодня вопросы к помощнику закончились — заходи завтра."
    if last_at is not None:
        elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
        if elapsed < AI_ASSISTANT_COOLDOWN_SEC:
            left = int(AI_ASSISTANT_COOLDOWN_SEC - elapsed)
            return f"🤖 Не так быстро — подожди {left}с и спроси ещё раз."

    await repo.register_query(db, user_id)

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=_MODEL_NAME,
            system_instruction=_SYSTEM_PROMPT.format(knowledge=system_knowledge),
            generation_config={"temperature": 0.3, "max_output_tokens": 400},
        )
        response = await model.generate_content_async(question)
        text = (response.text or "").strip()
        return text or "🤖 Не смог сформулировать ответ — попробуй переспросить иначе."
    except Exception as e:
        logger.error(f"AI assistant error for user {user_id}: {e}")
        return "🤖 ИИ-помощник сейчас недоступен, попробуй чуть позже."
