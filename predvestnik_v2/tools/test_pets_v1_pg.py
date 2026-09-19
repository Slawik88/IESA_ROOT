"""Real PostgreSQL proof for active-pet ownership, replay and slot-cost rules."""
from __future__ import annotations
import argparse, asyncio, pathlib, sys
from urllib.parse import urlparse
import asyncpg
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import pets_v1 as repo
from infrastructure.repositories import echo_shards_v1 as echo_repo
from services import pets_v1

def local_dsn(value: str) -> str:
    parsed=urlparse(value)
    if parsed.scheme not in {"postgres","postgresql"} or parsed.hostname not in {"127.0.0.1","localhost","::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value

async def run(dsn:str)->None:
    conn=await asyncpg.connect(dsn); db=PGAdapter(conn); tx=conn.transaction(); await tx.start()
    try:
        async def must_reject(sql: str, args: tuple, message: str) -> None:
            try:
                async with db.connection.transaction():
                    await db.execute(sql, args)
            except Exception:
                return
            raise AssertionError(message)

        await repo.ensure_tables(db)
        await echo_repo.ensure_tables(db)
        user,other=976101,976102
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?),(?,?,?,?)",(user,"A","cat","common",user,"B","cat","common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=? ORDER BY id",(user,)) as c: ids=[r[0] for r in await c.fetchall()]
        initial=await pets_v1.overview(db,user)
        assert len(initial["pets"])==2 and initial["pets"][0]["endurance"]==100
        try: await pets_v1.start_activity(db,user_id=other,kind="trek",hours=3,action_id="no-active")
        except Exception: pass
        else: raise AssertionError("activity must require an active owned pet")
        first=await pets_v1.select_active_pet(db,user,ids[0],"activate-a")
        assert first["active_pet_id"]==ids[0]
        replay=await pets_v1.select_active_pet(db,user,ids[0],"activate-a")
        assert replay["idempotent_replay"]
        moved=await pets_v1.select_active_pet(db,user,ids[1],"activate-b")
        assert moved["previous_pet_id"]==ids[0] and moved["previous_pet_endurance"]==95
        shown=await pets_v1.overview(db,user)
        assert shown["active_pet_id"]==ids[1] and shown["pets"][0]["endurance"]==95
        await db.execute("INSERT INTO chest_food_balances_v1(user_id,food_id,quantity) VALUES (?, 'food_basic',1)",(user,))
        fed=await pets_v1.feed_pet(db,user_id=user,pet_id=ids[0],food_id="food_basic",action_id="feed-a")
        assert fed["endurance"]==100 and fed["remaining"]==0
        fed_replay=await pets_v1.feed_pet(db,user_id=user,pet_id=ids[0],food_id="food_basic",action_id="feed-a")
        assert fed_replay["idempotent_replay"] and fed_replay["endurance"]==100
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND metric='pet_fed'",(user,)) as c:
            assert int((await c.fetchone())[0])==1
        run=await pets_v1.start_activity(db,user_id=user,kind="trek",hours=3,action_id="trek-a")
        assert run["activity"]["kind"]=="trek" and run["activity"]["status"]=="active"
        assert run["endurance_cost"]==25 and run["endurance"]==75
        replay_run=await pets_v1.start_activity(db,user_id=user,kind="trek",hours=3,action_id="trek-a")
        assert replay_run["idempotent_replay"] and replay_run["endurance"]==75
        async with db.execute("SELECT endurance FROM pet_v1_state WHERE user_id=? AND pet_id=?",(user,ids[1])) as c:
            assert int((await c.fetchone())[0])==75, "a replay must not debit endurance twice"
        try: await pets_v1.start_activity(db,user_id=user,kind="expedition",hours=3,action_id="expedition-a")
        except pets_v1.PetConflict: pass
        else: raise AssertionError("one shared pet timer must reject a second activity")
        try: await pets_v1.select_active_pet(db,user,ids[0],"activate-b")
        except pets_v1.PetConflict: pass
        else: raise AssertionError("conflicting action id must fail")
        try: await pets_v1.select_active_pet(db,other,ids[0],"foreign")
        except Exception: pass
        else: raise AssertionError("foreign pet must fail")
        decision_user=976103
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)",(decision_user,"C","cat","common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=?",(decision_user,)) as c: decision_pet=(await c.fetchone())[0]
        await pets_v1.select_active_pet(db,decision_user,decision_pet,"activate-decision")
        expedition=await pets_v1.start_activity(db,user_id=decision_user,kind="expedition",hours=3,action_id="expedition-decision")
        assert expedition["activity"]["status"]=="active"
        await db.execute("UPDATE pet_v1_runs SET status='ready',ready_at=NOW(),ends_at=NOW()-INTERVAL '1 second' WHERE user_id=?",(decision_user,))
        chosen=await pets_v1.choose_expedition(db,user_id=decision_user,decision="careful",action_id="route-careful")
        assert chosen["activity"]["decision"]=="careful" and chosen["activity"]["status"]=="claimed"
        assert chosen["completed_without_reward"] is False and chosen["amount_keys"] == 1
        async with db.execute("SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=? AND family='pets'",(decision_user,)) as c:
            assert int((await c.fetchone())[0])==1
        chosen_replay=await pets_v1.choose_expedition(db,user_id=decision_user,decision="careful",action_id="route-careful")
        assert chosen_replay["idempotent_replay"]
        try: await pets_v1.choose_expedition(db,user_id=decision_user,decision="bold",action_id="route-bold")
        except pets_v1.PetConflict: pass
        else: raise AssertionError("a ready expedition must accept exactly one route choice")
        next_run=await pets_v1.start_activity(db,user_id=decision_user,kind="trek",hours=3,action_id="after-route")
        assert next_run["activity"]["status"]=="active", "a chosen route must release the shared timer"
        trek_user=976104
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)",(trek_user,"D","cat","common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=?",(trek_user,)) as c: trek_pet=(await c.fetchone())[0]
        await pets_v1.select_active_pet(db,trek_user,trek_pet,"activate-trek")
        await pets_v1.start_activity(db,user_id=trek_user,kind="trek",hours=3,action_id="trek-due")
        await db.execute("UPDATE pet_v1_runs SET ends_at=NOW()-INTERVAL '1 second' WHERE user_id=?",(trek_user,))
        after_trek=await pets_v1.overview(db,trek_user)
        assert after_trek["activity"] is None, "a completed timer-only trek must release the shared slot"
        assert after_trek["activity_rewards"][0]["amount_keys"] == 1
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? AND metric='pet_activity_completed'",(trek_user,)) as c:
            assert int((await c.fetchone())[0])==1
        restarted=await pets_v1.start_activity(db,user_id=trek_user,kind="expedition",hours=3,action_id="after-trek")
        assert restarted["activity"]["status"]=="active", "a completed trek must not block the next activity"
        exhausted_user=976106
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)",(exhausted_user,"Tired","hare","common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=?",(exhausted_user,)) as c: exhausted_pet=(await c.fetchone())[0]
        await pets_v1.select_active_pet(db,exhausted_user,exhausted_pet,"activate-tired")
        state=await repo.get_state(db,exhausted_user,exhausted_pet)
        await repo.save_endurance(db,exhausted_user,exhausted_pet,24)
        try: await pets_v1.start_activity(db,user_id=exhausted_user,kind="trek",hours=3,action_id="too-tired")
        except pets_v1.PetPolicyError: pass
        else: raise AssertionError("an exhausted pet must not start an activity")
        async with db.execute("SELECT COUNT(*) FROM pet_v1_runs WHERE user_id=?",(exhausted_user,)) as c:
            assert int((await c.fetchone())[0])==0
        gated_user=976107
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)",(gated_user,"Gated","finch","common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=?",(gated_user,)) as c: gated_pet=(await c.fetchone())[0]
        await pets_v1.select_active_pet(db,gated_user,gated_pet,"activate-gated")
        await pets_v1.start_activity(db,user_id=gated_user,kind="trek",hours=3,action_id="gated-trek")
        await db.execute("UPDATE pet_v1_runs SET status='claimed',ends_at=NOW()-INTERVAL '1 second' WHERE user_id=?",(gated_user,))
        await db.execute("INSERT INTO system_flags(key,enabled,label) VALUES ('content_chests_v1',0,'test') ON CONFLICT(key) DO UPDATE SET enabled=0")
        assert await pets_v1._settle_activity_keys(db,gated_user)==[]
        async with db.execute("SELECT COUNT(*) FROM pet_v1_activity_rewards WHERE user_id=?",(gated_user,)) as c:
            assert int((await c.fetchone())[0])==0, "disabled chests must preserve the completed run without minting"
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key='content_chests_v1'")
        settled=await pets_v1._settle_activity_keys(db,gated_user)
        assert len(settled)==1 and settled[0]["amount_keys"]==1
        duplicate_user=976105
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)",(duplicate_user,"Duplicate","cat","common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=?",(duplicate_user,)) as c: duplicate_pet=(await c.fetchone())[0]
        try: await pets_v1.apply_duplicate_progression(db,user_id=duplicate_user,pet_id=duplicate_pet,source_event_id="missing-source")
        except pets_v1.PetPolicyError: pass
        else: raise AssertionError("a duplicate must require a terminal source receipt")
        for index in range(15):
            await db.execute(
                "INSERT INTO pet_v1_duplicate_sources(user_id,source_event_id,pet_id,source_kind,source_snapshot) VALUES (?,?,?,'chest_v1','{}'::jsonb)",
                (duplicate_user,f"duplicate-{index}",duplicate_pet),
            )
            result=await pets_v1.apply_duplicate_progression(
                db,user_id=duplicate_user,pet_id=duplicate_pet,source_event_id=f"duplicate-{index}",
            )
            assert result["outcome"]=="level_up" and result["level_before"]==index+1 and result["level_after"]==index+2
            assert result["echo_amount"]==0
        await db.execute(
            "INSERT INTO pet_v1_duplicate_sources(user_id,source_event_id,pet_id,source_kind,source_snapshot) VALUES (?,?,?,'chest_v1','{}'::jsonb)",
            (duplicate_user,"duplicate-16",duplicate_pet),
        )
        terminal=await pets_v1.apply_duplicate_progression(
            db,user_id=duplicate_user,pet_id=duplicate_pet,source_event_id="duplicate-16",
        )
        assert terminal["outcome"]=="max_compensated" and terminal["level_before"]==terminal["level_after"]==16
        assert terminal["echo_amount"]==1
        replay_terminal=await pets_v1.apply_duplicate_progression(
            db,user_id=duplicate_user,pet_id=duplicate_pet,source_event_id="duplicate-16",
        )
        assert replay_terminal["idempotent_replay"] and replay_terminal["echo_amount"]==1
        try: await pets_v1.apply_duplicate_progression(db,user_id=duplicate_user,pet_id=ids[0],source_event_id="duplicate-16")
        except pets_v1.PetConflict: pass
        else: raise AssertionError("duplicate source id must reject a different pet")
        async with db.execute("SELECT level FROM pet_v1_state WHERE user_id=? AND pet_id=?",(duplicate_user,duplicate_pet)) as c:
            assert int((await c.fetchone())[0])==16
        async with db.execute("SELECT balance FROM echo_shard_accounts_v1 WHERE user_id=?",(duplicate_user,)) as c:
            assert int((await c.fetchone())[0])==1
        async with db.execute("SELECT COUNT(*) FROM echo_shard_ledger_v1 WHERE user_id=?",(duplicate_user,)) as c:
            assert int((await c.fetchone())[0])==1
        await must_reject(
            "UPDATE pet_v1_duplicate_progressions SET outcome='level_up' WHERE user_id=? AND source_event_id=?",
            (duplicate_user,"duplicate-16"), "pet duplicate progression receipt must be append-only",
        )
        await must_reject(
            "UPDATE pet_v1_duplicate_sources SET pet_id=? WHERE user_id=? AND source_event_id=?",
            (ids[0],duplicate_user,"duplicate-16"), "terminal duplicate source must be append-only",
        )
    finally:
        await tx.rollback(); await conn.close()
    print("OK: pets v1 PostgreSQL ownership, replay, active-slot debit, route completion and shared timer release")

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--dsn",type=local_dsn,required=True); args=p.parse_args(); asyncio.run(run(args.dsn))
