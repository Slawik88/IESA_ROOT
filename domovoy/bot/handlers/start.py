"""
bot/handlers/start.py — /start, выбор дома, создание дома, deep-link приглашения.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import cb, keyboards as kb
from bot.states import CreateHouse
from bot.util import guard, resolve_house
from core.constants import MAX_HOUSE_NAME_LEN
from core.private_entry import public_url
from infrastructure import repositories as repo
from services import households

router = Router(name="start")

JOIN_PREFIX = "join_"


@router.message(Command("cancel"))
@guard
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено. Можно начать заново через меню.", reply_markup=kb.back_to_menu())


def _menu_text(house) -> str:
    return f"🏠 Дом «{house['name']}»\nЧто делаем?"


def _site_url(house_id: int | None = None) -> str | None:
    url = public_url()
    if url is None or house_id is None:
        return url
    parsed = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "house"]
    return urlunsplit(parsed._replace(query=urlencode([*query, ("house", str(house_id))])))


def _main_menu(can_switch_house: bool, house_id: int | None = None):
    return kb.main_menu(can_switch_house=can_switch_house, web_url=_site_url(house_id))


@router.message(CommandStart())
@guard
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    if message.chat.type != "private":
        await _start_in_group(message, (command.args or "").strip())
        return

    tg_id = message.from_user.id
    await repo.users.upsert_user(tg_id, message.from_user.first_name or "Жилец",
                                 message.from_user.username)

    payload = (command.args or "").strip()
    if payload.startswith(JOIN_PREFIX):
        await _join_by_invite(message, payload[len(JOIN_PREFIX):], state)
        return

    await state.clear()
    house = await resolve_house(tg_id)
    if house is not None:
        await message.answer(_menu_text(house), reply_markup=_main_menu(
            can_switch_house=len(await households.houses_of_user(tg_id)) > 1, house_id=house["id"]))
    elif len(await households.houses_of_user(tg_id)) > 1:
        web_url = public_url()
        await message.answer(
            "У вас несколько домов. Откройте Домового и выберите нужный дом в приложении."
            if web_url else "У вас несколько домов. Выберите, с каким работаем:",
            reply_markup=kb.onboarding(web_url) if web_url else kb.house_selector(
                await households.houses_of_user(tg_id)),
        )
    else:
        await message.answer(
            "Привет! Домовой помогает вести общие деньги и уборку.\n\n"
            "Откройте приложение: там можно создать свой дом или вступить по приглашению. "
            "Дальше все домашние дела будут под рукой.",
            reply_markup=kb.onboarding(public_url()),
        )


async def _start_in_group(message: Message, payload: str = ""):
    """Бот в чате: основные действия — в личке, здесь дом привязывают к чату."""
    if message.from_user is None:
        raise households.DomainError("Подключите группу от своего аккаунта, не от имени канала.")
    if payload:
        match = re.fullmatch(r"house_([1-9][0-9]{0,18})", payload)
        if match is None or int(match[1]).bit_length() > 63:
            raise households.DomainError("Ссылка подключения не распознана. Откройте новую ссылку из нужного дома.")
        house_id = int(match[1])
        await households.require(house_id, message.from_user.id, "manage_house_settings")
        house = await households.get_house(house_id)
        await message.answer(
            f"Подключить этот чат к дому «{house['name']}»?\n"
            "Сюда будут приходить уведомления, для которых жильцы выбрали общий чат.",
            reply_markup=kb.bind_chat_keyboard(house_id),
        )
        return
    house = await resolve_house(message.from_user.id)
    if house is None:
        await message.answer("Сначала создайте дом или войдите в него в личке у бота, "
                             "затем вернитесь сюда, чтобы привязать чат.")
        return
    is_owner = await households.can(house["id"], message.from_user.id, "manage_house_settings")
    text = (f"Этот чат можно привязать к дому «{house['name']}» — уведомления будут приходить сюда."
            if is_owner else
            f"Бот дома «{house['name']}» в этом чате. Основные действия — в личке у бота.")
    await message.answer(text, reply_markup=kb.bind_chat_keyboard() if is_owner else None)


async def _join_by_invite(message: Message, token: str, state: FSMContext):
    house = await households.get_house_by_invite(token)
    if house is None:
        await message.answer("Ссылка-приглашение недействительна: дом не найден. "
                             "Попросите свежую ссылку у владельца дома.")
        return
    await state.clear()
    display_name = message.from_user.first_name or "Жилец"
    added = await households.join_house(house, message.from_user.id, display_name)
    await repo.users.set_active_house(message.from_user.id, house["id"])
    greeting = "Вы вступили в дом" if added else "Вы уже участник дома"
    web_url = _site_url(house["id"])
    await message.answer(
        f"{greeting} «{house['name']}» 🏠\n\n"
        "Откройте приложение — здесь общие деньги, уборка и домашние дела.",
        reply_markup=kb.onboarding(web_url) if web_url else _main_menu(can_switch_house=False, house_id=house["id"]),
    )


@router.callback_query(F.data == cb.menu())
@guard
async def show_menu(cbq: CallbackQuery, state: FSMContext):
    await state.clear()
    house = await resolve_house(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    houses_count = len(await households.houses_of_user(cbq.from_user.id))
    try:
        await cbq.message.edit_text(_menu_text(house),
                                    reply_markup=_main_menu(can_switch_house=houses_count > 1, house_id=house["id"]))
    except Exception:
        await cbq.message.answer(_menu_text(house),
                                 reply_markup=_main_menu(can_switch_house=houses_count > 1, house_id=house["id"]))
    await cbq.answer()


@router.callback_query(F.data == cb.noop())
@guard
async def noop_button(cbq: CallbackQuery):
    """Недоступная кнопка (например, «›» в истории за текущий месяц) — просто снять спиннер."""
    await cbq.answer("Дальше пока ничего нет")


@router.callback_query(F.data == cb.houses_list())
@guard
async def show_houses(cbq: CallbackQuery):
    houses = await households.houses_of_user(cbq.from_user.id)
    await cbq.message.edit_text("Ваши дома:", reply_markup=kb.house_selector(houses))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^house:(\d+)$"))
@guard
async def select_house(cbq: CallbackQuery, state: FSMContext):
    house_id = int(cb.parse(cbq.data)[1])
    membership = await households.membership(house_id, cbq.from_user.id)
    if membership is None or membership["status"] != "active":
        await cbq.answer("Вы не участник этого дома", show_alert=True)
        return
    await repo.users.set_active_house(cbq.from_user.id, house_id)
    await state.clear()
    house = await households.get_house(house_id)
    await cbq.message.edit_text(_menu_text(house),
                                reply_markup=_main_menu(
                                    can_switch_house=len(await households.houses_of_user(cbq.from_user.id)) > 1,
                                    house_id=house["id"]))
    await cbq.answer()


@router.callback_query(F.data == cb.house_create())
@guard
async def start_house_creation(cbq: CallbackQuery, state: FSMContext):
    await state.set_state(CreateHouse.waiting_name)
    await cbq.message.answer(
        f"Как назовём дом? (до {MAX_HOUSE_NAME_LEN} символов)\n"
        "Например: «Квартира на Ленина», «Общага 3 этаж».",
    )
    await cbq.answer()


@router.message(CreateHouse.waiting_name, F.text)
@guard
async def create_house_named(message: Message, state: FSMContext):
    house_id = await households.create_house(
        message.from_user.id, message.from_user.first_name or "Жилец", message.text)
    await repo.users.set_active_house(message.from_user.id, house_id)
    house = await households.get_house(house_id)
    await state.clear()
    me = await message.bot.me()
    link = households.invite_link(house, me.username)
    await message.answer(
        f"Дом «{house['name']}» создан 🏠\n\n"
        f"Дальше два шага:\n"
        f"1. Пригласите жильцов: {link}\n"
        f"2. Настройте график: «Настройки» → или кнопку «График» в меню.\n\n"
        f"Ссылку можно обновить в «Настройки» → «Ссылка-приглашение».",
        reply_markup=_main_menu(can_switch_house=False, house_id=house["id"]),
    )
