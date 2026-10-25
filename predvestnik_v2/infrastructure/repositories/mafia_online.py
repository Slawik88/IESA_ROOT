"""Storage isolated from every mafia_v1_* table; one active online seat per person."""
import json


async def ensure_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS mafia_online_rooms (
        id BIGSERIAL PRIMARY KEY, state JSONB NOT NULL,
        phase TEXT NOT NULL DEFAULT 'lobby', deadline DOUBLE PRECISION,
        visibility TEXT NOT NULL DEFAULT 'public', invite TEXT NOT NULL UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    await db.execute("CREATE INDEX IF NOT EXISTS mafia_online_due ON mafia_online_rooms(deadline) WHERE phase IN ('lobby','night','discussion','voting','paused')")
    await db.execute("CREATE INDEX IF NOT EXISTS mafia_online_history ON mafia_online_rooms USING GIN ((state->'players') jsonb_path_ops)")
    await db.execute("""CREATE TABLE IF NOT EXISTS mafia_online_seats (
        user_id BIGINT PRIMARY KEY, room_id BIGINT NOT NULL REFERENCES mafia_online_rooms(id))""")
    await db.execute("CREATE INDEX IF NOT EXISTS mafia_online_room_seats ON mafia_online_seats(room_id)")
    await db.execute("""CREATE TABLE IF NOT EXISTS mafia_online_messages (
        id BIGSERIAL PRIMARY KEY, room_id BIGINT NOT NULL REFERENCES mafia_online_rooms(id),
        user_id BIGINT, name TEXT NOT NULL, channel TEXT NOT NULL CHECK(channel IN ('table','mafia','afterlife')),
        body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 600), nonce UUID,
        reply_to BIGINT REFERENCES mafia_online_messages(id), hidden BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(room_id,user_id,nonce))""")
    await db.execute("CREATE INDEX IF NOT EXISTS mafia_online_message_page ON mafia_online_messages(room_id,channel,id)")
    await db.execute("CREATE INDEX IF NOT EXISTS mafia_online_message_rate ON mafia_online_messages(user_id,created_at)")
    await db.execute("""CREATE TABLE IF NOT EXISTS mafia_online_reports (
        message_id BIGINT NOT NULL REFERENCES mafia_online_messages(id), user_id BIGINT NOT NULL,
        reason TEXT NOT NULL, resolved BOOLEAN NOT NULL DEFAULT FALSE, resolved_by BIGINT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(message_id,user_id))""")
    await db.execute("ALTER TABLE mafia_online_reports ADD COLUMN IF NOT EXISTS resolved BOOLEAN NOT NULL DEFAULT FALSE")
    await db.execute("ALTER TABLE mafia_online_reports ADD COLUMN IF NOT EXISTS resolved_by BIGINT")
    await db.execute("ALTER TABLE mafia_online_messages ADD COLUMN IF NOT EXISTS seat INTEGER")
    await db.execute("""CREATE TABLE IF NOT EXISTS mafia_online_commands (
        room_id BIGINT NOT NULL REFERENCES mafia_online_rooms(id), user_id BIGINT NOT NULL,
        nonce UUID NOT NULL, digest TEXT NOT NULL, result JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(room_id,user_id,nonce))""")


async def matchmaking_lock(db):
    await db.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('mafia-online:matchmaking', 0))")


async def profile_name(db, user_id):
    if not await db.connection.fetchval("SELECT to_regclass('users') IS NOT NULL"):
        return None
    return await db.connection.fetchval("SELECT COALESCE(NULLIF(to_jsonb(u)->>'nickname',''), "
        "NULLIF(to_jsonb(u)->>'display_name',''),NULLIF(to_jsonb(u)->>'user_tg_username','')) "
        "FROM users u WHERE user_tg_id=$1", user_id)


async def command_receipt(db, room_id, user_id, nonce):
    row = await db.connection.fetchrow("SELECT digest,result FROM mafia_online_commands WHERE room_id=$1 AND user_id=$2 AND nonce=$3",
                                      room_id, user_id, nonce)
    return {"digest": row["digest"], "result": json.loads(row["result"])} if row else None


async def remember_command(db, room_id, user_id, nonce, digest, result):
    await db.connection.execute("INSERT INTO mafia_online_commands(room_id,user_id,nonce,digest,result) VALUES($1,$2,$3,$4,$5)",
                                room_id, user_id, nonce, digest, json.dumps(result))


async def user_lock(db, user_id):
    await db.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('mafia-online:' || $1::text, 0))", str(user_id))


async def now(db):
    return float(await db.connection.fetchval("SELECT EXTRACT(EPOCH FROM clock_timestamp())"))


async def current(db, user_id):
    return await db.connection.fetchval("SELECT room_id FROM mafia_online_seats WHERE user_id=$1", user_id)


async def load(db, room_id, lock=False, skip_locked=False):
    lock_sql = (" FOR UPDATE" + (" SKIP LOCKED" if skip_locked else "")) if lock else ""
    row = await db.connection.fetchrow("SELECT id,state FROM mafia_online_rooms WHERE id=$1" + lock_sql, room_id)
    return ({**json.loads(row["state"]), "id": row["id"]} if row else None)


async def create(db, state):
    room_id = await db.connection.fetchval(
        "INSERT INTO mafia_online_rooms(state,deadline,visibility,invite) VALUES($1,$2,$3,$4) RETURNING id",
        json.dumps(state), state["deadline"], state["visibility"], state["invite"])
    state["id"] = room_id
    return room_id


async def save(db, state, bump=True):
    if bump:
        state["version"] += 1
    await db.connection.execute("UPDATE mafia_online_rooms SET state=$1,phase=$2,deadline=$3,visibility=$4 WHERE id=$5",
                                json.dumps(state), state["phase"], state.get("deadline"), state["visibility"], state["id"])


