"""Scene art D (skin-scene-d-v3.css): Тыквенный Фонарь, Паутина Полуночи, Час Ведьм, Снежный Шар, Огни Гирлянды, Бой Курантов, Алая Звезда, Багровый Мрак."""
from __future__ import annotations

import math
import random

from scene_kit import (arc_d, art, bezier, circ, d_poly, d_ridge, d_smooth, ell, flip, jag, lingrad, mirror, n, path, pine, poly, radgrad, rect, ribbon, ridge, spiral_points, star_d, stroke, svg)


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


# ── Снежный Шар: городок под снегом, ели, фонарь и снеговик, сани над луной, вихрь снега и блик стеклянного купола ──
SG_DEFS = (lingrad("hw", [(0, "#1f2f5c", 1), (1, "#0c1430", 1)]) + lingrad("hs", [(0, "#c9dcf8", 1), (1, "#7896c8", 1)])
           + lingrad("fg", [(0, "#173a5e", 1), (1, "#0a1a30", 1)]) + lingrad("gd", [(0, "#46659f", 1), (1, "#16264c", 1)]))
SG_SNOW, SG_NIGHT = "#d9e8fc", "#0d1630"


def snow_fir(x: float, base: float, h: float, w: float, tiers: int = 5, fill: str = "url(#fg)", snow: str = SG_SNOW, cap: float = .88) -> str:
    """A fir whose every tier carries a cap of snow with a scalloped edge."""
    pts, (tx, ty, tw_, th_) = pine(x, base, h, w, tiers)
    out = poly(pts, fill) + rect(tx, ty, tw_, th_, "#0a1220")
    top = base - h
    for k in range(tiers):
        y0 = top + k * h * .78 / tiers
        y1 = top + (k + 1) * h * .78 / tiers + h * .06
        half = w * (.28 + .72 * (k + 1) / tiers) / 2
        yc = y0 + (y1 - y0) * (.5 if k else .7)
        hc = half * (yc - y0) / (y1 - y0)
        out += path(f"M{n(x)} {n(y0 - .5)}L{n(x + hc)} {n(yc)}Q{n(x + hc * .5)} {n(yc + h * .03)} {n(x)} {n(yc - .4)}Q{n(x - hc * .5)} {n(yc + h * .03)} {n(x - hc)} {n(yc)}z", snow, f"fill-opacity='{n(cap)}'")
    return out


