import os
import random
import re

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd, WrongSyntaxCmd, UnknownBotCmd, AiQuestionCmd
from services.utils import check_callback_owner
from core.registry import ITEMS_REGISTRY
from core.constants import CHEST_REWARDS_BY_POSITION
from html import escape as _he
from bot.keyboards.cta import answer_group_only

_CHEST_POS = CHEST_REWARDS_BY_POSITION  # честные цифры сундука в помощи — из константы, не руками

_WEB_BASE_URL = os.getenv("WEB_BASE_URL", "")
# Dedicated Mini App URL — MUST be set explicitly. Never falls back to WEB_BASE_URL
# because that variable points to the IESA platform, not Predvestnik.
_MINIAPP_URL = os.getenv("MINIAPP_URL", "")

router = Router(name="common_router")

# Определяем структуру данных для кнопок
class HelpCallback(CallbackData, prefix="help"):
    tab: str
    user_id: int = 0

# ─────────────────────────────────────────────────────────────────────────────
# HELP PAGES — полный справочник по всем механикам
# ─────────────────────────────────────────────────────────────────────────────
HELP_PAGES = {
    # ── Главная ──────────────────────────────────────────────────────────────
    "main": (
        "🔮 <b>ПРЕДВЕСТНИК — ПОЛНЫЙ ГАЙД</b>\n\n"
        "📱 <b>Игра, косметика, биржа, спутники, кланы, семья и профиль\n"
        "Инвентарь, Темы и Крафт переехали в МИНИ-АПП</b> — пиши <code>бот сайт</code>.\n"
        "<i>В чате остались лёгкие команды, соц-действия и админка.</i>\n\n"
        "<b>Как писать команды:</b>\n"
        "▸ <code>бот [команда]</code> — простая команда\n"
        "▸ <code>бот [команда], [аргумент]</code> — с аргументом\n"
        "▸ Ответить на сообщение юзера = указать его как цель\n\n"
        "📌 <i>Нажми на любую команду — она скопируется!</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🛡 <b>Модерация</b> — варны, баны, ранги, чистка\n"
        "💰 <b>Экономика</b> — кошелёк, покупки, баланс\n"
        "🐾 <b>Спутники</b> — роли, связь и походы в мини-аппе\n"
        "👥 <b>Социальное</b> — профиль, брак, варпы, топы\n"
        "🌑 <b>Тёмная Мора</b> — сохранённый баланс и архивный каталог\n"
        "🎪 <b>Ивенты</b> — сундуки, акции, торговец\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Коротко о валютах:</b> 🪙 Мора — подготовка и мир; 💎 Алмазы — редкие\n"
        "заработанные решения; ✨ Зарники — внешний вид и сервис.\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Быстрый старт</b> — пишется в группе с ботом:\n"
        "<code>бот я</code> · <code>бот баланс</code> · <code>бот игры</code> · <code>бот сайт</code>\n\n"
        "🤖 <b>Вопрос?</b> Напиши <code>бот, [вопрос]</code> — отвечу как помощник"
    ),

    # ── Модерация ─────────────────────────────────────────────────────────────
    "admin": (
        "🛡 <b>МОДЕРАЦИЯ ЧАТА</b>\n\n"
        "⚠️ <b>Предупреждения</b>\n"
        "▸ <code>бот варн, @юзер [причина] [30д]</code> — варн (срок в конце — сгорит сам; без срока — вечный)\n"
        "▸ <code>бот снять варн, @юзер</code> — снять варн\n"
        "▸ <code>бот варны, @юзер</code> — история варнов\n"
        "  💡 При достижении лимита — «Суд Присяжных» (кнопки вердикта)\n\n"
        "🔇 <b>Мут / Бан / Кик</b>\n"
        "▸ <code>бот мут, @юзер 10м/2ч/1д</code> — временное молчание\n"
        "▸ <code>бот размут, @юзер</code> — снять мут\n"
        "▸ <code>бот бан, @юзер [причина]</code> — забанить\n"
        "▸ <code>бот разбан, @юзер</code> — разбанить\n"
        "▸ <code>бот кик, @юзер</code> — кикнуть из чата\n\n"
        "🔒 <b>Открыть / закрыть весь чат</b>\n"
        "▸ <code>бот -чат</code> — закрыть чат (писать смогут только админы)\n"
        "▸ <code>бот +чат</code> — открыть чат обратно\n"
        "  💡 Кто может: настрой ранг в <code>бот настройки чата</code> → 🔒, или на сайте\n\n"
        "🛡 <b>Защита от чистки</b>\n"
        "▸ <code>бот иммунитет, @юзер</code> — постоянная защита (тоггл вкл/выкл)\n"
        "▸ <code>бот рест, @юзер 5д/1ч</code> — временный щит (= <code>защита</code>, <code>отдых</code>)\n"
        "▸ <code>бот снять защиту, @юзер</code> — снять любую защиту\n\n"
        "👑 <b>Ранги</b> <i>(0=Юзер → 6=Владелец)</i>\n"
        "▸ <code>бот ранг, @юзер [0–6]</code> — локальный ранг\n"
        "▸ <code>бот ранг глобал, @юзер [0–3]</code> — глобальный\n"
        "  💡 Нельзя выдать ранг выше своего\n"
        "▸ <code>бот обновить права</code> — если вы админ Telegram, но без ранга:\n"
        "  создатель чата получит 👑 Владельца, админ — 🕵️‍♂️ Ст.Админа\n\n"
        "⚙️ <b>Настройки чата</b>\n"
        "▸ <code>бот настройки чата</code> — все параметры\n"
        "▸ <code>бот настройка щита, [дни]</code> — щит новичкам\n"
        "▸ <code>бот лимит варнов, [N]</code> — лимит до бана\n\n"
        "🧹 <b>Чистка активности 2.0</b> <i>(сводка + вердикты, без авто-наказаний)</i>\n"
        "▸ <code>бот чистка</code> — начать (7 дней, норма 50)\n"
        "▸ <code>бот чистка, 01.05-08.05 100</code> — свой период и норма\n"
        "▸ <code>бот чистка статус</code> — прогресс · <code>бот конец чистки</code> — завершить\n"
        "   Досье приходят <b>порциями</b> с кнопкой «Выслать ещё»; вердикты\n"
        "   (Варн/Кик/Бан/Простить) выносит <b>инициатор</b>. Начатую в чате чистку\n"
        "   можно продолжить на сайте (Админ → Чистка) и наоборот.\n"
        "   💡 «Кто пишет во время чистки»: <code>бот настройки чата</code> → ✍️\n\n"
        "🔗 <b>Админ-чат</b> <i>(куда слать сводки/досье)</i>\n"
        "▸ <code>бот привязать админ чат</code> — в основной группе (даст код)\n"
        "▸ <code>бот принять связь, КОД</code> — в админ-группе\n"
        "▸ <code>бот инфо чата</code> — показать привязки текущего чата\n\n"
        "📁 <b>Архив нарушителей</b>\n"
        "▸ <code>бот баны</code> · <code>бот кики</code> · <code>бот ушли</code>\n"
        "▸ <code>бот черный список</code> — блокировки чата"
    ),

    # ── Экономика ─────────────────────────────────────────────────────────────
    "economy": (
        "💰 <b>ЭКОНОМИКА</b>\n\n"
        "💳 <b>Кошелёк</b> — три валюты!\n"
        "▸ <code>бот баланс</code> — 🪙 Мора · 💎 Алмазы · 🌑 Тёмная Мора\n"
        "▸ Валюты не переводятся напрямую; косметику можно подарить на сайте\n"
        "▸ <code>бот история кошелька</code> — полный лог операций\n\n"
        "🪙 <b>Мора</b> — основная валюта\n"
        "  Старые пассивные начисления закрыты; актуальный источник всегда указан рядом с наградой.\n"
        "  На что: разрешённые покупки, комиссии и аукцион.\n\n"
        "💎 <b>Алмазы</b> — редкая заработанная свобода выбора\n"
        "  Получение: опубликованные испытания и сезонные рубежи; купить их нельзя.\n"
        "  Прямой обмен с Морой закрыт.\n\n"
        "🧰 <b>Снабжение</b>\n"
        "  Старый магазин и акция дня закрыты: они продавали предметы прежней прогрессии.\n"
        "▸ <code>бот инвентарь</code> — сохранённые предметы и права\n\n"
        "🏛 <b>Рынок</b>\n"
        "  Новые лоты и ставки закрыты до проверки происхождения товаров.\n"
        "  Старые лоты, резервы и возвраты не удаляются.\n\n"
        "💱 <b>Мора и Алмазы не обмениваются</b>\n"
        "▸ <code>бот обмен</code> — памятка о назначении валют\n\n"
        "🎫 <b>Прочее</b>\n"
        "▸ <code>бот промокод, КОД</code> — активировать промокод"
    ),

    # ── Гача & Игры ──────────────────────────────────────────────────────────
    "gacha": (
        "🔔 <b>ИГРА И АРХИВ НАХОДОК</b>\n\n"
        "🗃 <b>Архив</b>\n"
        "  Случайные крутки закрыты: они больше не продают силу и валюту.\n"
        "  Жетоны и накопленный гарант сохранены для прозрачного разбора без скрытых шансов.\n\n"
        "🔔 <b>Основная игра</b>\n"
        "▸ <code>бот игры</code> — открыть «Разлом колокола»\n"
        "  Важен правильный выбор руны; старые игры со ставками закрыты.\n\n"
        "📋 <b>Старые задания и достижения</b>\n"
        "  История видна, но старые действия больше не создают награды."
    ),

    # ── Питомцы ──────────────────────────────────────────────────────────────
    "pets": (
        "🐾 <b>СПУТНИКИ И ПОХОДЫ</b>\n\n"
        "Все прежние питомцы, имена и редкость сохранены. Старый уровень виден как исторический ранг и не становится новой силой.\n\n"
        "🎭 <b>Роль спутника</b>\n"
        "  Роль выбирается отдельно от вида и меняет решение или информацию, а не печатает валюту. Первый выбор доступен сразу, остальные открываются игровым путём.\n\n"
        "🤝 <b>Связь</b>\n"
        "  Растёт от короткой заботы и совместной игры. Пропущенный день не отнимает прогресс.\n\n"
        "🗺 <b>Походы</b>\n"
        "  Новые походы 2/6/12 часов находятся во вкладке «Игра → Спутник». Уже начатый старый поход завершится один раз по прежним условиям."
    ),

    # ── Социальное ───────────────────────────────────────────────────────────
    "social": (
        "👥 <b>СОЦИАЛЬНОЕ & ПРОФИЛЬ</b>\n\n"
        "👤 <b>Профиль</b>\n"
        "▸ <code>бот я</code> / <code>бот профиль</code> — мой профиль\n"
        "▸ <code>бот кто, @юзер</code> — карточка любого игрока\n"
        "▸ <code>бот инфо, @юзер</code> — досье игрока (алиас: <code>бот досье</code>)\n"
        "▸ <code>бот анкета</code> — с тегом и ссылкой (для репостов)\n"
        "▸ <code>бот мой ник, [псевдоним]</code> — установить никнейм\n"
        "  💡 Ник заменяет юзернейм во всех командах бота!\n\n"
        "🤝 <b>Приведи друга</b>\n"
        "▸ Реферальные награды закрыты; промокоды продолжают работать.\n\n"
        "🔥 <b>Рекорд серии</b>\n"
        "▸ <code>бот стрик</code> — сохранённый результат старой системы\n"
        "  Рекорд не уменьшается; сообщения не создают награды.\n\n"
        "💍 <b>Брак</b>\n"
        "▸ <code>бот брак, @юзер</code> — предложение руки и сердца 💕\n"
        "▸ <code>бот развод</code> — расстаться (грустно, но бывает)\n"
        "▸ <code>бот пара</code> — карточка вашей семьи\n"
        "▸ <code>бот общак</code> — сохранённый семейный баланс\n"
        "▸ <code>бот подарки</code> — витрина подарков партнёру · <code>бот подарок, [название]</code> — подарить\n"
        "  💡 Семейный баланс заморожен до безопасного переноса; новые переводы закрыты.\n\n"
        "🔔 <b>Разлом колокола</b>\n"
        "▸ <code>бот игры</code> — открыть основную игру\n"
        "  Побеждает точность решений и управление сборкой, а не частота нажатий. Старая клеточная боёвка закрыта.\n\n"
        "🤝 <b>Варп-команды</b> — выражай эмоции!\n"
        "❤️ Мирные: <code>обнять</code> · <code>поцеловать</code> · <code>погладить</code>\n"
        "             <code>накормить</code> · <code>пожать руку</code> · <code>подмигнуть</code> · <code>поднять</code>\n"
        "💢 Боевые:  <code>ударить</code> · <code>пнуть</code> · <code>укусить</code> · <code>шлёпнуть</code>\n"
        "             <code>толкнуть</code> · <code>задушить</code>\n"
        "😂 Юмор:    <code>показать язык</code> · <code>обозвать</code> · <code>пощекотать</code> · <code>испугать</code>\n"
        "  ✏️ Формат: <code>бот [действие], @юзер</code>\n\n"
        "🏆 <b>Топы</b>\n"
        "▸ <code>бот топ</code> — активность · <code>бот топ день/неделя</code>\n"
        "▸ <code>бот топ мора</code> · <code>алмазы</code> · <code>стрик</code> · <code>питомцев</code>\n"
        "▸ <code>бот призраки</code> — неактивные участники чата"
    ),

    # ── Тёмная Мора ──────────────────────────────────────────────────────────
    "dark": (
        "🌑 <b>НОЧНОЙ АРХИВ</b>\n\n"
        "Тёмная Мора больше не выпускается. Уже накопленный баланс сохранён и доступен только для прежнего каталога Ночи.\n\n"
        "💼 <b>Баланс</b>\n"
        "▸ <code>бот баланс</code> — показывает 🌑 в кошельке\n"
        "▸ <code>бот тёмная мора</code> — только тёмный баланс\n\n"
        "Старые контрабанда, ритуал и Теневой торговец закрыты и не меняют кошелёк.\n\n"
        "🗃 <b>Что доступно</b>\n"
        "▸ Просмотр сохранённого баланса\n"
        "▸ Прежние тёмные темы и права остаются у владельцев\n"
        "▸ Расход старого остатка будет показан только с заранее известным результатом"
    ),

    # ── Предметы ─────────────────────────────────────────────────────────────
    "items": (
        "📦 <b>СОХРАНЁННЫЕ ПРЕДМЕТЫ</b>\n\n"
        "Инвентарь не очищается: количество старых материалов, корма, жетонов и сундуков остаётся записанным за владельцем.\n\n"
        "Старая усталость, случайные крутки, сундуки и крафт закрыты, поэтому такие предметы сейчас нельзя случайно потратить.\n\n"
        "▸ <code>бот предмет, [ID]</code> — название, количество и актуальный статус\n"
        "▸ Питомцы и их имена доступны в «Игра → Спутник»"
    ),

    # ── Предметы 2 (спец.) ────────────────────────────────────────────────────
    "items2": (
        "📦 <b>СТАТУС МАТЕРИАЛОВ</b>\n\n"
        "Архивные ускорители, зелья удачи, пыль, осколки и жетоны сохранены, но не участвуют в новой силе и не расходуются скрыто.\n\n"
        "Новые предметы будут появляться только с понятным назначением, известной ценой и записью операции.\n\n"
        "▸ <code>бот инвентарь</code> — весь сохранённый список\n"
        "▸ <code>бот предмет, [ID]</code> — статус конкретного предмета"
    ),

    # ── Ивенты ───────────────────────────────────────────────────────────────
    "events": (
        "🎪 <b>СОБЫТИЯ</b>\n\n"
        "Старые сундуки активности, акция дня и случайные денежные события закрыты: они больше не создают валюту или предметы.\n\n"
        "Новый календарь будет строиться вокруг Разлома, Хроники, походов спутников, Союза и мировых состояний Биржи. Каждая награда появится только после публикации точного условия.\n\n"
        "▸ <code>бот игры</code> — текущая основная активность\n"
        "▸ <code>бот промокод, КОД</code> — действующая система промокодов"
    ),

    # ── Backward-compat aliases ───────────────────────────────────────────────
    "stats": None,    # old "stats" tab → now "social"
    "pets_old": None, # unused

    # ── Developer ─────────────────────────────────────────────────────────────
    "developer": (
        "👨‍💻 <b>DEVELOPER — ТОЛЬКО ДЛЯ РАЗРАБОТЧИКА</b>\n\n"
        "📊 <b>Статистика</b>\n"
        "▸ <code>бот dev стат</code> — общая статистика бота\n"
        "▸ <code>бот dev юзер, @ник</code> — данные конкретного юзера\n\n"
        "💰 <b>Управление балансом</b>\n"
        "▸ <code>бот dev баланс, @ник, [🪙], [💎]</code>\n\n"
        "🔍 <b>Поиск и инфо</b>\n"
        "▸ <code>бот dev айди, @ник1 @ник2 ...</code> — username → user_id\n"
        "▸ <code>бот dev чат</code> — полная инфо текущего чата\n"
        "▸ <code>бот dev чат, [chat_id]</code> — полная инфо чата по ID\n\n"
        "📢 <b>Анонсы</b>\n"
        "▸ <code>бот dev анонс, [текст]</code> — бот отправит текст от своего имени\n\n"
        "🔄 <b>Сбросы</b>\n"
        "▸ <code>бот dev сбросить стрик, @ник</code>\n"
        "▸ <code>бот dev гача сброс, @ник</code>\n\n"
        "⚡ <b>Ивенты</b>\n"
        "▸ <code>бот dev ивент сундук</code> — спавн сундука\n"
        "▸ <code>бот dev ивент обмен</code> — запустить обмен\n"
        "▸ <code>бот dev акция</code> — обновить акцию дня\n"
        "▸ <code>бот dev предметы</code> — список всех предметов\n\n"
        "🧩 <b>Модули чатов</b>\n"
        "▸ <code>бот dev модули</code> — статус модулей текущего чата\n"
        "▸ <code>бот dev модуль вкл/выкл, [модуль]</code>\n\n"
        "🚫 <b>Глобальный ЧС</b>\n"
        "▸ <code>бот dev глобал чс</code> — список\n"
        "▸ <code>бот dev глобал чс добавить, @юзер [причина]</code>\n"
        "▸ <code>бот dev глобал чс убрать, @юзер</code>\n\n"
        "🌑 <b>Тёмная Мора</b>\n"
        "▸ <code>бот god лог, [user_id]</code> — лог кошелька (50 записей)\n"
        "▸ Реплай на сообщение → лог без аргументов\n\n"
        "🎫 <b>Промокоды</b>\n"
        "▸ <code>бот dev промокод</code> — создать промокод (11 шагов)\n"
        "▸ <code>бот dev промокод список</code> — все промокоды\n"
        "▸ <code>бот dev промокод инфо, КОД</code> — детали + история активаций\n\n"
        "<i>Команды доступны только Главному разработчику.</i>"
    ),
}


