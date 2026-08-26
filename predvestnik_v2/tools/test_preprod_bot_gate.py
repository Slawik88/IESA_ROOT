import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.middlewares.preprod_gate_mw import preprod_gate_middleware


async def main() -> None:
    previous = {
        "PREDVESTNIK_ENV": os.environ.get("PREDVESTNIK_ENV"),
        "PREPROD_ALLOWED_TG_IDS": os.environ.get("PREPROD_ALLOWED_TG_IDS"),
    }
    calls: list[int] = []

    async def handler(_event, data):
        calls.append(data["event_from_user"].id)
        return "handled"

    try:
        os.environ["PREDVESTNIK_ENV"] = "preprod"
        os.environ["PREPROD_ALLOWED_TG_IDS"] = "101"
        event = SimpleNamespace(from_user=None)

        allowed = await preprod_gate_middleware(
            handler, event, {"event_from_user": SimpleNamespace(id=101)}
        )
        denied = await preprod_gate_middleware(
            handler, event, {"event_from_user": SimpleNamespace(id=202)}
        )
        missing_actor = await preprod_gate_middleware(handler, event, {})
        malformed_actor = await preprod_gate_middleware(
            handler, event, {"event_from_user": SimpleNamespace(id="101")}
        )
        boolean_actor = await preprod_gate_middleware(
            handler, event, {"event_from_user": SimpleNamespace(id=True)}
        )
        assert allowed == "handled"
        assert denied is None
        assert missing_actor is None
        assert malformed_actor is None
        assert boolean_actor is None
        assert calls == [101]

        os.environ["PREPROD_ALLOWED_TG_IDS"] = ""
        empty_allowlist = await preprod_gate_middleware(
            handler, event, {"event_from_user": SimpleNamespace(id=101)}
        )
        assert empty_allowlist is None
        assert calls == [101]

        os.environ["PREDVESTNIK_ENV"] = "production"
        production = await preprod_gate_middleware(
            handler, event, {"event_from_user": SimpleNamespace(id=202)}
        )
        assert production == "handled"
        assert calls == [101, 202]

        main_source = (Path(__file__).resolve().parents[1] / "bot/__main__.py").read_text(
            encoding="utf-8"
        )
        assert main_source.index("dp.update.middleware(preprod_gate_middleware)") < (
            main_source.index("dp.update.middleware(db_middleware)")
        )
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print("OK: preprod Telegram polling allowlist fails closed")


asyncio.run(main())
