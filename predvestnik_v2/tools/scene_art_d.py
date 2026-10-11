"""Scene art D (skin-scene-d-v3.css): Тыквенный Фонарь, Паутина Полуночи, Час Ведьм, Снежный Шар, Огни Гирлянды, Бой Курантов, Алая Звезда, Багровый Мрак."""
from __future__ import annotations

import math
import random

from scene_kit import (arc_d, art, bezier, circ, d_poly, d_ridge, d_smooth, ell, flip, jag, lingrad, mirror, n, path, poly, radgrad, rect, ribbon, ridge, spiral_points, star_d, stroke, svg)


def D(name: str, value: str) -> None:
    art(name, "d", value)


def pt(cx: float, cy: float, ang: float, rad: float) -> str:
    return f"{n(cx + rad * math.cos(ang))} {n(cy + rad * math.sin(ang))}"


# ── Тыквенный Фонарь: тыквенное поле, резные фонари, мёртвое дерево с вороной, пугало, летучие мыши, привидение и огромное пламя свечи за аватаром ──
PK_DEFS = ("<defs><radialGradient id='pk' cx='.36' cy='.32' r='.9'><stop offset='0' stop-color='#8e3d0e'/><stop offset='.55' stop-color='#4b1c06'/><stop offset='1' stop-color='#1d0902'/></radialGradient>"
           "<radialGradient id='fc' cx='.5' cy='.5' r='.62'><stop offset='0' stop-color='#fff3b8'/><stop offset='.5' stop-color='#ffb42e'/><stop offset='1' stop-color='#e8641a'/></radialGradient>"
           "<radialGradient id='gl' cx='.5' cy='.5' r='.5'><stop offset='0' stop-color='#ffb02e' stop-opacity='.6'/><stop offset='1' stop-color='#ff7a1a' stop-opacity='0'/></radialGradient></defs>")
FACE_EDGE = "stroke='#ffe08a' stroke-opacity='.55' stroke-width='.9' stroke-linejoin='round'"


def carved_face(cx: float, cy: float, rx: float, ry: float, style: str = "grin") -> str:
    """The carved holes of a jack-o'-lantern (the candle shows through them): eyes, a nose and a toothy mouth."""
    out = ""
    ex, ey, es = rx * .43, ry * .2, rx * .21
    for sx in (-1, 1):
        x, y = cx + sx * ex, cy - ey
        if style == "grin":
            out += poly([(x - es, y + es * .8), (x + es, y + es * .8), (x - sx * es * .1, y - es)], "url(#fc)", FACE_EDGE)
        elif style == "evil":
            out += poly([(x - sx * es * 1.2, y - es * 1.1), (x + sx * es * 1.1, y - es * .1), (x - sx * es * .1, y + es * .95)], "url(#fc)", FACE_EDGE)
        else:
            out += ell(x, y, es * .78, es * .92, "url(#fc)", FACE_EDGE)
    out += poly([(cx - rx * .09, cy + ry * .13), (cx + rx * .09, cy + ry * .13), (cx, cy - ry * .03)], "url(#fc)", FACE_EDGE)
    steps = 10
    top, low = [], []
    for i in range(steps + 1):
        t = i / steps
        x = cx + (t - .5) * rx * 1.36
        bow = 1 - (2 * t - 1) ** 2
        yc = cy + ry * (.3 + .17 * bow)
        tooth = ry * .1 if i % 2 else 0
        top.append((x, yc - ry * .13 + tooth))
        low.append((x, yc + ry * .12 - (ry * .09 if i % 2 == 0 and 0 < i < steps else 0)))
    out += poly(top + low[::-1], "url(#fc)", FACE_EDGE)
    return out


def pumpkin(cx: float, cy: float, rx: float, ry: float, style: str | None = None, tilt: float = 0, lit: bool = True) -> str:
    """A pumpkin of three ribbed lobes with a stalk; with a `style` it is carved and lit from inside."""
    g = ell(cx - rx * .5, cy + ry * .02, rx * .56, ry * .96, "url(#pk)") + ell(cx + rx * .5, cy + ry * .02, rx * .56, ry * .96, "url(#pk)") + ell(cx, cy, rx * .64, ry, "url(#pk)")
    for k in (-.66, -.3, .3, .66):
        g += stroke(f"M{n(cx + k * rx * .42)} {n(cy - ry * .93)}Q{n(cx + k * rx * 1.28)} {n(cy)} {n(cx + k * rx * .42)} {n(cy + ry * .93)}", "#120501", max(1, rx * .03), "stroke-opacity='.55'")
    g += stroke(f"M{n(cx - rx * .72)} {n(cy - ry * .42)}Q{n(cx - rx * .96)} {n(cy)} {n(cx - rx * .7)} {n(cy + ry * .5)}", "#b0541a", max(.8, rx * .03), "stroke-opacity='.38'")
    if style:
        g += ell(cx, cy + ry * .05, rx * .86, ry * .74, "url(#gl)") + carved_face(cx, cy, rx, ry, style)
    stem = f"M{n(cx - rx * .09)} {n(cy - ry * .88)}Q{n(cx - rx * .05)} {n(cy - ry * 1.12)} {n(cx + rx * .13)} {n(cy - ry * 1.24)}L{n(cx + rx * .24)} {n(cy - ry * 1.12)}Q{n(cx + rx * .12)} {n(cy - ry * 1.02)} {n(cx + rx * .11)} {n(cy - ry * .86)}z"
    g += path(stem, "#2c1707") + stroke(f"M{n(cx + rx * .16)} {n(cy - ry * 1.2)}L{n(cx + rx * .2)} {n(cy - ry * 1.12)}", "#7a4a1c", max(.8, rx * .03), "stroke-opacity='.6'")
    return f"<g transform='rotate({n(tilt)} {n(cx)} {n(cy)})'>{g}</g>" if tilt else g


