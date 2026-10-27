"""Tables and flags the Mini App needs at start-up.

FastAPI is co-hosted with the bot and runs with lifespan="off" (bot/__main__.py), so the ensure list in FastAPI/main.py lifespan does not run in production.
Everything the first request reads must be created here. The same function starts the local stand (tools/ui_stand.py): the stand and production run one path.
"""
from __future__ import annotations

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import coin_market_v2 as coin_market_v2_repo
from infrastructure.repositories import pet_chat, star_dust, mafia_online, league_pass, purge_sessions, word_chain
from infrastructure.repositories import support_reports
from infrastructure.repositories import (
    achievements_v1 as achievements_v1_repo, game_seasons as game_seasons_repo, gifts_v2 as gifts_v2_repo, global_skins_v1 as global_skins_v1_repo, mafia_v1 as mafia_v1_repo, marks_v1 as marks_v1_repo,
    minesweeper_v2 as minesweeper_v2_repo, nicknames_retired, pet_nudge_v1 as pet_nudge_v1_repo, casino_v1 as casino_v1_repo, pets_v1 as pets_v1_repo, pets_v2 as pets_v2_repo, player_exchange_v1 as player_exchange_v1_repo, presence_v1 as presence_v1_repo,
    public_profiles_v1 as public_profiles_v1_repo, rhythm_v2 as rhythm_v2_repo, season_pass as season_pass_repo, shop_v1 as shop_v1_repo, skin_chat_v1 as skin_chat_v1_repo, skins_v3 as skins_v3_repo,
    system_flags, vip_v2 as vip_v2_repo, patch_notes as patch_notes_repo,
)

# Order matters only for flags (first). Each entry is idempotent CREATE ... IF NOT EXISTS.
ENSURES = (
    ("system_flags", system_flags.ensure_table),
    ("rhythm_v2", rhythm_v2_repo.ensure_tables),
    ("mafia_v1", mafia_v1_repo.ensure_tables),
    ("purge", purge_sessions.ensure_operations),
    ("word_chain", word_chain.ensure_tables),
    ("support_reports", support_reports.ensure_tables),
    ("mafia_online", mafia_online.ensure_tables),
    ("minesweeper_v2", minesweeper_v2_repo.ensure_tables),
    ("game_seasons", game_seasons_repo.ensure_tables),
    ("season_pass", season_pass_repo.ensure_tables),
    ("league_pass", league_pass.ensure_tables),
    ("pets_v1", pets_v1_repo.ensure_tables),
    ("pets_v2", pets_v2_repo.ensure_tables),
    ("pet_chat", pet_chat.ensure_tables),
    ("star_dust", star_dust.ensure_tables),
    ("pet_nudge_v1", pet_nudge_v1_repo.ensure_tables),   # мягкое напоминание о питомцах
    ("casino_v1", casino_v1_repo.ensure_tables),         # казино «Зал Фортуны»: жетоны, раунды, покупки
    ("achievements_v1", achievements_v1_repo.ensure_tables),
    ("public_profiles_v1", public_profiles_v1_repo.ensure_tables),
    ("global_skins_v1", global_skins_v1_repo.ensure_tables),
    ("vip_v2", vip_v2_repo.ensure_tables),
    ("player_exchange_v1", player_exchange_v1_repo.ensure_tables),
    ("coin_market_v2", coin_market_v2_repo.ensure_tables),
    ("skins_v3", skins_v3_repo.ensure_tables),          # образы, Эссенция: профиль читает их в первом же запросе
    ("skin_chat_v1", skin_chat_v1_repo.ensure_tables),  # скины в чате: выключатель и очередь новостей; покупка пишет в неё в своей транзакции
    ("marks_v1", marks_v1_repo.ensure_tables),          # регалии
    ("presence_v1", presence_v1_repo.ensure_tables),    # «был в сети»
    ("shop_v1", shop_v1_repo.ensure_tables),            # чеки магазина (Шлифовка); после economic_operations из init_db
    ("gifts_v2", gifts_v2_repo.ensure_tables),          # чеки подарков и витрина полки; после economic_operations из init_db
    ("nicknames_retired", nicknames_retired.ensure_tables),   # ники старого бота удалены; после init_db (inventory, user_chat_stats)
    ("patch_notes", patch_notes_repo.ensure_tables),    # патч-ноуты и тема официального канала: бот отмечает её при первом сообщении
)


async def ensure_runtime_schema(pool) -> None:
    """Create the tables the Mini App reads on its first requests. Any failure stops start-up: a half-created schema is worse than no start."""
    async with pool.acquire() as connection:
        db = PGAdapter(connection)
        for _label, ensure in ENSURES:
            await ensure(db)
        from services.player_release import activate
        await activate(db)
    # Last startup schema step (bot and local stand): /api/ready may now answer 200 (audit A04).
    from infrastructure import readiness
    readiness.mark_startup_complete()
