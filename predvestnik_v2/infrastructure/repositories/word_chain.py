"""Durable word-chain rounds, receipts and per-round scores."""
import json
from core.word_chain import IDLE_HOURS


async def ensure_tables(db) -> None:
    async with db.execute("SELECT to_regclass('word_chain_rounds') IS NOT NULL AND to_regclass('word_chain_words') IS NOT NULL AND to_regclass('word_chain_moves') IS NOT NULL") as cur:
        if (await cur.fetchone())[0]:
            return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('schema:word-chain',0))")
        await db.execute("CREATE TABLE IF NOT EXISTS word_chain_rounds (id BIGSERIAL PRIMARY KEY,chat_id BIGINT NOT NULL,topic_id BIGINT NOT NULL DEFAULT 0,initiator_id BIGINT NOT NULL,status TEXT NOT NULL DEFAULT 'active',last_word TEXT NOT NULL,turns INTEGER NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),started_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP())")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS word_chain_one_active ON word_chain_rounds(chat_id,topic_id) WHERE status='active'")
        await db.execute("CREATE TABLE IF NOT EXISTS word_chain_words (round_id BIGINT NOT NULL REFERENCES word_chain_rounds(id),word TEXT NOT NULL,PRIMARY KEY(round_id,word))")
        await db.execute("CREATE TABLE IF NOT EXISTS word_chain_moves (round_id BIGINT NOT NULL REFERENCES word_chain_rounds(id),message_id BIGINT NOT NULL,user_id BIGINT NOT NULL,word TEXT NOT NULL,reply_json JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),PRIMARY KEY(round_id,message_id))")
        await db.execute("CREATE INDEX IF NOT EXISTS word_chain_player_moves ON word_chain_moves(round_id,user_id,created_at DESC)")


async def lock(db, chat_id: int, topic_id: int) -> None:
    await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", (f"word-chain:{chat_id}:{topic_id}",))


async def active(db, chat_id: int, topic_id: int) -> dict | None:
    async with db.execute("SELECT *, updated_at<CLOCK_TIMESTAMP()-make_interval(hours=>?) AS expired FROM word_chain_rounds WHERE chat_id=? AND topic_id=? AND status='active'", (IDLE_HOURS,chat_id,topic_id)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def latest(db, chat_id: int, topic_id: int) -> dict | None:
    async with db.execute("SELECT * FROM word_chain_rounds WHERE chat_id=? AND topic_id=? ORDER BY id DESC LIMIT 1",(chat_id,topic_id)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def paused(db, chat_id: int, topic_id: int) -> bool:
    async with db.execute("SELECT COALESCE(is_closed,FALSE) OR COALESCE(is_purging,FALSE) OR EXISTS (SELECT 1 FROM mafia_v1_matches WHERE chat_id=? AND COALESCE(topic_id,0)=? AND phase IN ('night','discussion','voting')) FROM chat_settings WHERE chat_id=?",(chat_id,topic_id,chat_id)) as cur:
        row = await cur.fetchone()
    return bool(row and row[0])


async def create(db, chat_id: int, topic_id: int, actor: int, word: str) -> dict:
    async with db.execute("INSERT INTO word_chain_rounds(chat_id,topic_id,initiator_id,last_word) VALUES (?,?,?,?) RETURNING *",(chat_id,topic_id,actor,word)) as cur:
        row = dict(await cur.fetchone())
    await db.execute("INSERT INTO word_chain_words(round_id,word) VALUES (?,?)",(row["id"],word))
    return row


async def finish(db, round_id: int, status: str = "finished") -> None:
    await db.execute("UPDATE word_chain_rounds SET status=?,updated_at=CLOCK_TIMESTAMP() WHERE id=?",(status,round_id))


async def used(db, round_id: int) -> set[str]:
    async with db.execute("SELECT word FROM word_chain_words WHERE round_id=?",(round_id,)) as cur:
        return {r[0] for r in await cur.fetchall()}


async def receipt(db, chat_id: int, topic_id: int, message_id: int) -> dict | None:
    async with db.execute("SELECT m.reply_json FROM word_chain_moves m JOIN word_chain_rounds r ON r.id=m.round_id WHERE r.chat_id=? AND r.topic_id=? AND m.message_id=? ORDER BY r.id DESC LIMIT 1",(chat_id,topic_id,message_id)) as cur:
        row = await cur.fetchone()
    return (json.loads(row[0]) if isinstance(row[0],str) else dict(row[0])) if row else None


async def cooling_down(db, round_id: int, user_id: int, seconds: int) -> bool:
    async with db.execute("SELECT EXISTS (SELECT 1 FROM word_chain_moves WHERE round_id=? AND user_id=? AND created_at>CLOCK_TIMESTAMP()-make_interval(secs=>?))",(round_id,user_id,seconds)) as cur:
        return bool((await cur.fetchone())[0])


async def save_move(db, round_id: int, message_id: int, user_id: int, word: str, reply: dict) -> None:
    for used_word in (word,reply.get("bot_word")):
        if used_word:
            await db.execute("INSERT INTO word_chain_words(round_id,word) VALUES (?,?)",(round_id,used_word))
    await db.execute("INSERT INTO word_chain_moves(round_id,message_id,user_id,word,reply_json) VALUES (?,?,?,?,?::jsonb)",(round_id,message_id,user_id,word,json.dumps(reply,ensure_ascii=False)))
    await db.execute("UPDATE word_chain_rounds SET last_word=?,turns=turns+1,updated_at=CLOCK_TIMESTAMP(),status=? WHERE id=?",(reply.get("bot_word") or word,"finished" if reply["finished"] else "active",round_id))



async def save_reply(db, round_id: int, message_id: int, reply: dict) -> None:
    await db.execute("UPDATE word_chain_moves SET reply_json=?::jsonb WHERE round_id=? AND message_id=?",(json.dumps(reply,ensure_ascii=False),round_id,message_id,))


async def leaders(db, round_id: int) -> list[dict]:
    async with db.execute("SELECT m.user_id,COUNT(*) AS score,COALESCE(MAX(u.user_tg_name),MAX(u.user_tg_username),'Игрок') AS name FROM word_chain_moves m LEFT JOIN users u ON u.user_tg_id=m.user_id WHERE m.round_id=? GROUP BY m.user_id ORDER BY score DESC,m.user_id LIMIT 10",(round_id,)) as cur:
        return [{"id":int(r[0]),"score":int(r[1]),"name":r[2]} for r in await cur.fetchall()]
