"""Disposable PostgreSQL proofs; no real Telegram call is possible in this test."""
from __future__ import annotations
import argparse
import asyncio
import json
import pathlib
import sys
from uuid import uuid4
from urllib.parse import urlparse

import asyncpg
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import pets_v2 as pets_repo, mafia_v1 as mafia_repo, official_updates as news_repo
from services import pets_v2 as pets, family_tree, mafia_review, purge, official_updates as news
from services import rhythm_v2 as rhythm
from core import pets_v2 as pet_rules


async def denied(awaitable, error=ValueError):
    try:
        await awaitable
    except error:
        return
    raise AssertionError("expected refusal")


async def run(dsn):
    conn = await asyncpg.connect(dsn)
    await conn.execute("SET search_path TO predvestnik,public")
    db = PGAdapter(conn)
    transaction = conn.transaction()
    await transaction.start()
    try:
        await pets_repo.ensure_tables(db); await mafia_repo.ensure_tables(db); await news_repo.ensure_tables(db)
        users = [98761101,98761102,98761103,98761104]
        for i, uid in enumerate(users):
            await db.execute("INSERT INTO users(user_tg_id,user_tg_username) VALUES (?,?) ON CONFLICT DO NOTHING", (uid,f"wave_qa_{i}"))
        owner, other = users[:2]
        pids = []
        for species in ("moss_cat","mirror_owl","salt_fox"):
            async with db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,'common') RETURNING id", (owner,species,species)) as cursor:
                pid = int((await cursor.fetchone())[0]); pids.append(pid)
        primary, companion, free = pids
        await pets_repo.ensure_state(db,owner,primary,100)
        await db.execute("UPDATE pet_v2_state SET level=10 WHERE user_id=? AND pet_id=?",(owner,primary))
        calling = next(iter(pet_rules.AVAILABLE_CALLINGS))
        draft = dict(user_id=owner,pet_id=primary,slot=1,name="Ночные походы",calling=calling,traits=[],talismans=[],action_id="save-draft")
        first = await pets.save_build_preset(db,**draft)
        assert (await pets.save_build_preset(db,**draft))["idempotent_replay"]
        assert first["build"]["calling"] == calling
        await denied(pets.save_build_preset(db,**{**draft,"name":"другой запрос"}))
        await denied(pets.save_build_preset(db,**{**draft,"user_id":other,"action_id":"foreign"}))
        await denied(pets.set_build(db,user_id=owner,pet_id=primary,calling=calling,traits=[],talisman_ids=[],action_id="wrong-price",expected_essence=99))
        before = int(await conn.fetchval("SELECT COUNT(*) FROM pet_v2_state WHERE user_id=$1",owner))
        q = await pets.preview_run(db,user_id=owner,pet_id=free,kind="trek",hours=3,route="forest")
        assert q["snapshot_only"] and q["excludes_random_finds"]
        assert before == int(await conn.fetchval("SELECT COUNT(*) FROM pet_v2_state WHERE user_id=$1",owner))
        run_id = uuid4().hex
        await db.execute("INSERT INTO pet_v2_runs(id,user_id,pet_id,companion_id,kind,hours,route,status,ends_at) VALUES (?,?,?,?,'trek',3,'forest','active',NOW()+INTERVAL '1 hour')",(run_id,owner,primary,companion))
        await denied(pets.set_build(db,user_id=owner,pet_id=companion,calling=None,traits=[],talisman_ids=[],action_id="busy-companion"))
        await pets_repo.add_talisman(db,owner,"wave-gear",next(iter(pet_rules.TALISMANS)),1)
        await db.execute("UPDATE pet_v2_talismans SET pet_id=? WHERE id='wave-gear'",(primary,))
        await denied(pets.set_build(db,user_id=owner,pet_id=free,calling=None,traits=[],talisman_ids=["wave-gear"],action_id="busy-donor"))
        cid = -98761100
        await db.execute("INSERT INTO chat_settings(chat_id,chat_title,is_closed) VALUES (?,'Wave QA',TRUE)",(cid,))
        for uid in users:
            await db.execute("INSERT INTO user_chat_stats(user_tg_id,chat_tg_id,is_left) VALUES (?,?,FALSE)",(uid,cid))
        match = await mafia_repo.create_match(db,chat_id=cid,topic_id=None,initiator_id=owner,max_players=4,enabled_roles=(),vote_mode="secret",ruleset_version="qa")
        mid = int(match["id"])
        for i,uid in enumerate(users):
            await mafia_repo.add_player(db,match_id=mid,user_id=uid,username=None,display_name=f"QA {i}")
        await mafia_repo.set_roles(db,match_id=mid,by_user={owner:"detective",other:"mafia",users[2]:"citizen",users[3]:"doctor"})
        assert await mafia_review.review(db,user_id=owner,match_id=mid) is None
        await mafia_repo.update_match(db,match_id=mid,phase="finished",phase_number=3,deadline=None,winner="town")
        await mafia_repo.audit(db,match_id=mid,event_type="phase_advanced",actor_id=None,payload={"previous_phase":"voting","previous_number":3,"eliminated_user_id":other,"private_checks":[{"target_user_id":other}]})
        await mafia_repo.upsert_action(db,match_id=mid,phase_number=3,user_id=owner,action_type="vote",target_user_id=other)
        review = await mafia_review.review(db,user_id=owner,match_id=mid)
        assert review["timeline"][0]["votes"][0]["count"] == 1 and "private_checks" not in json.dumps(review)
        assert await mafia_review.review(db,user_id=999,match_id=mid) is None
        await db.execute("UPDATE user_chat_stats SET is_left=TRUE WHERE user_tg_id=? AND chat_tg_id=?",(owner,cid))
        assert await mafia_review.review(db,user_id=owner,match_id=mid) is None
        await db.execute("UPDATE user_chat_stats SET is_left=FALSE WHERE user_tg_id=? AND chat_tg_id=?",(owner,cid))
        async with db.execute("INSERT INTO marriages(user1_id,user2_id,chat_id) VALUES (?,?,?) RETURNING id",(owner,other,cid)) as cursor:
            fid = int((await cursor.fetchone())[0])
        await db.execute("INSERT INTO marriage_members(user_id,marriage_id) VALUES (?,?),(?,?)",(owner,fid,other,fid))
        await db.execute("INSERT INTO family_children(marriage_id,user_id) VALUES (?,?)",(fid,users[2]))
        tree = await family_tree.own_tree(db,user_id=users[2])
        assert len(tree["nodes"]) == 3 and sum(e["kind"]=="parent" for e in tree["edges"]) == 2
        assert "balance" not in json.dumps(tree) and str(owner) not in json.dumps(tree)
        await db.execute("UPDATE family_children SET left_at=NOW() WHERE marriage_id=?",(fid,))
        assert len((await family_tree.own_tree(db,user_id=users[2]))["nodes"]) == 1
        sid = await purge.begin(db,chat_id=cid,actor=owner,norm=10,date_from="2026-10-01",date_to="2026-10-07",destination=cid,
                                 action_id="first-start",
                                 targets=[{"user_id":other,"count":2,"days_in_chat":10,"warns":0,"required":10},
                                          {"user_id":users[2],"count":1,"days_in_chat":10,"warns":0,"required":10}])
        calls = []
        async def authorize(*args): pass
        async def execute(*args): calls.append(args)
        kwargs = dict(session_id=sid,user_id=other,actor=owner,action="warn",action_id="warn-one",authorize=authorize,execute=execute)
        assert (await purge.decide(db,**kwargs))["ok"]
        assert (await purge.decide(db,**kwargs))["replayed"] and len(calls)==1
        async def uncertain(*args): raise TimeoutError()
        bad = {**kwargs,"user_id":users[2],"action":"ban","action_id":"uncertain","execute":uncertain}
        await denied(purge.decide(db,**bad))
        await denied(purge.decide(db,**bad))
        await denied(purge.complete(db,chat_id=cid,actor=owner,expected_session=sid))
        materialized=[]
        async def materialize(row,applied): materialized.append(applied)
        await purge.reconcile(db,session_id=sid,user_id=users[2],actor=owner,applied=False,reason="Проверен журнал Telegram: действие отсутствует",authorize=authorize,materialize=materialize)
        assert materialized == [False]
        await purge.complete(db,chat_id=cid,actor=owner,expected_session=sid)
        assert await conn.fetchval("SELECT is_closed AND NOT is_purging FROM chat_settings WHERE chat_id=$1",cid)
        repeated = dict(chat_id=cid,actor=owner,norm=10,date_from="2026-10-01",date_to="2026-10-07",destination=cid,
                        targets=[],action_id="first-start")
        assert await purge.begin(db,**repeated) == sid
        assert not await conn.fetchval("SELECT is_purging FROM chat_settings WHERE chat_id=$1",cid)
        await denied(purge.begin(db,**{**repeated,"norm":11}))
        newer = await purge.begin(db,**{**repeated,"action_id":"second-start"})
        assert newer != sid and await purge.begin(db,**repeated) == sid
        assert await conn.fetchval("SELECT id FROM purge_sessions WHERE chat_id=$1 AND status='active'",cid) == newer
        await purge.complete(db,chat_id=cid,actor=owner,expected_session=newer)
        for flag in ("game_rhythm_v2", "game_minesweeper_v2", "game_mafia_v1"):
            await db.execute("INSERT INTO system_flags(key,enabled) VALUES (?,1) ON CONFLICT(key) DO UPDATE SET enabled=1",(flag,))
        run = await rhythm.start_run(db,user_id=owner,mode="normal")
        rid = run["run_id"]
        ticket = await rhythm.issue_transport_ticket(db,user_id=owner,run_id=rid)
        _,lease,live = await rhythm.connect_transport(db,run_id=rid,ticket=ticket["ticket"])
        tap = dict(user_id=owner,run_id=rid,lease=lease,signal_no=1,rune=live["rune"],action_id="real-observed-tap")
        await rhythm.transport_tap(db,**tap)
        assert (await rhythm.transport_tap(db,**tap))["idempotent_replay"]
        await db.execute("UPDATE rhythm_v2_runs SET signal_opened_at=CLOCK_TIMESTAMP()-INTERVAL '40 seconds' WHERE run_id=?",(rid,))
        finished = await rhythm.transport_state(db,user_id=owner,run_id=rid,lease=lease)
        a = finished["analysis"]
        assert finished["status"] == "finished" and a["complete"] and a["best_streak"] == 1
        assert a["timeouts"] == rhythm.rules.initial_health() and a["wrong"] == 0
        assert a["signals"] == 1 + a["timeouts"] and a["hearts_lost"] == a["timeouts"]
        assert a["response_ms"] is not None and finished["integrity_status"] == "clear"
        key="wave-qa-"+uuid4().hex
        draft = await news.draft(db,key=key,kind="pets",caption="Важное обновление питомцев: прогноз перед отправкой и сохранённые сборки.",image="qa.png",image_digest="abc",version="qa",actor=owner)
        sent=[]
        async def preflight(row): pass
        async def send(row): sent.append(row["release_key"]); return 123
        send_args=dict(key=key,expected_digest=draft["content_digest"],version="qa",preflight=preflight,send=send)
        assert (await news.publish(db,**send_args))["ok"]
        assert (await news.publish(db,**send_args))["replayed"] and len(sent)==1
        await db.execute("UPDATE official_update_posts SET sent_at=NOW()-INTERVAL '2 days' WHERE release_key=?",(key,))
        badkey="wave-qa-"+uuid4().hex
        draft2=await news.draft(db,key=badkey,kind="family",caption="Семейное дерево появилось в приложении: теперь близких видно вместе.",image="qa.png",image_digest="abc",version="qa",actor=owner)
        await denied(news.publish(db,key=badkey,expected_digest=draft2["content_digest"],version="qa",preflight=preflight,send=uncertain))
        assert (await news_repo.get(db,badkey))["status"]=="unknown"
        await denied(news.publish(db,key=badkey,expected_digest=draft2["content_digest"],version="qa",preflight=preflight,send=send))
        print("OK: PostgreSQL forecast/presets/privacy/family/shared purge and publication receipt boundaries")
    finally:
        await transaction.rollback()
        await conn.close()


