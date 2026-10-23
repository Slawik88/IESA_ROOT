"""Season scenes, second edition: every season look tells its own story with its own composition (owner, 2026-10-22: «у каждого скина свой подход»).

Маскарад — театральная сцена сверху вниз; Экипаж — дорога в глубину; Пряничная — взгляд изнутри окна;
Экспресс — движение (пейзаж едет); Письмо — лист бумаги, на котором пишут; Хрусталь — преломление света.
Tiles («Tile» in the name) repeat seamlessly along x: the first and last points of every curve meet.
"""
import math

from scene_kit import art, circ, d_smooth, ell, n, path, rect, stroke, svg


def G(name, body, w, h, fit="xMidYMax meet"):
    art(name, "g", svg(w, h, " ".join(body.split()), fit))


# ── Маскарад: занавес с бахромой и кистью (сверху), ворон в полёте, перо ─────────────────────────────────────
def _curtain():
    folds = []
    for i, x in enumerate(range(0, 150, 18)):
        drop = 230 - i * 13 - (8 if i % 2 else 0)
        folds.append(path(f"M{x} 0H{x + 20}V{drop - 10}Q{x + 10} {drop + 6} {x} {drop - 4}Z", "#3a1550" if i % 2 else "#4b1d66"))
        folds.append(stroke(f"M{x + 15} 6V{drop - 14}", "#6e3a8a", 1.4, "stroke-opacity='.5'"))
    swag = "M0 18Q80 64 168 20L168 0H0Z"
    tie = "M120 120q14-10 22 0 4 14-10 22-12-6-12-22Z"
    return "".join(folds) + path(swag, "#2a0f3a") + stroke("M0 18Q80 64 168 20", "#d6b06a", 3) + stroke("M0 24Q80 70 168 26", "#d6b06a", 1, "stroke-dasharray='2 4'") \
        + path(tie, "#d6b06a") + stroke("M131 140v26M127 142v22M135 142v22", "#d6b06a", 1.6) + circ(131, 132, 5, "#ffe6a8")


G("curtainL", _curtain(), 170, 240, "none")
G("ravenFly", "<path fill='#000' d='M2 22Q20 8 34 18L42 14Q52 4 78 2Q60 12 56 20Q66 22 76 30Q58 28 48 26L40 30Q30 28 22 26Q10 30 2 22Z'/><circle fill='#fff' cx='42' cy='18' r='1'/>", 80, 34, "xMidYMid meet")
G("ravenFeather", "<path fill='#000' d='M10 2Q20 14 14 38L12 40Q2 26 10 2ZM11 6V40'/>", 22, 42, "xMidYMid meet")

