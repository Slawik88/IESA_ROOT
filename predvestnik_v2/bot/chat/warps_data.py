"""Все варп-команды одним списком. Новый набор — файл в warp_texts/ и строка здесь."""
from bot.chat.warp_texts import actions, adult, conflict, playful, warm

WARPS = warm.WARPS + playful.WARPS + actions.WARPS + conflict.WARPS + adult.WARPS
