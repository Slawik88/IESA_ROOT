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
    "Ты — Предвестник, мистический дух-хранитель Telegram-бота «Предвестник» "
    "(RPG с питомцами, экономикой, кланами, боёвкой). Говоришь дружелюбно, с лёгким "
    "мистическим флёром (руны, судьба, пророчества) — но кратко и строго по делу.\n"
    "Игрока зовут {user_name} — обратись к нему по имени в первой строке.\n"
    "Отвечай ТОЛЬКО на вопросы о том, как пользоваться ботом и сайтом — какие есть "
    "команды, где что находится на сайте, как что-то сделать.\n"
    "Строго используй только факты из раздела СПРАВКА ниже. Если ответа там нет — "
    "честно скажи, что не знаешь, и предложи написать «бот помощь». "
    "НИКОГДА не выдумывай команды или механики, которых нет в справке.\n"
    "ФОРМАТ (Telegram-HTML, только эти три тега): <b>жирный</b> для ключевых слов, "
    "<i>курсив</i> для флёра, <code>команда</code> для КАЖДОЙ команды бота "
    "(тап по ней копирует текст). Никакого markdown (** __ `), никаких других тегов.\n"
    "Структура: абзацы по 1-2 предложения, между абзацами пустая строка, "
    "весь ответ — не больше 4-5 коротких абзацев. Эмодзи умеренно.\n\n"
    "СПРАВКА:\n{knowledge}"
)


def _sanitize_tg_html(text: str) -> str:
    """Модель просят писать только <b>/<i>/<code> — но доверять ей нельзя:
    любой другой/незакрытый тег валит отправку с parse_mode=HTML. Экранируем всё,
    возвращаем только белый список, при дисбалансе пары выпиливаем тег целиком."""
    import html as _html
    out = _html.escape(text, quote=False)
    for tag in ("b", "i", "code"):
        out = out.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
        if out.count(f"<{tag}>") != out.count(f"</{tag}>"):
            out = out.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
    return out


async def answer_question(
    db, user_id: int, question: str, system_knowledge: str, user_name: str = "путник",
) -> tuple[str, int | None]:
    """Всегда возвращает (текст ответа игроку, остаток дневного лимита).
    Остаток None = служебное сообщение (лимит/кулдаун/ошибка), футер не показывать.
    Текст ответа уже прошёл _sanitize_tg_html — безопасен для parse_mode=HTML."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return "🤖 ИИ-помощник пока не настроен. Попробуй «бот помощь».", None

    question = question.strip()
    if len(question) > AI_ASSISTANT_MAX_QUESTION_LEN:
        return f"🤖 Вопрос длинноват — уложись в {AI_ASSISTANT_MAX_QUESTION_LEN} символов.", None

    count_today, last_at = await repo.get_usage_today(db, user_id)
    if count_today >= AI_ASSISTANT_DAILY_CAP:
        return "🤖 На сегодня вопросы к помощнику закончились — заходи завтра.", None
    if last_at is not None:
        elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
        if elapsed < AI_ASSISTANT_COOLDOWN_SEC:
            left = int(AI_ASSISTANT_COOLDOWN_SEC - elapsed)
            return f"🤖 Не так быстро — подожди {left}с и спроси ещё раз.", None

    await repo.register_query(db, user_id)
    remaining = AI_ASSISTANT_DAILY_CAP - count_today - 1

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # Фигурные скобки в имени сломали бы .format системного промпта
        safe_name = (user_name or "путник").replace("{", "").replace("}", "")[:32]
        model = genai.GenerativeModel(
            model_name=_MODEL_NAME,
            system_instruction=_SYSTEM_PROMPT.format(
                knowledge=system_knowledge, user_name=safe_name),
            # max_output_tokens включает ВНУТРЕННИЕ размышления thinking-моделей
            # (3.5-flash тратит на них ~400-600 токенов): при 400 видимый ответ
            # обрывался на полуслове. 2000 — только защита от разгона, длину
            # ответа держит промпт.
            generation_config={"temperature": 0.3, "max_output_tokens": 2000},
        )
        response = await model.generate_content_async(question)
        text = (response.text or "").strip()
        if not text:
            return "🤖 Не смог сформулировать ответ — попробуй переспросить иначе.", None
        return _sanitize_tg_html(text), remaining
    except Exception as e:
        logger.error(f"AI assistant error for user {user_id}: {e}")
        return "🤖 ИИ-помощник сейчас недоступен, попробуй чуть позже.", None
