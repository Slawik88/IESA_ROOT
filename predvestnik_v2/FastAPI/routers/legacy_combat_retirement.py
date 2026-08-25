"""Explicit, non-mutating compatibility boundary for retired combat URLs."""
from fastapi import APIRouter, HTTPException


router = APIRouter(tags=["legacy-combat-retirement"])

_MESSAGE = (
    "Старая боёвка закрыта. Врата, Рейды и Казарма заменены Разломом колокола; "
    "исторические данные сохранены для безопасного перехода."
)


def _closed() -> None:
    raise HTTPException(status_code=410, detail=_MESSAGE)


@router.api_route(
    "/combat2/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    include_in_schema=False,
)
async def retired_combat2(path: str):
    del path
    _closed()


@router.api_route(
    "/combat2",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    include_in_schema=False,
)
async def retired_combat2_root():
    _closed()


@router.api_route(
    "/combat/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    include_in_schema=False,
)
async def retired_combat(path: str):
    del path
    _closed()


@router.api_route(
    "/combat",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    include_in_schema=False,
)
async def retired_combat_root():
    _closed()
