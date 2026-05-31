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
    user_id: int = 0

# Словарь с текстами для каждой вкладки
HELP_PAGES = {
    "main": (
        "📖 <b>ПРЕДВЕСТНИК — ПОМОЩЬ</b>\n\n"
        "<b>Синтаксис команд:</b>\n"
        "<code>бот [команда]</code>\n"
        "<code>бот [команда], [аргумент]</code>\n"
        "<i>Ответ на сообщение = указать юзера</i>\n\n"
        "💡 <i>Нажми на команду чтобы скопировать</i>\n\n"
        "Выбери раздел ниже 👇"
    ),
    "admin": (
        "🛡 <b>МОДЕРАЦИЯ</b>\n\n"
        "⚠️ <b>Предупреждения</b>\n"
        "· <code>бот варн, @юзер [причина]</code>\n"
        "· <code>бот снять варн, @юзер</code>\n\n"
        "🔇 <b>Мут</b>\n"
        "· <code>бот мут, @юзер 10м/2ч/1д</code>\n"
        "· <code>бот размут, @юзер</code>\n\n"
        "⛔ <b>Бан / Кик</b>\n"
        "· <code>бот бан, @юзер [причина]</code>\n"
        "· <code>бот разбан, @юзер</code>\n"
        "· <code>бот кик, @юзер</code>\n\n"
        "🛡 <b>Защита</b>\n"
        "· <code>бот иммунитет, @юзер</code>\n"
        "· <code>бот защита, @юзер 5д/1ч</code>\n"
        "· <code>бот снять защиту, @юзер</code>\n\n"
        "👑 <b>Ранги</b>\n"
        "· <code>бот ранг, @юзер [0-6]</code>\n"
        "· <code>бот ранг глобал, @юзер [0-3]</code>\n\n"
        "⚙️ <b>Настройки</b>\n"
        "· <code>бот настройки чата</code>\n"
        "· <code>бот настройка щита, [дни]</code>\n"
        "· <code>бот лимит варнов, [N]</code>\n\n"
        "🧹 <b>Чистка</b>\n"
        "· <code>бот чистка</code> · <code>бот конец чистки</code>\n\n"
        "· <code>бот баны</code> · <code>бот кики</code> · <code>бот ушли</code>"
    ),
    "economy": (
        "💰 <b>ЭКОНОМИКА</b>\n\n"
        "💳 <b>Кошелёк</b>\n"
        "· <code>бот баланс</code>\n"
        "· <code>бот перевод, @юзер [сумма]</code>\n"
        "· <code>бот история кошелька</code>\n\n"
        "🛒 <b>Магазин</b>\n"
        "· <code>бот магазин</code>\n"
        "· <code>бот инвентарь</code>\n"
        "· <code>бот открыть, [яйцо] [N]</code>\n"
        "· <code>бот акция</code>\n\n"
        "🎰 <b>Гача и игры</b>\n"
        "· <code>бот крутка</code>\n"
        "· <code>бот пити</code>\n"
        "· <code>бот игры</code>\n"
        "· <code>бот обмен</code> — Мора → Алмазы\n\n"
        "🎫 <b>Промокоды</b>\n"
        "· <code>бот промокод, КОД</code>\n\n"
        "🏛 <b>Аукцион</b>\n"
        "· <code>бот аукцион</code>\n"
        "· <code>бот аукцион выставить</code>\n"
        "· <code>бот аукцион мои ставки</code>"
    ),
    "social": (
        "🐾 <b>ПИТОМЦЫ И ОТНОШЕНИЯ</b>\n\n"
        "💍 <b>Брак</b>\n"
        "· <code>бот брак, @юзер</code>\n"
        "· <code>бот развод</code>\n"
        "· <code>бот пара</code> · <code>бот общак</code>\n"
        "· <code>бот вложить, [сумма]</code>\n"
        "· <code>бот снять, [сумма]</code>\n\n"
        "🐾 <b>Питомцы</b>\n"
        "· <code>бот зоопарк</code>\n"
        "· <code>бот питомец</code>\n"
        "· <code>бот поход, 2/4/6/8</code>\n\n"
        "🤝 <b>Социальное</b>\n"
        "· <code>бот обнять, @юзер</code>\n"
        "· <code>бот ударить, @юзер</code>\n"
        "· <code>бот задания</code> · <code>бот достижения</code>\n\n"
        "⚔️ <b>Дуэли</b>\n"
        "· <code>бот дуэль, @юзер, [ставка]</code>"
    ),
    "stats": (
        "📊 <b>ПРОФИЛЬ И ТОПЫ</b>\n\n"
        "👤 <b>Профиль</b>\n"
        "· <code>бот я</code> / <code>бот профиль</code> — мой профиль\n"
        "· <code>бот кто, @юзер</code> — карточка игрока\n"
        "· <code>бот анкета</code> — полная анкета с тегом\n"
        "· <code>бот инфо, @юзер</code> — досье\n\n"
        "🏷 <b>Никнейм</b>\n"
        "· <code>бот мой ник, [псевдоним]</code>\n"
        "· <code>бот мой ник</code> — посмотреть\n\n"
        "🔥 <b>Стрик</b>\n"
        "· <code>бот стрик</code>\n"
        "· <code>бот стрик восстановить</code>\n\n"
        "🏆 <b>Топы</b>\n"
        "· <code>бот топ</code> — активность\n"
        "· <code>бот топ день</code> / <code>неделя</code> / <code>всё время</code>\n"
        "· <code>бот топ мора</code> / <code>алмазы</code> / <code>стрик</code>\n"
        "· <code>бот призраки</code>\n\n"
        "ℹ️ <b>Чат</b>\n"
        "· <code>бот инфо чата</code>\n"
        "· <code>бот настройки чата</code>\n"
        "· <code>бот сайт</code>"
    ),
    "developer": (
        "👨‍💻 <b>DEVELOPER</b>\n\n"
        "📊 <b>Статистика</b>\n"
        "· <code>бот dev стат</code>\n"
        "· <code>бот dev юзер, @ник</code>\n\n"
        "💰 <b>Баланс</b>\n"
        "· <code>бот dev баланс, @ник, [🪙], [💎]</code>\n\n"
        "🔄 <b>Сбросы</b>\n"
        "· <code>бот dev сбросить стрик, @ник</code>\n"
        "· <code>бот dev гача сброс, @ник</code>\n\n"
        "⚡ <b>Ивенты</b>\n"
        "· <code>бот dev ивент сундук</code>\n"
        "· <code>бот dev ивент обмен</code>\n"
        "· <code>бот dev акция</code>\n\n"
        "· <code>бот dev предметы</code>\n\n"
        "🎫 <b>Промокоды</b>\n"
        "· <code>бот dev промокод</code>\n"
        "· <code>бот dev промокод список</code>\n\n"
        "<i>Только для Главного разработчика.</i>"
    ),
}

