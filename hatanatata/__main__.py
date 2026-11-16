"""python -m hatanatata: one process, no web server or public ports."""

import asyncio
import logging
import os
import signal
from pathlib import Path

import aiohttp

from .bot import Bot
from .network import Fetcher, session
from .scanner import run_scanner
from .store import Store
from .telegram import Telegram

log = logging.getLogger(__name__)


async def main():
    token = os.environ["HATANATATA_BOT_TOKEN"]
    allowed_ids = [
        int(x.strip()) for x in os.environ["HATANATATA_ALLOWED_IDS"].split(",")
    ]
    if len(set(allowed_ids)) != 2 or any(x <= 0 for x in allowed_ids):
        raise RuntimeError("Exactly two positive Telegram user IDs required")
    path = Path(os.environ.get("HATANATATA_STATE", "/var/lib/hatanatata/state.db"))
    store = Store(path)
    for user_id in allowed_ids:
        store.ensure_user(user_id)
    # A second local invocation must fail before contacting Telegram.
    lock = path.with_suffix(".lock").open("w")
    try:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        raise RuntimeError(
            "Production entry point requires Linux file locking"
        ) from None
    for user_id in allowed_ids:
        store.add_source_once(user_id, "rentola")
    async with (
        session() as web,
        aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=3)
        ) as telegram_session,
    ):
        telegram = Telegram(token, telegram_session)
        await telegram.setup()
        bot = Bot(store, telegram, allowed_ids)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        workers = [
            asyncio.create_task(bot.poll()),
            asyncio.create_task(bot.deliver()),
            asyncio.create_task(run_scanner(store, Fetcher(store, web))),
        ]
        stop_task = asyncio.create_task(stop.wait())
        log.info("HataNatata started; private recipients=%s", len(allowed_ids))
        try:
            done, _ = await asyncio.wait(
                [*workers, stop_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                if task is not stop_task:
                    task.result()
        finally:
            for task in [*workers, stop_task]:
                task.cancel()
            await asyncio.gather(*workers, stop_task, return_exceptions=True)
            store.close()
            lock.close()


if __name__ == "__main__":
    os.umask(0o077)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 -- process boundary must redact all token-bearing exceptions
        # Even unexpected network exceptions must not print token-bearing URLs.
        log.error("Service stopped: %s", type(exc).__name__)
        raise SystemExit(1) from None
