"""Loopback PostgreSQL proof: retries, races, topics, expiry and ordinary activity."""
import argparse
import asyncio
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from core import word_chain as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import word_chain as repo, moderation_chats
from services import word_chain as game, purge


async def denied(call, needle=""):
    try:
        await call
    except game.WordChainError as error:
        assert needle in str(error),(needle,str(error))
        return
    raise AssertionError("expected rejection")


async def run(dsn):
    conns = [await asyncpg.connect(dsn) for _ in range(2)]
    for conn in conns:
        await conn.execute("SET search_path TO predvestnik,public")
    db, other = [PGAdapter(c) for c in conns]
    cid, owner, peer = -98651100,98651101,98651102
    try:
        await repo.ensure_tables(db)
        await db.execute("INSERT INTO chat_settings(chat_id,chat_title,owner_id) VALUES (?,'𝓒𝓾𝓼𝓽𝓸𝓶 ❤️',?)",(cid,owner))
        for uid in (owner,peer):
            await db.execute("INSERT INTO users(user_tg_id,user_tg_name) VALUES (?,?)",(uid,f"QA {uid}"))
        from bot.chat import registry
        from bot.chat.warps import adult_allowed
        for name in ("засосать","выебать","трахнуть","переспать"):
            assert registry.get(name) is not None,name
        assert not (await adult_allowed(db,cid,peer))[0]
        await db.execute("UPDATE users SET allow_adult_warps=TRUE WHERE user_tg_id=?",(peer,))
        assert (await adult_allowed(db,cid,peer))[0]
        await db.execute("UPDATE chat_settings SET nsfw_warps_allowed=0 WHERE chat_id=?",(cid,))
        assert not (await adult_allowed(db,cid,peer))[0]
        await db.execute("UPDATE chat_settings SET nsfw_warps_allowed=1 WHERE chat_id=?",(cid,))
        # A silent owner still discovers the chat without any user_chat_stats row.
        mine = await moderation_chats.listing(db,user_id=owner,purge_only=True)
        assert any(c["id"]==cid for c in mine["items"]),mine
        assert not (await moderation_chats.listing(db,user_id=peer))["items"]
        first,second = await asyncio.gather(game.start(db,chat_id=cid,topic_id=0,actor=owner),game.start(other,chat_id=cid,topic_id=0,actor=peer))
        assert first["round_id"]==second["round_id"] and first["created"]!=second["created"]
        sid=first["round_id"]
        assert rules.normalize(" ЁЖ ")=="еж" and rules.next_letter("соловей")=="е" and rules.next_letter("конь")=="н"
        assert len(rules.WORDS)>50000 and rules.COMMON_WORDS
        await denied(game.play(db,chat_id=cid,topic_id=0,actor=owner,message_id=1,value="<script>"),"существительное")
        await denied(game.play(db,chat_id=cid,topic_id=0,actor=owner,message_id=1,value="ааббввгг"),"словаре")
        hints=await game.status(db,chat_id=cid,topic_id=0,hint=True)
        word=hints["hints"][0]
        before=await conns[0].fetchval("SELECT COALESCE(SUM(message_count),0) FROM daily_user_stats WHERE chat_id=$1",cid)
        result=await game.play(db,chat_id=cid,topic_id=0,actor=owner,message_id=1,value=word)
        assert result["turns"]==1 and result["bot_word"] not in {word,first["last_word"]}
        assert result["bot_word"].startswith(rules.next_letter(word))
        assert (await game.play(db,chat_id=cid,topic_id=0,actor=owner,message_id=1,value=word))["replayed"]
        await denied(game.play(db,chat_id=cid,topic_id=0,actor=peer,message_id=1,value=word),"другим")
        next_word=(await game.status(db,chat_id=cid,topic_id=0,hint=True))["hints"][0]
        await denied(game.play(db,chat_id=cid,topic_id=0,actor=owner,message_id=2,value=next_word),"секунды")
        async def attempt(adapter,actor,mid):
            try:
                return await game.play(adapter,chat_id=cid,topic_id=0,actor=actor,message_id=mid,value=next_word)
            except game.WordChainError:
                return None
        raced=await asyncio.gather(attempt(db,peer,2),attempt(other,peer,3))
        assert sum(r is not None for r in raced)==1,raced
        assert await conns[0].fetchval("SELECT COUNT(*) FROM word_chain_moves WHERE round_id=$1",sid)==2
        assert await conns[0].fetchval("SELECT COALESCE(SUM(message_count),0) FROM daily_user_stats WHERE chat_id=$1",cid)==before
        await denied(game.stop(db,chat_id=cid,topic_id=0,actor=999,can_moderate=False),"Завершить")
        alternate=await game.start(db,chat_id=cid,topic_id=11,actor=owner)
        assert alternate["round_id"]!=sid
        await db.execute("UPDATE chat_settings SET is_purging=TRUE WHERE chat_id=?",(cid,))
        paused=await game.status(db,chat_id=cid,topic_id=0,hint=True)
        assert paused["paused"]
        await denied(game.play(db,chat_id=cid,topic_id=0,actor=peer,message_id=999,value=paused["hints"][0]),"Игра ждёт")
        await denied(game.start(db,chat_id=cid,topic_id=12,actor=owner),"закрыт")
        await db.execute("UPDATE chat_settings SET is_purging=FALSE WHERE chat_id=?",(cid,))
        await db.execute("UPDATE word_chain_rounds SET updated_at=CLOCK_TIMESTAMP()-INTERVAL '25 hours' WHERE id=?",(sid,))
        fresh=await game.start(db,chat_id=cid,topic_id=0,actor=owner)
        assert fresh["round_id"]!=sid
        await game.stop(db,chat_id=cid,topic_id=0,actor=owner,can_moderate=False)
        # Correction buttons bind the original message to one round and turn.
        correction=await game.start(db,chat_id=cid,topic_id=77,actor=owner)
        choices=(await game.status(db,chat_id=cid,topic_id=77,hint=True))["hints"]
        async def correction_attempt(adapter,value):
            try:
                return await game.play(adapter,chat_id=cid,topic_id=77,actor=owner,message_id=500,value=value,
                                       expected_round=correction["round_id"],expected_turn=0)
            except game.WordChainError:
                return None
        corrected=await asyncio.gather(correction_attempt(db,choices[0]),correction_attempt(other,choices[1]))
        assert sum(x is not None for x in corrected)==1,corrected
        winner=next(x for x in corrected if x is not None)
        assert (await correction_attempt(db,winner["word"]))["replayed"]
        await denied(game.play(db,chat_id=cid,topic_id=77,actor=owner,message_id=501,value=choices[0],
                              expected_round=correction["round_id"],expected_turn=0),"продолжил")
        await game.stop(db,chat_id=cid,topic_id=77,actor=owner,can_moderate=False)
        await game.start(db,chat_id=cid,topic_id=77,actor=owner)
        await denied(game.play(db,chat_id=cid,topic_id=77,actor=owner,message_id=501,value=choices[0],
                              expected_round=correction["round_id"],expected_turn=0),"продолжил")
        # An empty last page clamps in one request rather than repeated page-back calls.
        ps=await purge.begin(db,chat_id=cid,actor=owner,norm=10,date_from="2026-10-01",date_to="2026-10-07",destination=cid,
                             action_id="qa",targets=[{"user_id":peer,"count":0,"days_in_chat":30,"warns":0,"required":10}])
        class ReadBudget:
            connection=db.connection
            statements=[]
            def execute(self,sql,args=()):
                self.statements.append(sql)
                return db.execute(sql,args)
        budget=ReadBudget()
        view=await purge.view(budget,chat_id=cid,page=999)
        assert len(budget.statements)==3,budget.statements
        assert not any("ALTER TABLE" in sql or "CREATE " in sql for sql in budget.statements)
        assert view["page"]==0 and len(view["items"])==1 and view["counts"]["blocked"]==0
        assert await conns[0].fetchval("SELECT COUNT(*) FROM word_chain_words WHERE round_id=$1",sid)==5
        print("PASS: word dictionary, single start, idempotency, race, cooldown, scope, expiry, ordinary activity, silent-owner chat discovery and purge pagination")
    finally:
        await db.execute("DELETE FROM purge_targets WHERE session_id IN (SELECT id FROM purge_sessions WHERE chat_id=?)",(cid,))
        await db.execute("DELETE FROM purge_sessions WHERE chat_id=?",(cid,))
        for table in ("word_chain_moves","word_chain_words"):
            await db.execute(f"DELETE FROM {table} WHERE round_id IN (SELECT id FROM word_chain_rounds WHERE chat_id=?)",(cid,))
        await db.execute("DELETE FROM word_chain_rounds WHERE chat_id=?",(cid,))
        await db.execute("DELETE FROM moderation_logs WHERE chat_id=?",(cid,))
        await db.execute("DELETE FROM chat_settings WHERE chat_id=?",(cid,))
        for uid in (owner,peer):
            await db.execute("DELETE FROM users WHERE user_tg_id=?",(uid,))
        for conn in conns:
            await conn.close()


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--dsn",required=True);args=p.parse_args()
    if urlparse(args.dsn).hostname not in {"localhost","127.0.0.1","::1"}:
        raise SystemExit("loopback database required")
    asyncio.run(run(args.dsn))