def vine(x0: float, y0: float, x1: float, y1: float, bend: float, seed: int, leaves: int = 2) -> str:
    """A curling vine with a few leaves, dark green-brown."""
    r = random.Random(seed)
    mx, my = (x0 + x1) / 2 + bend, (y0 + y1) / 2 - abs(bend) * .6
    body = stroke(f"M{n(x0)} {n(y0)}Q{n(mx)} {n(my)} {n(x1)} {n(y1)}", "#1f1a0a", 1.6)
    for i in range(leaves):
        t = .35 + .5 * i / max(1, leaves - 1) * r.uniform(.7, 1)
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t * t * x1
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t * t * y1
        s = r.uniform(5, 8) * (1 if i % 2 else -1)
        body += path(f"M{n(x)} {n(y)}Q{n(x + s * .7)} {n(y - 6)} {n(x + s * 1.6)} {n(y - 1.5)}Q{n(x + s * .8)} {n(y + 3)} {n(x)} {n(y)}z", "#262a0e")
    return body


def patch_strip() -> str:
    """The pumpkin field (stretched over the whole bottom strip): rows of pumpkins that grow towards the viewer, a few of them lit, dry cornstalks and a low fence."""
    w, h = 420, 120
    r = random.Random(21)
    body = PK_DEFS + lingrad("gd", [(0, "#2a1208", 1), (1, "#0c0502", 1)])
    top = ridge(w, 58, 7, [(170, .7), (74, .4), (36, .18)], 4, .12, 30)
    body += path(d_ridge(top, w, h), "url(#gd)")
    for x in range(8, w, 26):                                    # the fence, far
        body += rect(x, 47 + 4 * math.sin(x / 40), 2.2, 18, "#1a0c05")
    body += stroke(f"M0 55Q{w * .25} 52 {w * .5} 56T{w} 54", "#1a0c05", 1.4)
    far = [(18, 66, 11), (58, 70, 12), (100, 64, 10), (150, 70, 7), (205, 69, 6), (255, 70, 7), (300, 64, 10), (344, 68, 13), (392, 66, 11)]
    for x, y, rr in far:
        body += pumpkin(x, y, rr, rr * .8)
    for x in (34, 128, 232, 318):                                # cornstalks leaning
        for k in range(5):
            lean = (k - 2) * 4 + r.uniform(-2, 2)
            body += stroke(f"M{x + k * 2} 72Q{x + k * 2 + lean * .4} 52 {x + k * 2 + lean} {36 + r.uniform(0, 8)}", "#2b2410", 1.3)
        body += path(f"M{x} 54Q{x - 10} 46 {x - 16} 50Q{x - 8} 54 {x} 58z", "#2b2410") + path(f"M{x + 6} 50Q{x + 16} 40 {x + 22} 44Q{x + 14} 50 {x + 6} 54z", "#2b2410")
    mid = [(34, 90, 18, "smile"), (96, 96, 19, None), (324, 92, 17, "evil"), (386, 96, 19, None)]
    for x, y, rr, style in mid:
        body += pumpkin(x, y, rr, rr * .82, style, r.uniform(-4, 4))
    near = [(-4, 120, 30), (66, 126, 26), (356, 124, 26), (424, 120, 30)]
    for x, y, rr in near:
        body += pumpkin(x, y, rr, rr * .8, None, r.uniform(-5, 5))
    body += vine(10, 112, 54, 102, 12, 5, 3) + vine(336, 112, 392, 104, -10, 8, 3)
    return svg(w, h, body, "none")


D("patch", patch_strip())


def jack_big() -> str:
    """A big carved jack-o'-lantern with a small plain pumpkin and a curling vine at its side: the warm light of the candle spills over the ground."""
    w, h = 210, 170
    body = PK_DEFS + radgrad("sp", [(0, "#ff9a3c", .5), (1, "#ff7a1a", 0)], .5, .5, .5)
    body += ell(100, 156, 92, 14, "url(#sp)") + ell(100, 160, 70, 8, "#0a0402", "fill-opacity='.7'")
    body += pumpkin(166, 138, 30, 24, None, 8) + vine(160, 118, 196, 96, 10, 11, 3)
    body += pumpkin(88, 98, 70, 58, "grin", -3)
    return svg(w, h, body, "xMinYMax meet")


D("jackBig", jack_big())