def get_help_keyboard(active_tab: str = "main", is_dev: bool = False, user_id: int = 0) -> types.InlineKeyboardMarkup:
    """Генерирует клавиатуру с вкладками; помечает активную."""
    def label(text: str, tab: str) -> str:
        return f"· {text} ·" if tab == active_tab else text

    builder = InlineKeyboardBuilder()
    builder.button(text=label("🏠 Главная", "main"), callback_data=HelpCallback(tab="main", user_id=user_id))
    builder.button(text=label("🛡 Админ", "admin"), callback_data=HelpCallback(tab="admin", user_id=user_id))
    builder.button(text=label("💰 Экономика", "economy"), callback_data=HelpCallback(tab="economy", user_id=user_id))
    builder.button(text=label("🐾 Питомцы", "social"), callback_data=HelpCallback(tab="social", user_id=user_id))
    builder.button(text=label("📊 Топы", "stats"), callback_data=HelpCallback(tab="stats", user_id=user_id))
    if is_dev:
        builder.button(text=label("👨‍💻 Developer", "developer"), callback_data=HelpCallback(tab="developer", user_id=user_id))
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
        reply_markup=get_help_keyboard("main", is_dev=is_dev, user_id=message.from_user.id),
        parse_mode="HTML",
    )


@router.callback_query(HelpCallback.filter())
async def handle_help_tabs(query: types.CallbackQuery, callback_data: HelpCallback, developer_id: int = 0):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    tab = callback_data.tab
    if tab not in HELP_PAGES:
        return await query.answer("Ошибка: страница не найдена.")
    if tab == "developer" and not (developer_id and query.from_user.id == developer_id):
        return await query.answer("🔒 Только для разработчика.", show_alert=True)

    is_dev = bool(developer_id and query.from_user.id == developer_id)
    try:
        await query.message.edit_text(
            text=HELP_PAGES[tab],
            reply_markup=get_help_keyboard(tab, is_dev=is_dev, user_id=callback_data.user_id),
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