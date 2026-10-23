"""Set «Тайное Знание»: Тихая Библиотека (B), Лаборатория Алхимика (A), Живой Гримуар (S).

Every picture stands in a lower corner of its scene (the avatar and the name in the middle stay clear) or is a thin mask
ring around the avatar. Coloured pictures keep dark tones of their skin; masks are filled by the layer colour.
"""
import random

from scene_kit import art, circ, ell, n, path, rect, stroke, svg


def F(name, body, w=160, h=200, fit="xMidYMax meet"):
    art(name, "f", svg(w, h, body, fit))


# ── Тихая Библиотека: полка до потолка, стол с раскрытой книгой и свечой, страница в полёте ─────────────────────
def _books(rng, x0, x1, base, top, palette):
    out, x = [], x0
    while x < x1 - 4:
        w = rng.choice((5, 6, 7, 8, 9))
        h = rng.randint(top, base - 4) if rng.random() < .82 else base - top - 6
        lean = rng.random() < .1
        color = rng.choice(palette)
        y = base - (base - h if not lean else (base - top) - 8)
        if lean:
            out.append(f"<path fill='{color}' d='M{n(x)} {base}L{n(x + w)} {base}L{n(x + w + 6)} {base - 28}L{n(x + 6)} {base - 28}z'/>")
            x += w + 7
            continue
        hh = base - y if base - y > 10 else 26
        out.append(rect(x, base - hh, w, hh, color))
        out.append(rect(x + 1, base - hh + 4, w - 2, 1.4, "#c9a56a", "fill-opacity='.55'"))
        if rng.random() < .5:
            out.append(rect(x + 1, base - 6, w - 2, 1.2, "#c9a56a", "fill-opacity='.4'"))
        x += w + rng.choice((0, 0, 1))
    return "".join(out)


def _shelves():
    rng = random.Random(7)
    books = ("#5a2f24", "#2f4a3c", "#6b5631", "#3b2f4f", "#4a3a22", "#6a3a2a")
    body = [rect(6, 0, 148, 200, "#1c140c"), rect(6, 0, 7, 200, "#2a1d12"), rect(147, 0, 7, 200, "#2a1d12")]
    for base in (46, 96, 146, 196):
        body.append(_books(rng, 14, 146, base - 3, base - 40, books))
        body.append(rect(6, base - 3, 148, 5, "#3a2817"))
        body.append(rect(6, base - 3, 148, 1.2, "#6b4c2c"))
    body.append(stroke("M118 200L136 8M148 200L154 40M121 170h29M124 140h27M127 110h25M130 80h22M133 50h20", "#5b4128", 3))
    return "".join(body)


F("libShelves", _shelves())
F("libDesk", "".join([
    rect(8, 150, 144, 9, "#3a2817"), rect(8, 150, 144, 1.5, "#7a5733"), rect(16, 159, 7, 41, "#2a1d12"), rect(137, 159, 7, 41, "#2a1d12"),
    path("M30 150Q48 132 78 140L78 150Z", "#e9d3a3"), path("M126 150Q108 132 78 140L78 150Z", "#dcc391"),
    stroke("M36 144q12-6 34-2M36 147q14-5 34-1M120 144q-12-6-34-2M120 147q-14-5-34-1", "#9a7444", .8),
    path("M78 140v10", "#000", "stroke='#9a7444' stroke-width='1'"),
    rect(122, 112, 9, 38, "#efe0bf"), path("M122 112q3 6 1 12M131 115q-2 7 0 13", "none", "stroke='#d8c4a0' stroke-width='1.4'"),
    path("M118 150h17l-3-6h-11Z", "#7a5733"), path("M126.5 112q-5-9 0-17 5 8 0 17Z", "#ffd38a"), path("M126.5 109q-2-4 0-8 2 4 0 8Z", "#fff4dc"),
    ell(44, 147, 7, 3, "#14100b"), path("M40 147v-7h8v7Z", "#14100b"), stroke("M46 140Q60 112 74 104", "#c9a56a", 1.4),
    path("M74 104q-10 4-15 12 9-3 15-12Z", "#e9d3a3"),
]))
F("libPage", path("M8 10Q30 4 52 10L50 66Q28 60 6 66Z", "#000") + stroke("M14 22q16-3 30 0M14 30q16-3 30 0M14 38q16-3 26 0", "#000", 1.2, "stroke-opacity='.0'"), 60, 76, "xMidYMid meet")

