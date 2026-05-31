import os
import random

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd, WrongSyntaxCmd, UnknownBotCmd
from services.utils import check_callback_owner
from core.registry import ITEMS_REGISTRY
from html import escape as _he

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
        "<b>Синтаксис:</b>\n"
        "· <code>бот [команда]</code>\n"
        "· <code>бот [команда], [аргумент]</code>\n"
        "· Ответ на сообщение = указать юзера\n\n"
        "💡 <i>Нажми на команду — она скопируется</i>\n\n"
        "🛡 <b>Модерация</b> — варны, баны, муты, ранги\n"
        "💰 <b>Экономика</b> — кошелёк, магазин, гача, аукцион\n"
        "🐾 <b>Питомцы</b> — зоопарк, походы, брак, дуэли\n"
        "📊 <b>Профиль</b> — статистика, стрик, топы\n"
        "🌑 <b>Тёмная Мора</b> — контрабанда, ритуал\n"
        "📦 <b>Предметы</b> — каталог всех предметов\n\n"
        "⚡ <b>Быстро:</b> <code>бот я</code> · <code>бот баланс</code> · <code>бот зоопарк</code>"
    ),
    "admin": (
        "🛡 <b>МОДЕРАЦИЯ</b>\n\n"
        "⚠️ <b>Предупреждения</b>\n"
        "· <code>бот варн, @юзер [причина]</code>\n"
        "· <code>бот снять варн, @юзер</code>\n"
        "· <code>бот варны, @юзер</code> — история\n\n"
        "🔇 <b>Мут / Бан / Кик</b>\n"
        "· <code>бот мут, @юзер 10м/2ч/1д</code>\n"
        "· <code>бот размут, @юзер</code>\n"
        "· <code>бот бан, @юзер [причина]</code>\n"
        "· <code>бот разбан, @юзер</code>\n"
        "· <code>бот кик, @юзер</code>\n\n"
        "🛡 <b>Защита</b>\n"
        "· <code>бот иммунитет, @юзер</code> — постоянный\n"
        "· <code>бот защита, @юзер 5д/1ч</code> — временный\n"
        "· <code>бот снять защиту, @юзер</code>\n\n"
        "👑 <b>Ранги</b>\n"
        "· <code>бот ранг, @юзер [0-6]</code> — локальный\n"
        "· <code>бот ранг глобал, @юзер [0-3]</code>\n\n"
        "⚙️ <b>Настройки чата</b>\n"
        "· <code>бот настройки чата</code>\n"
        "· <code>бот настройка щита, [дни]</code>\n"
        "· <code>бот лимит варнов, [N]</code>\n\n"
        "🧹 <b>Чистка / Логи</b>\n"
        "· <code>бот чистка</code> · <code>бот конец чистки</code>\n"
        "· <code>бот баны</code> · <code>бот кики</code> · <code>бот ушли</code>\n"
        "· <code>бот черный список</code>"
    ),
    "economy": (
        "💰 <b>ЭКОНОМИКА</b>\n\n"
        "💳 <b>Кошелёк</b>\n"
        "· <code>бот баланс</code> — 🪙 Мора и 💎 Алмазы\n"
        "· <code>бот перевод, @юзер [сумма]</code>\n"
        "· <code>бот дать, @юзер [сумма]</code> — альтернатива\n"
        "· <code>бот история кошелька</code> — лог операций\n"
        "· <code>бот баланс лог</code> — короткий вариант\n\n"
        "🛒 <b>Магазин</b>\n"
        "· <code>бот магазин</code> — основной магазин\n"
        "· <code>бот акция</code> — акция дня (скидки)\n"
        "· <code>бот инвентарь</code> — мои предметы\n"
        "· <code>бот открыть, [яйцо] [N]</code> — открыть яйца\n\n"
        "🎰 <b>Гача</b>\n"
        "· <code>бот крутка</code> — меню кручений\n"
        "· <code>бот пити</code> — счётчик жалости\n\n"
        "🎲 <b>Мини-игры</b>\n"
        "· <code>бот игры</code> — казино, монетка, рулетка\n"
        "· <code>бот обмен</code> — Мора → Алмазы\n\n"
        "📋 <b>Квесты и ачивки</b>\n"
        "· <code>бот задания</code> — дейли квесты\n"
        "· <code>бот достижения</code>\n\n"
        "🎫 <b>Промокоды</b>\n"
        "· <code>бот промокод, КОД</code>\n\n"
        "🏛 <b>Аукцион</b>\n"
        "· <code>бот аукцион</code> — просмотр лотов\n"
        "· <code>бот аукцион выставить</code>\n"
        "· <code>бот аукцион мои ставки</code>\n"
        "· <code>бот аукцион мои лоты</code>"
    ),
    "pets": (
        "🐾 <b>ПИТОМЦЫ И ПОХОДЫ</b>\n\n"
        "🏠 <b>Зоопарк</b>\n"
        "· <code>бот зоопарк</code> — управление питомцами\n"
        "· <code>бот питомец</code> — карточка активного\n"
        "· <code>бот покормить</code> — покормить активного\n\n"
        "🗺 <b>Экспедиции</b>\n"
        "· <code>бот поход, 2</code> — 2ч, бесплатно\n"
        "· <code>бот поход, 4</code> — 4ч, 15 🪙\n"
        "· <code>бот поход, 6</code> — 6ч, 25 🪙\n"
        "· <code>бот поход, 8</code> — 8ч, 35 🪙\n"
        "· <code>бот ускорить поход</code> — использовать ускоритель ⏩\n\n"
        "💍 <b>Брак</b>\n"
        "· <code>бот брак, @юзер</code>\n"
        "· <code>бот развод</code> · <code>бот пара</code>\n"
        "· <code>бот общак</code> — семейный банк\n"
        "· <code>бот вложить, [сумма]</code>\n"
        "· <code>бот снять, [сумма]</code>\n\n"
        "⚔️ <b>Дуэли</b>\n"
        "· <code>бот дуэль, @юзер, [ставка]</code>\n\n"
        "🤝 <b>Социальное</b>\n"
        "· <code>бот обнять, @юзер</code>\n"
        "· <code>бот ударить, @юзер</code>\n"
        "· <code>бот поцеловать, @юзер</code>\n"
        "· <code>бот погладить, @юзер</code>"
    ),
    "stats": (
        "📊 <b>ПРОФИЛЬ И ТОПЫ</b>\n\n"
        "👤 <b>Профиль</b>\n"
        "· <code>бот я</code> / <code>бот профиль</code> — мой профиль\n"
        "· <code>бот кто, @юзер</code> — карточка игрока\n"
        "· <code>бот анкета</code> — с тегом и доп. инфо\n"
        "· <code>бот инфо, @юзер</code> — досье\n\n"
        "🏷 <b>Никнейм</b>\n"
        "· <code>бот мой ник, [псевдоним]</code> — установить\n"
        "· <code>бот мой ник</code> — посмотреть\n\n"
        "🔥 <b>Стрик</b>\n"
        "· <code>бот стрик</code> — текущий стрик\n"
        "· <code>бот стрик восстановить</code> — восстановить пропущенный\n\n"
        "🏆 <b>Топы активности</b>\n"
        "· <code>бот топ</code> — за всё время\n"
        "· <code>бот топ день</code> / <code>неделя</code> / <code>вчера</code>\n\n"
        "🏆 <b>Топы по категориям</b>\n"
        "· <code>бот топ мора</code> — по балансу 🪙\n"
        "· <code>бот топ алмазы</code> — по балансу 💎\n"
        "· <code>бот топ стрик</code> — по стрику 🔥\n"
        "· <code>бот топ питомцев</code> — по уровню питомцев\n"
        "· <code>бот топ достижений</code>\n"
        "· <code>бот топ аукцион</code>\n\n"
        "👻 <b>Прочее</b>\n"
        "· <code>бот призраки</code> — неактивные участники\n"
        "· <code>бот инфо чата</code>\n"
        "· <code>бот сайт</code> — веб-профиль"
    ),
    "dark": (
        "🌑 <b>ТЁМНАЯ МОРА</b>\n\n"
        "<i>Нелегальная валюта теневого рынка Предвестника.\n"
        "За реальные деньги не купить — только добыть.</i>\n\n"
        "💼 <b>Баланс</b>\n"
        "· <code>бот тёмная мора</code> — текущий баланс 🌑\n\n"
        "🎲 <b>Контрабанда</b>\n"
        "· <code>бот контрабанда, [сумма]</code>\n"
        "· Ставка: 500 – 5 000 🪙 · Кулдаун: 7 дней\n"
        "· 40% успех → 1 🌑 за каждые 300 🪙\n"
        "· 35% провал → теряешь 50% ставки\n"
        "· 25% поймали → теряешь всё + бан 14 дней\n\n"
        "🌑 <b>Культ Бездны (Ритуал)</b>\n"
        "· <code>бот ритуал</code>\n"
        "· Доступно: <b>23:00–01:00 UTC</b>\n"
        "· Кулдаун: 30 дней\n"
        "· Требования:\n"
        "  ├ Стрик 7+ дней 🔥\n"
        "  ├ Уровень 6+ ⭐\n"
        "  └ 3+ питомца 🐾\n"
        "· Награда: 10–20 🌑\n\n"
        "🕵️ <b>Теневой Торговец</b>\n"
        "· Бот сам публикует зашифрованные пророчества раз в 3 дня\n"
        "· Найди ключевое слово → первые 3 игрока получают 5–15 🌑\n"
        "· <code>бот слово, [слово]</code>\n\n"
        "💀 <b>На что тратить 🌑</b>\n"
        "· Реликвии (Великий Аукцион Теней)\n"
        "· Теневые темы профиля (Чёрный рынок)\n"
        "· Испытание Бездны (5 🌑 вход)"
    ),
    "items": (
        "📦 <b>КАТАЛОГ ПРЕДМЕТОВ</b>\n\n"
        "🥚 <b>Яйца</b> — <code>бот открыть, [ID] [кол-во]</code>\n"
        "· <code>egg_basic</code> — 🥚 Базовое · 2 500 🪙 · 80%C/19%R/1%E\n"
        "· <code>egg_silver</code> — 🥈 Серебряное · 8 000 🪙 · 50%C/40%R/10%E\n"
        "· <code>egg_gold</code> — 🪙 Золотое · 25k🪙/150💎 · 75%R/25%E\n"
        "· <code>egg_mythic</code> — 💎 Мифическое · 400💎 · 40%R/60%E\n"
        "· <code>egg_unity</code> — 💖 Единства · 100%Leg · только семьям\n"
        "· <code>egg_crystal</code> — 🔷 Кристальное · 30%E/70%Leg · гача\n"
        "· <code>egg_daily</code> — 🎁 Яйцо дня · бесплатно 1 раз/день\n\n"
        "🍖 <b>Корм</b> — <code>бот зоопарк</code>\n"
        "· <code>food_basic</code> — 🥩 Базовый · 50🪙 · −15 уст.\n"
        "· <code>food_elite</code> — 🍗 Элитный · 150🪙 · −50 уст.\n"
        "· <code>food_energy</code> — ⚡ Энергетик · 250🪙 · −20 уст. + сброс КД похода\n"
        "· <code>food_super</code> — 💊 Суперкорм · 350🪙 · −60 уст. + −5 всем\n"
        "· <code>food_diamond</code> — 💎 Алмазное · 8💎 · −100 уст. + 20% эфф. 24ч\n\n"
        "🎟 <b>Жетоны крутки</b> — 1 бесплатный спин\n"
        "· <code>spin_token_novice</code> / <code>standard</code> / <code>premium</code> / <code>diamond</code>\n\n"
        "⏩ <b>Ускорители похода</b> — <code>бот ускорить поход</code>\n"
        "· <code>exp_boost_1h</code> — −1 ч · гача\n"
        "· <code>exp_boost_2h</code> — −2 ч · гача\n"
        "· <code>exp_boost_4h</code> — −4 ч · гача\n\n"
        "🧪 <b>Зелья игрока</b>\n"
        "· <code>potion_luck_s</code> — +15% шанс ред.+ след. спин · 100🪙\n"
        "· <code>potion_luck_m</code> — +15% ред.+ следующие 3 спина · гача\n"
        "· <code>potion_sprint</code> — +30% лут след. экспедиции · гача\n\n"
        "💠 <b>Материалы</b>\n"
        "· <code>soul_shard</code> — 💠 Осколок Души · 5 шт = Яйцо Призыва\n"
        "· <code>star_dust_s</code> — 🌟 Звёздная пыль · +1 дубликат питомцу\n"
        "· <code>star_dust_l</code> — ✨ Небесная пыль · +5 дубликатов\n\n"
        "🎯 <b>Прочее</b>\n"
        "· <code>treasure_map</code> — 🗺 Карта Сокровищ · +50% лут в походе\n"
        "· <code>lucky_charm</code> — 🍀 Подкова · +15% шанс ред.+ в яйце\n"
        "· <code>study_notes</code> — 📚 Конспект · +50% XP сообщений 4ч · 250🪙\n"
        "· <code>slot_expander</code> — 🏡 Расширитель · +1 слот питомника · 10💎"
    ),
    "social": None,  # backward-compat alias → "pets"
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
        "· <code>бот dev акция</code>\n"
        "· <code>бот dev предметы</code>\n\n"
        "🌑 <b>Тёмная Мора (DEV)</b>\n"
        "· <code>бот god лог, [user_id]</code> — лог кошелька юзера\n"
        "· <code>бот god лог кошелька</code> (реплай)\n\n"
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
    builder.button(text=label("🏠 Главная", "main"),     callback_data=HelpCallback(tab="main",     user_id=user_id))
    builder.button(text=label("🛡 Модерация", "admin"),  callback_data=HelpCallback(tab="admin",    user_id=user_id))
    builder.button(text=label("💰 Экономика", "economy"),callback_data=HelpCallback(tab="economy",  user_id=user_id))
    builder.button(text=label("🐾 Питомцы", "pets"),     callback_data=HelpCallback(tab="pets",     user_id=user_id))
    builder.button(text=label("📊 Профиль", "stats"),    callback_data=HelpCallback(tab="stats",    user_id=user_id))
    builder.button(text=label("🌑 Тёмная Мора", "dark"), callback_data=HelpCallback(tab="dark",     user_id=user_id))
    builder.button(text=label("📦 Предметы", "items"),   callback_data=HelpCallback(tab="items",    user_id=user_id))
    if is_dev:
        builder.button(text=label("👨‍💻 Developer", "developer"), callback_data=HelpCallback(tab="developer", user_id=user_id))
        builder.adjust(1, 2, 2, 2, 1)
    else:
        builder.adjust(1, 2, 2, 2)
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
    # Redirect old aliases
    _ALIASES = {"social": "pets"}
    tab = _ALIASES.get(tab, tab)
    if tab not in HELP_PAGES or HELP_PAGES[tab] is None:
        # Treat None-value aliases as redirects (e.g. social → pets already resolved above)
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


