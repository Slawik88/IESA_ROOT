"""Closed compatibility surface for the retired grid-combat clan modes.

Base clans remain available through ``/clans``. Their membership and ownership
data are not changed here. Cooperative play now starts in Reconstruction's
Alliance; projects and competition unlock only after the audience gates from
the approved economy plan are met.

Keeping explicit 410 responses is intentional: an old Mini App tab or Telegram
message gets a truthful explanation instead of a 404 or, worse, an old reward
writer.
"""

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/clans2", tags=["clans-transition"])

_MESSAGE = (
    "Старая клановая Бездна, здания за осколки и войны на клеточном поле закрыты. "
    "Клан и его участники сохранены; общий Союз доступен в Разломе."
)


def _closed() -> None:
    raise HTTPException(status_code=410, detail=_MESSAGE)


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def retired_clan_mode(path: str):
    del path
    _closed()


@router.api_route(
    "",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def retired_clan_mode_root():
    _closed()
