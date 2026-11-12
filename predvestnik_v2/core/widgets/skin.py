"""Образ игрока в виджете: виджет собирается под надетый образ целиком, как карточка «бот я» и рамки ответов в чате.

Та же косметика, что в других окнах игры, и тот же порядок «уровень добавляет богатство»:
    D…  цвета образа: фон, текст, поверхности, акцент, полоски в его палитре, мягкое свечение
    B   узоры набора: скобки имени (core/skins_v3_chat_kits.py), разделитель со знаком образа
    A   сцена образа во всю карточку — вихрь, сетка, лучи, звёзды… (kinds.bg), ореол вокруг значка (kinds.halo)
    S   рамка образа (kinds.frame) и линия-орнамент снизу, имя в цвете образа
    SS  искры образа в шапке (знак частиц kinds.pt)
    SSS фраза образа, корона и бегущий блик
Значки строк «серия» и «кошелёк» — те же, что у образа в чате (core.skins_v3_chat.ICONS).

Карточка тёмная в любой теме Telegram: образы тёмные, как приложение и картинка «бот я». HTML виджета после отправки
не меняется, поэтому образ «вшивается» при отправке (core.widgets.html), а в состоянии едет только его подпись
`k` (`<образ>:<уровень>`): сменил образ — виджет предложит прислать новое табло.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from core.skins_v3 import TIERS, contrast

# Без образа — «Обсидиан», как приложение без скина (FastAPI/static/shell-v3.css).
NO_SKIN: Final = {"bg": "#08090c", "acc": "#d8cffd", "pal": ("#d8cffd", "#7862ff", "#9fb4ff"), "ink": "#f3f4f7", "dim": "#8a90a2"}
KIT_FROM: Final = "B"      # узоры набора — с того же уровня, что разделитель в чате (SEP_FROM)
SCENE_FROM: Final = "A"
FRAME_FROM: Final = "S"    # как рамка ответа в чате (FRAME_FROM)
SPARKS_FROM: Final = "SS"
SHINE_AT: Final = "SSS"    # как фраза образа в чате (PHRASE_AT)
FRAME_LINE: Final = {"double": "3px double", "dash": "2px dashed", "seg": "2px dashed", "ring": "2px solid", "drip": "2px dotted"}
OK_COLOR: Final = "#7fd6a4"
BAD_COLOR: Final = "#ff8a8a"


def reached(tier: str, step: str) -> bool:
    return tier in TIERS and TIERS.index(tier) >= TIERS.index(step)


def rgba(color: str, alpha: float) -> str:
    c = color.lstrip("#")
    return f"rgba({int(c[0:2], 16)},{int(c[2:4], 16)},{int(c[4:6], 16)},{f'{alpha:g}'.lstrip('0')})"


def scene(kind: str, pal: tuple[str, str, str], acc: str) -> str:
    """Фон сцены образа (kinds.bg) слоями градиентов — то, что в приложении рисует фон профиля, без color-mix и масок
    (их нет в профиле виджета)."""
    p0, p1, p2 = pal
    glow = f"radial-gradient(70% 45% at 50% 0,{rgba(p1, .22)},transparent 70%)"
    if kind == "mesh":
        return (f"radial-gradient(60% 40% at 8% 12%,{rgba(p0, .26)},transparent 70%),"
                f"radial-gradient(55% 40% at 96% 32%,{rgba(p1, .24)},transparent 70%),"
                f"radial-gradient(70% 35% at 50% 100%,{rgba(p2, .12)},transparent 70%)")
    if kind == "vortex":
        return (f"radial-gradient(38% 22% at 84% 3%,#000 0 34%,{rgba(p1, .5)} 52%,transparent 76%),"
                f"radial-gradient(95% 55% at 84% 3%,{rgba(p0, .2)},transparent 72%),"
                f"radial-gradient(60% 40% at 0 100%,{rgba(p2, .1)},transparent 70%)")
    if kind == "grid":
        line = rgba(acc, .09)
        return (f"linear-gradient({line} 1px,transparent 1px) 0 0/100% 22px,"
                f"linear-gradient(90deg,{line} 1px,transparent 1px) 0 0/22px 100%,{glow}")
    if kind == "rays":
        return f"repeating-linear-gradient(112deg,{rgba(p0, .09)} 0 2px,transparent 2px 20px),{glow}"
    if kind == "stars":
        dots = ",".join(f"radial-gradient({s}px {s}px at {x}% {y}%,#fff,transparent)"
                        for x, y, s in ((12, 9, 2), (40, 5, 1), (66, 16, 2), (86, 7, 1)))
        return f"{dots},{glow}"
    if kind == "aurora":
        return (f"linear-gradient(168deg,{rgba(p0, .28)},transparent 42%),"
                f"linear-gradient(192deg,transparent 18%,{rgba(p1, .22)},transparent 58%)")
    return (f"radial-gradient(110% 55% at 92% -5%,{rgba(p1, .3)},transparent 62%),"
            f"radial-gradient(80% 45% at 0 105%,{rgba(p2, .12)},transparent 62%)")


def halo(kind: str, pal: tuple[str, str, str], acc: str) -> str:
    """Ореол вокруг значка образа в шапке (kinds.halo): кольцо и свечение, без размытых теней."""
    p0, p1, _ = pal
    ring = {"orbit": "1.5px dashed", "ripple": "3px double", "rays": "2px dotted", "eclipse": "2px solid",
            "flame": "2px solid", "neon": "2px solid"}.get(kind, "1px solid")
    core = "#000" if kind == "eclipse" else rgba(p1, .35)
    return f"border:{ring} {acc};background:radial-gradient(closest-side,{core},{rgba(p0, .18)} 70%,transparent)"


def heat(color: str) -> str:
    """Клетки «сообщения за 9 недель»: четыре ступени цвета образа (как график «бот я»)."""
    return "".join(f".hm .l{n}{{background:{rgba(color, a) if a < 1 else color}}}" for n, a in ((1, .28), (2, .5), (3, .74), (4, 1)))


@dataclass(frozen=True)
class Look:
    signature: str   # «<образ>:<уровень>» или "" — подпись в состоянии (`k`)
    css: str         # правила образа поверх _base.css
    data: str        # `var L={…}` для шаблона: подписи, узоры, значки


def _plain() -> Look:
    c = NO_SKIN
    css = (f":root{{--bg:{c['bg']};--ink:{c['ink']};--h:{c['dim']};--a:{c['acc']};--on:#15112b;"
           f"--p0:{c['pal'][0]};--p1:{c['pal'][1]};--p2:{c['pal'][2]}}}"
           f"body{{background:{scene('wash', c['pal'], c['acc'])},{c['bg']}}}{heat(c['pal'][0])}")
    data = {"s": "", "t": "", "ti": "", "g": "🔮", "b": ["", ""], "i": ["💬", "🔥", "💰"],
            "d": "", "f": "", "ph": "", "pt": "", "q": ""}
    return Look("", css, "var L=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";")


@lru_cache(maxsize=512)
def look(skin_id: str | None, tier: str = "D") -> Look:
    """Образ для виджета; неизвестный образ или уровень — карточка без образа."""
    from core.skins_v3_catalog import SKINS
    from core.skins_v3_chat import chat_look
    from core.skins_v3_chat_kits import kit_of
    sid = skin_id or ""
    skin = SKINS.get(sid)
    chat = chat_look(sid, tier) if skin else None
    if skin is None or chat is None:
        return _plain()
    tokens, pal, kinds, kit = skin["tokens"], tuple(skin["pal"]), skin["kinds"], kit_of(sid)
    acc, bg = tokens["--v3-acc"], tokens["--v3-bg"]
    on = tokens["--v3-on-acc"] if contrast(tokens["--v3-on-acc"], acc) >= 4.5 else "#000000"
    rules = [f":root{{--bg:{bg};--ink:{tokens['--v3-ink']};--h:{tokens['--v3-dim']};--s:{tokens['--v3-sheet']};"
             f"--t:{tokens['--v3-track']};--a:{acc};--on:{on};--p0:{pal[0]};--p1:{pal[1]};--p2:{pal[2]};"
             f"--g:{pal[2] if pal[2].lower() != '#ffffff' else pal[0]}}}"]
    layers = scene(kinds.get("bg", "wash"), pal, acc) if reached(tier, SCENE_FROM) else scene("wash", pal, acc)
    rules.append(f"body{{background:{layers},{bg}}}{heat(pal[0])}")
    if reached(tier, SCENE_FROM):
        rules.append(f".halo{{{halo(kinds.get('halo', ''), pal, acc)}}}")
    if reached(tier, FRAME_FROM):
        rules.append(f".card{{border:{FRAME_LINE.get(kinds.get('frame', ''), '2px solid')} {rgba(acc, .7)}}}"
                     f".nm{{color:{pal[0]}}}")
    data = {
        "s": chat_signature(sid, tier), "t": tier, "ti": chat.title, "g": chat.glyph or "✦",
        "b": list(kit.title) if reached(tier, KIT_FROM) else ["", ""],
        "i": list(chat.icons), "d": chat.divider or "", "f": chat.frame or "", "ph": chat.phrase or "",
        "pt": kit.mark if reached(tier, SPARKS_FROM) else "", "q": kit.crown if tier == SHINE_AT else "",
    }
    return Look(chat_signature(sid, tier), "".join(rules),
                "var L=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";")


def chat_signature(skin_id: str | None, tier: str | None) -> str:
    return f"{skin_id}:{tier}" if skin_id else ""


def of(own: dict | None) -> Look:
    """Образ в форме services.skins_v3.own_look (None — образ не надет)."""
    return look(own["id"], own["tier"]) if own else look(None)


def ink_readable(skin_id: str) -> bool:
    """Текст и приглушённый текст образа читаются на его фоне (WCAG AA с запасом для мелкого текста)."""
    from core.skins_v3_catalog import SKINS
    tokens = SKINS[skin_id]["tokens"]
    return contrast(tokens["--v3-ink"], tokens["--v3-bg"]) >= 7 and contrast(tokens["--v3-dim"], tokens["--v3-bg"]) >= 4.5

