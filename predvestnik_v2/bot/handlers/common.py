import os
import random

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd, WrongSyntaxCmd, UnknownBotCmd

_WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://127.0.0.1:8000")

router = Router(name="common_router")

# Определяем структуру данных для кнопок
class HelpCallback(CallbackData, prefix="help"):
    tab: str

# Словарь с текстами для каждой вкладки
HELP_PAGES = {
    "main": (
        "📖 <b>ПРЕДВЕСТНИК — ПОМОЩЬ</b>\n\n"
        "<b>Как пользоваться:</b>\n"
        "бот [команда]\n"
        "бот [команда], [аргумент]\n"
        "Ответ на сообщение = указать юзера\n\n"
        "Выбери раздел ниже 👇"
    ),
    "admin": (
        "🛡 <b>МОДЕРАЦИЯ</b>\n\n"
        "⚠️ <b>Предупреждения</b>\n"
        "· бот варн, @юзер [причина]\n"
        "· бот снять варн, @юзер\n\n"
        "🔇 <b>Мут</b>\n"
        "· бот мут, @юзер 10м/2ч/1д\n"
        "· бот размут, @юзер\n\n"
        "⛔ <b>Бан / Кик</b>\n"
        "· бот бан, @юзер [причина]\n"
        "· бот разбан, @юзер\n"
        "· бот кик, @юзер\n\n"
        "🛡 <b>Защита</b>\n"
        "· бот иммунитет, @юзер — навсегда\n"
        "· бот защита, @юзер 5д/1ч\n"
        "· бот снять защиту, @юзер\n\n"
        "👑 <b>Ранги</b>\n"
        "· бот ранг, @юзер [0-6]\n"
        "· бот ранг глобал, @юзер [0-3]\n\n"
        "⚙️ <b>Настройки</b>\n"
        "· бот настройки чата — меню\n"
        "· бот настройка щита, [дни]\n"
        "· бот лимит варнов, [N]\n\n"
        "🧹 <b>Чистка</b>\n"
        "· бот чистка — начать\n"
        "· бот конец чистки\n\n"
        "📋 бот баны · бот кики · бот ушли"
    ),
    "economy": (
        "💰 <b>ЭКОНОМИКА</b>\n\n"
        "💳 <b>Кошелёк</b>\n"
        "· бот баланс — мой баланс\n"
        "· бот перевод, @юзер [сумма]\n"
        "· бот история кошелька\n\n"
        "🛒 <b>Магазин</b>\n"
        "· бот магазин — покупки\n"
        "· бот инвентарь — мои предметы\n"
        "· бот открыть, [яйцо] [N]\n"
        "· бот акция — акция дня\n\n"
        "🎰 <b>Гача и игры</b>\n"
        "· бот крутка — гача-крутки\n"
        "· бот пити — счётчики пити\n"
        "· бот игры — мини-игры\n"
        "· бот обмен — Мора → Алмазы\n\n"
        "🎫 <b>Промокоды</b>\n"
        "· бот промокод, КОД — активировать\n\n"
        "🏛 <b>Аукцион</b>\n"
        "· бот аукцион — торги\n"
        "· бот аукцион выставить\n"
        "· бот аукцион мои ставки"
    ),
    "social": (
        "🐾 <b>ПИТОМЦЫ И ОТНОШЕНИЯ</b>\n\n"
        "💍 <b>Брак</b>\n"
        "· бот брак, @юзер — предложение\n"
        "· бот развод — расстаться\n"
        "· бот пара — мой партнёр\n"
        "· бот общак — семейный банк\n"
        "· бот вложить / снять, [сумма]\n\n"
        "🐾 <b>Питомцы</b>\n"
        "· бот зоопарк — питомник\n"
        "· бот питомец — активный питомец\n"
        "· бот поход, 2/4/6/8 — поход\n\n"
        "🤝 <b>Социальное</b>\n"
        "· бот обнять @юзер\n"
        "· бот ударить @юзер\n"
        "  (+ другие варп-команды)\n"
        "· бот задания — дейлики\n"
        "· бот достижения — ачивки\n\n"
        "⚔️ <b>Дуэли</b>\n"
        "· бот дуэль, @юзер, [ставка]"
    ),
    "stats": (
        "📊 <b>ПРОФИЛЬ И ТОПЫ</b>\n\n"
        "👤 <b>Профиль</b>\n"
        "· бот профиль — полный профиль\n"
        "· бот я — краткая карточка\n"
        "· бот кто, @юзер — чужая карточка\n"
        "· бот анкета — моя карточка с тегами\n"
        "· бот инфо, @юзер — досье\n\n"
        "🏷 <b>Никнейм в чате</b>\n"
        "· бот мой ник, [псевдоним] — задать\n"
        "· бот мой ник — посмотреть\n\n"
        "🔥 <b>Стрик</b>\n"
        "· бот стрик — мой стрик\n"
        "· бот стрик восстановить\n\n"
        "🏆 <b>Топы</b>\n"
        "· бот топ — за всё время\n"
        "· бот топ день / неделя / всё время\n"
        "· бот топ мора / алмазы / стрик\n"
        "· бот призраки — неактивные\n\n"
        "ℹ️ <b>Чат</b>\n"
        "· бот инфо чата\n"
        "· бот настройки чата\n"
        "· бот сайт — веб-панель"
    ),
    "developer": (
        "👨‍💻 <b>DEVELOPER</b>\n\n"
        "📊 <b>Статистика</b>\n"
        "· бот dev стат\n"
        "· бот dev юзер, @ник\n\n"
        "💰 <b>Баланс</b>\n"
        "· бот dev баланс, @ник, [🪙], [💎]\n\n"
        "🔄 <b>Сбросы</b>\n"
        "· бот dev сбросить стрик, @ник\n"
        "· бот dev гача сброс, @ник\n\n"
        "⚡ <b>Ивенты</b>\n"
        "· бот dev ивент сундук\n"
        "· бот dev ивент обмен\n"
        "· бот dev акция\n\n"
        "· бот dev предметы — реестр\n\n"
        "🎫 <b>Промокоды</b>\n"
        "· бот dev промокод — панель управления\n"
        "· бот dev промокод список\n\n"
        "<i>Только для Главного разработчика.</i>"
    ),
}