def scarecrow(x: float, y: float, s: float) -> str:
    """A scarecrow on a pole: a wide-brimmed hat, a stuffed head, arms stretched along the crossbar, a ragged shirt and straw at the cuffs."""
    ink = "#0f0807"
    body = rect(x - 1.5 * s, y - 40 * s, 3 * s, 78 * s, ink) + rect(x - 30 * s, y - 20 * s, 60 * s, 3 * s, ink)
    body += poly([(x - 11 * s, y - 20 * s), (x + 11 * s, y - 20 * s), (x + 14 * s, y + 8 * s), (x + 4 * s, y + 4 * s), (x, y + 12 * s), (x - 6 * s, y + 5 * s), (x - 14 * s, y + 10 * s)], ink)
    body += circ(x, y - 31 * s, 8 * s, ink) + ell(x, y - 37 * s, 17 * s, 3.2 * s, ink) + poly([(x - 8 * s, y - 38 * s), (x - 5 * s, y - 54 * s), (x + 6 * s, y - 55 * s), (x + 9 * s, y - 38 * s)], ink)
    for sx in (-1, 1):                                          # straw at the cuffs and hem
        for k in range(4):
            body += stroke(f"M{n(x + sx * 29 * s)} {n(y - 19 * s)}L{n(x + sx * (36 + k * 2) * s)} {n(y - (24 - k * 4.5) * s)}", "#3a2c10", 1.2 * s)
    body += stroke(f"M{n(x - 6 * s)} {n(y + 8 * s)}l-3 8M{n(x)} {n(y + 12 * s)}l0 9M{n(x + 5 * s)} {n(y + 6 * s)}l4 8", "#3a2c10", 1.2 * s)
    body += circ(x - 3 * s, y - 32 * s, 1.4 * s, "#ffb42e") + circ(x + 3 * s, y - 32 * s, 1.4 * s, "#ffb42e")
    return body


def pumpkin_pair() -> str:
    """The right side: a scarecrow on a pole and two pumpkins in front, one of them carved and lit."""
    w, h = 190, 190
    body = PK_DEFS + radgrad("sp", [(0, "#ff9a3c", .5), (1, "#ff7a1a", 0)], .5, .5, .5)
    body += scarecrow(120, 100, 1.08)
    body += ell(100, 178, 86, 12, "url(#sp)") + ell(100, 182, 64, 7, "#0a0402", "fill-opacity='.7'")
    body += pumpkin(46, 152, 34, 28, None, -6) + vine(34, 126, 12, 100, -10, 4, 3)
    body += pumpkin(124, 150, 50, 40, "smile", 4)
    return svg(w, h, body, "xMaxYMax meet")


D("pumpkinPair", pumpkin_pair())


def dead_tree() -> str:
    """A crooked bare tree that leans in from the right edge with a crow on one of the branches."""
    w, h = 200, 280
    ink = "#0d0610"
    r = random.Random(14)
    body = ""

    def limb(x, y, ang, ln, wd, depth):
        nonlocal body
        x2, y2 = x + ln * math.cos(ang), y + ln * math.sin(ang)
        mx, my = (x + x2) / 2 + r.uniform(-ln * .12, ln * .12), (y + y2) / 2 + r.uniform(-ln * .12, ln * .12)
        body += stroke(f"M{n(x)} {n(y)}Q{n(mx)} {n(my)} {n(x2)} {n(y2)}", ink, wd)
        if depth > 0:
            for k in range(r.choice((2, 2, 3))):
                a = ang + r.uniform(-.85, .85)
                limb(x2 - (x2 - x) * r.uniform(0, .25), y2 - (y2 - y) * r.uniform(0, .25), a, ln * r.uniform(.55, .75), max(1, wd * .62), depth - 1)

    body += poly([(150, 280), (158, 200), (166, 150), (176, 150), (182, 200), (200, 280)], ink)
    body += stroke("M164 160Q150 120 168 70", ink, 9)
    limb(166, 90, -2.2, 62, 6, 3)
    limb(166, 104, -.9, 70, 6, 3)
    limb(166, 150, -2.7, 58, 5.5, 3)
    limb(172, 128, -.2, 48, 5, 2)
    body += ell(98, 54, 8, 5.4, ink, "transform='rotate(-22 98 54)'") + circ(92, 49, 3.4, ink) + poly([(90, 48), (82, 51), (90, 52)], ink) + poly([(102, 58), (112, 66), (104, 62)], ink)
    body += rect(97, 58, 1.2, 6, ink)
    return svg(w, h, body, "xMaxYMax meet")


D("deadTree", dead_tree())