async def take_seat(db, room_id, user_id):
    await db.connection.execute("INSERT INTO mafia_online_seats(user_id,room_id) VALUES($1,$2)", user_id, room_id)


async def release(db, room_id, user_id=None):
    if user_id is None:
        await db.connection.execute("DELETE FROM mafia_online_seats WHERE room_id=$1", room_id)
    else:
        await db.connection.execute("DELETE FROM mafia_online_seats WHERE room_id=$1 AND user_id=$2", room_id, user_id)


async def candidates(db):
    return [r["id"] for r in await db.connection.fetch(
        "SELECT id FROM mafia_online_rooms WHERE phase='lobby' AND visibility='public' "
        "AND deadline>EXTRACT(EPOCH FROM clock_timestamp()) "
        "AND jsonb_array_length(state->'players') < (state->>'seats')::int ORDER BY id LIMIT 40")]


async def latest_id(db):
    return await db.connection.fetchval("SELECT COALESCE(MAX(id),0) FROM mafia_online_rooms")


async def due(db, after=0, through=2**63-1):
    return [r["id"] for r in await db.connection.fetch(
        "SELECT id FROM mafia_online_rooms WHERE phase=ANY($1::text[]) AND deadline<=EXTRACT(EPOCH FROM clock_timestamp()) "
        "AND id>$2 AND id<=$3 ORDER BY id LIMIT 100",
        ["lobby", "night", "discussion", "voting", "paused"], after, through)]


async def history(db, user_id):
    rows = await db.connection.fetch("SELECT id,state FROM mafia_online_rooms WHERE phase IN ('finished','cancelled') "
        "AND state->'players' @> $1::jsonb ORDER BY id DESC LIMIT 20", json.dumps([{"id": user_id}]))
    return [{**json.loads(r["state"]), "id": r["id"]} for r in rows]


async def message(db, room_id, channel, body, *, user_id=None, name="Предвестник", nonce=None, reply_to=None, seat=None):
    row = await db.connection.fetchrow("INSERT INTO mafia_online_messages(room_id,user_id,name,channel,body,nonce,reply_to,seat) "
        "VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(room_id,user_id,nonce) DO NOTHING RETURNING id",
        room_id, user_id, name, channel, body, nonce, reply_to, seat)
    return row["id"] if row else None


async def get_message(db, message_id):
    row = await db.connection.fetchrow("SELECT *,EXTRACT(EPOCH FROM created_at)::float8 AS time FROM mafia_online_messages WHERE id=$1", message_id)
    return dict(row) if row else None


async def message_receipt(db, room_id, user_id, nonce):
    row = await db.connection.fetchrow("SELECT id,channel,body,reply_to FROM mafia_online_messages "
                                     "WHERE room_id=$1 AND user_id=$2 AND nonce=$3", room_id, user_id, nonce)
    return dict(row) if row else None


async def channel_latest(db, room_id, allowed):
    rows = await db.connection.fetch("SELECT channel,MAX(id) AS latest_id FROM mafia_online_messages "
                                    "WHERE room_id=$1 AND channel=ANY($2::text[]) GROUP BY channel", room_id, allowed)
    return {row["channel"]: row["latest_id"] for row in rows}


async def last_message_at(db, user_id):
    return await db.connection.fetchval("SELECT EXTRACT(EPOCH FROM MAX(created_at))::float8 FROM mafia_online_messages WHERE user_id=$1", user_id)


async def messages(db, room_id, channel, after, before=0):
    rows = await db.connection.fetch("SELECT m.id,m.user_id,m.name,m.seat,m.body,m.hidden,m.reply_to, "
        "EXTRACT(EPOCH FROM m.created_at)::float8 AS time, p.name AS reply_name, p.seat AS reply_seat, "
        "CASE WHEN p.hidden THEN 'Сообщение скрыто' ELSE left(p.body,100) END AS reply_body, p.hidden AS reply_hidden "
        "FROM mafia_online_messages m LEFT JOIN mafia_online_messages p ON p.id=m.reply_to AND p.room_id=m.room_id AND p.channel=m.channel "
        "WHERE m.room_id=$1 AND m.channel=$2 AND m.id>$3 AND ($4::bigint=0 OR m.id<$4) ORDER BY m.id " + ("ASC" if after else "DESC") + " LIMIT 80",
        room_id, channel, after, before)
    return [dict(r) for r in (rows if after else reversed(rows))]


async def hide(db, message_id):
    await db.connection.execute("UPDATE mafia_online_messages SET hidden=TRUE WHERE id=$1", message_id)


async def report(db, message_id, user_id, reason):
    await db.connection.execute("INSERT INTO mafia_online_reports(message_id,user_id,reason) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                                message_id, user_id, reason)


async def reports(db, resolved=False, before=0):
    rows = await db.connection.fetch("SELECT m.id,m.room_id,m.user_id,m.name,m.body,m.channel,m.hidden, "
        "COUNT(*)::int AS reports, array_agg(DISTINCT r.reason) AS reasons FROM mafia_online_reports r "
        "JOIN mafia_online_messages m ON m.id=r.message_id WHERE r.resolved=$1 AND ($2::bigint=0 OR m.id<$2) "
        "GROUP BY m.id ORDER BY m.id DESC LIMIT 100", resolved, before)
    return [dict(row) for row in rows]


async def resolve_report(db, message_id, actor):
    await db.connection.execute("UPDATE mafia_online_reports SET resolved=TRUE,resolved_by=$1 WHERE message_id=$2", actor, message_id)