@router.message(TextCmd(["предмет", "item info", "инфо предмет"]))
async def cmd_item_info(message: types.Message, text_args: str = None):
    raw = (text_args or "").strip().lower()
    if not raw:
        return await message.answer(
            "📦 <b>Информация о предмете</b>\n\n"
            "<code>бот предмет, [ID предмета]</code>\n\n"
            "<i>Например: <code>бот предмет, egg_basic</code></i>\n"
            "<i>Полный список — раздел «📦 Предметы» в <code>бот помощь</code></i>",
            parse_mode="HTML",
        )

    safe_raw = _he(raw)
    item = ITEMS_REGISTRY.get(raw)
    if not item:
        matches = [k for k in ITEMS_REGISTRY if raw in k]
        if matches:
            tip = "\n".join(f"· <code>{_he(m)}</code>" for m in matches[:5])
            return await message.answer(
                f"❓ Предмет <code>{safe_raw}</code> не найден. Похожие:\n{tip}",
                parse_mode="HTML",
            )
        return await message.answer(
            f"❌ Предмет <code>{safe_raw}</code> не найден.\n"
            "<i>Список предметов: раздел «📦 Предметы» в <code>бот помощь</code></i>",
            parse_mode="HTML",
        )

    name = item.get("name", raw)
    desc = _he(item.get("description", "Нет описания."))
    cat = item.get("category", "—")
    lines = [f"📦 <b>{name}</b>", f"└ ID: <code>{safe_raw}</code>", ""]

    _CAT_LABELS = {
        "egg": "🥚 Яйцо",
        "food": "🍖 Корм",
        "booster": "⚡ Усилитель",
        "spin_token": "🎟 Жетон крутки",
        "material": "💠 Материал",
        "utility": "🔧 Утилита",
    }
    lines.append(f"Категория: <i>{_CAT_LABELS.get(cat, cat)}</i>")

    if item.get("price_mora"):
        lines.append(f"Цена: <code>{item['price_mora']:,.0f} 🪙</code>".replace(",", " "))
    if item.get("price_diamonds"):
        lines.append(f"Цена: <code>{item['price_diamonds']:.0f} 💎</code>")
    if item.get("is_tradable") is False:
        lines.append("Торговля: <i>не торгуемый</i>")

    lines.append("")
    lines.append(f"<i>{desc}</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


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