"""ADM-02: страж маршрутов админки и модель доступа (без БД).

1) Каждый маршрут /bot-admin/api/* зависит от зарегистрированного стража (`guard`). Тест проверен мутацией:
   маршрут без стража обязан быть пойман.
2) Владелец чата (rank=0, kind="owner") не проходит ни одну проверку сотрудников; чужой чат закрыт; свой открыт.
3) Права ролей: порог ужимается до [FLOOR, CEILING] при чтении, закреплённое не настраивается, выше — монотонно.
4) Исполнители действий вызывают require_chat (иначе обход через внутренние вызовы, как report_punish -> player_action).
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://x/x")
os.environ.setdefault("DEVELOPER_ID", "1001")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import APIRouter, Depends, HTTPException  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from FastAPI.routers import bot_admin  # noqa: E402
from FastAPI.routers.bot_admin import auth, owner, people, reports, switches  # noqa: E402
from services import admin_access as acc  # noqa: E402

PREFIX = "/bot-admin/api"
CREATOR_RANK = 6


def _deps(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _deps(d)


def _routes(router):
    """FastAPI 0.121 включает роутеры лениво: настоящие маршруты лежат внутри original_router."""
    for route in router.routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _routes(inner)
        else:
            yield route


def unguarded(router) -> list[str]:
    out = []
    for route in _routes(router):
        if isinstance(route, APIRoute) and route.path.startswith(PREFIX):
            if not any(getattr(c, "admin_guard", False) for c in _deps(route.dependant)):
                out.append(f"{sorted(route.methods)} {route.path}")
    return out


def raises(fn, code=403):
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == code, exc.status_code
        return
    raise AssertionError("ожидали отказ")


async def check_section_denies_owner():
    owner_p = acc.owner_principal(77, [-100])
    for key in auth.SECTIONS:
        check = auth.section(key)
        try:
            await check(user=owner_p)
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError(f"владелец прошёл раздел {key}")
    try:
        await owner.owner_user("", "", None)
    except HTTPException as exc:
        assert exc.status_code == 401   # без подписи Telegram владелец не опознан
    else:
        raise AssertionError("владелец без подписи не должен пройти")


def main():
    # 1. страж маршрутов + мутация
    found = unguarded(bot_admin.router)
    assert not found, f"маршруты без стража: {found}"
    total = sum(1 for r in _routes(bot_admin.router) if isinstance(r, APIRoute) and r.path.startswith(PREFIX))
    assert total > 40, total
    mutant = APIRouter()

    @mutant.get(PREFIX + "/oops")
    async def oops():
        return {}

    assert unguarded(mutant) == ["['GET'] /bot-admin/api/oops"], "страж не поймал маршрут без проверки"

    @mutant.get(PREFIX + "/ok")
    async def fine(user=Depends(auth.staff_user)):
        return {}

    assert len(unguarded(mutant)) == 1

    # 2. принципалы и область
    asyncio.run(check_section_denies_owner())
    staff, own = acc.staff_principal(5, 4), acc.owner_principal(77, [-100, -200])
    assert acc.is_staff(staff) and not acc.is_staff(own)
    assert not acc.is_staff({"id": 1, "rank": 0}) and not acc.is_staff({"id": 1, "rank": 3, "kind": "owner"})
    acc.require_chat(staff, -999)
    acc.require_chat(own, -100)
    raises(lambda: acc.require_chat(own, -999))
    raises(lambda: acc.require_chat(own, 0))
    raises(lambda: acc.require_chat({"id": 1, "rank": 0, "kind": "owner", "chats": None}, -100))
    raises(lambda: acc.require_chat({"id": 1, "rank": 0}, -100))
    raises(lambda: acc.require_staff(own))

    # 3. права ролей: потолок при чтении, монотонность
    assert acc.effective_min("action:ban", 4, None) == 4
    assert acc.effective_min("action:ban", 4, {"action:ban": 3}) == 3
    assert acc.effective_min("action:ban", 4, {"action:ban": 1}) == acc.FLOOR    # ниже пола — ужато
    assert acc.effective_min("action:ban", 4, {"action:ban": 6}) == acc.CEILING  # создатель не теряет доступ
    assert acc.effective_min("action:balance", 5, {"action:balance": 2}) == 5    # закреплено в коде
    assert acc.effective_min("action:rank", 5, {"action:rank": 2}) == 5
    for g in range(-3, 10):
        t = acc.effective_min("action:ban", 4, {"action:ban": g})
        assert acc.FLOOR <= t <= acc.CEILING
        assert t <= CREATOR_RANK   # создатель (6) всегда проходит любой порог
    fixed = {"action:" + k for k, (_, r, _) in people.ACTIONS.items() if r >= 5}
    assert not (fixed & acc.CONFIGURABLE), fixed & acc.CONFIGURABLE
    assert {"section:broadcast", "section:promo", "section:switches", "section:settings"}.isdisjoint(acc.CONFIGURABLE)
    configurable_actions = {k[7:] for k in acc.CONFIGURABLE if k.startswith("action:")}
    assert configurable_actions <= set(people.ACTIONS), configurable_actions - set(people.ACTIONS)
    assert {k[8:] for k in acc.CONFIGURABLE if k.startswith("section:")} <= set(auth.SECTIONS)

    async def setter(actor, key, rank):
        class DB:
            async def execute(self, *a, **k):
                return None
        try:
            await acc.set_grant(DB(), actor, key, rank)
        except HTTPException as exc:
            return exc.status_code
        return 200
    run = asyncio.run
    assert run(setter(acc.staff_principal(5, 5), "action:ban", 3)) == 403   # разработчик не создатель
    assert run(setter(own, "action:ban", 3)) == 403
    assert run(setter(acc.staff_principal(1, 6), "action:balance", 3)) == 400  # не настраивается
    assert run(setter(acc.staff_principal(1, 6), "action:ban", 1)) == 400      # ниже пола

    # 4. исполнители проверяют область сами
    for fn in (people.player_action, people.chat_action, people.chat_card, people.chat_sanctions, people.players_bulk,
               reports.report_action, reports.report_punish, reports.reports_bulk, switches.get_switches, switches.set_switch,
               owner.owner_chat, owner.owner_chat_action, owner.owner_member_action):
        assert "admin_access.require_" in inspect.getsource(fn), fn.__name__
    print(f"OK: {total} маршрутов под стражем, владелец закрыт от разделов сотрудников, область и потолок прав на месте")


main()
