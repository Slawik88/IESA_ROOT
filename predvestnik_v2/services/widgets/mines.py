"""«Сапёр» в сообщении (S30b): та же серверная партия, что в мини-приложении (services.minesweeper_v2).

Мины на устройство не уходят: виджет получает только открытые клетки, каждый ход проверяет сервер. Партия у игрока
одна на оба окна — открытую в приложении можно доиграть в чате и наоборот. Опыт Пропуска, задания и таблица
лидеров начисляются сервисом при победе так же, как в приложении. Флажки живут только на устройстве: на итог
партии они не влияют, а лишний запрос съел бы лимит Telegram (5 запросов за 5 секунд).

Состояние: z сторона поля · b поле (`#` закрыто, `0–8` открыто, `*` мина после проигрыша) · c мин · st статус
(`n` партии нет, `f` ждёт первого хода, `a` идёт, `w` победа, `l` проигрыш) · v ревизия · t прошло мс · x метка партии
(ключ флажков на устройстве) · n подпись сложности · p кнопки новой партии. Поле `e` занято отказом (core.widgets.error).
"""
from __future__ import annotations

from core import league_pass as pass_rules
from core import minesweeper_v2 as game_rules
from services.widgets import Refused, Reply

STATUS = {"awaiting_first_open": "f", "active": "a", "won": "w", "lost": "l", "cancelled": "n"}
SHOW_FINISHED_SEC = 6 * 3600     # законченную партию виджет показывает ещё столько, потом — выбор сложности
PICKER = [[d.id, f"{d.label} · {d.size}×{d.size}, мин: {d.mines}"] for d in game_rules.DIFFICULTIES.values()]

SAMPLE = {
    "z": 9, "b": "#" * 40 + "012345678" * 4 + "*" * 5, "c": 18, "st": "l", "v": 999, "t": 3_599_000,
    "x": "0123456789ab", "n": "Сложный · 9×9, мин: 18", "p": PICKER,
    "o": "💥 Мина! Партия окончена. Сыграй ещё — опыт Пропуска даётся за победу.",
}


async def available(db) -> bool:
    """Сапёр закрыт в админке («Глобальные модули» или выключатель сайта «Сапёр») — закрыт и в чате."""
    from infrastructure.repositories import system_flags
    from services import feature_switches
    return (await system_flags.is_enabled(db, "game_minesweeper_v2")
            and await feature_switches.disabled(db, ["all", "site:minesweeper"], None) is None)


async def _latest(db, user_id: int) -> dict | None:
    from infrastructure.repositories import minesweeper_v2 as repo
    await repo.ensure_tables(db)
    async with db.execute(
        "SELECT run_id FROM minesweeper_v2_runs WHERE user_id = ? AND (status IN ('awaiting_first_open','active') "
        "OR (status IN ('won','lost') AND finished_at > NOW() - make_interval(secs => ?))) "
        "ORDER BY (status IN ('awaiting_first_open','active')) DESC, created_at DESC LIMIT 1",
        (int(user_id), SHOW_FINISHED_SEC),
    ) as c:
        row = await c.fetchone()
    if row is None:
        return None
    from services import minesweeper_v2 as game
    return await game.current_run(db, user_id=user_id, run_id=row[0])


def _board(run: dict) -> str:
    size = int(run["size"])
    adjacent = {c["cell"]: c["adjacent"] for c in run.get("changed", [])}
    mines = set(run.get("mines") or ())
    cells = []
    for cell in range(size * size):
        if cell in mines:
            cells.append("*")
        elif cell in adjacent:
            cells.append(str(adjacent[cell]))
        else:
            cells.append("#")
    return "".join(cells)


def _view(run: dict | None, outcome: str = "") -> dict:
    if run is None:
        return {"st": "n", "p": PICKER, **({"o": outcome} if outcome else {})}
    spec = game_rules.difficulty(run["difficulty"])
    out = {"z": spec.size, "b": _board(run), "c": spec.mines, "st": STATUS.get(run["status"], "n"),
           "v": int(run["revision"]), "t": int(run.get("elapsed_ms") or 0), "x": str(run["run_id"])[:12],
           "n": f"{spec.label} · {spec.size}×{spec.size}"}
    if out["st"] not in ("a", "f"):
        out["p"] = PICKER
    if outcome:
        out["o"] = outcome
    return out


