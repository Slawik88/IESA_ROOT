"""Семья: один брак на все чаты, до 6 детей, роли, общий кошелёк, развод, родословная.

Поколения: у игрока может быть свой брак (он родитель) и одна родительская семья
(он ребёнок) одновременно, поэтому дети заводят свои семьи, а их дети — свои.
Внутри рода (предки, потомки, братья и сёстры, супруг) браки и усыновления запрещены.
Развод закрывает только брак этой пары: её дети выходят из семьи, их браки и внуки остаются.

Источник правды о браке — marriage_members (один брак на аккаунт), те же
таблицы читает Mini App. Старые браки, где у игрока их было несколько:
семьёй считается самый ранний, остальные строки в БД не трогаются
(решение владельца, 2026-10). Развод — только после ввода случайной фразы.
"""
from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, field
from datetime import datetime

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from core.economy_contract import EconomyContractError, InsufficientBalance
from infrastructure.repositories import divorce_v1, family_wallet_v1
from infrastructure.repositories.marriages import MarriageConflict, create_marriage, create_proposal
from bot.chat import settings
from bot.chat.settings import CURRENCY_VIEW
from bot.chat.framework import Ctx, UsageError, norm, registry
from bot.chat.targets import resolve_target
from bot.chat.transfer import fmt, parse_amount
from bot.chat.tracking import local_now
from bot.chat.style import quote

router = Router(name="chat_family")

MAX_CHILDREN = 6
PARENT_ROLES = ("супруг", "супруга", "муж", "жена")
CHILD_ROLES = ("ребёнок", "сын", "дочь")
WALLET_CURRENCIES = ("mora", "diamonds", "dark_mora", "zarniki", "essence")   # колонки семейного кошелька
WALLET_BUTTONS = ("mora", "diamonds", "essence", "zarniki")          # тёмная мора — легаси, только вывод
BACKFILL_KEY = "family_registry_backfill_v1"

