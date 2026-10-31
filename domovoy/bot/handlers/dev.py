"""
bot/handlers/dev.py — служебные команды разработчика (скрытый супер-доступ).

Не афишируются в справке и меню; доступны только tg_id из
DOMOVOY_SUPERADMIN_TG_IDS. Для всех остальных команды не существуют.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.util import guard
from core import config
from services import households, money

router = Router(name="dev")


def _is_superadmin(message: Message) -> bool:
    return config.is_superadmin(message.from_user.id)


@router.message(Command("dev_houses"))
@guard
async def dev_houses(message: Message):
    if not _is_superadmin(message):
        return
    houses = await households.houses_of_user(message.from_user.id)
    lines = ["Ваши дома:"] if houses else ["Домов нет"]
    for house in houses:
        members = await households.members(house["id"])
        balance = await money.pot_balance(house["id"])
        lines.append(f"  id={house['id']} «{house['name']}» ({house['role']}): "
                     f"участников {len(members)}, баланс {balance['balance']} коп.")
    await message.answer("\n".join(lines))


@router.message(Command("dev_start"))
@guard
async def dev_start(message: Message):
    """Диагностика: бот жив, супер-доступ активен."""
    if not _is_superadmin(message):
        return
    ids = ",".join(str(i) for i in sorted(config.superadmin_tg_ids()))
    await message.answer(f"🛠 Супер-доступ активен ({ids}). Команды: /dev_houses")
