"""Путеводитель администрации: темы из FastAPI/static/bot-admin/guide-admin.json, отобранные под читателя.

Показывает их тот же экран, что Путеводитель игрока (Mini App, app.57.js), поэтому данные приходят в его формате:
группы → темы → блоки, словарь, вопросы. Роль видит только свои темы: с нужной ролью (`min_rank`) и из открытых ей
разделов (`section`); владелец чата — только темы с `owner`. Кнопка темы ведёт в раздел админки: `where.admin`.
"""
from __future__ import annotations

import copy
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "FastAPI", "static", "bot-admin", "guide-admin.json")
_data: dict | None = None


def data() -> dict:
    global _data
    if _data is None:
        with open(_PATH, encoding="utf-8") as source:
            _data = json.load(source)
    return _data


def _visible(topic: dict, *, rank: int, sections: set[str], owner: bool) -> bool:
    if owner:
        return bool(topic.get("owner"))
    section = topic.get("section")
    return rank >= int(topic.get("min_rank", 2)) and (not section or section in sections)


def for_reader(*, rank: int = 0, sections: set[str] | frozenset[str] = frozenset(), owner: bool = False) -> dict:
    """Темы, словарь и вопросы, которые нужны этому читателю; группы без тем не показываются."""
    source = data()
    topics = [copy.deepcopy(t) for t in source["topics"] if _visible(t, rank=rank, sections=set(sections), owner=owner)]
    ids = {t["id"] for t in topics}
    for t in topics:
        where = t["where"]
        go = where.pop("go", "")
        if go and go in sections:   # «Открыть»: раздел админки, если он открыт этому читателю
            where["admin"] = go
        else:
            where["label"] = ""
        where.setdefault("path", "")
        where.setdefault("label", "")
        t["next"] = [n for n in t.get("next", []) if n in ids]
        for key in ("min_rank", "section", "actions", "owner"):
            t.pop(key, None)
    groups = [{**g, "topics": [i for i in g["topics"] if i in ids]} for g in source["groups"]]
    return {"version": source["version"], "groups": [g for g in groups if g["topics"]], "topics": topics,
            "glossary": [g for g in source["glossary"] if g["t"] in ids], "faq": [f for f in source["faq"] if f["t"] in ids]}