def get_help_keyboard(active_tab: str = "main", is_dev: bool = False, user_id: int = 0) -> types.InlineKeyboardMarkup:
    def label(text: str, tab: str) -> str:
        return f"· {text} ·" if tab == active_tab else text

    b = InlineKeyboardBuilder()
    b.button(text=label("🏠 Главная",      "main"),    callback_data=HelpCallback(tab="main",    user_id=user_id))
    b.button(text=label("🛡 Модерация",    "admin"),   callback_data=HelpCallback(tab="admin",   user_id=user_id))
    b.button(text=label("💰 Экономика",    "economy"), callback_data=HelpCallback(tab="economy", user_id=user_id))
    b.button(text=label("🔔 Игра & Архив", "gacha"), callback_data=HelpCallback(tab="gacha", user_id=user_id))
    b.button(text=label("🐾 Питомцы",     "pets"),    callback_data=HelpCallback(tab="pets",    user_id=user_id))
    b.button(text=label("👥 Социальное",  "social"),  callback_data=HelpCallback(tab="social",  user_id=user_id))
    b.button(text=label("🌑 Тёмная Мора", "dark"),    callback_data=HelpCallback(tab="dark",    user_id=user_id))
    b.button(text=label("📦 Предметы 1",  "items"),   callback_data=HelpCallback(tab="items",   user_id=user_id))
    b.button(text=label("🔮 Предметы 2",  "items2"),  callback_data=HelpCallback(tab="items2",  user_id=user_id))
    b.button(text=label("🎪 Ивенты",      "events"),  callback_data=HelpCallback(tab="events",  user_id=user_id))
    if is_dev:
        b.button(text=label("👨‍💻 Dev", "developer"), callback_data=HelpCallback(tab="developer", user_id=user_id))
        b.adjust(1, 2, 2, 2, 3, 1)
    else:
        b.adjust(1, 2, 2, 2, 3)
    return b.as_markup()