# ── Лаборатория Алхимика: колба на треноге над огнём, полка банок, кольцо знаков стихий ─────────────────────────
F("alcRetort", "".join([
    stroke("M40 196L60 132M120 196L100 132M48 172h64", "#4b3218", 4),
    ell(80, 132, 30, 5, "#6b4a24"), path("M66 190q14-26 14-40 0 14 14 40Z", "#d8973f", "fill-opacity='.85'"), path("M74 190q6-14 6-24 0 10 6 24Z", "#ffe0a0"),
    circ(80, 100, 30, "#1d3a2c", "stroke='#9fe8c2' stroke-width='2' stroke-opacity='.55'"),
    path("M52 108q28 14 56 0 0 22-28 22-28 0-28-22Z", "#3fcf86", "fill-opacity='.8'"),
    path("M70 72V40h20v32", "#1d3a2c", "stroke='#9fe8c2' stroke-width='2' stroke-opacity='.55'"),
    stroke("M90 46Q130 30 150 70L152 92", "#9fe8c2", 5, "stroke-opacity='.45'"),
    stroke("M90 46Q130 30 150 70L152 92", "#1d3a2c", 3),
    ell(152, 96, 6, 4, "#3fcf86", "fill-opacity='.7'"),
    circ(66, 92, 5, "#e9fff2", "fill-opacity='.35'"), circ(88, 112, 3, "#e9fff2", "fill-opacity='.5'"), circ(76, 118, 2, "#e9fff2", "fill-opacity='.5'"),
    rect(66, 34, 28, 7, "#b8763a"),
]))
F("alcShelf", "".join([
    rect(4, 96, 152, 6, "#4b3218"), rect(4, 96, 152, 1.4, "#8a5d2f"), rect(4, 176, 152, 6, "#4b3218"), rect(4, 176, 152, 1.4, "#8a5d2f"),
    path("M16 96V62q0-8 8-8h6q8 0 8 8v34Z", "#1d3a2c", "stroke='#9fe8c2' stroke-opacity='.4'"), rect(16, 74, 22, 22, "#3fcf86", "fill-opacity='.55'"),
    rect(14, 50, 26, 6, "#b8763a"), rect(18, 78, 18, 8, "#e9d3a3", "fill-opacity='.8'"),
    path("M52 96q-4-16 6-24V58h10v14q10 8 6 24Z", "#2a2410", "stroke='#d8973f' stroke-opacity='.5'"), rect(54, 82, 20, 14, "#d8973f", "fill-opacity='.6'"),
    path("M92 96V70l8-12h12l8 12v26Z", "#162a22", "stroke='#9fe8c2' stroke-opacity='.4'"), rect(92, 80, 28, 16, "#7a52e0", "fill-opacity='.45'"),
    circ(138, 84, 12, "#1d3a2c", "stroke='#9fe8c2' stroke-opacity='.4'"), rect(134, 66, 8, 8, "#1d3a2c"), path("M126 88q12 8 24 0v4q-12 8-24 0Z", "#3fcf86", "fill-opacity='.6'"),
    path("M20 176v-30h30v30Z", "#2a1d12"), stroke("M24 154h22M24 162h22M24 170h14", "#8a5d2f", 1.4),
    path("M66 176q-6-22 10-32 16 10 10 32Z", "#1d3a2c", "stroke='#9fe8c2' stroke-opacity='.35'"), path("M68 172q8-6 16 0v4H68Z", "#3fcf86", "fill-opacity='.6'"),
    rect(104, 140, 6, 36, "#e9d3a3"), rect(114, 150, 6, 26, "#e9d3a3"), rect(124, 132, 6, 44, "#d8c4a0"), rect(134, 156, 14, 20, "#5a3a20"),
]))


def _sigils():
    parts = ["<circle cx='100' cy='100' r='92' fill='none' stroke='#000' stroke-width='1.6'/>",
             "<circle cx='100' cy='100' r='84' fill='none' stroke='#000' stroke-width='.8' stroke-dasharray='2 5'/>"]
    marks = ("M-9 6 0-9 9 6Z", "M-9-6 0 9 9-6Z", "M-9 6 0-9 9 6ZM-6 1h12", "M-9-6 0 9 9-6ZM-6-1h12", "M-7 0a7 7 0 1 0 14 0 7 7 0 1 0-14 0M0-7v14")
    for i in range(10):
        import math
        a = i * 36 * math.pi / 180
        x, y = 100 + 92 * math.sin(a), 100 - 92 * math.cos(a)
        parts.append(f"<path transform='translate({n(x)} {n(y)}) rotate({i * 36})' fill='none' stroke='#000' stroke-width='2' stroke-linejoin='round' d='{marks[i % 5]}'/>")
    return "".join(parts)


F("alcSigils", _sigils(), 200, 200, "xMidYMid meet")

