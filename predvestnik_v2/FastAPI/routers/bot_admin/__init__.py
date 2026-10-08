"""Новая админка бота: страница /bot-admin и её API /bot-admin/api/*.

Вход — тот же, что у мини-приложения (initData из Telegram или сессия Login Widget),
но без «сайт закрыт для игроков»: персонал работает и при закрытом сайте.
Доступ к разделу — по глобальной роли в боте (bot/chat/global_ranks.py).
"""
from __future__ import annotations

from fastapi import APIRouter

from FastAPI.routers.bot_admin import page, promo, settings, switches
from FastAPI.routers.bot_admin.auth import router as auth_router

router = APIRouter()
router.include_router(page.router)
router.include_router(auth_router)
router.include_router(promo.router)
router.include_router(switches.router)
router.include_router(settings.router)
site_gate = switches.site_gate