# UX_AUDIT Б21: пул откликов на голое «бот» — в интонации бренда («тихая мистика»),
# юмор оставлен, мемность убрана. Часть откликов мягко ведёт в «бот помощь».
_BOT_ALONE_RESPONSES = [
    "👁 Я здесь. Я всегда здесь.",
    "🌘 Ты произнёс имя — и тьма откликнулась. Чего желаешь?",
    "🕯 Свеча дрогнула. Слушаю.",
    "🔮 Шар помутнел от твоего зова. Желание формулируют словами: <code>бот помощь</code> покажет пути.",
    "🌫 Туман расступился. За ним — я. За мной — все команды: <code>бот помощь</code>.",
    "📖 Книга открылась на пустой странице. Впиши в неё команду.",
    "🌑 Бездна услышала. Бездна ждёт продолжения.",
    "🚪 Ты постучал, но не вошёл. Смелее: <code>бот помощь</code> — связка ключей.",
    "🕸 Паутина дрогнула — кто-то звал. Говори.",
    "🌙 Луна на месте, Мора сосчитана. Что тебе нужно?",
    "👁‍🗨 Один зов — один взгляд из тени. Дальше — команда.",
    "🪞 Зеркало показывает того, кто пишет «бот» без команды. Узнаёшь?",
    "🌘 Слово сказано. Эхо вернулось. Мы квиты.",
    "☄️ Знамение гласит: сегодня кто-то допишет команду до конца. Возможно, ты.",
    "🃏 Карта дня — «Незаконченная мысль». Перевёрнутая.",
    "⏳ Песок сыплется. Я никуда не тороплюсь. А ты?",
    "🌌 Я существовал до этого чата. Подожду и после этого сообщения.",
    "🪶 Перо занесено над пергаментом. Диктуй.",
    "🍵 Гуща на дне твоей чашки сложилась в слова «бот помощь». Странно, да?",
    "🗿 Древние тоже иногда звали духов без дела. Духи привыкли.",
    "🌒 Полумрак. Тишина. Ты и я. Неплохое начало — теперь команду.",
    "⚖️ Одно слово — и целый Предвестник в ответ. Неравный обмен в твою пользу.",
    "🕯 Две свечи погасли, третья горит. Это ничего не значит. Но звучит загадочно.",
    "🌫 Я мог бы предсказать, что ты напишешь дальше. Но вдруг ты сам не знаешь.",
    "👁 Глаз открылся. Глаз моргнул. Глаз ждёт.",
    "🗝 Тысяча дверей — и ни одного названия. Подсказка: <code>бот помощь</code>.",
    "🌘 Предвестник чувствует твоё присутствие. И лёгкое замешательство.",
    "🪙 Брошенная монета встала на ребро. Загадай уже что-нибудь.",
    "📜 Свиток развёрнут. Строка пуста. История ждёт автора.",
    "🌑 Тьма не осуждает. Тьма просто ждёт команду.",
    "🔔 Колокол прозвенел один раз. Один раз — это просто «привет».",
    "🕰 Стрелки замерли. Время пойдёт, когда допишешь мысль.",
    "🌙 Шёпот дошёл. Смысл — потерялся по дороге. Повтори с командой.",
    "🧿 Я не читаю мысли. Только Мору, судьбы и <code>бот помощь</code>.",
    "🌠 Три буквы — целая вселенная вопросов.",
    "🌗 Полузов — полуответ. Справедливо.",
    "🕯 Огонёк наклонился в твою сторону. Ты избран. Избранным тоже нужна команда.",
    "⚗️ В котле забулькало. Рецепт неполон: добавь слово после «бот».",
    "🌒 Я явился. Расскажешь, зачем звал, — или оставим это тайной?",
    "🪄 Жезл поднят. Заклинание не названо. Классика.",
    "👣 Следы на пепле ведут к тебе. Что дальше, путник?",
    "🌌 Зов без просьбы — тоже ритуал. Я его принял.",
]


