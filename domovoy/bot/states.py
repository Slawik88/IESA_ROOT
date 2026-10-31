"""
bot/states.py — состояния диалогов (FSM).
"""
from aiogram.fsm.state import State, StatesGroup


class CreateHouse(StatesGroup):
    waiting_name = State()


class Contribution(StatesGroup):
    waiting_amount = State()


class Expense(StatesGroup):
    waiting_amount = State()
    choosing_category = State()
    choosing_mode = State()
    waiting_photos = State()
    waiting_description = State()


class CategoryAdd(StatesGroup):
    waiting_name = State()
