"""Read-only live adapter smoke check; never uses a Telegram token or live DB."""

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from .models import SOURCES, Search
from .network import Fetcher, session
from .scanner import collect
from .sources import SourceError, search_url
from .store import Store


async def check(city, selected_source=None):
    with tempfile.TemporaryDirectory(prefix="hatanatata-check-") as temp:
        store = Store(Path(temp) / "test.db")
        async with session() as web:
            fetcher = Fetcher(store, web)
            for source in [selected_source] if selected_source else SOURCES:
                try:
                    page = await collect(
                        fetcher, source, city, search_url(source, city)
                    )
                    result = {
                        "source": source,
                        "count": len(page.listings),
                        "partial": page.partial,
                        "matches": sum(
                            Search(cities=[city]).matches(x) for x in page.listings
                        ),
                    }
                except (SourceError, ValueError, KeyError, TypeError) as exc:
                    result = {
                        "source": source,
                        "error": str(exc)
                        if isinstance(exc, SourceError)
                        else type(exc).__name__,
                    }
                print(json.dumps(result, ensure_ascii=False), flush=True)
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", default="Wetzikon ZH")
    parser.add_argument(
        "--source", choices=list(SOURCES), help="Check only this portal"
    )
    args = parser.parse_args()
    asyncio.run(check(args.city, args.source))
