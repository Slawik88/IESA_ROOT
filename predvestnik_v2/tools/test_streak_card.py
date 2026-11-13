"""Streak card delivery uses the shared bounded profile graph and safe fallback."""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "1:offline")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1:1/offline")
from bot.chat import streak as s
from bot.chat.targets import Target

async def main():
    class Db:   # a real adapter exposes release_if_idle (PGAdapter): graph_media gives the connection back before composing
        async def release_if_idle(self):
            return False

    for png, failure in [(b"png",False),(None,False),(b"png",True)]:
        message=SimpleNamespace(answer_photo=AsyncMock(side_effect=RuntimeError("offline") if failure else None))
        ctx=SimpleNamespace(db=Db(),message=message,args="",user_id=42,reply=AsyncMock())
        graph=AsyncMock(return_value=png)
        with patch.object(s,"resolve_target",AsyncMock(return_value=(Target(55,None,"<Name>"),""))), patch.object(s,"streak_of",AsyncMock(return_value=(4,12,True))), patch.object(s.activity_graph,"get_graph",graph):
            await s.cmd_streak(ctx)
        graph.assert_awaited_once_with(ctx.db,55)
        if png and not failure:
            ctx.reply.assert_not_awaited()
            text=message.answer_photo.call_args.kwargs["caption"]
            assert "&lt;Name&gt;" in text and "12" in text and "во всех чатах" in text
            assert len(text.encode("utf-16-le"))//2 < 1024
        else:
            ctx.reply.assert_awaited_once()
    ctx=SimpleNamespace(db=None,message=None,args="@unknown",user_id=42,reply=AsyncMock())
    with patch.object(s,"resolve_target",AsyncMock(return_value=(None,""))):
        await s.cmd_streak(ctx)
    ctx.reply.assert_awaited_once_with(s.NOT_FOUND)
    print("streak photo, shared user scope, escaped caption, fallback and missing target OK")

if __name__=="__main__":
    asyncio.run(main())