# ── Живой Гримуар: кафедра с раскрытой книгой, свечи, кольцо рун, страница в полёте ───────────────────────────
F("grimLectern", "".join([
    path("M70 200l6-70h8l6 70Z", "#2a1d33"), path("M50 200h60l-6-8H56Z", "#3a2a46"),
    path("M22 132l58-18 58 18-6 10-52-14-52 14Z", "#3a2a46", "stroke='#c9a35a' stroke-opacity='.45'"),
    path("M26 124Q52 100 80 112L80 124Q52 114 30 132Z", "#e9dcc0"), path("M134 124Q108 100 80 112L80 124Q108 114 130 132Z", "#ddcfae"),
    stroke("M36 118q18-8 38-4M38 124q16-6 34-3M124 118q-18-8-38-4M122 124q-16-6-34-3", "#7a52e0", 1),
    stroke("M44 108l4-8 4 8M48 100v-6M108 106l6-4 2 7M114 102l-4-6", "#c9a35a", 1.4),
    path("M80 112v12", "#000", "stroke='#b49a6a' stroke-width='1.2'"),
    path("M28 130q2 14 8 22M132 130q-2 14-8 22", "none", "stroke='#c9a35a' stroke-width='3' stroke-opacity='.7'"),
]))
F("grimCandles", "".join([
    rect(28, 120, 14, 80, "#e9dcc0"), rect(54, 146, 12, 54, "#ddcfae"), rect(78, 104, 16, 96, "#e9dcc0"),
    path("M28 120q4 10 2 22M42 124q-3 8-1 18M54 146q3 7 1 14M94 108q-3 10-1 20", "none", "stroke='#cbb894' stroke-width='2'"),
    path("M35 120q-6-11 0-21 6 10 0 21Z", "#ffcf7a"), path("M35 116q-2-5 0-10 2 5 0 10Z", "#fff6dc"),
    path("M60 146q-5-9 0-17 5 8 0 17Z", "#ffcf7a"), path("M86 104q-7-12 0-24 7 12 0 24Z", "#ffcf7a"), path("M86 100q-3-6 0-12 3 6 0 12Z", "#fff6dc"),
    path("M18 200q4-10 16-10h60q12 0 16 10Z", "#3a2a46"), ell(64, 200, 50, 4, "#2a1d33"),
]))


def _runes():
    import math
    glyphs = ("M0-7v14M0-4l5-3M0 0l5-3", "M-3-7v14M-3-7l5 3-5 3 6 8", "M-3-7v14M-3-3l5 3-5 3", "M0-7v14M0-6l5 3M0-2l5 3",
              "M4-7l-6 7 6 7", "M-5-7 5 7M5-7-5 7", "M-3-7v14M-3-7h5l-5 6", "M-4-7v14M4-7v14M-4-2l8 4")
    parts = ["<circle cx='100' cy='100' r='86' fill='none' stroke='#000' stroke-width='1'/>"]
    for i in range(16):
        a = i * 22.5 * math.pi / 180
        x, y = 100 + 94 * math.sin(a), 100 - 94 * math.cos(a)
        parts.append(f"<path transform='translate({n(x)} {n(y)}) rotate({i * 22.5})' fill='none' stroke='#000' stroke-width='1.8' stroke-linecap='round' d='{glyphs[i % 8]}'/>")
    return "".join(parts)


F("grimRunes", _runes(), 200, 200, "xMidYMid meet")
F("grimPage", path("M4 12Q26 0 50 10L48 64Q26 54 2 66Z", "#000"), 54, 70, "xMidYMid meet")

# ── второе издание композиций: у каждого образа свой способ показать знание ──────────────────────────────────
# Библиотека: высокое стрельчатое окно — источник луча (свет идёт по диагонали через всю сцену).
F("libWindow", "".join([
    path("M10 200V60Q10 6 60 0Q110 6 110 60V200Z", "#2a1d12"),
    path("M18 192V62Q18 14 60 8Q102 14 102 62V192Z", "#fff4dc", "fill-opacity='.9'"),
    stroke("M60 8V192M18 70H102M18 130H102M18 160H102", "#2a1d12", 4),
    stroke("M30 30Q60 20 90 30", "#2a1d12", 2.4),
    path("M18 192V62Q18 14 60 8Q102 14 102 62V192Z", "none", "stroke='#c9a56a' stroke-width='1.5' stroke-opacity='.7'"),
]), 120, 200)


# Алхимик: поверхность эликсира — лента, которая повторяется по x и едет (кипение).
def _liquid(width=160, depth=40):
    import math
    pts = [(x, 8 + 3 * math.sin(x / width * math.tau * 2) + 2 * math.sin(x / width * math.tau * 3 + 1)) for x in range(0, width + 1, 8)]
    crest = "M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts)
    return (f"<defs><linearGradient id='lq' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#000' stop-opacity='.95'/>"
            f"<stop offset='1' stop-color='#000' stop-opacity='.35'/></linearGradient></defs><path fill='url(#lq)' d='{crest}V{depth}H0Z'/>")


F("alcLiquidTile", _liquid(), 160, 40, "none")
