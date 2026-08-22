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
        "📱 <b>Магазин, Гача, Аукцион, Биржа, Питомцы, Боевой пропуск, Кланы,\n"
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
        "🐾 <b>Питомцы</b> — поход (остальное — в мини-аппе)\n"
        "👥 <b>Социальное</b> — профиль, брак, варпы, топы\n"
        "🌑 <b>Тёмная Мора</b> — контрабанда, ритуал, торговец\n"
        "🎪 <b>Ивенты</b> — сундуки, акции, торговец\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Коротко о валютах:</b> 🪙 Мора — на всё подряд; 💎 Алмазы — премиум-крутки\n"
        "и корм; ✨ Зарники — донат и VIP. Подробнее — кнопка «💰 Экономика» ниже.\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Быстрый старт</b> — пишется в группе с ботом:\n"
        "<code>бот я</code> · <code>бот баланс</code> · <code>бот поход</code> · <code>бот сайт</code>\n\n"
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
        "  Откуда: сообщения в чате, стрик, квесты, ивенты, походы\n"
        "  На что: магазин, гача, походы, аукцион\n\n"
        "💎 <b>Алмазы</b> — премиум валюта\n"
        "  Откуда: стрик 7/30/100 дней, достижения, бонус за все квесты, обмен Моры\n"
        "  На что: Алмазная крутка, премиум-корм, обмен на Мору\n\n"
        "🛒 <b>Магазин</b>\n"
        "▸ <code>бот магазин</code> — корм, зелья, утилиты\n"
        "▸ <code>бот акция</code> — 5 скидочных лотов каждый день!\n"
        "▸ <code>бот инвентарь</code> — мои предметы\n\n"
        "🏛 <b>Аукцион</b> — торги между игроками\n"
        "▸ <code>бот аукцион</code> — просмотр всех лотов\n"
        "▸ <code>бот аукцион выставить</code> — продать предмет/питомца\n"
        "▸ <code>бот аукцион мои ставки</code> · <code>бот аукцион мои лоты</code>\n"
        "  💡 Ставки до 1 000 000 🪙 · Комиссия 5% · Длительность 24ч\n\n"
        "💱 <b>Обменник валют</b> — Мора ↔ Алмазы (постоянный)\n"
        "▸ <code>бот обмен</code> или клик на 🪙/💎 в профиле на сайте\n"
        "  🛒 3 000 🪙 = 1 💎 · 💸 1 💎 = 2 000 🪙 · лимит 300 💎/день в каждую сторону\n\n"
        "🎫 <b>Прочее</b>\n"
        "▸ <code>бот промокод, КОД</code> — активировать промокод"
    ),

    # ── Гача & Игры ──────────────────────────────────────────────────────────
    "gacha": (
        "🎲 <b>ГАЧА, МИНИ-ИГРЫ & КВЕСТЫ</b>\n\n"
        "🎰 <b>Крутка (Гача)</b>\n"
        "▸ <code>бот крутка</code> — открыть меню кручений\n"
        "▸ <code>бот пити</code> — счётчик жалости (гарант.)\n\n"
        "Режимы крутки:\n"
        "🪙 <b>Крутка за Мору</b> — 600 🪙 · Common→Epic, мора, ресурсы\n"
        "💎 <b>Алмазная крутка</b> — 8 💎 · выше шанс редких (Epic→Legendary)\n"
        "  💡 ×10 крутка — со скидкой 10%\n"
        "  💡 Пити — счётчик без-удачи → гарант на редкость!\n"
        "  💡 🎟 Жетон Гачи = 1 БЕСПЛАТНЫЙ спин мора-режима (ивенты, ачивки, квесты)\n\n"
        "🎯 <b>Мини-игры</b>\n"
        "▸ <code>бот игры</code> — меню всех игр\n"
        "  🎲 Кубик — 50–1 000 🪙 · ×2 при победе · КД 20мин\n"
        "  🪙 Монетка — 50–1 000 🪙 · ×1.9 · КД 20мин\n"
        "  🔢 Число (1–5) — 50–500 🪙 · ×8 · КД 30мин\n"
        "  🎡 Рулетка — 100–2 000 🪙 · ×1.9 · КД 1ч\n"
        "  ⚠️ Дневной лимит выигрыша: 5 000 🪙\n\n"
        "📋 <b>Ежедневные квесты</b>\n"
        "▸ <code>бот задания</code> — 3 задания в день (обнов. в 00:00 UTC)\n"
        "  Типы: сообщения · экспедиции · гача · варпы · ставки\n"
        "  Награда: Мора + предметы за каждое\n"
        "  🏆 Закрыл ВСЕ 3 → супер-бонус: 1 000 🪙 + 3 💎 + 🎟 жетон!\n\n"
        "🏆 <b>Достижения</b>\n"
        "▸ <code>бот достижения</code> — прогресс по всем ачивкам\n"
        "  10 уровней каждой ачивки · Награды: Мора + Алмазы + жетоны\n"
        "  Категории: гача · питомцы · стрик · брак · аукцион\n\n"
        "🛒 <b>Акция дня</b>\n"
        "▸ <code>бот акция</code> — 3 лота за 🪙 + 2 за 💎 · обновл. каждый день\n"
        "  Скидки 10–50% · Жетоны · Корм · Редкие предметы"
    ),

    # ── Питомцы ──────────────────────────────────────────────────────────────
    "pets": (
        "🐾 <b>ПИТОМЦЫ & ПОХОДЫ</b>\n\n"
        "🏠 <b>Зоопарк — управление</b>\n"
        "▸ <code>бот зоопарк</code> — центр управления питомниками\n"
        "  Слоты: 🟢 Активный (поход+бафф) · 🔵 Пассивный (бафф) · ⬜ Склад\n"
        "▸ <code>бот питомец</code> — карточка активного питомца\n"
        "  Прокачка: дубликаты (star_dust) → уровень питомца растёт → бафф сильнее\n\n"
        "🍖 <b>Усталость и кормление</b>\n"
        "  0–79 🟢 норма · 80–99 🔴 устал · 100 ⛔ поход невозможен!\n"
        "▸ Кормить через <code>бот зоопарк</code> → кнопка «Покормить»\n"
        "  🥩 Базовый −15 · 🍗 Элитный −50 · ⚡ Энергетик −20+КД сброс\n"
        "  💊 Суперкорм −60+все питомцы · 💎 Алмазное −100+20% эфф. 24ч\n\n"
        "🗺 <b>Экспедиции</b> — питомец добывает Мору пока ты спишь!\n"
        "▸ <code>бот поход, 2</code> — 2ч · бесплатно · 55–85 🪙 + XP\n"
        "▸ <code>бот поход, 4</code> — 4ч · 40 🪙 · 130–175 🪙 + XP\n"
        "▸ <code>бот поход, 6</code> — 6ч · 60 🪙 · 270–380 🪙 + XP\n"
        "▸ <code>бот поход, 8</code> — 8ч · 100 🪙 · 430–620 🪙 + XP\n"
        "▸ <code>бот ускорить поход</code> — использовать ускоритель ⏩\n\n"
        "🐾 <b>Виды питомцев и их баффы</b>\n"
        "Common: 🐹 Хомяк (+Мора/день) · 🦉 Сова (+XP/сообщ.) · 🐕 Собака (−время похода)\n"
        "Rare: 🐢 Черепаха (−цены в магазине) · 🦅 Сокол (+лут из похода)\n"
        "Epic: 🐺 Волк (−усталость питомнику) · 🦊 Лиса (шанс 💎 в походе)\n"
        "Leg: 🐉 Дракон (+лимит банка) · 🦄 Единорог (−усталость семьи)\n\n"
        "🎰 <b>Получить питомца</b>\n"
        "Только через Гачу — вкладка «Гача» в мини-аппе\n"
        "Крутка за Мору/Алмазы, бесплатно — по Жетонам гачи 🎟"
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
        "▸ <code>бот рефералка</code> — личная ссылка-приглашение\n"
        "  Другу — бонус за вход по ссылке, тебе — тот же бонус + % с его покупок ✨\n\n"
        "🔥 <b>Рекорд серии</b>\n"
        "▸ <code>бот стрик</code> — сохранённый результат старой системы\n"
        "  Рекорд не уменьшается; сообщения не создают награды.\n\n"
        "💍 <b>Брак</b>\n"
        "▸ <code>бот брак, @юзер</code> — предложение руки и сердца 💕\n"
        "▸ <code>бот развод</code> — расстаться (грустно, но бывает)\n"
        "▸ <code>бот пара</code> — карточка вашей семьи\n"
        "▸ <code>бот общак</code> · <code>бот вложить</code> · <code>бот снять</code>\n"
        "▸ <code>бот подарки</code> — витрина подарков партнёру · <code>бот подарок, [название]</code> — подарить\n"
        "  💡 В браке копится общий семейный бюджет на гачу и подарки!\n\n"
        "⚔️ <b>Боёвка 3.0 — боевые юниты</b>\n"
        "▸ <code>бот казарма</code> — Казарма: призыв юнитов за 🔷, отряд из 3\n"
        "▸ <code>бот арена</code> — Врата, Бездна, Рейды (бои отрядом в мини-аппе)\n"
        "  Сила = отряд юнитов из Казармы. Мирные питомцы не сражаются —\n"
        "  они заняты экономикой (экспедиции, баффы) 🐾\n\n"
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
        "🌑 <b>ТЁМНАЯ МОРА — НЕЛЕГАЛЬНАЯ ВАЛЮТА</b>\n\n"
        "<i>Тёмная Мора ходит по теневому рынку Предвестника.\n"
        "За реальные деньги не купить — только добыть хитростью.</i>\n\n"
        "💼 <b>Баланс</b>\n"
        "▸ <code>бот баланс</code> — показывает 🌑 в кошельке\n"
        "▸ <code>бот тёмная мора</code> — только тёмный баланс\n\n"
        "🎲 <b>Контрабанда</b>\n"
        "▸ <code>бот контрабанда, [сумма]</code>\n"
        "  Ставка: 100 – 5 000 🪙 · Кулдаун: 7 дней\n"
        "  🟢 40% успех → 1 🌑 за каждые 600 🪙\n"
        "  🟡 35% провал → теряешь 50% ставки, кулдаун 7д\n"
        "  🔴 25% поймали → теряешь всё + бан команды 4 дня!\n\n"
        "🕯 <b>Культ Бездны — Ритуал</b>\n"
        "▸ <code>бот ритуал</code> (только 23:00–01:00 UTC)\n"
        "  Требования: 🔥 стрик 7+ · ⭐ уровень 6+ · 🐾 3+ питомца\n"
        "  Кулдаун: 30 дней · Награда: 10–20 🌑\n"
        "  💡 Поставь будильник на 23:00 UTC — многие пропускают!\n\n"
        "🕵️ <b>Теневой Торговец</b>\n"
        "  Пророчество в случайном активном чате раз в ~3 дня (окно 2 часа).\n"
        "  Разгадай слово из маски → первые 3 игрока: 🌑 + ВАУЧЕР на Теневую реликвию\n"
        "▸ <code>бот слово, [догадка]</code> — ответить торговцу\n"
        "▸ <code>бот теневые реликвии</code> — теневая лавка: 4 эксклюзива за 🌑\n"
        "  (покупка только по ваучеру победителя; дают +% к 🌑 из Теневых Врат)\n\n"
        "💀 <b>На что тратить 🌑</b>\n"
        "▸ Реликвии (Маркет в мини-аппе) — +% к моро-награде походов\n"
        "▸ Теневые реликвии (см. выше) · Тёмные темы профиля"
    ),

    # ── Предметы ─────────────────────────────────────────────────────────────
    "items": (
        "📦 <b>КАТАЛОГ ПРЕДМЕТОВ</b>\n"
        "<i>💡 Подробнее о любом: <code>бот предмет, [ID]</code></i>\n\n"
        "🐾 <b>ПИТОМЦЫ</b> — только через Гачу (вкладка «Гача» в мини-аппе)\n"
        "  📍 Крутка за Мору 🪙 или Алмазы 💎; бесплатно — по Жетонам гачи 🎟\n\n"
        "🍖 <b>КОРМ</b> — использовать через <code>бот зоопарк</code>\n"
        "▸ <code>food_basic</code> 🥩 120🪙 — −15 усталости\n"
        "▸ <code>food_elite</code> 🍗 450🪙 — −50 усталости\n"
        "▸ <code>food_energy</code> ⚡ 750🪙 — −20 уст. + сброс КД похода\n"
        "▸ <code>food_super</code> 💊 1100🪙 — −60 акт. + −5 всем питомцам\n"
        "▸ <code>food_diamond</code> 💎 12💎 — −100 уст. + 20% эфф. 24ч\n\n"
        "🎟 <b>ЖЕТОН ГАЧИ</b> — 1 бесплатный спин мора-режима\n"
        "  📍 Ивенты, сундуки, достижения, квесты, питомец 🦉 Сова Lv10\n"
        "▸ <code>spin_token</code>"
    ),

    # ── Предметы 2 (спец.) ────────────────────────────────────────────────────
    "items2": (
        "📦 <b>ПРЕДМЕТЫ — БУСТ & МАТЕРИАЛЫ</b>\n"
        "<i>💡 Подробнее: <code>бот предмет, [ID]</code></i>\n\n"
        "⏩ <b>УСКОРИТЕЛИ ПОХОДА</b> — только из гачи!\n"
        "  📍 Гача · Как использовать: <code>бот ускорить поход</code>\n"
        "▸ <code>exp_boost_1h</code> ⏩ — текущий поход −1 час\n"
        "▸ <code>exp_boost_2h</code> ⏩⏩ — текущий поход −2 часа\n"
        "▸ <code>exp_boost_4h</code> 🚀 — текущий поход −4 часа\n"
        "  💡 Применяется к АКТИВНОЙ экспедиции. Нет похода = не работает!\n\n"
        "🧪 <b>ЗЕЛЬЯ ИГРОКА</b>\n"
        "▸ <code>potion_luck_s</code> 🧪 400🪙 — Зелье Удачи (М)\n"
        "  📍 Магазин · Что делает: следующий спин гачи +15% к ред.+\n"
        "▸ <code>potion_luck_m</code> 🔮 — Зелье Удачи (Б)\n"
        "  📍 Гача/Квесты · Что делает: следующие 3 спина +15% к ред.+\n"
        "▸ <code>potion_sprint</code> ⚡ — Зелье Рывка\n"
        "  📍 Гача/Ивенты · Что делает: след. экспедиция +30% к луту\n\n"
        "💠 <b>МАТЕРИАЛЫ</b>\n"
        "▸ <code>soul_shard</code> 💠 Осколок Души\n"
        "  📍 Гача/распыление питомцев · 5 шт = 🎟 Жетон Призыва (Крафт)\n"
        "▸ <code>star_dust_s</code> 🌟 Звёздная пыль\n"
        "  📍 Гача · Применить: <code>бот зоопарк</code> → +1 дубликат питомцу\n"
        "▸ <code>star_dust_l</code> ✨ Небесная пыль\n"
        "  📍 Гача · Применить: <code>бот зоопарк</code> → +5 дубликатов\n\n"
        "🎯 <b>ПРОЧЕЕ</b>\n"
        "▸ <code>treasure_map</code> 🗺 Карта Сокровищ\n"
        "  📍 Гача · Применяется автоматически → +50% лут в след. походе\n"
        "▸ <code>lucky_charm</code> 🍀 Подкова Удачи\n"
        "  📍 Гача · Применяется авто → +15% шанс ред.+ в след. крутке гачи\n"
        "▸ <code>study_notes</code> 📚 Конспект · 600🪙\n"
        "  📍 Магазин · Применить: <code>бот использовать, study_notes</code> → +50% XP от сообщ. 4ч\n"
        "▸ 🏡 Слоты питомника — покупаются за 💎 в «бот зоопарк» (5/15/30/50💎)"
    ),

    # ── Ивенты ───────────────────────────────────────────────────────────────
    "events": (
        "🎪 <b>ИВЕНТЫ & СОБЫТИЯ</b>\n\n"
        "💰 <b>Сундук активности</b>\n"
        "  Бот автоматически спавнит сундук в чате каждые 4–8 часов.\n"
        "  Написал сообщение = зарегистрирован. До 15 игроков успевают!\n"
        f"  🥇 1 место: {int(_CHEST_POS[1])}🪙 + 🎟 жетон · 🥈 2-е: {int(_CHEST_POS[2])}🪙 + жетон · "
        f"🥉 3-е: {int(_CHEST_POS[3])}🪙 + жетон\n"
        f"  Место 4-15: {int(_CHEST_POS[4])}→{int(_CHEST_POS[15])}🪙 (полная разбивка: «бот ивент») · "
        "Сундук исчезает через 90 сек!\n\n"
        "💱 <b>Обменник валют</b> (постоянный)\n"
        "▸ <code>бот обмен</code> или клик на 🪙/💎 в профиле на сайте\n"
        "  🛒 Покупка: 3 000 🪙 = 1 💎 · 💸 Продажа: 1 💎 = 2 000 🪙\n"
        "  Лимит: 300 💎/день в каждую сторону\n\n"
        "🛒 <b>Акция дня</b>\n"
        "▸ <code>бот акция</code> — 5 лотов со скидкой каждый день\n"
        "  3 лота за 🪙 + 2 за 💎 · Скидки 10–50% · Редкие предметы!\n"
        "  Обновляется в 00:00 UTC · 1 покупка каждого лота в день\n\n"
        "🕵️ <b>Теневой Торговец</b>\n"
        "  Раз в 3 дня бот публикует «зашифрованное пророчество».\n"
        "  Найди ключевое слово в тексте — оно скрыто, не написано прямо!\n"
        "▸ <code>бот слово, [слово]</code> — ответить первым → 5–15 🌑\n"
        "  Первые 3 правильных ответа получают Тёмную Мору!\n\n"
        "🏆 <b>Топ активности месяца</b>\n"
        "  Топ-5 по сообщениям за месяц (нужно 3 000+ сообщений!)\n"
        "  Награда: случайный 🔶 Артефакт · Бот пишет разработчику в ЛС\n\n"
        "🌍 <b>Топ активных чатов</b>\n"
        "  Раз в 2 месяца: топ-3 чата по суммарной активности (4 000+ сообщ.)\n"
        "  Топ-5 игроков каждого чата получают 🔴 Реликвию!\n\n"
        "🎃 <b>Сезонные события</b>\n"
        "  Самайн (октябрь) · Новый год (декабрь) · Карнавал (февраль)\n"
        "  Выдают эксклюзивные сезонные темы профиля 🎭"
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
    b.button(text=label("🎲 Гача & Игры", "gacha"),   callback_data=HelpCallback(tab="gacha",   user_id=user_id))
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
        # Encode chat_id so the mini-app knows which chat it was opened from
        # (used to scope quests/duels/local-top to that chat).
        builder.button(
            text="🔮 Открыть мини-апп",
            url=f"{_MINIAPP_URL}?chat_id={message.chat.id}",
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
    if action.get("type") != "expedition":
        return None
    from core.registry import EXPEDITIONS_DATA
    b = InlineKeyboardBuilder()
    hours = action.get("hours")
    if hours in EXPEDITIONS_DATA:
        cost = EXPEDITIONS_DATA[hours]["cost"]
        cost_s = "бесплатно" if not cost else f"{cost}🪙"
        b.button(text=f"✅ В поход на {hours}ч ({cost_s})",
                 callback_data=AiActionCB(act="exp", hours=hours, user_id=user_id))
    else:
        for h, d in sorted(EXPEDITIONS_DATA.items()):
            cost_s = "бесплатно" if not d["cost"] else f"{d['cost']}🪙"
            b.button(text=f"{h}ч · {cost_s}",
                     callback_data=AiActionCB(act="exp", hours=h, user_id=user_id))
    b.button(text="❌ Отмена", callback_data=AiActionCB(act="cancel", user_id=user_id))
    b.adjust(2, 2, 1)
    return b.as_markup()


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
        # Исполнение — ТОЛЬКО общий движок обычной команды «бот поход»: все
        # проверки (баланс/питомец/занятость/модуль чата) внутри него.
        from bot.handlers.expeditions import _start_expedition_core
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            _ok, text = await _start_expedition_core(
                db, callback_data.user_id, query.message.chat.id, callback_data.hours)
        except Exception as e:
            from loguru import logger
            logger.error(f"AI action expedition error: {e}")
            text = "❌ Не получилось запустить поход, попробуй командой <code>бот поход</code>."
        await query.message.answer(text, parse_mode="HTML")
        return await query.answer()
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