def get_help_keyboard(active_tab: str = "main", is_dev: bool = False) -> types.InlineKeyboardMarkup:
    """Генерирует клавиатуру с вкладками; помечает активную."""
    def label(text: str, tab: str) -> str:
        return f"· {text} ·" if tab == active_tab else text

    builder = InlineKeyboardBuilder()
    builder.button(text=label("🏠 Главная", "main"), callback_data=HelpCallback(tab="main"))
    builder.button(text=label("🛡 Админ", "admin"), callback_data=HelpCallback(tab="admin"))
    builder.button(text=label("💰 Экономика", "economy"), callback_data=HelpCallback(tab="economy"))
    builder.button(text=label("🐾 Питомцы", "social"), callback_data=HelpCallback(tab="social"))
    builder.button(text=label("📊 Топы", "stats"), callback_data=HelpCallback(tab="stats"))
    if is_dev:
        builder.button(text=label("👨‍💻 Developer", "developer"), callback_data=HelpCallback(tab="developer"))
        builder.adjust(1, 2, 2, 1)
    else:
        builder.adjust(1, 2, 2)
    return builder.as_markup()


_BOT_ALONE_RESPONSES = [
    "👁 Я здесь. Всегда.",
    "🤨 Чего хотел? Бот не читает мысли. Хотя... пока не читает.",
    "👂 Слушаю. Молча. Уже третью минуту.",
    "📖 Напиши <code>бот помощь</code> — там всё. Серьёзно, всё.",
    "🐕 Да-да, я тут. Жду команды как верный пёс. Но умнее.",
    "👋 О, кто-то позвал бота. Бот пришёл. Бот ждёт.",
    "🤷 Ты позвал меня без причины? Это нормально. Я не осуждаю.",
    "😐 Привет. Это всё? Потому что у меня дела.",
    "🤖 БЕЕЕЕП. Это значит: напиши что-нибудь ещё.",
    "🌌 Я существую. Ты позвал меня. Я откликнулся. Что дальше?",
    "✋ Вот я. Рад? Теперь напиши команду, пожалуйста.",
    "😌 Некоторые зовут бота просто так. Бот не против. Бот уже привык.",
    "⚖️ Одно слово. Целый бот в ответ. Разумный обмен, да?",
    "🧞 Я как джинн — появляюсь когда зовут. Только без желаний.",
    "❓ Бот вызван. Бот в замешательстве. Бот ждёт.",
    "🔁 Ты написал 'бот'. Я написал это. Мы в тупике.",
    "🔮 Предвестник чувствует твоё присутствие. И некоторое замешательство.",
    "😊 Не знаю зачем ты это написал, но мне понравилось.",
    "💔 Каждый раз когда кто-то пишет просто 'бот' — бот теряет 1 HP. У меня осталось немного.",
    "🧐 Ты случайно написал 'бот'? Или это тест? Мне засчитывать?",
    "🛡 Бот активирован. Угроза не обнаружена. Жду дальнейших указаний.",
    "📞 Это как позвонить другу и молчать в трубку. Я твой друг. Молчать не буду.",
    "😅 Ладно, я тут. Только не говори что я первый откликнулся.",
    "🎯 Написать просто 'бот' — это уже почти команда. Почти.",
    "📊 Знаешь сколько таких как ты каждый день? Много. Мне не одиноко.",
    "⏳ Ты явно что-то хотел сказать. Я подожду.",
    "☕ Бот зафиксирован в чате. Хронология нарушена. Кофе кончился.",
    "🔎 Если ты написал это случайно — ничего страшного. Если специально — мне любопытно зачем.",
    "📡 Сигнал получен. Содержание: отсутствует. Перезапрашиваю вселенную...",
    "🌸 Привет себе. Привет тебе. Бот здесь. Все здесь. Хорошо.",
    "🐱 Я откликаюсь на 'бот' как кот на шуршание пакета. Рефлекс.",
    "👆 Вот. Именно это и происходит когда пишешь просто 'бот'.",
    "🧠 Бот не читает мысли. Напиши <code>бот помощь</code> и узнай что умею.",
    "🏡 Я тут. Ты тут. Чат тут. Это уже неплохо.",
    "🎙 Ок, слушаю. ...Всё ещё слушаю. ...Ладно, пиши сам.",
    "♟ Меня позвали — я пришёл. Теперь твой ход.",
    "🛗 Это как нажать кнопку вызова лифта без этажа. Я лифт. Куда едем?",
    "🧘 Бот готов. Команда не получена. Бот философски принимает реальность.",
    "✅ Если ты это читаешь — значит я работаю. Это уже хорошая новость.",
    "🕵️ Ты позвал меня. Я пришёл. Детектив уже строит теории.",
    "🌠 Три буквы. Целая вселенная вопросов.",
    "💭 Что-то подсказывает мне что ты хотел написать что-то после 'бот'. Угадал?",
    "🤔 Бот думает... Бот не понял... Бот всё равно тут.",
    "🔄 А знаешь что бывает когда пишешь просто 'бот'? Вот это и бывает.",
    "🥲 Ты — единственный кто написал мне сегодня. Это грустно и мило одновременно.",
    "😵 Бот явился. Бот немного растерян. Бот справится.",
    "💡 Можешь написать 'бот помощь' и узнать на что я способен. Или и дальше так.",
    "📬 Зов получен. Статус: прибыл. Миссия: неизвестна. Настроение: хорошее.",
]