STATEMENTS = (
    "ALTER TABLE marriages ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ NULL",
    # Реестр «один брак на аккаунт» (та же схема, что у операторской миграции).
    """CREATE TABLE IF NOT EXISTS marriage_members (
        user_id     BIGINT PRIMARY KEY,
        marriage_id INTEGER NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (marriage_id, user_id)
    )""",
    # Дети семьи. Строка не удаляется: уход из семьи — отметка left_at.
    """CREATE TABLE IF NOT EXISTS family_children (
        id          BIGSERIAL PRIMARY KEY,
        marriage_id INTEGER NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
        user_id     BIGINT NOT NULL,
        role        TEXT NOT NULL DEFAULT 'ребёнок',
        added_by    BIGINT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        left_at     TIMESTAMPTZ NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_family_children_active ON family_children (marriage_id) WHERE left_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_family_children_user ON family_children (user_id) WHERE left_at IS NULL",
    # Роль родителя в семье (муж/жена/…); у детей роль в family_children.
    """CREATE TABLE IF NOT EXISTS family_roles (
        user_id     BIGINT  NOT NULL,
        marriage_id INTEGER NOT NULL,
        role        TEXT    NOT NULL,
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (user_id, marriage_id)
    )""",
)


async def ensure_family_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)
    await _backfill_registry(db)
    await _ensure_wallet(db)


async def _backfill_registry(db) -> None:
    """Один раз: заполнить реестр из старых браков. Идём от самого раннего;
    брак попадает в реестр, только если оба игрока ещё свободны."""
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(7710301)")
        if await settings.get_json(db, BACKFILL_KEY, None):
            return
        async with db.execute("SELECT user_id FROM marriage_members") as cur:
            taken = {int(r[0]) for r in await cur.fetchall()}
        async with db.execute(
            "SELECT id, user1_id, user2_id FROM marriages WHERE ended_at IS NULL "
            "AND user1_id IS NOT NULL AND user2_id IS NOT NULL AND user1_id <> user2_id "
            "AND id NOT IN (SELECT marriage_id FROM marriage_members) "
            "ORDER BY marriage_date ASC NULLS LAST, id ASC"
        ) as cur:
            rows = await cur.fetchall()
        added = skipped = 0
        for mid, u1, u2 in rows:
            u1, u2 = int(u1), int(u2)
            if u1 in taken or u2 in taken:
                skipped += 1
                continue
            await db.execute("INSERT INTO marriage_members (user_id, marriage_id) VALUES (?, ?), (?, ?)",
                             (u1, mid, u2, mid))
            taken |= {u1, u2}
            added += 1
        await settings.set_json(db, BACKFILL_KEY, {"added": added, "skipped": skipped}, 0)
    logger.info(f"family registry backfill: {added} families, {skipped} later duplicates left as is")


async def _ensure_wallet(db) -> None:
    try:
        async with db.connection.transaction():
            await db.execute("SELECT pg_advisory_xact_lock(7710302)")
            if not await wallet_ready(db):
                await family_wallet_v1.install_family_wallet_schema(db, registry_resolves_duplicates=True)
            else:
                await family_wallet_v1.ensure_essence_custody(db)
    except Exception as exc:   # кошелёк не должен ронять запуск бота
        logger.warning(f"family wallet unavailable: {exc}")


async def wallet_ready(db) -> bool:
    async with db.execute("SELECT to_regclass('family_wallet_telegram_intents') IS NOT NULL") as cur:
        return bool((await cur.fetchone())[0])


# ── Чтение семьи ──────────────────────────────────────────────────────────────

@dataclass
class Family:
    marriage_id: int
    parents: list[int]
    since: datetime | None
    children: list[tuple[int, str]] = field(default_factory=list)
    roles: dict[int, str] = field(default_factory=dict)

    @property
    def members(self) -> list[int]:
        return self.parents + [c for c, _ in self.children]

    def is_parent(self, uid: int) -> bool:
        return uid in self.parents

    def partner_of(self, uid: int) -> int | None:
        others = [p for p in self.parents if p != uid]
        return others[0] if others else None


async def family_id_of(db, uid: int) -> tuple[int, bool] | None:
    """(marriage_id, родитель ли) или None."""
    async with db.execute(
        "SELECT mm.marriage_id FROM marriage_members mm JOIN marriages m ON m.id = mm.marriage_id "
        "WHERE mm.user_id = ? AND m.ended_at IS NULL", (uid,)) as cur:
        row = await cur.fetchone()
    if row:
        return int(row[0]), True
    async with db.execute(
        "SELECT c.marriage_id FROM family_children c JOIN marriages m ON m.id = c.marriage_id "
        "WHERE c.user_id = ? AND c.left_at IS NULL AND m.ended_at IS NULL "
        "ORDER BY c.created_at LIMIT 1", (uid,)) as cur:
        row = await cur.fetchone()
    return (int(row[0]), False) if row else None


async def spouse_family_id(db, uid: int) -> int | None:
    """Свой брак игрока (он в нём родитель)."""
    async with db.execute(
        "SELECT mm.marriage_id FROM marriage_members mm JOIN marriages m ON m.id = mm.marriage_id "
        "WHERE mm.user_id = ? AND m.ended_at IS NULL", (uid,)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else None


async def parent_family_id(db, uid: int) -> int | None:
    """Семья, где игрок — ребёнок."""
    async with db.execute(
        "SELECT c.marriage_id FROM family_children c JOIN marriages m ON m.id = c.marriage_id "
        "WHERE c.user_id = ? AND c.left_at IS NULL AND m.ended_at IS NULL "
        "ORDER BY c.created_at LIMIT 1", (uid,)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else None


async def _parents_of(db, uid: int) -> list[int]:
    async with db.execute(
        "SELECT m.user1_id, m.user2_id FROM family_children c JOIN marriages m ON m.id = c.marriage_id "
        "WHERE c.user_id = ? AND c.left_at IS NULL AND m.ended_at IS NULL "
        "ORDER BY c.created_at LIMIT 1", (uid,)) as cur:
        row = await cur.fetchone()
    return [int(row[0]), int(row[1])] if row else []


async def _children_of(db, uid: int) -> list[int]:
    async with db.execute(
        "SELECT c.user_id FROM marriage_members mm JOIN marriages m ON m.id = mm.marriage_id "
        "JOIN family_children c ON c.marriage_id = m.id AND c.left_at IS NULL "
        "WHERE mm.user_id = ? AND m.ended_at IS NULL ORDER BY c.created_at", (uid,)) as cur:
        return [int(r[0]) for r in await cur.fetchall()]


async def _walk(db, start: list[int], step, limit: int = 300) -> set[int]:
    seen: set[int] = set()
    todo = list(start)
    while todo and len(seen) < limit:
        uid = todo.pop()
        if uid in seen:
            continue
        seen.add(uid)
        todo.extend(await step(db, uid))
    return seen


async def kin(db, uid: int) -> set[int]:
    """Род игрока: он сам, супруг, предки, потомки, братья и сёстры."""
    out = {uid}
    parents = await _parents_of(db, uid)
    out |= await _walk(db, parents, _parents_of)
    out |= await _walk(db, await _children_of(db, uid), _children_of)
    for p in parents:
        out |= set(await _children_of(db, p))
    fid = await spouse_family_id(db, uid)
    if fid:
        fam = await load_family(db, fid)
        if fam:
            out |= set(fam.parents)
    return out


async def load_family(db, marriage_id: int) -> Family | None:
    async with db.execute(
        "SELECT user1_id, user2_id, marriage_date FROM marriages WHERE id = ? AND ended_at IS NULL",
        (marriage_id,)) as cur:
        m = await cur.fetchone()
    if not m:
        return None
    fam = Family(marriage_id, [int(m[0]), int(m[1])], m[2])
    async with db.execute(
        "SELECT user_id, role FROM family_children WHERE marriage_id = ? AND left_at IS NULL ORDER BY created_at",
        (marriage_id,)) as cur:
        fam.children = [(int(r[0]), r[1]) for r in await cur.fetchall()]
    async with db.execute("SELECT user_id, role FROM family_roles WHERE marriage_id = ?", (marriage_id,)) as cur:
        fam.roles = {int(r[0]): r[1] for r in await cur.fetchall()}
    fam.roles.update(dict(fam.children))
    return fam


async def family_of(db, uid: int) -> Family | None:
    found = await family_id_of(db, uid)
    return await load_family(db, found[0]) if found else None


async def labels(db, ids) -> dict[int, str]:
    """Имена без пинга: «@​ник» (с нулевым пробелом) или id."""
    ids = list(dict.fromkeys(int(i) for i in ids))
    out = {i: f"id{i}" for i in ids}
    if ids:
        marks = ", ".join("?" for _ in ids)
        async with db.execute(
            f"SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id IN ({marks})", tuple(ids)) as cur:
            for uid, uname in await cur.fetchall():
                if uname:
                    out[int(uid)] = f"@​{uname}"
    return {k: html.escape(v) for k, v in out.items()}


async def plain_names(db, ids) -> dict[int, str]:
    """Имена для записи в marriages.userN_name (их показывает Mini App)."""
    out = {int(i): f"id{i}" for i in ids}
    for uid in out:
        async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (uid,)) as cur:
            row = await cur.fetchone()
        if row and row[0]:
            out[uid] = row[0]
    return out


def ping(uid: int, name: str) -> str:
    return f'<a href="tg://user?id={uid}">{html.escape(name or "игрок")}</a>'


async def wallet_balances(db, marriage_id: int) -> dict[str, float]:
    if await wallet_ready(db):
        sql = f"SELECT {', '.join(WALLET_CURRENCIES)} FROM family_wallet_balances WHERE marriage_id = ?"
    else:
        sql = ("SELECT family_balance, family_balance_diamonds, family_balance_dark_mora, "
               "family_balance_zarniki, 0 FROM marriages WHERE id = ?")
    async with db.execute(sql, (marriage_id,)) as cur:
        row = await cur.fetchone()
    return {c: float(row[i] or 0) if row else 0.0 for i, c in enumerate(WALLET_CURRENCIES)}


def days_together(since: datetime | None) -> int | None:
    return (local_now().date() - since.date()).days if since else None


# СТИЛЬ v1 (оформлено, см. docs/CHAT_BOT_DESIGN_HANDOFF.md): родители, дети и кошелёк в цитатах, ники без пинга.
async def card(db, fam: Family) -> str:
    names = await labels(db, fam.members)
    lines = ["💞 <b>Семья</b>"]
    if fam.since:
        days = days_together(fam.since)
        lines.append(f"Вместе с {fam.since.strftime('%d.%m.%Y')} · {days} дн.")
    lines.append("\n👫 <b>Родители</b>")
    lines.append(quote([f"{names[p]} — <i>{fam.roles.get(p, 'супруг(а)')}</i>" for p in fam.parents]))
    lines.append(f"\n👶 <b>Дети</b> · {len(fam.children)}/{MAX_CHILDREN}")
    if fam.children:
        lines.append(quote([f"{names[c]} — <i>{role}</i>" for c, role in fam.children]))
    else:
        lines.append("Пока нет. Позвать: <code>бот усыновить, @ник</code>")
    bal = await wallet_balances(db, fam.marriage_id)
    shown = [c for c in WALLET_CURRENCIES if c in WALLET_BUTTONS or bal[c]]
    lines.append("\n🏦 <b>Общий кошелёк</b>")
    lines.append(quote([f"{CURRENCY_VIEW[c].icon} {CURRENCY_VIEW[c].label}: <b>{fmt_amount(bal[c], CURRENCY_VIEW[c].display_decimals)}</b>" for c in shown]))
    return "\n".join(lines)


def fmt_amount(v: float, decimals: int) -> str:
    s = f"{v:,.{decimals}f}".replace(",", " ")
    return s.rstrip("0").rstrip(".") if decimals else s


# ── Брак ──────────────────────────────────────────────────────────────────────

class ProposalCB(CallbackData, prefix="fp"):
    pid: int
    act: str   # y — да, n — нет, x — отозвать


@registry.command("брак", aliases=("пожениться", "свадьба", "предложение"), usage="бот брак, @ник",
                  section="family", summary="Сделать предложение. Брак один на все чаты.",
                  example="бот брак, @ник")
async def cmd_propose(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is None:
        raise UsageError("бот брак, @ник  (или ответом на сообщение)")
    if target.user_id == ctx.user_id:
        await ctx.reply("🙃 Жениться на себе пока нельзя.")
        return
    for uid, who in ((ctx.user_id, "Вы уже"), (target.user_id, f"{html.escape(target.label())} уже")):
        if await spouse_family_id(ctx.db, uid):
            await ctx.reply(f"💍 {who} в браке.")
            return
    if target.user_id in await kin(ctx.db, ctx.user_id):
        await ctx.reply("💍 Нельзя: вы из одного рода (родители, дети, братья и сёстры).")
        return
    pid = await create_proposal(ctx.db, ctx.message.chat.id, ctx.user_id, target.user_id)
    u = ctx.message.from_user
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💍 Да", callback_data=ProposalCB(pid=pid, act="y").pack()),
         InlineKeyboardButton(text="💔 Нет", callback_data=ProposalCB(pid=pid, act="n").pack())],
        [InlineKeyboardButton(text="✖️ Отозвать", callback_data=ProposalCB(pid=pid, act="x").pack())],
    ])
    await ctx.reply(f"💍 {ping(u.id, u.first_name)} делает предложение {ping(target.user_id, target.name.lstrip('@'))}!\n"
                    "Ответить может только тот, кому предложили. Предложение действует сутки.", reply_markup=kb)


@router.callback_query(ProposalCB.filter())
async def on_proposal(call: CallbackQuery, callback_data: ProposalCB, db) -> None:
    async with db.execute(
        "SELECT chat_id, proposer_id, target_id, status, expires_at > NOW() FROM marriage_proposals WHERE id = ?",
        (callback_data.pid,)) as cur:
        p = await cur.fetchone()
    if not p:
        await call.answer("Предложение не найдено.", show_alert=True)
        return
    chat_id, proposer, target, status, alive = int(p[0] or 0), int(p[1]), int(p[2]), p[3], p[4]
    uid, act = call.from_user.id, callback_data.act
    if (act == "x" and uid != proposer) or (act != "x" and uid != target):
        await call.answer("Это предложение не вам.", show_alert=True)
        return
    if status != "pending" or not alive:
        await call.answer("Предложение уже не действует.", show_alert=True)
        return
    names = await labels(db, (proposer, target))
    if act in ("n", "x"):
        await db.execute("UPDATE marriage_proposals SET status = ? WHERE id = ? AND status = 'pending'",
                         ("declined" if act == "n" else "cancelled", callback_data.pid))
        text = (f"💔 {names[target]} отказывает {names[proposer]}." if act == "n"
                else f"✖️ {names[proposer]} отзывает предложение.")
        await call.message.edit_text(text, parse_mode="HTML")
        await call.answer()
        return
    for u in (proposer, target):
        if await spouse_family_id(db, u):
            await call.answer("Кто-то из вас уже в браке.", show_alert=True)
            return
    if target in await kin(db, proposer):
        await call.answer("Нельзя: вы из одного рода.", show_alert=True)
        return
    raw = await plain_names(db, (proposer, target))
    raw[target] = call.from_user.full_name or raw[target]
    try:
        await create_marriage(db, chat_id, proposer, raw[proposer], target, raw[target],
                              proposal_id=callback_data.pid)
    except MarriageConflict as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.message.edit_text(
        f"💒 {names[proposer]} и {names[target]} теперь семья! Брак действует во всех чатах.\n"
        "Карточка семьи: <code>бот семья</code>", parse_mode="HTML")
    await call.answer("Поздравляем!")


# ── Карточка, дети, роли ─────────────────────────────────────────────────────

@registry.command("семья", aliases=("моя семья",), usage="бот семья [@ник]", section="family",
                  summary="Карточка семьи: родители, дети, общий кошелёк.")
async def cmd_family(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    uid = target.user_id if target else ctx.user_id
    fam = await family_of(ctx.db, uid)
    if fam is None:
        who = "У вас" if uid == ctx.user_id else "У этого игрока"
        await ctx.reply(f"💞 {who} пока нет семьи. Создать: <code>бот брак, @ник</code>")
        return
    await ctx.reply(await card(ctx.db, fam))


UP_TITLES = ("Родители", "Бабушки и дедушки", "Прабабушки и прадедушки")
TREE_DEPTH = 4
INDENT = "\u2003"


async def _spouse_of(db, uid: int) -> int | None:
    fid = await spouse_family_id(db, uid)
    fam = await load_family(db, fid) if fid else None
    return fam.partner_of(uid) if fam else None


# СТИЛЬ v1 (черновик): предки по поколениям, потомки лесенкой, каждый блок в цитате.
async def tree_text(db, uid: int) -> str | None:
    up: list[list[tuple[int, int]]] = []
    level = [uid]
    for _ in UP_TITLES:
        pairs = [tuple(ps) for ps in [await _parents_of(db, x) for x in level] if ps]
        if not pairs:
            break
        up.append(pairs)
        level = [p for pair in pairs for p in pair]
    down: list[tuple[int, int, int | None]] = []   # (глубина, кто, супруг)

    async def descend(x: int, depth: int) -> None:
        if depth > TREE_DEPTH or len(down) > 60:
            return
        for child in await _children_of(db, x):
            down.append((depth, child, await _spouse_of(db, child)))
            await descend(child, depth + 1)

    await descend(uid, 1)
    spouse = await _spouse_of(db, uid)
    parents = up[0][0] if up else ()
    siblings = [c for c in (await _children_of(db, parents[0]) if parents else []) if c != uid]
    if not up and not down and spouse is None:
        return None
    ids = {uid, *siblings, *(i for gen in up for pair in gen for i in pair),
           *(c for _, c, _ in down), *(sp for _, _, sp in down if sp), *([spouse] if spouse else [])}
    names = await labels(db, ids)
    lines = [f"🌳 <b>Родословная</b> · {names[uid]}"]
    for title, gen in reversed(list(zip(UP_TITLES, up))):
        lines.append(f"\n<b>{title}</b>")
        lines.append(quote([f"{names[a]} 💍 {names[b]}" for a, b in gen]))
    lines.append("\n<b>Семья</b>")
    me = [f"👤 {names[uid]}" + (f" 💍 {names[spouse]}" if spouse else "")]
    if siblings:
        me.append("Братья и сёстры: " + ", ".join(names[x] for x in siblings))
    lines.append(quote(me))
    if down:
        lines.append(f"\n<b>Потомки</b> · {len(down)}")
        lines.append(quote([INDENT * (d - 1) + f"└ {names[c]}" + (f" 💍 {names[sp]}" if sp else "")
                            for d, c, sp in down]))
    return "\n".join(lines)


@registry.command("древо", aliases=("родословная", "семейное древо", "дерево"), usage="бот древо [@ник]",
                  section="family", summary="Родословная: предки, братья и сёстры, дети и внуки.")
async def cmd_tree(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    uid = target.user_id if target else ctx.user_id
    text = await tree_text(ctx.db, uid)
    if text is None:
        who = "У вас" if uid == ctx.user_id else "У этого игрока"
        await ctx.reply(f"🌳 {who} пока нет родни. Создать семью: <code>бот брак, @ник</code>")
        return
    await ctx.reply(text)


class AdoptCB(CallbackData, prefix="fa"):
    m: int      # marriage_id
    by: int     # кто позвал
    t: int      # кого
    act: str    # y / n


@registry.command("усыновить", aliases=("удочерить", "взять в семью"), usage="бот усыновить, @ник",
                  section="family", summary=f"Позвать игрока в семью ребёнком (до {MAX_CHILDREN}).",
                  example="бот усыновить, @ник")
async def cmd_adopt(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is None:
        raise UsageError("бот усыновить, @ник  (или ответом на сообщение)")
    fam = await family_of(ctx.db, ctx.user_id)
    if fam is None or not fam.is_parent(ctx.user_id):
        await ctx.reply("👪 Звать детей могут только родители. Сначала: <code>бот брак, @ник</code>")
        return
    if len(fam.children) >= MAX_CHILDREN:
        await ctx.reply(f"👪 В семье уже {MAX_CHILDREN} детей — это максимум.")
        return
    if await parent_family_id(ctx.db, target.user_id):
        await ctx.reply(f"👪 У {html.escape(target.label())} уже есть родители.")
        return
    if target.user_id in await _family_kin(ctx.db, fam):
        await ctx.reply("👪 Нельзя: это ваш супруг, предок или родственник.")
        return
    u = ctx.message.from_user
    cb = dict(m=fam.marriage_id, by=ctx.user_id, t=target.user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🤗 Согласен(на)", callback_data=AdoptCB(**cb, act="y").pack()),
        InlineKeyboardButton(text="🙅 Нет", callback_data=AdoptCB(**cb, act="n").pack()),
    ]])
    await ctx.reply(f"👪 {ping(u.id, u.first_name)} зовёт {ping(target.user_id, target.name.lstrip('@'))} "
                    "в свою семью ребёнком. Согласны?", reply_markup=kb)


async def _family_kin(db, fam: Family) -> set[int]:
    """Кого нельзя взять в эту семью ребёнком: род обоих родителей (предки, братья, сёстры, они сами)."""
    out: set[int] = set()
    for p in fam.parents:
        out |= await kin(db, p)
    return out


@router.callback_query(AdoptCB.filter())
async def on_adopt(call: CallbackQuery, callback_data: AdoptCB, db) -> None:
    cb = callback_data
    if call.from_user.id != cb.t:
        await call.answer("Это приглашение не вам.", show_alert=True)
        return
    names = await labels(db, (cb.by, cb.t))
    if cb.act == "n":
        await call.message.edit_text(f"🙅 {names[cb.t]} не хочет в семью.", parse_mode="HTML")
        await call.answer()
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(?)", (cb.t,))   # одно принятие на игрока за раз
        async with db.execute("SELECT 1 FROM marriages WHERE id = ? AND ended_at IS NULL FOR UPDATE",
                              (cb.m,)) as cur:
            alive = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM family_children WHERE marriage_id = ? AND left_at IS NULL",
                              (cb.m,)) as cur:
            count = int((await cur.fetchone())[0])
        busy = await parent_family_id(db, cb.t)
        fam = await load_family(db, cb.m) if alive else None
        if not alive or fam is None:
            problem = "Этой семьи больше нет."
        elif count >= MAX_CHILDREN:
            problem = f"В семье уже {MAX_CHILDREN} детей."
        elif busy:
            problem = "У вас уже есть родители."
        elif cb.t in await _family_kin(db, fam):
            problem = "Нельзя: вы родственники."
        else:
            problem = None
            await db.execute("INSERT INTO family_children (marriage_id, user_id, added_by) VALUES (?, ?, ?)",
                             (cb.m, cb.t, cb.by))
    if problem:
        await call.answer(problem, show_alert=True)
        return
    await call.message.edit_text(f"🎉 {names[cb.t]} теперь в семье {names[cb.by]}!", parse_mode="HTML")
    await call.answer("Добро пожаловать в семью!")


@registry.command("семья роль", aliases=("роль в семье",), usage="бот семья роль, жена  ·  бот семья роль, @ник дочь",
                  section="family", summary="Своя роль в семье; родители меняют и роли детей.",
                  example="бот семья роль, муж")
async def cmd_role(ctx: Ctx) -> None:
    fam = await family_of(ctx.db, ctx.user_id)
    if fam is None:
        await ctx.reply("💞 Вы не в семье.")
        return
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args)
    uid = target.user_id if target else ctx.user_id
    role = norm(rest).replace("ребенок", "ребёнок")
    if uid == ctx.user_id and role in CHILD_ROLES and fam.is_parent(uid):
        # Женатый ребёнок меняет свою роль в родительской семье.
        parent_fid = await parent_family_id(ctx.db, uid)
        if parent_fid:
            await ctx.db.execute(
                "UPDATE family_children SET role = ? WHERE marriage_id = ? AND user_id = ? AND left_at IS NULL",
                (role, parent_fid, uid))
            await ctx.reply(f"✅ В родительской семье вы теперь: <b>{role}</b>.")
            return
    if uid not in fam.members:
        await ctx.reply("💞 Этот игрок не из вашей семьи.")
        return
    if uid != ctx.user_id and not fam.is_parent(ctx.user_id):
        await ctx.reply("💞 Роли других меняют только родители.")
        return
    allowed = PARENT_ROLES if fam.is_parent(uid) else CHILD_ROLES
    if role not in allowed:
        raise UsageError(f"бот семья роль, [@ник] {' | '.join(allowed)}")
    if fam.is_parent(uid):
        await ctx.db.execute(
            "INSERT INTO family_roles (user_id, marriage_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, marriage_id) DO UPDATE SET role = EXCLUDED.role, updated_at = NOW()",
            (uid, fam.marriage_id, role))
    else:
        await ctx.db.execute(
            "UPDATE family_children SET role = ? WHERE marriage_id = ? AND user_id = ? AND left_at IS NULL",
            (role, fam.marriage_id, uid))
    names = await labels(ctx.db, (uid,))
    await ctx.reply(f"✅ {names[uid]} теперь в семье: <b>{role}</b>.")


@registry.command("семья выйти", aliases=("выйти из семьи",), usage="бот семья выйти", section="family",
                  summary="Уйти из родительской семьи. Свой брак и дети остаются.")
async def cmd_leave(ctx: Ctx) -> None:
    if not await parent_family_id(ctx.db, ctx.user_id):
        if await spouse_family_id(ctx.db, ctx.user_id):
            await ctx.reply("💞 Родитель уходит из семьи только через развод: <code>бот развод</code>")
        else:
            await ctx.reply("💞 Вы не в семье.")
        return
    await ctx.db.execute("UPDATE family_children SET left_at = NOW() WHERE user_id = ? AND left_at IS NULL",
                         (ctx.user_id,))
    tail = " Ваш брак и ваши дети остаются с вами." if await spouse_family_id(ctx.db, ctx.user_id) else ""
    await ctx.reply(f"👋 Вы вышли из родительской семьи.{tail}")


@registry.command("семья выгнать", aliases=("выгнать из семьи",), usage="бот семья выгнать, @ник",
                  section="family", summary="Родителям — убрать ребёнка из семьи.")
async def cmd_kick_child(ctx: Ctx) -> None:
    target, _ = await resolve_target(ctx.db, ctx.message, ctx.args)
    if target is None:
        raise UsageError("бот семья выгнать, @ник")
    fam = await family_of(ctx.db, ctx.user_id)
    if fam is None or not fam.is_parent(ctx.user_id):
        await ctx.reply("💞 Это могут только родители.")
        return
    if target.user_id not in dict(fam.children):
        await ctx.reply("💞 Это не ваш ребёнок в семье.")
        return
    await ctx.db.execute(
        "UPDATE family_children SET left_at = NOW() WHERE marriage_id = ? AND user_id = ? AND left_at IS NULL",
        (fam.marriage_id, target.user_id))
    await ctx.reply(f"🚪 {html.escape(target.label())} больше не в семье.")


# ── Общий кошелёк ─────────────────────────────────────────────────────────────

class WalletCB(CallbackData, prefix="fw"):
    uid: int
    intent: str
    cur: str     # код валюты или x — отмена


async def _wallet_command(ctx: Ctx, action: str) -> None:
    amount = parse_amount(ctx.args)
    word = "положить" if action == "deposit" else "снять"
    if amount is None:
        raise UsageError(f"бот семья {word}, 100")
    fam = await family_of(ctx.db, ctx.user_id)
    if fam is None or not fam.is_parent(ctx.user_id):
        await ctx.reply("🏦 Общим кошельком распоряжаются родители.")
        return
    if not await wallet_ready(ctx.db):
        await ctx.reply("🏦 Общий кошелёк временно недоступен.")
        return
    intent = await family_wallet_v1.create_telegram_transfer_intent(
        ctx.db, actor_id=ctx.user_id, action=action, amount=amount)
    codes = list(WALLET_BUTTONS)
    if action == "withdrawal" and (await wallet_balances(ctx.db, fam.marriage_id))["dark_mora"] > 0:
        codes.append("dark_mora")
    buttons = [InlineKeyboardButton(text=f"{CURRENCY_VIEW[c].icon} {CURRENCY_VIEW[c].label}",
                                    callback_data=WalletCB(uid=ctx.user_id, intent=intent, cur=c).pack())
               for c in codes]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="✖️ Отмена",
                                      callback_data=WalletCB(uid=ctx.user_id, intent=intent, cur="x").pack())])
    head = "в общий кошелёк" if action == "deposit" else "из общего кошелька"
    await ctx.reply(f"🏦 {word.capitalize()} {head}: <b>{fmt(amount)}</b>\nКакую валюту?",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@registry.command("семья положить", aliases=("в общак",), usage="бот семья положить, 100", section="family",
                  summary="Положить валюту в общий кошелёк семьи.")
async def cmd_deposit(ctx: Ctx) -> None:
    await _wallet_command(ctx, "deposit")


@registry.command("семья снять", aliases=("из общака",), usage="бот семья снять, 100", section="family",
                  summary="Взять валюту из общего кошелька семьи.")
async def cmd_withdraw(ctx: Ctx) -> None:
    await _wallet_command(ctx, "withdrawal")


@router.callback_query(WalletCB.filter())
async def on_wallet(call: CallbackQuery, callback_data: WalletCB, db) -> None:
    cb = callback_data
    if call.from_user.id != cb.uid:
        await call.answer("Это не ваша операция.", show_alert=True)
        return
    if cb.cur == "x":
        await call.message.edit_text("✖️ Отменено.")
        await call.answer()
        return
    spec = CURRENCY_VIEW.get(cb.cur)
    if spec is None or cb.cur not in WALLET_CURRENCIES:
        await call.answer()
        return
    async with db.execute("SELECT amount FROM family_wallet_telegram_intents WHERE id = ?", (cb.intent,)) as cur:
        row = await cur.fetchone()
    if row and spec.display_decimals == 0 and row[0] != int(row[0]):
        await call.answer(f"{spec.label} — только целым числом.", show_alert=True)
        return
    try:
        result = await family_wallet_v1.consume_telegram_transfer_intent(
            db, intent_id=cb.intent, actor_id=cb.uid, currency=cb.cur)
    except InsufficientBalance:
        await call.answer(f"Не хватает: {spec.label}.", show_alert=True)
        return
    except EconomyContractError as exc:
        await call.answer(str(exc)[:190], show_alert=True)
        return
    verb = "Положено в общий кошелёк" if result.action == "deposit" else "Снято из общего кошелька"
    await call.message.edit_text(f"✅ {verb}: <b>{fmt(result.amount)}</b> {spec.icon} {spec.label}",
                                 parse_mode="HTML")
    await call.answer("Готово")


# ── Развод ────────────────────────────────────────────────────────────────────

_WORDS_A = ("тихий", "синий", "ржавый", "лунный", "звёздный", "старый", "медный", "сонный", "ледяной",
            "янтарный", "дикий", "белый", "горький", "тёплый", "пустой", "ночной")
_WORDS_B = ("маяк", "кот", "ключ", "фонарь", "ворон", "компас", "чайник", "мост", "колокол", "парус",
            "камень", "лис", "шарф", "замок", "огонь", "клён")


def divorce_phrase(intent_id: str) -> str:
    h = hashlib.sha256(intent_id.encode()).digest()
    return f"{_WORDS_A[h[0] % len(_WORDS_A)]} {_WORDS_B[h[1] % len(_WORDS_B)]} {1000 + int.from_bytes(h[2:4], 'big') % 9000}"


class DivorceCB(CallbackData, prefix="fd"):
    uid: int
    intent: str


@registry.command("развод", aliases=("развестись",), usage="бот развод", section="family",
                  summary="Развод. Нужно подтвердить случайной фразой, отменить нельзя.")
async def cmd_divorce(ctx: Ctx) -> None:
    if ctx.args.strip():
        await _confirm_divorce(ctx)
        return
    if not await spouse_family_id(ctx.db, ctx.user_id):
        await ctx.reply("💞 Вы не в браке.")
        return
    try:
        intent = await divorce_v1.create_intent(ctx.db, actor_id=ctx.user_id)
    except divorce_v1.DivorceError as exc:
        await ctx.reply(f"💔 {html.escape(str(exc))}")
        return
    names = await labels(ctx.db, (intent["partner_id"],))
    phrase = divorce_phrase(intent["id"])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="✖️ Передумал(а)", callback_data=DivorceCB(uid=ctx.user_id, intent=intent["id"]).pack())]])
    await ctx.reply(
        f"⚠️ <b>Развод с {names[intent['partner_id']]}</b>\n\n"
        "Что произойдёт:\n• общий кошелёк (все валюты, включая эссенцию) делится пополам;\n• семейные питомцы делятся поровну;\n"
        "• дети покидают вашу семью, но их браки и внуки остаются;\n• отменить развод будет нельзя.\n\n"
        f"Если вы уверены, в течение 15 минут напишите:\n<code>бот развод {phrase}</code>",
        reply_markup=kb)


async def _confirm_divorce(ctx: Ctx) -> None:
    async with ctx.db.execute(
        "SELECT id, marriage_id, partner_id FROM divorce_intents WHERE actor_id = ? AND status = 'pending' "
        "AND expires_at > NOW() ORDER BY created_at DESC LIMIT 1", (ctx.user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await ctx.reply("💔 Нет начатого развода. Сначала напишите <code>бот развод</code>.")
        return
    intent_id, marriage_id, partner = str(row[0]), int(row[1]), int(row[2])
    if " ".join(norm(w) for w in ctx.args.split()) != " ".join(norm(w) for w in divorce_phrase(intent_id).split()):
        await ctx.reply("❌ Фраза не совпала. Развод не выполнен.")
        return
    try:
        if await wallet_ready(ctx.db):
            # У браков, созданных после установки кошелька, строки баланса может не быть.
            await ctx.db.execute("INSERT INTO family_wallet_balances (marriage_id) VALUES (?) ON CONFLICT DO NOTHING",
                                 (marriage_id,))
            await divorce_v1.allocate_property(ctx.db, intent_id=intent_id, actor_id=ctx.user_id)
        else:
            await divorce_v1.settle_intent(ctx.db, intent_id=intent_id, actor_id=ctx.user_id)
    except divorce_v1.DivorceError as exc:
        await ctx.reply(f"💔 {html.escape(str(exc))}")
        return
    await ctx.db.execute("UPDATE family_children SET left_at = NOW() WHERE marriage_id = ? AND left_at IS NULL",
                         (marriage_id,))
    names = await labels(ctx.db, (ctx.user_id, partner))
    await ctx.reply(f"💔 {names[ctx.user_id]} и {names[partner]} развелись. "
                    "Общий кошелёк поделён пополам, дети покинули семью.")


@router.callback_query(DivorceCB.filter())
async def on_divorce_cancel(call: CallbackQuery, callback_data: DivorceCB, db) -> None:
    if call.from_user.id != callback_data.uid:
        await call.answer("Это не ваш развод.", show_alert=True)
        return
    await divorce_v1.cancel_intent(db, intent_id=callback_data.intent, actor_id=callback_data.uid)
    await call.message.edit_text("💞 Развод отменён. Берегите друг друга.")
    await call.answer()
