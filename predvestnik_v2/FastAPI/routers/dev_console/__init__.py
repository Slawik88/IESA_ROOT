"""FastAPI/routers/dev_console — консоль разработчика, разбита на под-роутеры по доменам.

main.py импортирует `dev_console.router` как раньше — пакет реэкспортирует его.
"""
from fastapi import APIRouter
from . import player, vip, system, bp, broadcast, sql, themes, metrics, promocodes, twins

router = APIRouter(prefix="/admin/dev", tags=["dev_console"])
for _m in (player, vip, system, bp, broadcast, sql, themes, metrics, promocodes, twins):
    router.include_router(_m.router)
