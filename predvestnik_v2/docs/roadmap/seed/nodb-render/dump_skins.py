#!/usr/bin/env python3
"""Выгружает каталог образов в build/skins.js и build/skins.json для стенда без базы.

Запуск из этой папки:  python3 -I dump_skins.py
Каталог читается из core/skins_v3_catalog.py (чистый модуль, зависимостей не требует).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # predvestnik_v2/
sys.path.insert(0, str(ROOT))

from core import skins_v3 as v3  # noqa: E402
from core import skins_v3_catalog as catalog  # noqa: E402

data = {}
for skin_id, skin in catalog.SKINS.items():
    data[skin_id] = {
        "id": skin_id,
        "name": skin["name"],
        "rarity": skin["tier"],
        "pal": skin["pal"],
        "kinds": skin["kinds"],
        "sig": skin["sig"],
        "sig_from": v3.signature_tier(skin["tier"]),
        "ceiling": v3.CEILING,
        "title": skin["items"]["title"],
        "tokens": skin["tokens"],
    }

out = HERE / "build"
out.mkdir(exist_ok=True)
(out / "skins.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
(out / "skins.js").write_text("window.SKINS_DATA=" + json.dumps(data, ensure_ascii=False) + ";", encoding="utf-8")
print(f"skins: {len(data)} -> {out}")