@router.message(F.text.lower().strip() == "бот")
async def cmd_bot_alone(message: types.Message):
    if message.chat.type == "private":
        return
    await message.answer(random.choice(_BOT_ALONE_RESPONSES), parse_mode="HTML")


@router.message(TextCmd(["помощь", "меню", "команды", "хелп"]))
async def cmd_help(message: types.Message, developer_id: int = 0):
    is_dev = bool(developer_id and message.from_user.id == developer_id)
    await message.answer(
        text=HELP_PAGES["main"],
        reply_markup=get_help_keyboard("main", is_dev=is_dev),
        parse_mode="HTML",
    )


@router.callback_query(HelpCallback.filter())
async def handle_help_tabs(query: types.CallbackQuery, callback_data: HelpCallback, developer_id: int = 0):
    tab = callback_data.tab
    if tab not in HELP_PAGES:
        return await query.answer("Ошибка: страница не найдена.")
    if tab == "developer" and not (developer_id and query.from_user.id == developer_id):
        return await query.answer("🔒 Только для разработчика.", show_alert=True)

    is_dev = bool(developer_id and query.from_user.id == developer_id)
    try:
        await query.message.edit_text(
            text=HELP_PAGES[tab],
            reply_markup=get_help_keyboard(tab, is_dev=is_dev),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await query.answer()



@router.message(TextCmd(["сайт", "веб", "панель"]))
async def cmd_web(message: types.Message):
    builder = InlineKeyboardBuilder()

    # Динамическая ссылка: подставляем ID пользователя прямо в URL
    user_id = message.from_user.id
    url = f"{_WEB_BASE_URL}/profile/{user_id}/"

    builder.button(text="🌐 Открыть мой профиль", url=url)

    await message.answer(
        "🖥 <b>ВЕБ-ПАНЕЛЬ ПРЕДВЕСТНИКА</b>\n\n"
        "<i>Нажмите на кнопку ниже, чтобы открыть свою персональную страницу.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


fallback_router = Router(name="fallback_router")


@fallback_router.message(WrongSyntaxCmd())
async def cmd_wrong_syntax(message: types.Message, correct_usage: str):
    await message.answer(
        f"💡 Нужна запятая!\n\n"
        f"{correct_usage}",
        parse_mode="HTML",
    )


# ── Unknown command suggestions (B6) ─────────────────────────────────────────
# Registered AFTER all known routers — only fires for unmatched "бот X" messages.

unknown_cmd_router = Router(name="unknown_cmd_router")


@unknown_cmd_router.message(UnknownBotCmd())
async def cmd_suggest(message: types.Message, bot_cmd_text: str):
    from services.command_suggester import suggest_commands
    suggestions = suggest_commands(bot_cmd_text)
    if not suggestions:
        return

    tips = "\n".join(
        f"{'└' if i == len(suggestions) - 1 else '├'} бот {cmd}"
        for i, cmd in enumerate(suggestions)
    )
    await message.answer(
        f"❓ Команда не найдена. Имели в виду?\n\n{tips}",
        parse_mode="HTML",
    )