def snow_house(x: float, base: float, w: float, h: float, roof: float, seed: int, lit: float = .8) -> str:
    """A cottage in the snow: dark walls with a cold edge of moonlight, a steep roof under a thick cap of snow, a chimney, icicles and warm windows."""
    r = random.Random(seed)
    top = base - h
    ax = x + w * r.uniform(.44, .56)
    cx = x + w * r.uniform(.64, .76)
    body = rect(cx, top - roof * .8, w * .13, roof * .62, SG_NIGHT) + rect(cx - 1.2, top - roof * .86, w * .13 + 2.4, 3.4, SG_SNOW)
    body += rect(x, top, w, h, "url(#hw)") + rect(x, top, 1.3, h, "#8db4ee", "fill-opacity='.4'")
    body += poly([(x - 3.4, top + 2), (ax, top - roof), (x + w + 3.4, top + 2)], "url(#hs)")
    body += rect(x - 3.4, top + 2, w + 6.8, 2.2, SG_NIGHT, "fill-opacity='.55'")
    for k in range(int(w // 7)):
        ix = x + 2 + k * 7 + r.uniform(-1, 1)
        body += poly([(ix, top + 4), (ix + 1.5, top + 4), (ix + .75, top + 4 + r.uniform(2.4, 5))], SG_SNOW, "fill-opacity='.8'")
    for k in range(2 if w >= 24 else 1):
        wx = x + (w * (.2 + .5 * k) if w >= 24 else w * .36)
        wy = top + h * r.uniform(.24, .44)
        if r.random() < lit:
            body += rect(wx, wy, 4.8, 6.2, "#ffd27a", f"fill-opacity='{n(r.uniform(.8, 1))}'") + rect(wx + 2.2, wy, .5, 6.2, SG_NIGHT, "fill-opacity='.55'") + rect(wx, wy + 3, 4.8, .5, SG_NIGHT, "fill-opacity='.55'")
        else:
            body += rect(wx, wy, 4.8, 6.2, "#2c4379")
        body += rect(wx - .8, wy + 6.2, 6.4, 1.3, SG_SNOW, "fill-opacity='.85'")
    return body


def snow_church(x: float, base: float) -> str:
    """A tiny church with a nave, a tower under a needle spire with a cross, a lit round window and an arched door."""
    body = rect(x, base - 24, 30, 24, "url(#hw)") + rect(x, base - 24, 1.3, 24, "#8db4ee", "fill-opacity='.4'")
    body += poly([(x - 3, base - 23), (x + 15, base - 38), (x + 33, base - 23)], "url(#hs)") + rect(x + 9, base - 52, 12, 30, "url(#hw)") + rect(x + 9, base - 52, 1.3, 30, "#8db4ee", "fill-opacity='.4'")
    body += poly([(x + 7, base - 52), (x + 15, base - 76), (x + 23, base - 52)], "url(#hs)") + stroke(f"M{n(x + 15)} {n(base - 76)}V{n(base - 86)}M{n(x + 11.6)} {n(base - 83)}H{n(x + 18.4)}", SG_SNOW, 1.3)
    body += path(f"M{n(x + 12)} {n(base - 36)}Q{n(x + 12)} {n(base - 43)} {n(x + 15)} {n(base - 43)}Q{n(x + 18)} {n(base - 43)} {n(x + 18)} {n(base - 36)}z", "#ffd27a", "fill-opacity='.95'") + circ(x + 15, base - 16, 3.2, "#ffd27a", "fill-opacity='.9'")
    body += path(f"M{n(x + 11.5)} {n(base)}V{n(base - 8)}Q{n(x + 11.5)} {n(base - 12)} {n(x + 15)} {n(base - 12)}Q{n(x + 18.5)} {n(base - 12)} {n(x + 18.5)} {n(base - 8)}V{n(base)}z", "#0a1228")
    return body


def snow_town() -> str:
    """The town strip along the bottom (stretched): a row of far firs, a church, two rows of snowed-in cottages with warm windows, a picket fence and the moonlit drifts in front."""
    w, h = 420, 120
    r = random.Random(31)
    body = SG_DEFS
    for x, th, tw in [(10, 36, 15), (44, 28, 12), (92, 32, 13), (150, 24, 10), (222, 26, 11), (258, 34, 14), (358, 30, 13), (404, 38, 15)]:
        body += snow_fir(x, 80, th, tw, 4, "#13244a", "#8aa9d8", .65)
    body += snow_church(292, 94)
    for i, (hx, ww, hh, rr, base) in enumerate([(-10, 30, 24, 15, 98), (18, 26, 30, 17, 100), (42, 34, 22, 15, 98), (72, 28, 27, 16, 101), (98, 34, 24, 15, 98), (130, 30, 29, 17, 100), (158, 28, 22, 14, 98),
                                                 (184, 36, 26, 16, 101), (216, 30, 22, 15, 98), (246, 28, 28, 16, 100), (330, 30, 26, 15, 100), (360, 28, 22, 14, 98), (386, 38, 28, 16, 101)]):
        body += snow_house(hx, base, ww, hh, rr, 40 + i, .85)
    top = ridge(w, 101, 3.2, [(150, .7), (62, .4), (30, .15)], 5, .1, 28)
    body += path(d_ridge(top, w, h), "url(#gd)") + stroke(d_smooth(top, closed=False), "#bcd4f4", 1.1, "stroke-opacity='.55'")
    fence = "".join(f"M{x}{n(102 + 1.2 * math.sin(x / 9))}v7" for x in range(18, 120, 5))
    body += stroke(fence, "#0d1630", 1.2, "stroke-opacity='.8'") + stroke("M18 105Q70 103 116 106", "#0d1630", 1, "stroke-opacity='.8'")
    for dx, dy, rx, ry in [(70, 112, 44, 4), (210, 114, 60, 4), (340, 112, 50, 4)]:
        body += ell(dx, dy, rx, ry, "#9bb9e4", "fill-opacity='.22'")
    return svg(w, h, body, "none")


D("snowTown", snow_town())


def snow_fir_pic() -> str:
    """A big snowed fir for the left edge (mirrored for the right one); its lower branches are cut by the picture edge."""
    w, h = 120, 190
    body = SG_DEFS + snow_fir(54, 190, 188, 108, 6)
    return svg(w, h, body, "xMinYMax meet")


D("snowFir", snow_fir_pic())


def lamp_post() -> str:
    """A street lamp with a snow cap on its lantern and a curled arm; the lantern is lit (its glow is a separate layer of the scene)."""
    w, h = 60, 130
    ink = "#0a1124"
    body = radgrad("lm", [(0, "#fff6c8", 1), (.55, "#ffd070", 1), (1, "#ff9a3c", 1)])
    body += rect(28.2, 40, 3.6, 84, ink) + path("M21 126Q24 117 28.2 117H31.8Q36 117 39 126z", ink) + rect(25.6, 94, 8.8, 3.2, ink) + rect(26.4, 64, 7.2, 2.6, ink)
    body += stroke("M30 76Q45 72 47 85Q47 90 43 90", ink, 1.8) + circ(42.6, 90, 2, ink)
    body += poly([(16.5, 37), (30, 22.4), (43.5, 37)], ink) + rect(28.6, 15.6, 2.8, 8, ink) + circ(30, 14.4, 2.2, ink)
    body += path("M17.5 36.4L30 23.6L42.5 36.4Q36 34.2 30 36.6Q24 34.2 17.5 36.4z", SG_SNOW, "fill-opacity='.95'")
    body += rect(20.2, 37, 19.6, 22, "url(#lm)") + rect(20.2, 37, 19.6, 22, "none", f"stroke='{ink}' stroke-width='1.5'") + rect(29.4, 37, 1.2, 22, ink, "fill-opacity='.7'")
    body += rect(18.6, 59, 22.8, 3.6, ink) + poly([(21, 62.6), (39, 62.6), (33, 68), (27, 68)], ink)
    return svg(w, h, body, "xMidYMax meet")


D("lampPost", lamp_post())


def snowman() -> str:
    """A snowman in a top hat and a red scarf, coal eyes and buttons, a carrot nose and two twig arms; lit from the top left, cold at the right edge."""
    w, h = 44, 72
    body = lingrad("sn", [(0, "#eef6ff", 1), (1, "#7f9fd0", 1)], 0, 0, 1, 1)
    body += circ(22, 58, 14.5, "url(#sn)") + circ(22, 38, 10.6, "url(#sn)") + circ(22, 22.5, 8, "url(#sn)")
    body += stroke("M33 49Q36 58 30 68", "#16264c", 2, "stroke-opacity='.3'") + stroke("M31 33Q33 40 29 46", "#16264c", 1.8, "stroke-opacity='.3'")
    body += stroke("M12 38L2 29M5 31L3 26M31 39L41 33M38 35L41 38", "#2a1c14", 1.5)
    body += rect(13, 12.4, 18, 2.8, "#0d1630") + rect(16.4, 2, 11.2, 11, "#0d1630") + rect(16.4, 9, 11.2, 2.4, "#e8566f")
    body += circ(19.2, 21, .95, "#0d1630") + circ(24.8, 21, .95, "#0d1630") + poly([(22, 22.6), (30, 24), (22, 25)], "#ff8a3c")
    body += rect(13, 28.6, 18, 3.8, "#e8566f") + poly([(25, 31), (30, 31), (31.5, 42), (26, 42)], "#e8566f") + stroke("M14 30.6H30", "#ff9aae", .8, "stroke-opacity='.6'")
    for y in (37, 42.5, 54, 61):
        body += circ(22, y, 1.1, "#0d1630")
    return svg(w, h, body, "xMidYMax meet")


D("snowman", snowman())


def reindeer(x: float, y: float, s: float, lift: float) -> str:
    """A leaping reindeer facing right (a silhouette for a mask): body, neck and head with branching antlers, forelegs out front and hind legs stretched back."""
    ink = "#000"
    body = ell(x, y, 11 * s, 5.2 * s, ink, f"transform='rotate({n(-10 - lift)} {n(x)} {n(y)})'")
    body += path(f"M{n(x + 7 * s)} {n(y - 3 * s)}Q{n(x + 11 * s)} {n(y - 9 * s)} {n(x + 14 * s)} {n(y - 13 * s)}L{n(x + 17 * s)} {n(y - 11 * s)}Q{n(x + 15 * s)} {n(y - 3 * s)} {n(x + 10 * s)} {n(y + 2 * s)}z", ink)
    body += ell(x + 17.5 * s, y - 13 * s, 4.2 * s, 2.6 * s, ink, f"transform='rotate(-18 {n(x + 17.5 * s)} {n(y - 13 * s)})'")
    body += stroke(f"M{n(x + 15 * s)} {n(y - 15 * s)}L{n(x + 13 * s)} {n(y - 22 * s)}M{n(x + 14 * s)} {n(y - 19 * s)}L{n(x + 18 * s)} {n(y - 23 * s)}M{n(x + 13 * s)} {n(y - 22 * s)}L{n(x + 10 * s)} {n(y - 24 * s)}", ink, 1.1 * s)
    body += stroke(f"M{n(x + 8 * s)} {n(y + 3 * s)}L{n(x + 17 * s)} {n(y + 1 * s)}L{n(x + 20 * s)} {n(y + 3 * s)}M{n(x + 6 * s)} {n(y + 4 * s)}L{n(x + 14 * s)} {n(y + 7 * s)}L{n(x + 18 * s)} {n(y + 6 * s)}", ink, 1.7 * s)
    body += stroke(f"M{n(x - 8 * s)} {n(y + 1 * s)}L{n(x - 17 * s)} {n(y + 5 * s)}L{n(x - 21 * s)} {n(y + 4 * s)}M{n(x - 6 * s)} {n(y + 3 * s)}L{n(x - 14 * s)} {n(y + 9 * s)}L{n(x - 18 * s)} {n(y + 9 * s)}", ink, 1.7 * s)
    return body


def sleigh() -> str:
    """Santa's sleigh in a leap (a mask): two reindeer on thin reins, a curled runner, Santa in a pointed hat and a sack at his back."""
    w, h = 150, 56
    ink = "#000"
    body = reindeer(112, 24, 1, 2) + reindeer(78, 28, .9, 6)
    body += stroke("M100 26Q80 28 56 30M66 30Q58 31 54 31", ink, .7)
    body += path("M10 34Q12 30 24 30L52 29Q58 26 60 20L62 22Q62 34 52 40L22 42Q10 42 6 36Q4 34 8 32z", ink)
    body += stroke("M4 46Q24 48 52 44Q58 42 62 36Q66 30 62 24", ink, 1.6) + stroke("M24 43L22 48M44 42L46 47", ink, 1.2)
    body += circ(44, 22, 4.2, ink) + poly([(40, 19), (45, 8), (48, 20)], ink) + circ(45.5, 7.4, 2, ink) + ell(24, 24, 11, 7.5, ink)
    return svg(w, h, body, "xMidYMid meet")


D("sleigh", sleigh())


def snow_swirl() -> str:
    """A swirl of snow (a mask): three arms of flakes that curl out of the middle and thin out towards the edge, a few of them six-armed crystals."""
    cx = cy = 150
    r = random.Random(7)
    body = "<defs><radialGradient id='f' gradientUnits='userSpaceOnUse' cx='150' cy='150' r='150'><stop offset='.1' stop-color='#000' stop-opacity='.35'/><stop offset='.45' stop-color='#000' stop-opacity='1'/><stop offset='1' stop-color='#000' stop-opacity='0'/></radialGradient></defs>"
    for arm in range(3):
        a0 = arm * math.tau / 3
        centre = spiral_points(cx, cy, 22, 146, .72, a0, 46)
        for i, (x, y) in enumerate(centre):
            spread = 4 + 18 * math.sin(math.pi * (i / 46) ** .8)
            for _ in range(4 if i % 2 else 2):
                dx, dy = r.uniform(-spread, spread), r.uniform(-spread, spread)
                body += circ(x + dx, y + dy, r.uniform(1, 2.8), "url(#f)", f"fill-opacity='{n(r.uniform(.6, 1))}'")
            if i % 6 == 3:
                for k in range(3):
                    a = k * math.pi / 3
                    body += stroke(f"M{n(x - 6 * math.cos(a))} {n(y - 6 * math.sin(a))}L{n(x + 6 * math.cos(a))} {n(y + 6 * math.sin(a))}", "url(#f)", 1.3)
    return svg(300, 300, body, "xMidYMid meet")


D("snowSwirl", snow_swirl())


def dome_glint() -> str:
    """The reflections on the glass of a big sphere (a mask the size of the scene): a long crescent at the top left, a short one at the top right, a thin arc at the lower right and two specks of light."""
    w, h = 400, 260
    cx, cy, rx, ry = 200, 130, 190, 122

    def arc(a0: float, a1: float, k: float, wmax: float, steps: int = 20) -> str:
        pts = [(cx + rx * k * math.cos(math.radians(a0 + (a1 - a0) * i / steps)), cy + ry * k * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]
        return path(d_poly(ribbon(pts, [wmax * math.sin(math.pi * i / steps) ** .8 + .25 for i in range(steps + 1)])), "#000")
    body = arc(196, 262, .93, 4.2) + arc(292, 318, .93, 2.4) + arc(16, 52, .93, 2) + arc(208, 250, .84, 1.6)
    body += ell(92, 62, 7, 3.2, "#000", "transform='rotate(-38 92 62)'") + circ(112, 46, 1.9, "#000")
    return svg(w, h, body, "xMidYMid meet")


D("domeGlint", dome_glint())


# ── Огни Гирлянды: подарки у ёлки, ёлка с шарами и звездой, замёрзшее окно со шторами, гирлянда под потолком, шары на нитях и венок из огней ──
GL_PINK, GL_GREEN, GL_GOLD = "#ff6b8a", "#35d68a", "#ffd36b"


def gift(x: float, base: float, w: float, h: float, body: str, ribbon: str, bow: bool = True) -> str:
    """A wrapped present: a box with a darker lid, a ribbon across and along it, and a bow of two loops."""
    top = base - h
    out = rect(x, top, w, h, body) + rect(x, top, w, h * .34, "#000", "fill-opacity='.16'") + rect(x - 1, top, w + 2, h * .22, body) + rect(x - 1, top + h * .2, w + 2, 1.2, "#000", "fill-opacity='.35'")
    out += rect(x + w / 2 - w * .09, top, w * .18, h, ribbon) + rect(x - 1, top + h * .05, w + 2, h * .1, ribbon, "fill-opacity='.9'")
    out += rect(x, top, 1.4, h, "#fff", "fill-opacity='.14'")
    if bow:
        cx, cy = x + w / 2, top - 1
        out += path(f"M{n(cx)} {n(cy)}Q{n(cx - w * .34)} {n(cy - h * .5)} {n(cx - w * .3)} {n(cy - h * .12)}Q{n(cx - w * .2)} {n(cy + 1)} {n(cx)} {n(cy)}z", ribbon)
        out += path(f"M{n(cx)} {n(cy)}Q{n(cx + w * .34)} {n(cy - h * .5)} {n(cx + w * .3)} {n(cy - h * .12)}Q{n(cx + w * .2)} {n(cy + 1)} {n(cx)} {n(cy)}z", ribbon)
        out += circ(cx, cy, max(1.1, w * .06), ribbon) + circ(cx, cy, max(.5, w * .03), "#fff", "fill-opacity='.4'")
    return out


def gift_row() -> str:
    """The floor of the room along the bottom (stretched): a dark boards line with a warm highlight and presents in a few heaps, most of them at the sides, around the tree."""
    w, h = 420, 120
    body = lingrad("fl", [(0, "#2a0f1e", 1), (1, "#0a0408", 1)])
    body += rect(0, 100, w, 22, "url(#fl)") + stroke("M0 100.5H420", "#ff9ab0", .9, "stroke-opacity='.4'")
    for x in range(30, w, 46):
        body += rect(x, 101, .8, 21, "#000", "fill-opacity='.4'")
    heaps = [(4, 106, 24, 22, "#b52f58", GL_GOLD), (30, 106, 16, 14, "#1d8a58", "#ff8fa6"), (22, 84, 14, 12, "#d6a94e", "#b52f58"), (50, 106, 12, 10, "#2a3a82", GL_GOLD),
             (92, 107, 14, 9, "#8f1d3c", GL_GREEN), (196, 107, 10, 8, "#1d8a58", GL_GOLD),
             (300, 107, 14, 10, "#2a3a82", "#ff8fa6"), (318, 107, 22, 18, "#1d8a58", "#ff8fa6"), (344, 107, 18, 14, "#d6a94e", "#b52f58"), (366, 107, 24, 24, "#b52f58", GL_GOLD), (394, 107, 20, 12, "#8f1d3c", GL_GREEN),
             (332, 89, 12, 10, "#b52f58", GL_GOLD)]
    for gx, gb, gw, gh, gc, gr in heaps:
        body += gift(gx, gb, gw, gh, gc, gr)
    return svg(w, h, body, "none")


D("giftRow", gift_row())


def xmas_tree() -> str:
    """A tall decorated fir: dark green tiers lit from the left, three golden garlands, baubles in pink, gold, green and red with a glint, a star on top and a skirt at the foot (the lights are separate layers)."""
    w, h = 100, 210
    body = lingrad("tg", [(0, "#14603f", 1), (1, "#06241a", 1)], 0, 0, 1, 0) + radgrad("bs", [(0, "#fff", .85), (.35, "#fff", 0)], .3, .28, .7)
    pts, (tx, ty, tw_, th_) = pine(50, 196, 180, 80, 6)
    body += poly(pts, "url(#tg)") + rect(tx, ty, tw_, th_, "#2a1608") + stroke(d_poly([pts[1], pts[4], pts[7]])[:-1], "#4fc58a", .8, "stroke-opacity='.25'")
    body += ell(50, 199, 36, 6.5, "#8f1d3c") + ell(50, 197.5, 36, 5, "#b52f58") + stroke("M14 199Q50 208 86 199", GL_GOLD, 1, "stroke-opacity='.8'")
    for y0, amp, half in [(60, 9, 20), (92, 12, 28), (124, 14, 35), (158, 16, 40)]:
        body += stroke(f"M{n(50 - half)} {n(y0)}Q50 {n(y0 + amp * 1.8)} {n(50 + half)} {n(y0)}", GL_GOLD, 1.5, "stroke-opacity='.85'")
    balls = [(40, 52, GL_PINK), (58, 74, GL_GOLD), (34, 88, GL_GREEN), (66, 110, "#e8465e"), (28, 128, GL_GOLD), (52, 138, GL_PINK), (70, 150, GL_GREEN), (22, 160, "#e8465e"), (44, 170, GL_GOLD), (62, 178, GL_PINK), (80, 172, GL_GOLD), (16, 176, GL_GREEN), (50, 104, GL_GREEN), (46, 76, "#e8465e")]
    for bx, by, bc in balls:
        body += circ(bx, by, 3.6, bc) + circ(bx, by, 3.6, "url(#bs)") + rect(bx - 1, by - 4.9, 2, 1.6, GL_GOLD)
    star = d_poly([(50 + (7.5 if k % 2 == 0 else 3.2) * math.cos(-math.pi / 2 + k * math.pi / 5), 15 + (7.5 if k % 2 == 0 else 3.2) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)])
    body += path(star, "#ffe9a6") + stroke(star, "#ffb347", .7, "stroke-opacity='.8'")
    return svg(w, h, body, "xMidYMax meet")


D("xmasTree", xmas_tree())


def frost_window() -> str:
    """A window on a snowy night with frost in the corners, a stone sill and two drapes tied back with gold cords: the panes show a dark blue sky with stars and snow and a roof line."""
    w, h = 100, 124
    ink = "#241019"
    body = lingrad("sk", [(0, "#0f2650", 1), (1, "#143a5c", 1)]) + lingrad("dr", [(0, "#8f1d3c", 1), (1, "#5a0f26", 1)], 0, 0, 1, 0)
    body += rect(6, 4, 88, 112, ink) + rect(10, 8, 38, 49, "url(#sk)") + rect(52, 8, 38, 49, "url(#sk)") + rect(10, 61, 38, 51, "url(#sk)") + rect(52, 61, 38, 51, "url(#sk)")
    r = random.Random(3)
    for _ in range(26):
        x, y = r.uniform(11, 89), r.uniform(9, 110)
        body += circ(x, y, r.uniform(.4, .9), "#fff", f"fill-opacity='{n(r.uniform(.4, .95))}'")
    body += poly([(10, 112), (10, 98), (22, 92), (30, 98), (36, 91), (48, 98), (48, 112)], "#0a1a30") + poly([(52, 112), (52, 99), (62, 94), (72, 99), (80, 93), (90, 99), (90, 112)], "#0a1a30")
    body += rect(14, 98, 3, 4, "#ffd27a", "fill-opacity='.9'") + rect(60, 99, 3, 4, "#ffd27a", "fill-opacity='.8'")
    for cx, cy, sx, sy in [(10, 8, 1, 1), (90, 8, -1, 1), (10, 112, 1, -1), (90, 112, -1, -1), (10, 61, 1, 1), (90, 61, -1, 1)]:
        for k, (ex, ey) in enumerate([(14, 4), (10, 9), (5, 14), (16, 12)]):
            body += stroke(f"M{n(cx)} {n(cy)}L{n(cx + sx * ex)} {n(cy + sy * ey)}M{n(cx + sx * ex * .55)} {n(cy + sy * ey * .55)}l{n(sx * 2.2)} {n(sy * -1.8)}", "#e8f4ff", .8, "stroke-opacity='.55'")
    body += rect(2, 116, 96, 5, "#cdb7a5") + rect(2, 116, 96, 1.2, "#fff", "fill-opacity='.35'")
    body += path("M0 0H24Q16 26 20 60Q12 90 8 118H0z", "url(#dr)") + path("M100 0H76Q84 26 80 60Q88 90 92 118H100z", "url(#dr)")
    for dx in (7, 13, 18):
        body += stroke(f"M{dx} 4Q{dx - 4} 40 {dx - 2} 112", "#2a0612", 1, "stroke-opacity='.5'") + stroke(f"M{100 - dx} 4Q{100 - dx + 4} 40 {100 - dx + 2} 112", "#2a0612", 1, "stroke-opacity='.5'")
    body += stroke("M2 66Q14 60 22 70", GL_GOLD, 1.8) + stroke("M98 66Q86 60 78 70", GL_GOLD, 1.8) + circ(22, 70, 2, GL_GOLD) + circ(78, 70, 2, GL_GOLD)
    return svg(w, h, body, "xMaxYMin meet")


D("frostWindow", frost_window())


def swag_bulbs():
    """Where the bulbs hang on the ceiling garland (picture units, 420 x 70): the points on three sagging spans and the colour of each, in turn."""
    out, k = [], 0
    for x0 in (0, 140, 280):
        for i in range(1, 9):
            t = i / 9
            x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * (x0 + 70) + t * t * (x0 + 140)
            y = (1 - t) ** 2 * 8 + 2 * (1 - t) * t * 58 + t * t * 8
            out.append((x, y + 1.5, k % 3))
            k += 1
    return out


def swag_top() -> str:
    """The garland under the ceiling (stretched over the top strip): a dark cord sagging in three spans from gold hooks, with a glass bulb hanging at every step (pink, green, gold in turn; the light in them is a separate layer)."""
    w, h = 420, 70
    body = ""
    cord = "M0 8Q70 58 140 8Q210 58 280 8Q350 58 420 8"
    body += stroke(cord, "#120a10", 1.7) + stroke(cord, "#ff9ab0", .6, "stroke-opacity='.25'")
    for x in (0, 140, 280, 420):
        body += circ(x, 7, 2.2, GL_GOLD)
    cols = ("#c4365c", "#1f9a62", "#d7ac4c")
    for x, y, c in swag_bulbs():
        body += rect(x - 1.5, y - 1.2, 3, 2.6, "#120a10") + path(f"M{n(x - 1.4)} {n(y + 1.2)}Q{n(x - 3.6)} {n(y + 6)} {n(x)} {n(y + 8.4)}Q{n(x + 3.6)} {n(y + 6)} {n(x + 1.4)} {n(y + 1.2)}z", cols[c])
        body += ell(x - .9, y + 4.2, .7, 1.4, "#fff", "fill-opacity='.45'")
    return svg(w, h, body, "none")


D("swagTop", swag_top())


def ornaments() -> str:
    """Three glass baubles on thin threads of different length, hanging from the top (they sway as one picture): pink with a gold band, green, and gold with a pink band."""
    w, h = 100, 92
    body = radgrad("gl", [(0, "#fff", .85), (.35, "#fff", 0)], .3, .28, .7)
    for x, ln, r, col, band in [(20, 40, 8.5, GL_PINK, GL_GOLD), (50, 66, 7.5, GL_GREEN, "#fff"), (79, 28, 6.5, GL_GOLD, GL_PINK)]:
        body += stroke(f"M{x} 0V{ln - r}", "#e8d4b8", .8, "stroke-opacity='.55'") + rect(x - 1.8, ln - r - 3.4, 3.6, 3.4, GL_GOLD) + circ(x, ln, r, col) + stroke(f"M{n(x - r * .94)} {n(ln - r * .3)}Q{x} {n(ln + r * .25)} {n(x + r * .94)} {n(ln - r * .3)}", band, 1.4, "stroke-opacity='.85'") + circ(x, ln, r, "url(#gl)")
    return svg(w, h, body, "xMinYMin meet")


D("ornaments", ornaments())


def sparkle() -> str:
    """A bright four-point flare with a smaller one across it (a mask)."""
    body = path(star_d(50, 50, 48, .11), "#000") + f"<g transform='rotate(45 50 50)'>{path(star_d(50, 50, 30, .16), '#000')}</g>" + circ(50, 50, 5, "#000")
    return svg(100, 100, body, "xMidYMid meet")


D("sparkle", sparkle())


def wreath() -> str:
    """A ring of bulbs on a cord (a mask): twenty-eight teardrop bulbs that point outwards, with a ring of tiny dots outside."""
    cx = cy = 170
    body = circ(cx, cy, 148, "none", "stroke='#000' stroke-width='1.4'")
    for k in range(28):
        a = math.tau * k / 28
        bx, by = cx + 156 * math.cos(a), cy + 156 * math.sin(a)
        body += f"<g transform='translate({n(bx)} {n(by)}) rotate({n(math.degrees(a) + 90)})'>{rect(-1.3, 5.6, 2.6, 3, '#000')}{ell(0, 0, 3.4 if k % 2 else 2.8, 5.2 if k % 2 else 4.4, '#000')}</g>"
        body += circ(cx + 168 * math.cos(a + math.pi / 28), cy + 168 * math.sin(a + math.pi / 28), 1.2, "#000", "fill-opacity='.7'")
    return svg(340, 340, body, "xMidYMid meet")


D("wreath", wreath())


# ── Бой Курантов: крыши старого города с куполами, башня с часами, бокалы с золотом, салют: круглый и «ива» ──
MC_GOLD, MC_NIGHT = "#ffd36b", "#0a0d22"


def mc_defs() -> str:
    return (lingrad("bw", [(0, "#1a2048", 1), (1, "#090c20", 1)]) + lingrad("dm", [(0, "#ffe9a0", 1), (.55, "#e0a83e", 1), (1, "#9a5f18", 1)], 0, 0, 1, 0)
            + lingrad("cf", [(0, "#fff4cf", 1), (1, "#e2b560", 1)], 0, 0, 1, 1))


def onion(cx: float, base: float, r: float, h: float) -> str:
    """A golden onion dome on a drum, with a thin cross."""
    body = rect(cx - r * .62, base, r * 1.24, h * .22, "url(#bw)")
    body += path(f"M{n(cx - r * .62)} {n(base)}Q{n(cx - r * 1.5)} {n(base - h * .34)} {n(cx)} {n(base - h)}Q{n(cx + r * 1.5)} {n(base - h * .34)} {n(cx + r * .62)} {n(base)}z", "url(#dm)")
    body += stroke(f"M{n(cx)} {n(base - h)}V{n(base - h - r * .9)}M{n(cx - r * .3)} {n(base - h - r * .55)}H{n(cx + r * .3)}", MC_GOLD, 1)
    return body


def city_block(x: float, base: float, w: float, h: float, kind: str, seed: int, lit: float = .55) -> str:
    """An old-town house: a dark body with a thin rim of gold on its left edge, a roof of one of a few kinds (flat cornice, mansard, gable) and warm windows in rows."""
    r = random.Random(seed)
    top = base - h
    body = rect(x, top, w, h, "url(#bw)") + rect(x, top, 1.2, h, MC_GOLD, "fill-opacity='.3'")
    if kind == "mansard":
        body += poly([(x - 1.5, top + 1), (x + w * .16, top - 8), (x + w * .84, top - 8), (x + w + 1.5, top + 1)], "#0c1028") + stroke(f"M{n(x + w * .16)} {n(top - 8)}H{n(x + w * .84)}", MC_GOLD, .7, "stroke-opacity='.4'")
    elif kind == "gable":
        body += poly([(x - 1.5, top + 1), (x + w / 2, top - w * .42), (x + w + 1.5, top + 1)], "#0c1028") + stroke(f"M{n(x - 1.5)} {n(top + 1)}L{n(x + w / 2)} {n(top - w * .42)}", MC_GOLD, .7, "stroke-opacity='.4'")
    else:
        body += rect(x - 1.5, top - 2.4, w + 3, 3.4, "#0c1028") + rect(x - 1.5, top - 2.4, w + 3, .8, MC_GOLD, "fill-opacity='.35'")
    cols = max(1, int(w // 7))
    rows = max(1, int((h - 6) // 9))
    for rr in range(rows):
        for cc in range(cols):
            if r.random() < lit:
                body += rect(x + 3 + cc * (w - 6) / cols, top + 5 + rr * 9, 3.2, 4.6, MC_GOLD, f"fill-opacity='{n(r.uniform(.55, 1))}'")
    return body


def city_roofs() -> str:
    """The old town along the bottom (stretched): a cluster of golden domes on the left, houses of many kinds and heights with warm windows, and the dark street below."""
    w, h = 420, 120
    body = mc_defs()
    body += onion(88, 70, 11, 28) + onion(70, 76, 7, 18) + onion(106, 76, 7, 18) + rect(64, 76, 48, 26, "url(#bw)") + rect(64, 76, 48, 1.1, MC_GOLD, "fill-opacity='.4'")
    for k in range(5):
        body += path(f"M{70 + k * 9} 102V90Q{70 + k * 9} 84 {74.5 + k * 9} 84Q{79 + k * 9} 84 {79 + k * 9} 90V102z", MC_GOLD, "fill-opacity='.8'")
    plan = [(-6, 28, 38, "flat"), (22, 24, 30, "mansard"), (46, 18, 44, "gable"), (116, 26, 34, "mansard"), (142, 30, 26, "flat"), (172, 24, 40, "gable"), (196, 28, 30, "mansard"), (224, 24, 36, "flat"),
            (248, 30, 28, "gable"), (278, 26, 42, "mansard"), (304, 28, 30, "flat"), (332, 22, 36, "gable"), (354, 30, 28, "mansard"), (384, 40, 34, "flat")]
    for i, (bx, bw, bh, kind) in enumerate(plan):
        body += city_block(bx, 102, bw, bh, kind, 50 + i, .55)
    body += poly([(206, 64), (212, 36), (218, 64)], "#0c1028") + stroke("M212 36V28", MC_GOLD, .8)
    body += rect(0, 102, w, 18, "#07091a") + rect(0, 102, w, 1, MC_GOLD, "fill-opacity='.3'")
    for x in range(14, w, 46):
        body += ell(x, 108, 14, 1.6, MC_GOLD, "fill-opacity='.16'")
    return svg(w, h, body, "none")


D("cityRoofs", city_roofs())


def clock_tower() -> str:
    """A tall clock tower in the manner of a Kremlin gate: a base with lit arches, a shaft, a block with a big round dial (both hands at twelve), a belfry of lit arches, a tiered hip roof and a red star on a spire."""
    w, h = 56, 210
    body = mc_defs()
    body += rect(9, 160, 38, 50, "url(#bw)") + rect(7, 158, 42, 4, "#0c1028") + rect(7, 158, 42, .9, MC_GOLD, "fill-opacity='.45'")
    for x in (14, 25, 36):
        body += path(f"M{x} 205V188Q{x} 181 {x + 3} 181Q{x + 6} 181 {x + 6} 188V205z", MC_GOLD, "fill-opacity='.85'")
    body += rect(13, 108, 30, 52, "url(#bw)") + rect(13, 108, 1.2, 52, MC_GOLD, "fill-opacity='.3'") + path("M25 150V132Q25 128 28 128Q31 128 31 132V150z", MC_GOLD, "fill-opacity='.75'")
    body += rect(5, 60, 46, 50, "url(#bw)") + rect(3, 108, 50, 4, "#0c1028") + rect(3, 108, 50, .9, MC_GOLD, "fill-opacity='.45'") + rect(5, 60, 1.2, 50, MC_GOLD, "fill-opacity='.3'")
    body += circ(28, 86, 18.5, "#0c1028") + circ(28, 86, 17, "url(#cf)") + circ(28, 86, 17, "none", f"stroke='{MC_GOLD}' stroke-width='1.2'")
    for k in range(12):
        a = math.tau * k / 12
        body += stroke(f"M{n(28 + 13.6 * math.cos(a))} {n(86 + 13.6 * math.sin(a))}L{n(28 + 15.6 * math.cos(a))} {n(86 + 15.6 * math.sin(a))}", "#3a2608", 1.1 if k % 3 == 0 else .7)
    body += stroke("M28 86V71M28 86V77", "#2a1a06", 1.6) + circ(28, 86, 1.8, "#2a1a06")
    body += rect(10, 34, 36, 28, "url(#bw)") + rect(10, 34, 1.2, 28, MC_GOLD, "fill-opacity='.3'")
    for x in (14, 24, 34):
        body += path(f"M{x} 62V46Q{x} 41 {x + 4} 41Q{x + 8} 41 {x + 8} 46V62z", MC_GOLD, "fill-opacity='.8'")
    body += poly([(8, 36), (28, 12), (48, 36)], "#0c1028") + poly([(14, 24), (28, 6), (42, 24), (36, 24), (28, 14), (20, 24)], "url(#bw)") + stroke("M8 36L28 12", MC_GOLD, .8, "stroke-opacity='.5'")
    body += stroke("M28 12V3", "#c9863a", 1.1)
    star = d_poly([(28 + (4.6 if k % 2 == 0 else 1.9) * math.cos(-math.pi / 2 + k * math.pi / 5), 3 + (4.6 if k % 2 == 0 else 1.9) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)])
    body += path(star, "#ff3b4e") + stroke(star, "#ffb0a0", .5, "stroke-opacity='.8'")
    return svg(w, h, body, "xMidYMax meet")


D("clockTower", clock_tower())


def flutes() -> str:
    """Two champagne flutes tipped towards each other at the rims, golden wine with tiny bubbles in glass drawn with thin white outlines, slim stems and round feet."""
    w, h = 90, 80
    body = lingrad("wn", [(0, "#ffe9a0", .95), (1, "#c9863a", .95)]) + radgrad("bb", [(0, "#fff", .9), (1, "#fff", 0)])
    for cx, ang in ((29, 13), (61, -13)):
        g = f"<g transform='rotate({ang} {cx} 76)'>"
        g += path(f"M{cx - 6.6} 6L{cx - 4.4} 46Q{cx - 4.2} 54 {cx} 54Q{cx + 4.2} 54 {cx + 4.4} 46L{cx + 6.6} 6z", "#fff", "fill-opacity='.1'")
        g += path(f"M{cx - 6.1} 15L{cx - 4.3} 46Q{cx - 4.1} 53.2 {cx} 53.2Q{cx + 4.1} 53.2 {cx + 4.3} 46L{cx + 6.1} 15z", "url(#wn)")
        g += stroke(f"M{cx - 6.1} 15Q{cx} 17 {cx + 6.1} 15", "#fff7d6", .8, "stroke-opacity='.8'")
        g += stroke(f"M{cx - 6.6} 6L{cx - 4.4} 46Q{cx - 4.2} 54 {cx} 54Q{cx + 4.2} 54 {cx + 4.4} 46L{cx + 6.6} 6", "#fff", .9, "stroke-opacity='.75'")
        g += stroke(f"M{cx - 3.6} 16L{cx - 2.6} 44", "#fff", .8, "stroke-opacity='.5'")
        for bx, by, br in ((-1.8, 40, 1), (1.4, 33, .8), (-.6, 27, 1), (1.8, 21, .7), (-1.6, 46, .7)):
            g += circ(cx + bx, by, br, "url(#bb)")
        g += rect(cx - .8, 54, 1.6, 17, "#fff", "fill-opacity='.7'") + ell(cx, 72.4, 7.4, 1.8, "#fff", "fill-opacity='.65'") + "</g>"
        body += g
    return svg(w, h, body, "xMinYMax meet")


D("flutes", flutes())


def burst() -> str:
    """A round firework (a mask): twenty-four long rays with a bead at the tip, twenty-four short rays between them and a bright heart."""
    cx = cy = 100
    body = ""
    for k in range(24):
        a = math.tau * k / 24
        body += stroke(f"M{n(cx + 16 * math.cos(a))} {n(cy + 16 * math.sin(a))}L{n(cx + 84 * math.cos(a))} {n(cy + 84 * math.sin(a))}", "#000", 1.6) + circ(cx + 88 * math.cos(a), cy + 88 * math.sin(a), 3.4, "#000")
        b = a + math.tau / 48
        body += stroke(f"M{n(cx + 24 * math.cos(b))} {n(cy + 24 * math.sin(b))}L{n(cx + 52 * math.cos(b))} {n(cy + 52 * math.sin(b))}", "#000", 1.2) + circ(cx + 57 * math.cos(b), cy + 57 * math.sin(b), 2.2, "#000")
    body += circ(cx, cy, 7, "#000")
    return svg(200, 200, body, "xMidYMid meet")


D("burst", burst())


def willow() -> str:
    """A drooping firework like a willow (a mask): eighteen arcs that leave the heart, bend over and fall, each ending in a trail of dots."""
    cx, cy = 110, 80
    body = ""
    for k in range(18):
        a = -math.pi / 2 + (k - 8.5) * math.radians(17)
        ex, ey = cx + 70 * math.cos(a), cy + 64 * math.sin(a)
        fx, fy = ex + 26 * math.cos(a) * .4, ey + 70
        body += stroke(f"M{cx} {cy}Q{n(ex)} {n(ey - 8)} {n(fx)} {n(fy)}", "#000", 1.3)
        for t in (.74, .84, .94):
            px = (1 - t) ** 2 * cx + 2 * (1 - t) * t * ex + t * t * fx
            py = (1 - t) ** 2 * cy + 2 * (1 - t) * t * (ey - 8) + t * t * fy
            body += circ(px + 2, py + 5 * t, 1.9 - (t - .74) * 4, "#000")
    body += circ(cx, cy, 6, "#000")
    return svg(220, 180, body, "xMidYMin meet")


D("willow", willow())


# ── Алая Звезда: неоновая вывеска-звезда, созвездие, закрученная лента вдоль низа, комета и кольцо звёзд вокруг аватара (всё маски: цвет даёт слой) ──
def star5(cx: float, cy: float, big: float, small: float, rot: float = -math.pi / 2):
    """Points of a five-point star: ten vertices on two radii."""
    return [(cx + (big if i % 2 == 0 else small) * math.cos(rot + math.pi * i / 5), cy + (big if i % 2 == 0 else small) * math.sin(rot + math.pi * i / 5)) for i in range(10)]


def tube(d: str, w: float, halo: float = .2) -> str:
    """A neon tube (a mask): the line and a wider faint copy around it, the glow."""
    return stroke(d, "#000", w * 3.4, f"stroke-opacity='{halo}'") + stroke(d, "#000", w)


def star_sign() -> str:
    """A neon star sign: the outline of a star, a smaller one inside it and a bright heart."""
    body = tube(d_poly(star5(100, 106, 86, 40)), 4.8, .26) + tube(d_poly(star5(100, 106, 45, 21)), 3, .2) + circ(100, 106, 5.5, "#000")
    return svg(200, 200, body, "xMidYMid meet")


D("starSign", star_sign())


def star_map() -> str:
    """A flat constellation of eight glints joined by thin lines (it lies between the notice and the greeting)."""
    pts = [(10, 32, 4), (38, 15, 5.5), (70, 27, 4), (104, 9, 7), (136, 25, 4.5), (166, 11, 5.5), (192, 31, 4), (86, 40, 3)]
    body = stroke("M" + "L".join(f"{x} {y}" for x, y, _ in pts[:7]), "#000", 1.2, "stroke-opacity='.62'") + stroke("M70 27L86 40", "#000", 1.2, "stroke-opacity='.62'")
    for x, y, r in pts:
        body += path(star_d(x, y, r * 1.5), "#000") + circ(x, y, 1.5, "#000")
    return svg(200, 46, body, "xMinYMin meet")


D("starMap", star_map())


def ribbon_floor() -> str:
    """A satin ribbon laid along the bottom edge: it twists, so its two edges cross every few dozen units; the lenses between the crossings are faintly filled, a glint sits on some crossings."""
    w, h, half, amp = 420, 60, 42, 12
    mid = lambda x: 34 + 6 * math.sin(x / 130 * math.tau + .7)   # noqa: E731 (the whole ribbon undulates)
    body = ""
    for k in range(w // half):
        x0 = k * half
        top = [(x0 + half * i / 7, mid(x0 + half * i / 7) - amp * math.sin(math.pi * i / 7) * (1 if k % 2 == 0 else -1)) for i in range(8)]
        low = [(x, 2 * mid(x) - y) for x, y in top]
        body += poly(top + low[::-1], "#000", f"fill-opacity='{.16 if k % 2 == 0 else .06}'") + stroke("M" + "L".join(f"{n(x)} {n(y)}" for x, y in top), "#000", 5.6, "stroke-opacity='.18'") + stroke("M" + "L".join(f"{n(x)} {n(y)}" for x, y in low), "#000", 5.6, "stroke-opacity='.18'")
        body += stroke("M" + "L".join(f"{n(x)} {n(y)}" for x, y in top), "#000", 1.8) + stroke("M" + "L".join(f"{n(x)} {n(y)}" for x, y in low), "#000", 1.8)
    for k in (2, 5, 8):
        body += path(star_d(k * half, mid(k * half), 9, .2), "#000")
    return svg(w, h, body, "xMidYMax meet")


D("ribbonFloor", ribbon_floor())


def comet() -> str:
    """A comet flying to the right: a bright head, a long tapering tail and two thin streaks beside it."""
    body = poly([(176, 23), (2, 30), (176, 37)], "#000", "fill-opacity='.5'") + stroke("M168 21L56 25M168 39L74 35", "#000", 1.1, "stroke-opacity='.7'")
    body += path(star_d(180, 30, 17, .2), "#000") + circ(180, 30, 6.5, "#000")
    return svg(200, 60, body, "xMaxYMid meet")


D("comet", comet())



def star_small() -> str:
    """One small outlined star (a mask) for the ones that rise."""
    return svg(40, 40, tube(d_poly(star5(20, 21, 16, 7.4)), 2.8), "xMidYMid meet")


D("starSm", star_small())


# ── Багровый Мрак: кладбище под багровым небом, готический собор с горящими окнами, вороны и окно-розетка за аватаром ──
CR_INK = "#080205"
CR_RIM = "#7a1c26"


def grave_slab(x: float, base: float, w: float, h: float, lean: float = 0) -> str:
    """A tombstone: a slab with a rounded top and a thin cold-red rim on the edge the light falls on."""
    cx = x + w / 2
    d = f"M{n(x)} {n(base)}V{n(base - h + w / 2)}Q{n(x)} {n(base - h)} {n(cx)} {n(base - h)}Q{n(x + w)} {n(base - h)} {n(x + w)} {n(base - h + w / 2)}V{n(base)}z"
    g = path(d, CR_INK) + stroke(f"M{n(x + .7)} {n(base)}V{n(base - h + w / 2)}Q{n(x + .7)} {n(base - h + .7)} {n(cx)} {n(base - h + .7)}", CR_RIM, .9, "stroke-opacity='.65'")
    return f"<g transform='rotate({n(lean)} {n(cx)} {n(base)})'>{g}</g>" if lean else g


def grave_cross(x: float, base: float, h: float, lean: float = 0) -> str:
    """A stone cross on a step."""
    arm = h * .34
    g = rect(x - 1.8, base - h, 3.6, h, CR_INK) + rect(x - arm, base - h * .72, arm * 2, 3.4, CR_INK) + rect(x - 5, base - 3, 10, 3, CR_INK)
    g += stroke(f"M{n(x - 1)} {n(base - 3)}V{n(base - h + 1)}", CR_RIM, .8, "stroke-opacity='.55'")
    return f"<g transform='rotate({n(lean)} {n(x)} {n(base)})'>{g}</g>" if lean else g


def iron_fence(x0: float, x1: float, base: float, h: float, step: float = 8) -> str:
    """A wrought-iron fence: pickets with spear tips between two rails."""
    body = rect(x0, base - h * .78, x1 - x0, 1.8, CR_INK) + rect(x0, base - h * .22, x1 - x0, 1.8, CR_INK)
    x = x0
    while x < x1:
        body += rect(x, base - h, 1.8, h, CR_INK) + poly([(x - 1.6, base - h + 1), (x + .9, base - h - 5.5), (x + 3.4, base - h + 1)], CR_INK)
        x += step
    return body


def graveyard() -> str:
    """The graveyard along the bottom (stretched over the whole strip): a far ridge with a wrought-iron fence, tombstones and crosses that lean, dry grass in front and a low red mist."""
    w, h = 420, 120
    r = random.Random(33)
    body = lingrad("gy", [(0, "#4a121c", 1), (1, "#12040a", 1)]) + radgrad("gm", [(0, "#d02a36", .26), (1, "#d02a36", 0)])
    far = ridge(w, 58, 7, [(210, .7), (90, .4), (40, .16)], 6, .1, 30)
    body += path(d_ridge(far, w, h), "url(#gy)") + stroke(d_smooth(far, closed=False), CR_RIM, 1, "stroke-opacity='.5'")
    body += iron_fence(0, w, 66, 17, 13)
    for x, base, ww, hh, lean in [(24, 96, 16, 22, -4), (62, 99, 14, 18, 5), (104, 95, 18, 26, -2), (150, 99, 13, 16, 7), (206, 97, 17, 24, 0), (250, 100, 14, 17, -6), (296, 96, 18, 27, 3), (340, 99, 14, 18, -5), (384, 97, 17, 23, 4)]:
        body += grave_slab(x, base, ww, hh, lean)
    for x, base, hh, lean in [(44, 101, 30, 3), (178, 102, 26, -5), (322, 101, 28, 4), (404, 102, 36, -3)]:
        body += grave_cross(x, base, hh, lean)
    body += ell(210, 86, 220, 13, "url(#gm)")
    near = ridge(w, 108, 4, [(150, .6), (60, .3)], 9, .2, 40)
    body += path(d_ridge(near, w, h), "#050102")
    for x in range(4, w, 12):
        body += stroke(f"M{x} 112q{n(r.uniform(-4, 4))} -8 {n(r.uniform(-8, 8))} {n(-r.uniform(10, 17))}", "#050102", 1.2)
    return svg(w, h, body, "none")


D("graveyard", graveyard())


def cathedral() -> str:
    """A ruined gothic cathedral front: a steep gable with a rose window and a pointed window, a needle spire, a broken tower on the left and a pointed one on the right; the windows glow crimson."""
    w, h = 130, 300
    ink = CR_INK
    body = lingrad("cw", [(0, "#ff8a62", 1), (.5, "#e0303c", 1), (1, "#6a0c18", 1)])
    body += poly([(44, 300), (44, 150), (72, 84), (100, 150), (100, 300)], ink) + poly([(68, 90), (72, 8), (76, 90)], ink) + rect(70.6, 0, 2.8, 16, ink) + rect(66, 4, 11, 2.2, ink)
    body += poly([(14, 300), (14, 178), (20, 168), (24, 176), (30, 152), (36, 164), (44, 156), (44, 300)], ink)
    body += poly([(100, 300), (100, 142), (113, 94), (126, 142), (126, 300)], ink) + rect(112, 84, 2.2, 14, ink) + rect(108.5, 88, 9, 2, ink)
    body += poly([(126, 200), (130, 200), (130, 228), (126, 238)], ink)
    for d in ("M62 224V182Q62 166 72 158Q82 166 82 182V224z", "M50 272V250Q50 242 54 238Q58 242 58 250V272z", "M86 272V250Q86 242 90 238Q94 242 94 250V272z", "M110 176V154Q110 146 113 142Q116 146 116 154V176z", "M23 232V214Q23 208 26 205Q29 208 29 214V232z"):
        body += path(d, "url(#cw)")
    body += circ(72, 134, 10, "url(#cw)") + stroke("M72 124V144M62 134H82M65 127L79 141M79 127L65 141", ink, 1.2) + circ(72, 134, 3, ink)
    body += stroke("M72 160V224M62 196H82", ink, 1.4)
    body += stroke("M44 298V152L71 87M14 298V180L20 170M100 300V144L112 97", CR_RIM, 1, "stroke-opacity='.55'")
    return svg(w, h, body, "xMaxYMax meet")


D("cathedral", cathedral())

CROW_WING = [(5, 0), (3, -18), (-1, -34), (-6, -45), (-9, -37), (-13, -43), (-14, -33), (-19, -36), (-17, -26), (-12, -14), (-8, 2)]


def crow(cx: float, cy: float, s: float, ang: float) -> str:
    """A crow in flight, side view (a mask): a body with a head and a beak, a fan tail and one wing; the wing angle sets the phase of the flap."""
    k = s / 10
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    wing = [(cx + k * (x * ca - y * sa), cy - k * 2 + k * (x * sa + y * ca)) for x, y in CROW_WING]
    body = ell(cx, cy, 10 * k, 4.2 * k, "#000") + circ(cx + 11 * k, cy - 1.4 * k, 3.4 * k, "#000") + poly([(cx + 13 * k, cy - 2.4 * k), (cx + 19 * k, cy - .8 * k), (cx + 13 * k, cy + .4 * k)], "#000")
    body += poly([(cx - 8 * k, cy - 1.5 * k), (cx - 19 * k, cy - 4 * k), (cx - 18 * k, cy + 1 * k), (cx - 8 * k, cy + 2.5 * k)], "#000")
    return body + poly(wing, "#000")


def crows() -> str:
    """A flock of four crows with the wings in different phases (a mask)."""
    body = crow(54, 62, 10, -18) + crow(120, 34, 7, 24) + crow(98, 90, 6, 100) + crow(168, 66, 8.5, 150)
    return svg(200, 120, body, "xMidYMid meet")


D("crows", crows())


def rose_window() -> str:
    """A gothic rose window (a mask): two rings, twelve pointed petals round a heart and a bead at the tip of each one."""
    c = 110
    body = stroke(arc_d(c, c, 102, 0, math.tau - .001), "#000", 3.2) + stroke(arc_d(c, c, 92, 0, math.tau - .001), "#000", 1.3, "stroke-opacity='.7'") + stroke(arc_d(c, c, 15, 0, math.tau - .001), "#000", 2.4) + circ(c, c, 6, "#000")
    for k in range(12):
        a = math.tau * k / 12
        body += stroke(f"M{pt(c, c, a, 30)}Q{pt(c, c, a - .22, 58)} {pt(c, c, a, 84)}Q{pt(c, c, a + .22, 58)} {pt(c, c, a, 30)}z", "#000", 2.2)
        body += stroke(f"M{pt(c, c, a, 16)}L{pt(c, c, a, 30)}", "#000", 1.4, "stroke-opacity='.8'") + circ(c + 90 * math.cos(a), c + 90 * math.sin(a), 3, "#000")
    return svg(220, 220, body, "xMidYMid meet")


D("roseWindow", rose_window())