def bat_shape(cx: float, cy: float, s: float, lift: float) -> str:
    body = ell(cx, cy, s * .16, s * .3, "#000") + circ(cx, cy - s * .33, s * .12, "#000")
    body += poly([(cx - s * .1, cy - s * .4), (cx - s * .06, cy - s * .62), (cx, cy - s * .42)], "#000") + poly([(cx + s * .1, cy - s * .4), (cx + s * .06, cy - s * .62), (cx, cy - s * .42)], "#000")
    for sx in (-1, 1):
        tip = (cx + sx * s, cy - lift * s)
        sh = (cx + sx * s * .12, cy - s * .18)
        lo = (cx + sx * s * .1, cy + s * .22)
        pts = [(cx + sx * s * .72, cy + s * .02 - lift * s * .12), (cx + sx * s * .46, cy + s * .2 - lift * s * .02)]
        d = f"M{n(sh[0])} {n(sh[1])}Q{n(cx + sx * s * .55)} {n(cy - lift * s * 1.2 - s * .12)} {n(tip[0])} {n(tip[1])}"
        prev = tip
        for p in pts + [lo]:
            d += f"Q{n((prev[0] + p[0]) / 2 + sx * s * .02)} {n(min(prev[1], p[1]) - s * .02)} {n(p[0])} {n(p[1])}"
            prev = p
        body += path(d + "z", "#000")
    return body


def bats() -> str:
    """Three bats of one flock with the wings in different phases (a mask)."""
    body = bat_shape(60, 44, 40, .55) + bat_shape(150, 30, 26, -.3) + bat_shape(112, 88, 20, .25)
    return svg(200, 120, body, "xMidYMid meet")


D("bats", bats())


def ghost() -> str:
    """A sheet ghost with a wavy hem and two raised arms; the eyes and the mouth are holes (a mask)."""
    hem = ""
    for i in range(5):
        hem += f"Q{90 - i * 16 - 8} {136 if i % 2 == 0 else 112} {90 - (i + 1) * 16} 118"
    d = "M10 118L8 56Q8 8 50 6Q92 8 92 56L90 118" + hem + "z"
    arms = "M9 84Q-8 78 -12 54Q-4 50 -1 58Q2 50 8 52Q6 62 12 70zM91 84Q108 78 112 54Q104 50 101 58Q98 50 92 52Q94 62 88 70z"
    holes = "M30 44a7 10 0 1 0 .1 0zM70 44a7 10 0 1 0 .1 0zM42 74Q50 90 58 74Q50 70 42 74z"
    return svg(132, 140, f"<g transform='translate(16 0)'><path fill='#000' fill-rule='evenodd' d='{d}{arms}{holes}'/></g>", "xMidYMid meet")


D("ghost", ghost())


def flame() -> str:
    """A tall candle flame behind the avatar (a mask): the outer tongue, a middle one and a bright heart (their weights add up), two little tongues that split off at the sides."""
    outer = "M150 352C34 352 16 254 66 172C98 122 140 96 128 18C186 62 198 116 214 160C252 222 266 352 150 352z"
    body = "".join(f"<path fill='#000' fill-opacity='{a}' transform='translate(150 352) scale({s}) translate(-150 -352)' d='{outer}'/>" for s, a in ((1, .42), (.74, .5), (.46, .7)))
    body += f"<path fill='#000' fill-opacity='.4' transform='translate(46 232) rotate(-18) scale(.2)' d='{outer}'/><path fill='#000' fill-opacity='.4' transform='translate(250 200) rotate(14) scale(.16)' d='{outer}'/>"
    return svg(300, 360, body, "xMidYMax meet")


D("flame", flame())


# ── Паутина Полуночи: сухая трава, ветви с паутиной, нити с росой, паук, мотылёк и огромная паутина вокруг аватара ──
def limb(p0, p1, p2, p3, w0: float, w1: float, steps: int = 16):
    """A branch along a cubic curve, tapered from w0 to w1: the outline and the points of its middle line (for anchors and twigs)."""
    line = bezier(p0, p1, p2, p3, steps)
    return d_poly(ribbon(line, [w0 + (w1 - w0) * i / steps for i in range(steps + 1)])), line


def web(cx, cy, anchors, rings, color, width=.9, op=.6, sag=.2, closed=False, bead=None, seed=1, bead_chance=.4) -> str:
    """An orb web: spokes from the hub to the anchor points, spiral threads at the given fractions of the spokes, each sagging towards the hub between two spokes; dew beads where the threads cross."""
    r = random.Random(seed)
    spokes = [(math.atan2(y - cy, x - cx), math.hypot(x - cx, y - cy)) for x, y in anchors]
    spokes.sort()
    d = "".join(f"M{n(cx)} {n(cy)}L{n(x)} {n(y)}" for x, y in anchors)
    body = stroke(d, color, width * 1.1, f"stroke-opacity='{op}'")
    ring_d = ""
    beads = ""
    pairs = len(spokes) if closed else len(spokes) - 1
    for f in rings:
        for i in range(pairs):
            (a0, l0), (a1, l1) = spokes[i], spokes[(i + 1) % len(spokes)]
            if a1 < a0:
                a1 += math.tau
            p0 = (cx + l0 * f * math.cos(a0), cy + l0 * f * math.sin(a0))
            p1 = (cx + l1 * f * math.cos(a1), cy + l1 * f * math.sin(a1))
            am, lm = (a0 + a1) / 2, (l0 + l1) / 2 * f * (1 - sag * (.7 + .3 * r.random()))
            ring_d += f"M{n(p0[0])} {n(p0[1])}Q{n(cx + lm * math.cos(am))} {n(cy + lm * math.sin(am))} {n(p1[0])} {n(p1[1])}"
            if bead and r.random() < bead_chance:
                beads += circ(p0[0], p0[1], r.uniform(1.1, 1.9), bead, "fill-opacity='.95'")
    return body + stroke(ring_d, color, width, f"stroke-opacity='{op * .85}'") + beads