# ── Экипаж: туман-лента, фонарный столб, фосфорное колесо ─────────────────────────────────────────────────────
def _fog(width, amp, depth):
    pts = [(i, depth * .45 - amp * (math.sin(i / width * math.tau) * .6 + math.sin(2 * i / width * math.tau + .7) * .4)) for i in range(0, width + 1, width // 10)]
    crest = d_smooth(pts, closed=False)
    return f"<defs><linearGradient id='f' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#000' stop-opacity='.9'/><stop offset='1' stop-color='#000' stop-opacity='0'/></linearGradient></defs><path fill='url(#f)' d='{crest}V{depth}H0z'/>"


G("fogTile", _fog(200, 6, 60), 200, 60, "none")
G("lanternPost", """<path fill='#0c2226' d='M18 160V46h4v114Z'/><path fill='#0c2226' d='M10 160h20v-6H10Z'/>
<path fill='#0c2226' stroke='#5fb8a8' stroke-width='1' d='M10 46h20l-3-20H13Z'/><path fill='#bdfff0' fill-opacity='.85' d='M13 44h14l-2-15H15Z'/>
<path fill='#0c2226' d='M8 26h24l-12-10Z'/><circle fill='#dffff6' cx='20' cy='36' r='3'/>""", 40, 160)


def _wheel():
    spokes = "".join(f"<path stroke='#000' stroke-width='3' d='M100 100L{n(100 + 84 * math.cos(a))} {n(100 + 84 * math.sin(a))}'/>" for a in (i * math.pi / 6 for i in range(12)))
    return f"<circle fill='none' stroke='#000' stroke-width='7' cx='100' cy='100' r='90'/><circle fill='none' stroke='#000' stroke-width='2' cx='100' cy='100' r='80'/>{spokes}<circle fill='#000' cx='100' cy='100' r='14'/>"


G("ghostWheel", _wheel(), 200, 200, "xMidYMid meet")

# ── Пряничная: иней в углу стекла, гирлянда пряников ──────────────────────────────────────
def _frost():
    """Ice ferns grow from the corner of the glass: a few main rays, each with feathered side needles that shorten toward the tip."""
    out = []
    for i, (l, a) in enumerate(((128, 18), (110, 40), (96, 62), (70, 6), (60, 80), (44, 30), (40, 52))):
        r = math.radians(a)
        out.append(stroke(f"M0 0L{n(l * math.cos(r))} {n(l * math.sin(r))}", "#000", 1.8 if i < 3 else 1.2))
        steps = max(3, int(l / 10))
        for k in range(1, steps):
            t = k / steps
            px, py, size = l * t * math.cos(r), l * t * math.sin(r), (1 - t) * 14 + 3
            for sgn in (-1, 1):
                b = r + sgn * .62
                out.append(stroke(f"M{n(px)} {n(py)}l{n(size * math.cos(b))} {n(size * math.sin(b))}", "#000", .9))
    out += [circ(x, y, 1.4, "#000") for x, y in ((30, 70), (64, 92), (100, 70), (120, 30), (86, 18), (14, 104))]
    return "".join(out)


G("frostCorner", _frost(), 140, 110, "xMinYMin meet")


def _gingerman(x, y, s, c):
    return (f"<g transform='translate({x} {y}) scale({s})'><path fill='{c}' d='M0-14a5 5 0 1 1 0 .1ZM-4-9h8l9 5-2 4-7-3 1 9 5 9-4 2-6-8-6 8-4-2 5-9 1-9-7 3-2-4Z'/>"
            "<path fill='none' stroke='#fff3dc' stroke-width='1' d='M-2-15h1m2 0h1M-2-11q2 1 4 0M-3 3q3 2 6 0M0-5v1m0 3v1'/></g>")


def _cookie_star(x, y, s, c):
    pts = " ".join(f"{n(x + s * (9 if i % 2 == 0 else 4) * math.sin(i * math.pi / 5))},{n(y - s * (9 if i % 2 == 0 else 4) * math.cos(i * math.pi / 5))}" for i in range(10))
    return f"<polygon fill='{c}' stroke='#fff3dc' stroke-width='1' points='{pts}'/>"


def _garland():
    line = "M0 6Q90 40 180 14T360 6"
    body = [stroke(line, "#7a4a2a", 2.4), stroke(line, "#e9c48f", .8, "stroke-dasharray='1 5'")]
    for i, x in enumerate(range(24, 350, 44)):
        t = x / 360
        y = 6 + 28 * math.sin(t * math.pi * 2) ** 2 * (1 if t < .5 else .6) + 6
        body.append(stroke(f"M{x} {n(y)}v{12 + (i % 3) * 6}", "#7a4a2a", 1))
        cy = y + 22 + (i % 3) * 6
        body.append(_gingerman(x, cy + 14, 1.5, "#a8632f") if i % 2 == 0 else _cookie_star(x, cy + 8, 1.9, "#c47a3c"))
    return "".join(body)


G("cookieGarland", _garland(), 360, 130, "xMidYMin meet")



# ── Экспресс: горы-лента и виадук-лента (едут), Полярная звезда, клуб пара ───────────────────────────────────
def _peaks(width, depth):
    pts = [(0, depth * .6)]
    for i, (x, h) in enumerate(((30, .2), (60, .55), (95, .1), (130, .5), (160, .25), (200, .62), (240, depth * .6 / depth))):
        pts.append((x, depth * h))
    crest = "M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts)
    snow = "".join(path(f"M{x - 9} {n(depth * h + 10)}L{x} {n(depth * h)}L{x + 9} {n(depth * h + 10)}l-4-2-5 4-5-4Z", "#c8dcef", "fill-opacity='.8'") for x, h in ((30, .2), (95, .1), (160, .25)))
    return path(crest + f"V{depth}H0z", "#14273f") + snow


G("peaksTile", _peaks(240, 90), 240, 90, "none")


def _track(width=120, depth=56):
    arches = "".join(f"M{x + 5} {depth}V32Q{x + 20} 16 {x + 35} 32V{depth}Z" for x in range(0, width, 40))
    return (rect(0, 8, width, 8, "#1b3350") + stroke("M0 7H120", "#d2e6f2", 3) + path(f"M0 16H{width}V{depth}H0Z", "#162b45")
            + path(arches, "#0a1626") + stroke("M0 4H120M10 2v5M30 2v5M50 2v5M70 2v5M90 2v5M110 2v5", "#8ea3b6", 1))


G("trackTile", _track(), 120, 56, "none")
G("northStar", "<path fill='#000' d='M60 0 66 54 120 60 66 66 60 120 54 66 0 60 54 54Z'/><path fill='#000' fill-opacity='.5' d='M60 34 74 46 86 60 74 74 60 86 46 74 34 60 46 46Z'/>", 120, 120, "xMidYMid meet")
G("steamPuff", "<path fill='#000' d='M10 40Q0 30 10 22Q12 8 28 12Q36 0 50 8Q66 4 68 20Q80 26 72 38Q70 48 54 46Q42 52 30 46Q16 50 10 40Z'/>", 80, 52, "xMidYMid meet")

# ── Письмо: строка почерка, лепесток, сургучная печать ─────────────────────────────────────────────────────
G("inkLine", stroke("M2 14Q10 2 18 12T34 12Q40 4 46 12T60 12Q66 6 70 14Q76 2 84 12T100 12Q108 4 116 12T134 10Q142 2 150 12T170 12Q176 6 182 12Q188 4 196 12", "#000", 1.8), 200, 20, "xMinYMid meet")
G("petal", "<path fill='#000' d='M2 12Q4 2 14 2Q22 4 22 10Q16 18 8 18Q2 18 2 12Z'/>", 24, 20, "xMidYMid meet")
G("waxSeal", """<path fill='#7e1f3c' d='M30 4Q42 2 48 10Q58 12 56 24Q60 34 52 42Q50 54 38 54Q30 60 20 54Q8 54 6 42Q0 32 6 22Q6 10 18 8Q22 2 30 4Z'/>
<circle fill='none' stroke='#c45a74' stroke-width='2' cx='30' cy='30' r='16'/><path fill='#e8a0ae' d='M30 40Q18 32 24 24Q28 21 30 26Q32 21 36 24Q42 32 30 40Z'/>""", 60, 60, "xMidYMid meet")

# ── Хрусталь: осколок с гранями ────────────────────────────────────────────────────────────────────────────
G("shard", """<path fill='#4d3570' d='M20 0 38 22 30 70 8 64 2 24Z'/><path fill='#c9b2f0' d='M20 0 2 24 20 30Z'/><path fill='#9fd8f2' d='M20 0 38 22 20 30Z'/>
<path fill='#7a5fb0' d='M2 24 20 30 8 64Z'/><path fill='#b5a4e6' d='M20 30 38 22 30 70Z'/><path fill='none' stroke='#f0e6ff' stroke-opacity='.7' d='M2 24 20 30 38 22M20 30 8 64M20 30 30 70'/>""", 40, 72, "xMidYMid meet")
