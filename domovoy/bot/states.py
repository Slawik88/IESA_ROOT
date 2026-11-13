"""
bot/states.py — состояния диалогов (FSM).
"""
from aiogram.fsm.state import State, StatesGroup


class CreateHouse(StatesGroup):
    waiting_name = State()


class CategoryAdd(StatesGroup):
    waiting_name = State()


class TransactionForm(StatesGroup):
    amount = State()
    review = State()
    date = State()
    month = State()
    category = State()
    description = State()
    photos = State()


class MoneyTransfer(StatesGroup):
    waiting_file = State()
    review = State()
    export_month = State()