def dry_grass() -> str:
    """Tall dry grass and thistles in the dark (stretched over the bottom strip): blades with a thin rim light, seed heads and dew."""
    w, h = 420, 110
    r = random.Random(41)
    body = lingrad("gd", [(0, "#171236", 1), (1, "#07050f", 1)])
    top = ridge(w, 74, 6, [(150, .7), (62, .4), (30, .2)], 3, .15, 30)
    body += path(d_ridge(top, w, h), "url(#gd)")
    for k in range(70):
        x = r.uniform(-4, w + 4)
        edge = abs(x - w / 2) / (w / 2)                          # taller at the sides, low in the middle (the nick stands there)
        ht = r.uniform(26, 62) * (.45 + .55 * edge ** 1.2)
        lean = r.uniform(-14, 14)
        base = 82 + r.uniform(0, 14)
        body += stroke(f"M{n(x)} {n(base)}Q{n(x + lean * .3)} {n(base - ht * .55)} {n(x + lean)} {n(base - ht)}", "#1d1745", r.uniform(1, 1.8))
        if k % 4 == 0:
            body += stroke(f"M{n(x + .8)} {n(base)}Q{n(x + lean * .3 + .8)} {n(base - ht * .55)} {n(x + lean + .8)} {n(base - ht)}", "#7a6bd0", .6, "stroke-opacity='.45'")
        if k % 9 == 0 and ht > 40:                                 # a thistle head
            body += ell(x + lean, base - ht - 3, 2.6, 4, "#2a2160") + stroke(f"M{n(x + lean - 3)} {n(base - ht - 6)}l-2 -4M{n(x + lean)} {n(base - ht - 7)}l0 -5M{n(x + lean + 3)} {n(base - ht - 6)}l2 -4", "#8e7fe0", .8, "stroke-opacity='.7'")
    for x, y in ((40, 66), (98, 70), (330, 68), (388, 64)):        # little webs between the stalks
        body += web(x, y, [(x - 16, y - 10), (x - 4, y - 18), (x + 12, y - 14), (x + 18, y + 2)], (.5, .8), "#d9ccff", .6, .5, .3)
    for _ in range(26):
        x, y = r.uniform(0, w), r.uniform(62, 100)
        body += circ(x, y, r.uniform(.6, 1.3), "#e8e0ff", f"fill-opacity='{n(r.uniform(.35, .85))}'")
    return svg(w, h, body, "none")


D("dryGrass", dry_grass())


def web_branches(mirrored: bool = False) -> str:
    """Dead branches reaching in from a corner with an orb web strung between a limb and four twigs: the spokes end on the branches, dew shines on the threads and a star trembles in two drops."""
    w, h = 230, 270
    ink, rim = "#2b2160", "#b3a5ff"
    shapes, lines = [], []

    def add(p0, p1, p2, p3, w0, w1):
        d, line = limb(p0, p1, p2, p3, w0, w1)
        shapes.append(d)
        lines.append(line)
        return line

    top = add((-16, 4), (50, 22), (130, 26), (216, 70), 11, 2)
    t1 = add(top[5], (50, 64), (52, 96), (58, 122), 5, 1.2)
    t2 = add(top[11], (150, 70), (164, 100), (160, 134), 4.4, 1)
    t4 = add(top[15], (212, 90), (220, 120), (214, 154), 3.6, 1)
    left = add((-16, 112), (36, 126), (80, 176), (96, 246), 10, 2)
    t3 = add(left[9], (120, 190), (152, 196), (178, 214), 4.4, 1)
    t5 = add(left[4], (20, 118), (12, 132), (6, 146), 3, 1)
    twig = add(t1[10], (50, 128), (44, 136), (36, 140), 2.2, .8)
    body = "".join(path(d, ink) for d in shapes) + "".join(stroke(d_smooth(line, closed=False), rim, .8, "stroke-opacity='.5'") for line in lines)
    hub = (104, 136)
    anchors = [t1[-1], top[7], top[10], t2[-1], t4[-1], t3[-1], left[-1], left[10], t5[-1]]
    body += web(hub[0], hub[1], anchors, (.2, .34, .48, .62, .76, .9), "#d9ccff", .8, .62, .22, False, "#ffffff", 3, .32)
    for x, y in ((74, 100), (164, 112)):
        body += path(star_d(x, y, 4.4, .2), "#ffffff", "fill-opacity='.9'") + circ(x, y, 7.5, "#cbb8ff", "fill-opacity='.2'")
    return svg(w, h, flip(body, w) if mirrored else body, "xMinYMin meet" if not mirrored else "xMaxYMin meet")


D("webBranchL", web_branches())
D("webBranchR", web_branches(True))


