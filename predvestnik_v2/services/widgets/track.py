"""«Выслеживание» в сообщении (S30c): поиск тайника питомцем на поле 3×3 теми же правилами, что «бот выслеживание».

Тайник прячет и проверяет сервер (services.pets_v2.start_track / open_track_cell): пока поиск открыт, клетка тайника
на устройство не уходит. Две попытки в сутки, три подсказки открыты сразу, остальное — очками внимания питомца.

Состояние: st `n` поиска нет (выбор питомца) · `o` идёт · `w` найдено · `l` не нашли · c 9 клеток (`?` закрыта, `w` тепло,
`c` холодно, `f` тайник, `h` тайник, который не нашли) · i поиск · pt очки внимания · a попыток сегодня ·
n питомец · p [[номер, «значок имя»], …] питомцы для нового поиска · o итог.
"""
from __future__ import annotations

from types import SimpleNamespace

from core import pets_v2 as pet_rules
from services.widgets import Refused, Reply

HEAT = {"warm": "w", "cold": "c", "found": "f"}
MAX_PETS = 6           # кнопок выбора питомца в виджете; остальные — «бот выслеживание»

SAMPLE = {"st": "w", "c": "cwc?fw?cw", "i": "f" * 32, "pt": 5, "a": 1, "n": "🦉 Совушка Полуночная",
          "p": [[123456, "🦊 Рыжик Огненнохвостый"]] * MAX_PETS,
          "o": "🎁 Тайник найден: Мора +60, Алмазы +1, Эссенция +4, Лакомства +2."}


async def _open(db, user_id: int) -> bool:
    from bot.chat import pets as pets_chat
    return await pets_chat.available(db, user_id, SimpleNamespace(type="private", id=int(user_id)), {"screen": "track"})


async def _today(db, user_id: int) -> tuple[list[dict], dict | None]:
    from infrastructure.repositories import pets_v2 as repo
    day = (await repo.clock(db))["day"]
    tracks = await repo.tracks_today(db, user_id, day, lock=False)
    return tracks, (tracks[-1] if tracks else None)


async def _pets(db, user_id: int) -> tuple[list[list], dict]:
    from bot.chat.pet_menu import name
    from core.chests_v1 import PET_SPECIES
    from infrastructure.repositories import pets_v2 as repo
    owned = [p for p in await repo.list_owned_pets(db, user_id) if p.get("species_id") in pet_rules.SPECIES]
    labels = {int(p["id"]): f"{PET_SPECIES.get(p['species_id'], {}).get('icon', '🐾')} {name(p)}"[:40] for p in owned}
    return [[pid, label] for pid, label in list(labels.items())[:MAX_PETS]], labels


def _cells(track: dict) -> str:
    opened = {int(o["cell"]): HEAT.get(o["heat"], "?") for o in track["opened"]}
    cells = [opened.get(cell, "?") for cell in range(9)]
    if track["status"] == "lost" and track.get("hidden") is not None and cells[int(track["hidden"])] == "?":
        cells[int(track["hidden"])] = "h"
    return "".join(cells)


def _finds(result: dict | None) -> str:
    names = {"mora": "Мора", "diamond": "Алмазы", "essence": "Эссенция", "treat": "Лакомства", "talisman": "Талисманы"}
    found = [f"{names.get(k, k)} +{v}" for k, v in ((result or {}).get("finds") or {}).items() if v]
    return "🎁 Тайник найден" + (": " + ", ".join(found) if found else ", но сегодня находок больше не положено") + "."


async def state(db, user_id: int, view: str | None) -> dict:   # noqa: ARG001 — экран один
    if not await _open(db, user_id):
        return {"st": "n", "a": 0, "o": "Выслеживание сейчас недоступно."}
    tracks, last = await _today(db, user_id)
    left = max(0, pet_rules.TRACK_DAILY - len(tracks))
    choices, labels = await _pets(db, user_id)
    if last is None:   # законченный поиск остаётся на экране до следующего: итог виден и после перезапуска Telegram
        return {"st": "n", "a": left, "p": choices if left else []}
    out = {"st": {"open": "o", "won": "w", "lost": "l"}.get(last["status"], "n"), "c": _cells(last), "i": last["id"],
           "pt": int(last["points"]), "a": left, "n": labels.get(int(last["pet_id"]), "🐾")}
    if out["st"] != "o" and left:
        out["p"] = choices
    return out


async def act(db, user_id: int, verb: str, args: list[str], *, action_id: str) -> Reply:
    from services import pets_v2
    if not await _open(db, user_id):
        raise Refused("Выслеживание сейчас недоступно.")
    try:
        if verb == "b" and len(args) == 1 and args[0].isascii() and args[0].isdigit():
            await pets_v2.start_track(db, user_id=user_id, pet_id=int(args[0]), action_id=action_id)
            return Reply({**await state(db, user_id, None), "o": "Подсказки открыты: ♨ — тайник рядом, ❄ — дальше."}, persist=True)
        if verb == "o" and len(args) == 2 and len(args[0]) == 32 and args[1] in tuple("012345678"):
            # тот же поиск и та же клетка — одна квитанция: повтор после обрыва связи не тратит второе очко
            result = await pets_v2.open_track_cell(db, user_id=user_id, track_id=args[0], cell=int(args[1]),
                                                   action_id=f"widget:track:{args[0]}:{args[1]}")
            track = result["track"]
            outcome = (_finds(track.get("result")) if track["status"] == "won"
                       else "Очки внимания кончились — тайник был там, где 🎁." if track["status"] == "lost" else "")
            return Reply({**await state(db, user_id, None), **({"o": outcome} if outcome else {})}, persist=True)
    except (pets_v2.PetV2Conflict, pet_rules.PetV2PolicyError) as exc:
        raise Refused(str(exc)[:200]) from exc
    raise Refused("Этот виджет устарел. Напиши «выслеживание», чтобы получить новый.")