@router.message(F.text.lower().strip() == "бот")
async def cmd_bot_alone(message: types.Message):
    if message.chat.type == "private":
        return await answer_group_only(message)
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
    # Redirect old aliases (backward compat for cached buttons)
    _ALIASES = {
        "stats": "social",     # old "stats" tab → new "social"
        "pets_old": "pets",
    }
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



@router.message(TextCmd(["сайт", "веб", "мини апп", "miniapp", "app", "приложение"]))
async def cmd_web(message: types.Message):
    if not _MINIAPP_URL:
        return await message.answer(
            "🔮 <b>ПРЕДВЕСТНИК — МИНИ-АПП</b>\n\n"
            "⚙️ <i>Мини-апп ещё не развёрнут.</i>\n"
            "Разработчик настраивает сервис — скоро будет доступен!",
            parse_mode="HTML",
        )

    builder = InlineKeyboardBuilder()
    # Telegram allows WebAppInfo buttons ONLY in private chats (DMs).
    # In groups, web_app type raises BUTTON_TYPE_INVALID — use plain url instead.
    is_private = message.chat.type == "private"
    if is_private and _MINIAPP_URL.startswith("https://"):
        builder.button(
            text="🔮 Открыть мини-апп",
            web_app=types.WebAppInfo(url=_MINIAPP_URL),
        )
    else:
        # A direct app HTTPS link opens an external browser from group chats.
        # Telegram's bot deep link keeps the experience inside Telegram.
        _bot_username = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")
        builder.button(
            text="🔮 Открыть мини-апп",
            url=f"https://t.me/{_bot_username}?startapp=home",
        )

    await message.answer(
        "🔮 <b>ПРЕДВЕСТНИК — МИНИ-АПП</b>\n\n"
        "Твой профиль, топы, статус ивентов — прямо в Telegram.\n\n"
        "<i>Нажми кнопку ниже ↓</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(TextCmd(["предмет", "item info", "инфо предмет"]))
async def cmd_item_info(message: types.Message, text_args: str = None):
    raw = (text_args or "").strip().lower()
    if not raw:
        return await message.answer(
            "📦 <b>Информация о предмете</b>\n\n"
            "<code>бот предмет, [ID предмета]</code>\n\n"
            "<i>Например: <code>бот предмет, spin_token</code></i>\n"
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


# ── Рарити easter egg ─────────────────────────────────────────────────────────
# RARITY_STICKER_ID — установите через /setcommands в @BotFather или
# загрузите стикер боту и скопируйте file_id из ответа.
_RARITY_STICKER_ID = os.getenv("RARITY_STICKER_ID", "")
_RARITY_RESPONSES = [
    "🦄✨ <b>РАРИТИ!</b> — Дарлинг, ты меня позвал?",
    "💎 <b>Рарити</b> — лучшая пони! Не обсуждается.",
    "🪡 Рарити занята созданием шедевра. Не мешай.",
    "✨ <i>«Я. Просто. В. Восторге!»</i> — Рарити",
    "💜 Рарити одобряет твой вкус.",
    "🎀 Рарити говорит: главное — стиль!",
]


@router.message(F.text.lower().regexp(r"рар+и+т+и|раррити|рарит+и"))
async def cmd_rarity(message: types.Message):
    """Пасхалка — ответ на упоминание Рарити."""
    response = random.choice(_RARITY_RESPONSES)
    if _RARITY_STICKER_ID:
        try:
            await message.answer_sticker(_RARITY_STICKER_ID)
        except Exception:
            pass
    await message.answer(response, parse_mode="HTML")


_AI_KNOWLEDGE_CACHE: str | None = None


def _ai_knowledge_text() -> str:
    """HELP_PAGES целиком, без HTML-тегов — контекст для ИИ-помощника (services/ai_assistant.py).
    Именно HELP_PAGES, а не GAME_BIBLE.md: это то, что реально видят живые игроки прямо
    сейчас, самокорректируется и уже актуализировано под Web First (в отличие от GAME_BIBLE.md,
    который не обновляется автоматически и местами устарел)."""
    global _AI_KNOWLEDGE_CACHE
    if _AI_KNOWLEDGE_CACHE is None:
        # HELP_PAGES содержит None-заглушки легаси-вкладок ("stats", "pets_old")
        raw = "\n\n".join(v for v in HELP_PAGES.values() if isinstance(v, str))
        _AI_KNOWLEDGE_CACHE = re.sub(r"<[^>]+>", "", raw)
    return _AI_KNOWLEDGE_CACHE


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


# Лорные закрывашки под ответом ИИ — мистический флёр «Предвестника»
_AI_CLOSERS = [
    "Руны уже шепчут твой следующий вопрос…",
    "Судьба любит любопытных.",
    "Чернила пророчества ещё не высохли.",
    "Звёзды записали этот разговор.",
    "Вопрос — первый шаг любого пути.",
    "Тьма отвечает тем, кто спрашивает.",
]


# Действия, предложенные ИИ-помощником: исполняются ТОЛЬКО после нажатия
# кнопки самим игроком (user_id зашивается в callback при создании кнопки
# из message.from_user.id — модель на него влиять не может).
class AiActionCB(CallbackData, prefix="aiact"):
    act: str          # "exp" — поход, "tr" — перевод, "cancel" — отмена
    hours: int = 0
    user_id: int = 0
    pa_id: int = 0     # id строки ai_pending_actions (перевод)
    target_id: int = 0  # получатель перевода


def _ai_action_kb(action: dict, user_id: int) -> types.InlineKeyboardMarkup | None:
    """Кнопки подтверждения для pending_action от ИИ. None = действие неизвестно."""
    if action.get("type") == "transfer":
        from infrastructure.repositories.economy import TRANSFER_CURRENCIES
        meta = TRANSFER_CURRENCIES.get(action.get("currency") or "mora", TRANSFER_CURRENCIES["mora"])
        amount = action.get("amount") or 0
        amount_s = f"{amount:g}"
        b = InlineKeyboardBuilder()
        for cand in (action.get("candidates") or [])[:4]:
            name = str(cand.get("name") or "?")[:20]
            b.button(
                text=f"✅ {amount_s}{meta['icon']} → {name}",
                callback_data=AiActionCB(act="tr", user_id=user_id,
                                         pa_id=action.get("action_id") or 0,
                                         target_id=cand.get("id") or 0))
        b.button(text="❌ Отмена", callback_data=AiActionCB(act="cancel", user_id=user_id))
        b.adjust(1)
        return b.as_markup()
    return None


@unknown_cmd_router.callback_query(AiActionCB.filter())
async def cb_ai_action(query: types.CallbackQuery, callback_data: AiActionCB, db):
    # Жёсткая проверка владельца: кнопку исполняет только тот, чей вопрос
    if query.from_user.id != callback_data.user_id:
        return await query.answer("❌ Эта кнопка не для вас.", show_alert=True)
    if callback_data.act == "cancel":
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await query.answer("Отменено")
    if callback_data.act == "tr":
        # Перевод: одноразовость гарантирует атомарный consume в БД (двойной
        # клик/гонка/рестарт → второй клик получает «уже исполнено»). Получатель
        # сверяется со списком, зашитым при создании предложения.
        import json
        from infrastructure.repositories.ai_assistant import consume_pending_action
        from infrastructure.repositories.economy import transfer_currency, TRANSFER_CURRENCIES
        from services.utils import resolve_display_name, format_currency
        payload_raw = await consume_pending_action(db, callback_data.pa_id, callback_data.user_id)
        if payload_raw is None:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return await query.answer("⌛ Предложение устарело или уже исполнено.", show_alert=True)
        try:
            payload = json.loads(payload_raw)
        except (TypeError, ValueError):
            payload = {}
        targets = payload.get("targets") or {}
        if str(callback_data.target_id) not in targets:
            return await query.answer("❌ Некорректный получатель.", show_alert=True)
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        currency = payload.get("currency") or "mora"
        amount = float(payload.get("amount") or 0)
        meta = TRANSFER_CURRENCIES.get(currency, TRANSFER_CURRENCIES["mora"])
        try:
            success, msg = await transfer_currency(
                db, callback_data.user_id, callback_data.target_id,
                currency, amount, chat_id=query.message.chat.id)
        except Exception as e:
            from loguru import logger
            logger.error(f"AI action transfer error: {e}")
            success, msg = False, "внутренняя ошибка, попробуй командой «бот перевод»."
        if success:
            target_name = await resolve_display_name(
                db, callback_data.target_id, query.message.chat.id, "игроку")
            text = (f"💸 <b>Перевод выполнен!</b>\n"
                    f"<code>{format_currency(amount)}</code> {meta['icon']} {meta['label']} → "
                    f"<b>{target_name}</b>")
        else:
            text = f"❌ <b>Отказ:</b> {msg}"
        await query.message.answer(text, parse_mode="HTML")
        return await query.answer()
    if callback_data.act == "exp":
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.answer(
            "Старое предложение похода закрыто. Новый маршрут: <b>Игра → Спутник</b>.",
            parse_mode="HTML",
        )
        return await query.answer("Открой новый поход в мини-аппе.")
    return await query.answer()


@unknown_cmd_router.message(AiQuestionCmd())
async def cmd_ai_question(message: types.Message, ai_question: str, db):
    """«бот, <вопрос>» (запятая после «бот»), не совпавший ни с одной командой →
    вопрос ИИ-помощнику. «бот <текст>» без запятой сюда не попадает — идёт в
    cmd_suggest, как раньше."""
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:
        pass
    # Глобального error-хендлера в боте нет: любое исключение здесь = молчание
    # для игрока, поэтому страхуем весь путь, не только вызов API внутри сервиса.
    action = None
    try:
        from services.ai_assistant import answer_question
        answer, remaining, action = await answer_question(
            db, message.from_user.id, message.chat.id, ai_question, _ai_knowledge_text(),
            user_name=message.from_user.first_name or "путник",
        )
    except Exception as e:
        from loguru import logger
        logger.error(f"AI question handler error: {e}")
        answer, remaining = "🤖 ИИ-помощник сейчас недоступен, попробуй чуть позже.", None

    if remaining is not None:
        # Дневной лимит теперь зависит от VIP (block 8) — знаменатель у каждого свой,
        # поэтому показываем только остаток, без «/N».
        answer += (f"\n\n<i>🔮 {random.choice(_AI_CLOSERS)}"
                   f" · ✨ осталось {remaining} на сегодня</i>")

    # Предложенное ИИ действие → кнопки подтверждения (владелец зашит в callback)
    action_kb = _ai_action_kb(action, message.from_user.id) if action else None
    if action_kb is not None:
        # Железный дисклеймер ОТ СИСТЕМЫ: модель могла написать «перевёл/готово»,
        # но правда всегда на экране — действие исполняет только кнопка, итог
        # приходит отдельным сообщением из реального API (cb_ai_action).
        answer += "\n⏳ <i>Действие ещё НЕ выполнено — его исполняет только кнопка ниже.</i>"
        kb_markup = action_kb
    else:
        # Вопрос явно про раздел мини-аппа (биржа/акция дня/...) → сразу кнопка
        # туда, а не общая. Тот же список алиасов, что у текстовых команд-редиректов
        # (web_redirect.py) — один источник правды, не расходится с ним.
        from bot.handlers.web_redirect import _REDIRECTS as _sections, section_url
        q = ai_question.lower()
        section_hit = next(
            ((sec, title) for aliases, sec, title in _sections
             if any(re.search(rf"\b{re.escape(a)}\b", q) for a in aliases)),
            None,
        )
        kb = InlineKeyboardBuilder()
        if section_hit:
            sec, title = section_hit
            kb.button(text=f"🚀 {title}", url=section_url(sec))
        else:
            kb.button(text="📖 Полная справка", callback_data=HelpCallback(tab="main", user_id=0))
            if _MINIAPP_URL:
                kb.button(text="🌐 Мини-апп", url=_MINIAPP_URL)
        kb.adjust(2)
        kb_markup = kb.as_markup()

    # Реплай на вопрос — в живом чате видно, кому именно ответил бот
    try:
        await message.reply(answer, parse_mode="HTML", reply_markup=kb_markup)
    except Exception:
        # Кривой HTML от модели не должен стоить игроку ответа
        await message.reply(re.sub(r"<[^>]+>", "", answer), reply_markup=kb_markup)


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