async def concurrent(dsn):
    """Two real connections competing for one verdict / one publication slot."""
    connections = [await asyncpg.connect(dsn) for _ in range(2)]
    for connection in connections:
        await connection.execute("SET search_path TO predvestnik,public")
    a, b = [PGAdapter(c) for c in connections]
    cid = -int(uuid4().int % 1000000000 + 7000000000)
    keys = ["wave-race-"+uuid4().hex for _ in range(2)]
    sid = None
    try:
        start = dict(chat_id=cid,actor=101,norm=10,date_from="2026-10-01",date_to="2026-10-07",destination=cid,action_id="concurrent-start",
                     targets=[{"user_id":202,"count":0,"days_in_chat":7,"warns":0,"required":10}])
        starts = await asyncio.gather(purge.begin_with_receipt(a,**start),purge.begin_with_receipt(b,**start))
        assert sum(r["created"] for r in starts) == 1 and starts[0]["session_id"] == starts[1]["session_id"]
        sid = starts[0]["session_id"]
        effects=[]
        async def authorize(*args): pass
        async def effect(*args):
            effects.append(args)
            await asyncio.sleep(.04)
        async def decide(db, actor):
            return await purge.decide(db,session_id=sid,user_id=202,actor=actor,action="warn",action_id=f"actor-{actor}",authorize=authorize,execute=effect)
        results = await asyncio.gather(decide(a,101),decide(b,303))
        assert len(effects)==1 and sum(bool(r.get("replayed")) for r in results)==1
        await news_repo.ensure_tables(a)
        drafts=[]
        for key in keys:
            drafts.append(await news.draft(a,key=key,kind="pets",caption="Важное обновление: прогноз питомца проверяет сборку до отправки в путь.",image="qa.png",image_digest="abc",version="qa",actor=101))
        sent=[]
        async def preflight(*args):pass
        async def send(row):
            sent.append(row["release_key"])
            await asyncio.sleep(.08)
            return 123
        async def publish(db,row):
            try:
                return await news.publish(db,key=row["release_key"],expected_digest=row["content_digest"],version="qa",preflight=preflight,send=send)
            except news.PublicationError:
                return None
        results=await asyncio.gather(publish(a,drafts[0]),publish(b,drafts[1]))
        assert len(sent)==1 and sum(r is not None for r in results)==1
        print("OK: real concurrent moderators apply once; concurrent releases send at most one post")
    finally:
        if sid:
            await a.execute("DELETE FROM purge_targets WHERE session_id=?",(sid,))
            await a.execute("DELETE FROM purge_sessions WHERE id=?",(sid,))
        await a.execute("DELETE FROM moderation_logs WHERE chat_id=?",(cid,))
        await a.execute("DELETE FROM chat_settings WHERE chat_id=?",(cid,))
        for key in keys:await a.execute("DELETE FROM official_update_posts WHERE release_key=?",(key,))
        for connection in connections:await connection.close()


async def main(dsn):
    await run(dsn)
    await concurrent(dsn)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--dsn",required=True);args=parser.parse_args()
    if urlparse(args.dsn).hostname not in {"localhost","127.0.0.1","::1"}: raise SystemExit("loopback only")
    asyncio.run(main(args.dsn))
