#!/usr/bin/env python3
"""Silhouette art of the skin scenes (FastAPI/static/skin-scene-{a,b,c,d}-v3.css): the pictures are drawn in tools/scene_art_{a,b,c,d}.py (kit: tools/scene_kit.py)
and baked into data-URI classes.

    python tools/scene_art.py          # rewrites the four skin-scene-*-v3.css files (never edit them by hand)
    python tools/scene_art.py --check  # fails when the files on disk differ from what the art files draw

A class `i-<name>` sets `--img`; a scene layer picks it with `sil i-<name>` (a coloured picture) or `sil m i-<name>` (a mask coloured by the layer), see app.35–38.js and skin-scene-v3.css.
Keep every picture small: it is a CSS background, drawn once, never animated by itself.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene_kit import ARTS  # noqa: E402

STATIC = Path(__file__).resolve().parents[1] / "FastAPI/static"
HEAD = {
    "a": "образы D и C: Лесной Странник, Песчаная Тропа, Тихая Гавань, Пруд Лотосов, Порог, Изморозь, Медные Сумерки, Бутон Сакуры",
    "b": "образы B и A: Инферно, Ханами, Нефритовый Двор, Небесное Сияние, Рубиновый Собор, Лазурная Обсерватория, Золотой Лотос",
    "c": "образы S, SS и SSS: Бездна, Северное Сияние, Расплавленное Солнце, Лепестковый Вихрь, Артефакт, Лунный Лотос, Прилив Рюдзина, Полуночная Комета, Хроно-ткач, Сердце Звезды",
    "d": "сезонные и личные образы: Тыквенный Фонарь, Паутина Полуночи, Час Ведьм, Снежный Шар, Огни Гирлянды, Бой Курантов, Алая Звезда, Багровый Мрак",
}
for letter in HEAD:
    importlib.import_module(f"scene_art_{letter}")


def render() -> dict[str, str]:
    out = {}
    for letter, head in HEAD.items():
        lines = [f"/* ═══ СЦЕНА · картинки · {letter.upper()} ({head}) ═══", "   Файл создаёт tools/scene_art.py, руками не править. Класс i-<имя> задаёт --img для слоя «sil». */"]
        lines += [f".i-{name} {{ --img: {value}; }}" for name, (l, value) in ARTS.items() if l == letter]
        out[f"skin-scene-{letter}-v3.css"] = "\n".join(lines) + "\n"
    return out


def main() -> int:
    files = render()
    if "--check" in sys.argv:
        bad = [name for name, text in files.items() if not (STATIC / name).exists() or (STATIC / name).read_text(encoding="utf-8") != text]
        if bad:
            print("scene art is out of date, run tools/scene_art.py:", *bad); return 1
        print("OK: scene art matches tools/scene_art*.py"); return 0
    for name, text in files.items():
        (STATIC / name).write_text(text, encoding="utf-8")
    print("wrote", *files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