def _finish_text(run: dict) -> str:
    if run["status"] == "won":
        seconds = int(run.get("elapsed_ms") or 0) // 1000
        xp = pass_rules.MINES_WIN_XP.get(run["difficulty"], 0)
        return (f"🏆 Победа за {seconds // 60}:{seconds % 60:02d}! До +{xp} опыта Пропуска "
                f"(за игры — не больше {pass_rules.CASUAL_DAILY_CAP} в день).")
    if run["status"] == "lost":
        return "💥 Мина! Партия окончена. Сыграй ещё — опыт Пропуска даётся за победу."
    return ""


async def state(db, user_id: int, view: str | None) -> dict:   # noqa: ARG001 — экран у Сапёра один
    if not await available(db):
        return {"st": "n", "o": "Сапёр сейчас закрыт."}
    return _view(await _latest(db, user_id))


async def act(db, user_id: int, verb: str, args: list[str], *, action_id: str) -> Reply:
    from services import minesweeper_v2 as game
    if not await available(db):
        raise Refused("Сапёр сейчас закрыт.")
    if verb == "n" and len(args) == 1 and args[0] in game_rules.DIFFICULTIES:
        try:
            run = await game.start_run(db, user_id=user_id, difficulty=args[0])
        except game.MinesweeperError as exc:
            raise Refused("Не получилось начать партию. Попробуй ещё раз.") from exc
        return Reply(_view(run, "Открой любую клетку: первая всегда безопасна."), persist=True)
    if verb == "o" and len(args) == 3 and all(a.isascii() and a.isdigit() and len(a) <= 6 for a in args[1:]):
        return await _open_cell(db, user_id, args[0], int(args[1]), int(args[2]), action_id)
    raise Refused("Этот виджет устарел. Напиши «сапёр», чтобы получить новый.")


async def _open_cell(db, user_id: int, mark: str, cell: int, revision: int, action_id: str) -> Reply:
    """Ход в партию, которую виджет показывает (`mark` — метка `x`): ревизии у разных партий совпадают, и без метки
    нажатие в старом сообщении ушло бы вслепую в новую партию, начатую в приложении."""
    from services import minesweeper_v2 as game
    current = await _latest(db, user_id)
    if current is None or current["status"] not in ("awaiting_first_open", "active"):
        return Reply(_view(current, "Эта партия уже закончилась. Выбери сложность."))
    if str(current["run_id"])[:12] != mark:
        return Reply(_view(current, "Поле обновилось — посмотри и ходи снова."))
    if cell >= int(current["size"]) ** 2:
        raise Refused("Такой клетки нет.")
    from infrastructure.repositories import minesweeper_v2 as repo
    from services.local_games import PACKET_ID
    if await repo.action(db, run_id=current["run_id"], action_id=PACKET_ID):
        raise Refused("Эту партию ты играешь в приложении без сети — доиграй её там или начни новую.")
    try:
        result = await game.act(db, user_id=user_id, run_id=current["run_id"], action_id=action_id,
                                expected_revision=revision, kind="open", cell=cell)
    except game.MinesweeperConflict:
        # ход из старого вида поля (партию двигали в приложении или ответ потерялся) — показываем, как есть сейчас
        return Reply(_view(await _latest(db, user_id), "Поле обновилось — посмотри и ходи снова."))
    except game.MinesweeperError as exc:
        raise Refused("Этот ход не получился. Попробуй другую клетку.") from exc
    # в ответе хода только новые клетки, а виджету нужно всё поле
    run = await game.current_run(db, user_id=user_id, run_id=result["run_id"])
    finished = run["status"] in ("won", "lost")
    return Reply(_view(run, _finish_text(run)), persist=finished)
