"""Новая админка бота: страница /bot-admin и её API /bot-admin/api/*.

Вход — тот же, что у мини-приложения (initData из Telegram или сессия Login Widget),
но без «сайт закрыт для игроков»: персонал работает и при закрытом сайте.
Доступ к разделу — по глобальной роли в боте (bot/chat/global_ranks.py).
"""
from __future__ import annotations

from fastapi import APIRouter

from FastAPI.routers.bot_admin import access, avatars, broadcasts, health, journal, metrics, owner, page, people, promo, reports, settings, switches, patch_notes
from FastAPI.routers.bot_admin.auth import router as auth_router
from FastAPI.routers.bot_admin import mafia_online

router = APIRouter()
router.include_router(page.router)
router.include_router(avatars.router)
router.include_router(auth_router)
router.include_router(people.router)
router.include_router(owner.router)
router.include_router(access.router)
router.include_router(reports.router)
router.include_router(mafia_online.router)
router.include_router(metrics.router)
router.include_router(journal.router)
router.include_router(broadcasts.router)
router.include_router(patch_notes.router)
router.include_router(health.router)
router.include_router(promo.router)
router.include_router(switches.router)
router.include_router(settings.router)
site_gate = switches.site_gate
