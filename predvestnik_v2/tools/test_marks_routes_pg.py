"""Read-only fact projection from real, owned expedition receipts; rollback only."""
import asyncio,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
async def main():
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import marks_v1 as repo
    c=await asyncpg.connect(os.environ['DATABASE_URL']);tx=c.transaction();await tx.start()
    try:
        # Temporary table shadows production-shaped storage without altering it.
        await c.execute("""CREATE TEMP TABLE pet_v2_runs(user_id BIGINT,kind TEXT,status TEXT,route TEXT,claimed_at TIMESTAMPTZ) ON COMMIT DROP;
          INSERT INTO pet_v2_runs VALUES
          (1,'expedition','claimed','forest',NOW()),(1,'expedition','claimed','forest',NOW()),
          (1,'expedition','claimed','pass',NOW()),(1,'trek','claimed','ruins',NOW()),
          (1,'expedition','active','ruins',NULL),(2,'expedition','claimed','ruins',NOW()),
          (1,'expedition','claimed','swamp',NOW()+INTERVAL '1 day');""")
        db=PGAdapter(c)
        assert await repo.completed_pet_routes(db,1)==2
        await c.execute("INSERT INTO pet_v2_runs VALUES(1,'expedition','claimed','ruins',NOW()),(1,'expedition','claimed','swamp',NOW())")
        assert await repo.completed_pet_routes(db,1)==4
        assert await repo.completed_pet_routes(db,2)==1
        print('PASS cartographer facts: owned, distinct, claimed expedition-only, four routes, no future rows')
    finally:await tx.rollback();await c.close()
if __name__=='__main__':asyncio.run(main())
