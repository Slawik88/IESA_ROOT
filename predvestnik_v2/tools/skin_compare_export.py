"""Read one checkout in an isolated process; export real look payloads and chat cards."""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import date
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cards", action="store_true")
    parser.add_argument("--only")
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / "predvestnik_v2"))
    os.environ["BOT_TOKEN"] = "1:x"
    os.environ["DATABASE_URL"] = "postgresql://unused/unused"
    os.environ["LOGURU_LEVEL"] = "ERROR"
    from core.skins_v3 import TIERS
    from core.skins_v3_catalog import SKINS, SETS, SEASONS
    from services.skins_v3 import look_payload

    args.out.mkdir(parents=True, exist_ok=True)
    payload = {"catalog": SKINS, "sets": SETS, "seasons": SEASONS,
               "looks": {sid: {tier: look_payload(sid, tier) for tier in TIERS} for sid in SKINS}}
    (args.out / "catalog.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if args.cards:
        from PIL import Image
        from bot.chat import activity_graph, skin_card
        from core.skins_v3_chat import chat_look
        card_dir = args.out / "cards"
        card_dir.mkdir(exist_ok=True)
        selected = args.only.split(",") if args.only else list(SKINS)
        for sid in selected:
            graph = activity_graph.render([4, 12, 7, 19, 10, 17, 14], date(2026, 10, 1),
                                          theme=skin_card.theme_for(chat_look(sid, "D")))
            for tier in TIERS:
                card = skin_card.compose(graph, chat_look(sid, tier), "Предвестник", None)
                image = Image.open(io.BytesIO(card)).convert("RGB")
                image.save(card_dir / f"{sid}-{tier}.png")
        print(f"chat cards: {len(selected) * len(TIERS)}")


if __name__ == "__main__":
    main()