def silk() -> str:
    """Silk threads that hang from the top edge with beads of dew, one ends in a wrapped cocoon (a mask)."""
    w, h = 140, 270
    r = random.Random(17)
    body = ""
    for x, ln in ((16, 120), (44, 210), (70, 150), (98, 240), (124, 100)):
        sway = r.uniform(-4, 4)
        body += stroke(f"M{x} 0Q{x + sway} {ln * .5} {x + sway * .6} {ln}", "#000", .9, "stroke-opacity='.65'")
        for k in range(1, int(ln // 38) + 1):
            y = k * 36 + r.uniform(-6, 6)
            if y < ln - 4:
                body += circ(x + sway * (y / ln), y, r.uniform(1.4, 2.2), "#000")
    body += ell(98 + 1, 244, 5, 11, "#000") + stroke("M94 236l10 0M93 242l12 0M93 248l12 0M95 254l9 0", "#000", .6, "stroke-opacity='.4'")
    return svg(w, h, body, "xMidYMin meet")


D("silk", silk())


def spider(cx: float, cy: float, s: float) -> str:
    """A spider seen from above: round abdomen, small head, eight bent legs, two eyes as light dots left to the layer's colour."""
    body = ""
    for side in (-1, 1):
        for k, (ang, ln) in enumerate(((-62, 1.0), (-24, 1.1), (18, 1.1), (56, 1.0))):
            a = math.radians(ang)
            kx, ky = cx + side * s * (.8 + .5 * math.cos(a)), cy + s * (-.1 + .85 * math.sin(a)) * .7
            ex, ey = cx + side * s * (1.6 + .6 * math.cos(a)) * ln, cy + s * (.25 + 1.3 * math.sin(a)) * ln * .8
            body += stroke(f"M{n(cx + side * s * .35)} {n(cy + s * .1 * k - s * .1)}L{n(kx)} {n(ky - s * .55)}L{n(ex)} {n(ey)}", "#000", max(.9, s * .11))
    return body + ell(cx, cy + s * .75, s * .62, s * .8, "#000") + circ(cx, cy - s * .15, s * .38, "#000")


def spider_thread() -> str:
    """A spider that goes down its thread: a long silk line from the top edge and the spider at the bottom end (a mask)."""
    w, h = 60, 190
    body = stroke("M30 0L30 138", "#000", 1.2, "stroke-opacity='.8'") + spider(30, 152, 11)
    return svg(w, h, body, "xMidYMin meet")


D("spiderThread", spider_thread())


def moth() -> str:
    """A night moth with rounded wings and feathered feelers (a mask)."""
    w, h = 80, 56
    body = ell(40, 32, 3.2, 13, "#000") + circ(40, 17, 3.4, "#000")
    for side in (-1, 1):
        body += path(f"M{40 + side * 3} 24Q{40 + side * 22} 0 {40 + side * 38} 8Q{40 + side * 40} 24 {40 + side * 6} 34z", "#000")
        body += path(f"M{40 + side * 4} 32Q{40 + side * 30} 30 {40 + side * 30} 48Q{40 + side * 14} 52 {40 + side * 4} 40z", "#000", "fill-opacity='.85'")
        body += stroke(f"M{40 + side * 2} 14Q{40 + side * 10} 2 {40 + side * 16} 4", "#000", .9)
    return svg(w, h, body, "xMidYMid meet")


D("moth", moth())


def orb_web() -> str:
    """A huge orb web around the middle of the stage (a mask): the spokes run out to the edges, the threads sag between them, beads of dew sit on the nodes and a big spider waits on the top spoke."""
    w = h = 400
    cx = cy = 200
    r = random.Random(5)
    spokes = 15
    anchors = []
    for i in range(spokes):
        a = math.tau * i / spokes - math.pi / 2 + r.uniform(-.06, .06)
        ln = r.uniform(185, 200)
        anchors.append((cx + ln * math.cos(a), cy + ln * math.sin(a)))
    body = web(cx, cy, anchors, (.22, .34, .46, .58, .7, .82, .94), "#000", 1, .62, .16, True, "#000", 9, .45)
    body += stroke("".join(f"M{n(x)} {n(y)}l{n((x - cx) * .12)} {n((y - cy) * .12)}" for x, y in anchors), "#000", 1, "stroke-opacity='.5'")
    body += spider(cx + 2, 98, 14)
    return svg(w, h, body, "xMidYMid meet")


D("orbWeb", orb_web())


# ── Час Ведьм: крыши с трубами, башня ведьмы, кривой дом, вихрь туч, кольцо рун, молния, чёрная кошка ──
def house(x: float, base: float, w: float, h: float, roof: float, lean: float, seed: int, lit: float = .5) -> str:
    """A crooked gabled house: the body leans a little, the roof is a steep triangle with a drooping ridge, a chimney and a few lit windows."""
    r = random.Random(seed)
    top = base - h
    body = poly([(x, base), (x + lean, top), (x + w + lean, top), (x + w, base)], "url(#rf)")
    ridge_x = x + w / 2 + lean * 1.3 + r.uniform(-w * .08, w * .08)
    body += path(f"M{n(x - w * .1 + lean)} {n(top + 1)}Q{n(x + w * .3 + lean)} {n(top - roof * .55)} {n(ridge_x)} {n(top - roof)}Q{n(x + w * .75 + lean)} {n(top - roof * .5)} {n(x + w * 1.1 + lean)} {n(top + 1)}z", "url(#rf)")
    cx = x + w * r.uniform(.62, .78) + lean
    body += rect(cx, top - roof * .62, w * .13, roof * .5, "url(#rf)") + rect(cx - 1, top - roof * .66, w * .13 + 2, 2.4, "url(#rf)")
    for k in range(int(w // 11)):
        if r.random() < lit + .25:
            wx, wy = x + 4 + k * 11 + lean * .5, top + r.uniform(h * .15, h * .6)
            body += rect(wx, wy, 4.2, 5.4, "#ffd36b" if r.random() < .6 else "#8dff9c", f"fill-opacity='{n(r.uniform(.6, 1))}'")
    body += stroke(f"M{n(x - w * .1 + lean)} {n(top + 1)}Q{n(x + w * .3 + lean)} {n(top - roof * .55)} {n(ridge_x)} {n(top - roof)}", "#6a55c0", .8, "stroke-opacity='.5'")
    return body


def roofs() -> str:
    """The roofs of a witches' town (stretched over the bottom strip): crooked houses with chimneys, tall at the sides and low in the middle, a few windows burn green and amber."""
    w, h = 420, 120
    r = random.Random(33)
    body = lingrad("rf", [(0, "#1d1238", 1), (1, "#06030d", 1)])
    body += rect(0, 92, w, 30, "url(#rf)")
    x = -10
    while x < w:
        edge = abs(x + 20 - w / 2) / (w / 2)
        hh = (16 + 34 * edge ** 1.1) * r.uniform(.8, 1.15)
        ww = r.uniform(26, 44)
        body += house(x, 100, ww, hh, ww * r.uniform(.6, .95) * (.55 + .45 * edge), r.uniform(-3, 3), r.randint(1, 999), .35)
        x += ww * r.uniform(.78, 1.0)
    return svg(w, h, body, "none")


D("roofs", roofs())


def witch_tower() -> str:
    """A tall crooked tower with a witch-hat roof whose tip is bent over, a round window, a lit arched window and a little balcony."""
    w, h = 120, 270
    body = lingrad("rf", [(0, "#1d1238", 1), (1, "#06030d", 1)], 0, 0, 1, 0)
    body += path("M26 270L34 128Q36 108 42 104L82 104Q88 108 90 128L96 270z", "url(#rf)")
    body += path("M20 106Q48 98 52 62Q56 30 78 6Q72 12 66 4Q62 30 72 62Q80 94 100 106Q60 114 20 106z", "url(#rf)")
    body += ell(60, 107, 42, 5, "url(#rf)")
    body += stroke("M42 62Q60 70 70 62", "#6a55c0", .8, "stroke-opacity='.4'") + stroke("M92 108Q96 106 100 106", "#6a55c0", .8, "stroke-opacity='.5'")
    body += circ(60, 138, 7, "#ffd36b", "fill-opacity='.95'") + path("M50 196Q50 176 60 172Q70 176 70 196z", "#8dff9c", "fill-opacity='.9'") + rect(56, 180, 1.4, 16, "#0b0618") + rect(46, 214, 28, 3, "url(#rf)") + rect(44, 210, 32, 1.6, "url(#rf)")
    for x in (46, 52, 60, 68, 74):
        body += rect(x, 202, 1.4, 12, "url(#rf)")
    body += stroke("M90 140L92 270M34 150L30 270", "#6a55c0", .9, "stroke-opacity='.35'")
    body += stroke("M88 220Q104 214 108 196Q112 214 100 236", "#1d1238", 1.6)
    return svg(w, h, body, "xMinYMax meet")


D("witchTower", witch_tower())


def crooked_house() -> str:
    """A leaning cottage on the right: a drooping roof, a crooked chimney, a lit window with a cross, a door with green light under it and a bat on the ridge."""
    w, h = 160, 200
    body = lingrad("rf", [(0, "#1d1238", 1), (1, "#06030d", 1)], 0, 0, 1, 0)
    body += poly([(28, 200), (36, 112), (128, 104), (136, 200)], "url(#rf)")
    body += path("M16 116Q54 106 66 56Q74 26 92 10Q100 36 112 62Q126 96 148 112Q84 120 16 116z", "url(#rf)")
    body += poly([(104, 74), (126, 70), (130, 34), (116, 36), (114, 56), (106, 60)], "url(#rf)") + rect(112, 30, 20, 5, "url(#rf)")
    body += rect(50, 132, 24, 22, "#ffd36b", "fill-opacity='.95'") + rect(61, 132, 2, 22, "#0b0618") + rect(50, 142, 24, 2, "#0b0618")
    body += path("M92 200V170Q92 160 102 160Q112 160 112 170V200z", "#0b0618") + rect(94, 194, 16, 6, "#8dff9c", "fill-opacity='.8'")
    body += poly([(88, 66), (92, 58), (96, 66), (100, 62), (98, 70), (90, 70)], "#06030d") + stroke("M16 116Q54 106 66 56Q74 26 92 10", "#6a55c0", .9, "stroke-opacity='.5'")
    body += stroke("M30 150L28 200M132 130L134 200", "#6a55c0", .8, "stroke-opacity='.3'")
    return svg(w, h, body, "xMaxYMax meet")


D("crookedHouse", crooked_house())


def witch_swirl() -> str:
    """Three thick arms of storm cloud that curl out of the middle (a mask): puffy edges, brighter along the middle of each arm."""
    cx = cy = 200
    r = random.Random(12)
    body = "<defs><radialGradient id='f' gradientUnits='userSpaceOnUse' cx='200' cy='200' r='200'><stop offset='.15' stop-color='#000' stop-opacity='.35'/><stop offset='.5' stop-color='#000' stop-opacity='1'/><stop offset='1' stop-color='#000' stop-opacity='0'/></radialGradient></defs>"
    for arm in range(3):
        a0 = arm * math.tau / 3
        centre = spiral_points(cx, cy, 36, 196, .78, a0, 40)
        widths = [26 * math.sin(math.pi * (i / 40) ** .8) + 3 for i in range(41)]
        body += path(d_poly(ribbon(centre, widths)), "url(#f)", "fill-opacity='.6'")
        body += path(d_poly(ribbon(centre, [x * .5 for x in widths])), "url(#f)", "fill-opacity='.7'")
        for i in range(3, 40, 2):
            x, y = centre[i]
            body += circ(x + r.uniform(-6, 6), y + r.uniform(-6, 6), widths[i] * r.uniform(.5, .9), "url(#f)", "fill-opacity='.5'")
    return svg(400, 400, body, "xMidYMid meet")


D("witchSwirl", witch_swirl())


def rune_ring() -> str:
    """A ritual circle (a mask): two thin rings, a ring of dashes between them and twelve runes of three or four strokes."""
    cx = cy = 180
    r = random.Random(9)
    body = circ(cx, cy, 172, "none", "stroke='#000' stroke-width='1.6'") + circ(cx, cy, 150, "none", "stroke='#000' stroke-width='1' stroke-opacity='.8'") + circ(cx, cy, 176, "none", "stroke='#000' stroke-width='.7' stroke-opacity='.5' stroke-dasharray='2 5'")
    for k in range(12):
        a = math.tau * k / 12
        rr = 161
        gx, gy = cx + rr * math.cos(a), cy + rr * math.sin(a)
        rot = math.degrees(a) + 90
        glyph = ""
        kind = k % 4
        if kind == 0:
            glyph = "M-3 -6L0 -9L3 -6M0 -9V7M-4 2L4 -2"
        elif kind == 1:
            glyph = "M-4 -7L4 -7M0 -7V7M-4 7L4 3"
        elif kind == 2:
            glyph = "M-4 -6Q0 -10 4 -6Q4 0 0 2Q-4 0 -4 -6M0 2V8M-3 5L3 5"
        else:
            glyph = "M0 -8L5 0L0 8L-5 0zM0 -3V3"
        body += f"<g transform='translate({n(gx)} {n(gy)}) rotate({n(rot)})'>{stroke(glyph, '#000', 1.3)}</g>"
        body += circ(cx + 150 * math.cos(a + math.pi / 12), cy + 150 * math.sin(a + math.pi / 12), 1.8, "#000")
    return svg(360, 360, body, "xMidYMid meet")


D("runeRing", rune_ring())


def witch_bolt() -> str:
    """A forked bolt of lightning from the top edge (a mask)."""
    pts = [(54, 0), (40, 52), (62, 70), (34, 130), (58, 150), (30, 210), (44, 218), (26, 296)]
    body = stroke("M" + "L".join(f"{x} {y}" for x, y in pts), "#000", 3.4) + stroke("M62 70L88 100L82 128", "#000", 2.2) + stroke("M34 130L12 150L16 178", "#000", 2) + stroke("M" + "L".join(f"{x} {y}" for x, y in pts), "#000", 8, "stroke-opacity='.22'")
    return svg(100, 300, body, "xMidYMin meet")


D("witchBolt", witch_bolt())


def black_cat() -> str:
    """A cat that sits on a ridge with an arched back and the tail curled up; the eyes are left to two dots of the layer."""
    w, h = 80, 80
    ink = "#06030d"
    body = ell(34, 58, 22, 18, ink) + circ(48, 30, 11, ink) + poly([(39, 24), (41, 10), (48, 20)], ink) + poly([(48, 20), (55, 10), (57, 26)], ink)
    body += rect(30, 62, 6, 18, ink) + rect(44, 64, 6, 16, ink) + stroke("M14 62Q-2 56 4 38Q8 26 18 30", ink, 5)
    body += stroke("M24 44Q36 38 46 44", "#6a55c0", .9, "stroke-opacity='.5'") + stroke("M40 22L41 10M55 12L56 26", "#6a55c0", .7, "stroke-opacity='.5'")
    return svg(w, h, body, "xMidYMax meet")


D("blackCat", black_cat())
