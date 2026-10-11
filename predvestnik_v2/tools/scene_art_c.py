"""Scene art C (skin-scene-c-v3.css): Бездна, Северное Сияние, Расплавленное Солнце, Лепестковый Вихрь, Артефакт, Лунный Лотос, Прилив Рюдзина, Полуночная Комета, Хроно-ткач, Сердце Звезды."""
from __future__ import annotations

import math
import random

from scene_kit import (arc_d, art, bezier, circ, d_poly, d_ridge, d_smooth, ell, flip, gear_d, jag, lingrad, mirror, n, path, poly, radgrad, rect, ribbon, ridge, spiral_points, star_d, stroke, svg, tide as kit_tide)


def C(name: str, value: str) -> None:
    art(name, "c", value)


def tide(name: str, width: int, amp: float, top: str, rim: str, depth: int = 40, opacity: float = .55) -> None:
    kit_tide("c", name, width, amp, top, rim, depth, opacity)


def pt(cx: float, cy: float, ang: float, rad: float) -> str:
    return f"{n(cx + rad * math.cos(ang))} {n(cy + rad * math.sin(ang))}"


# ── Бездна: вихрь аккреции, дуги линзирования, обломки и разорванная планета, струя ──
def void_spiral() -> str:
    """Five dust arms of an accretion vortex that sweep out of the middle and fade."""
    cx = cy = 150
    body = "<defs><radialGradient id='f' gradientUnits='userSpaceOnUse' cx='150' cy='150' r='150'><stop offset='.3' stop-color='#000' stop-opacity='1'/><stop offset='.7' stop-color='#000' stop-opacity='.55'/><stop offset='1' stop-color='#000' stop-opacity='0'/></radialGradient></defs>"
    r = random.Random(5)
    for arm in range(5):
        a0 = arm * math.tau / 5
        centre = spiral_points(cx, cy, 44, 148, .62, a0, 36)
        widths = [9 * (1 - i / 36) ** .9 + .7 for i in range(37)]
        body += path(d_poly(ribbon(centre, widths)), "url(#f)")
        for i in range(6, 36, 2):                                           # dust that drifts off the arm
            x, y = centre[i]
            body += circ(x + r.uniform(-11, 11), y + r.uniform(-11, 11), r.uniform(.5, 1.5), "url(#f)")
    return svg(300, 300, body, "xMidYMid meet")


C("spiral", void_spiral())


def lens_arcs() -> str:
    """Arcs of lensed light around the dark centre: stars stretched into short and long circular strokes."""
    cx = cy = 150
    r = random.Random(7)
    body = ""
    for radius, count in ((74, 5), (88, 6), (102, 7), (118, 6), (134, 5)):
        a = r.uniform(0, math.tau)
        for _ in range(count):
            span = r.uniform(.12, .55)
            body += stroke(arc_d(cx, cy, radius + r.uniform(-2, 2), a, a + span), "#000", r.uniform(1.1, 2.6), f"stroke-opacity='{n(r.uniform(.5, 1))}'")
            a += span + r.uniform(.25, 1.1)
    for _ in range(26):
        a, radius = r.uniform(0, math.tau), r.uniform(70, 142)
        body += circ(cx + radius * math.cos(a), cy + radius * math.sin(a), r.uniform(.8, 1.7), "#000")
    return svg(300, 300, body, "xMidYMid meet")


C("lensArcs", lens_arcs())


def rubble() -> str:
    """A drifting cluster of rocks that the dark centre is pulling in: the rim of every rock facing the centre (the right) glows, a faint trail points to the centre."""
    r = random.Random(12)
    body = lingrad("rk", [(0, "#4a3392", 1), (1, "#150b30", 1)], 0, 0, 1, 1) + lingrad("tr", [(0, "#cf74ff", .0), (1, "#cf74ff", .38)], 0, 0, 1, 0)
    for x, y, sz in ((52, 44, 26), (22, 92, 16), (86, 104, 20), (38, 148, 12), (92, 56, 9), (70, 150, 7), (14, 36, 8)):
        body += path(d_poly([(x + 1.3 * sz * r.uniform(.5, 1) * math.cos(a), y + sz * r.uniform(.55, 1) * math.sin(a)) for a in [math.tau * i / 9 + r.uniform(-.2, .2) for i in range(9)]]), "url(#rk)")
        body += stroke(f"M{n(x + sz * .2)} {n(y - sz * .85)}Q{n(x + sz * 1.3)} {n(y)} {n(x + sz * .3)} {n(y + sz * .8)}", "#ff7ad9", 1.2, "stroke-opacity='.65'")
        body += path(f"M{n(x + sz * 1.1)} {n(y - sz * .3)}L{n(x + sz * 4.5)} {n(y)}L{n(x + sz * 1.1)} {n(y + sz * .3)}z", "url(#tr)")
    return svg(130, 190, body, "xMinYMid meet")


C("rubble", rubble())


def shredded() -> str:
    """A planet torn apart by tides: the stripes of the planet on the left and a long tail of matter that curves towards the dark centre."""
    body = "<defs><clipPath id='p'><circle cx='34' cy='40' r='24'/></clipPath></defs>" + lingrad("tl", [(0, "#ff7ad9", .75), (1, "#ff7ad9", 0)], 0, 0, 1, 0)
    body += "<g clip-path='url(#p)'>" + circ(34, 40, 24, "#4a3aa8") + "".join(rect(0, y, 80, hh, c, "fill-opacity='.85'") for y, hh, c in ((22, 7, "#8a6aff"), (33, 6, "#2a1a70"), (44, 8, "#a98cff"), (56, 5, "#2a1a70")))
    body += radgrad("sh", [(0, "#000", 0), (.5, "#000", .2), (1, "#000", .85)], .74, .34, .9) + circ(34, 40, 24, "url(#sh)") + "</g>"
    body += stroke("M12 36Q34 22 58 34", "#ff7ad9", 1, "stroke-opacity='.7'")
    centre = bezier((52, 38), (90, 30), (126, 52), (190, 96), 20)
    body += path(d_poly(ribbon(centre, [10 * (1 - i / 20) ** .9 + .6 for i in range(21)])), "url(#tl)")
    r = random.Random(3)
    for i in range(28):
        x, y = centre[min(20, int(i * .75))]
        body += circ(x + r.uniform(-8, 8) + i * 1.5, y + r.uniform(-8, 8), r.uniform(.5, 1.6), "#ffb0ec", f"fill-opacity='{n(r.uniform(.4, .9))}'")
    return svg(200, 110, body, "xMinYMin meet")


C("shredded", shredded())


def jet() -> str:
    """A thin jet shot upwards out of the bottom edge of the picture: a narrow cone that widens, fading, with knots of brighter matter."""
    body = lingrad("j", [(0, "#000", 0), (.45, "#000", .55), (1, "#000", 1)], 0, 0, 0, 1)
    body += path("M46 300L30 0L70 0L54 300z", "url(#j)")
    body += "".join(ell(50, y, 5 + (300 - y) * .03, 3.6, "#000", f"fill-opacity='{n(.35 + .5 * y / 300)}'") for y in (260, 214, 160, 100, 44))
    return svg(100, 300, body, "xMidYMax meet")


C("jet", jet())


# ── Северное Сияние: занавеси, горы и ледяной лес, волк, корона сияния ──
def curtain(seed: int, w: int = 300, h: int = 300) -> str:
    """A curtain of polar light: a bright wavy hem, a veil above it and a comb of rays that fade upwards and towards both sides (the colour comes from the mask layer: green on the hem, violet on top)."""
    r = random.Random(seed)
    phase = r.uniform(0, math.tau)
    hem = lambda x: h * .78 + 15 * math.sin(x / w * math.tau * 1.4 + phase) + 7 * math.sin(x / w * math.tau * 3.3 + phase * 2)      # noqa: E731
    reach = lambda x: .5 + .5 * math.sin(x / w * math.tau * 1.7 + phase * 1.3)      # noqa: E731 (where the curtain stands tall)
    body = lingrad("c", [(0, "#000", 0), (.4, "#000", .3), (.78, "#000", 1), (1, "#000", 1)], 0, 0, 0, h, True)
    body += "<linearGradient id='f' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#fff' stop-opacity='0'/><stop offset='.22' stop-color='#fff'/><stop offset='.78' stop-color='#fff'/><stop offset='1' stop-color='#fff' stop-opacity='0'/></linearGradient>"
    body = f"<defs>{body}<mask id='e' maskUnits='userSpaceOnUse' x='0' y='0' width='{w}' height='{h}'><rect width='{w}' height='{h}' fill='url(#f)'/></mask></defs>"
    veil = [(x, hem(x) - (36 + 120 * reach(x)) * r.uniform(.8, 1)) for x in range(0, w + 1, 12)]
    inner = path(d_smooth([(0, hem(0))] + veil + [(w, hem(w))], closed=False) + "".join(f"L{n(x)} {n(hem(x))}" for x in range(w, -1, -10)) + "z", "url(#c)", "fill-opacity='.55'")
    rays = ""
    for _ in range(110):
        x = r.uniform(0, w)
        length = (30 + 170 * reach(x)) * r.uniform(.25, 1)
        rays += f"<path stroke-width='{n(r.uniform(.6, 1.7))}' stroke-opacity='{n(r.uniform(.3, .9))}' d='M{n(x)} {n(hem(x))}v{n(-length)}'/>"
    inner += f"<g fill='none' stroke='url(#c)' stroke-linecap='round'>{rays}</g>"
    hem_d = d_smooth([(x, hem(x)) for x in range(0, w + 1, 10)], closed=False)
    inner += stroke(hem_d, "#000", 9, "stroke-opacity='.28'") + stroke(hem_d, "#000", 2.4)
    return svg(w, h, body + f"<g mask='url(#e)'>{inner}</g>", "none")


C("curtain", curtain(4))
C("curtain2", curtain(9, 260, 280))


def snow_range() -> str:
    """Two ranges of polar mountains that stand high at both sides and sink in the middle (the nickname and the title live there): dark masses, a soft rim light on the ridges."""
    w, h = 400, 110
    dip = lambda t, low, high: low - (low - high) * abs(2 * t - 1) ** 1.25      # noqa: E731
    far = ridge(w, lambda t: dip(t, 80, 22), 11, [(210, 1), (84, .5), (36, .22)], 21, .55, 70)
    near = ridge(w, lambda t: dip(t, 96, 52), 8, [(150, 1), (64, .5), (30, .25)], 33, .7, 80)
    body = lingrad("f", [(0, "#2d5a7c", .8), (1, "#0f2a3c", .8)]) + lingrad("n", [(0, "#0c2230", 1), (1, "#04101a", 1)])
    body += path(d_ridge(far, w, h), "url(#f)") + stroke(d_smooth(far, closed=False), "#e8fbff", 1, "stroke-opacity='.55'")
    body += path(d_ridge(near, w, h), "url(#n)") + stroke(d_smooth(near, closed=False), "#7bf0c8", .9, "stroke-opacity='.4'")
    return svg(w, h, body, "none")


C("snowRange", snow_range())


def ice_pines() -> str:
    """Three snow-laden pines (the right cluster is this picture mirrored by the layer)."""
    from scene_kit import pine
    w, h = 130, 230
    trees = ((38, 206, 62), (88, 156, 46), (118, 112, 32))
    body = lingrad("g", [(0, "#16404a", 1), (1, "#06161c", 1)])
    for x, th, tw in trees:
        pts, (tx, ty, tw_, th_) = pine(x, h, th, tw, 6)
        body += poly(pts, "url(#g)") + rect(tx, ty, tw_, th_, "url(#g)")
    r = random.Random(4)
    for x, th, tw in trees:             # snow on the shoulders of the branches
        for k in range(1, 6):
            y = h - th + k * th * .78 / 6
            half = tw * (.28 + .72 * k / 6) / 2
            body += stroke(f"M{n(x - half * .95)} {n(y + th * .05)}Q{n(x - half * .4)} {n(y - 1)} {n(x)} {n(y - 2 - r.uniform(0, 2))}", "#e8fbff", 1.6, "stroke-opacity='.55'")
    return svg(w, h, body, "xMinYMax meet")


C("icePines", ice_pines())


def wolf() -> str:
    """A wolf sitting on a rock with the head thrown back and the muzzle to the sky: a dark silhouette (haunch, back, neck, head, ears, tail, legs) with a thin cold rim light on the back."""
    ink = "#08171f"
    body = path("M0 100L6 93Q34 88 62 92Q84 90 100 100z", ink)                       # the rock
    body += ell(30, 80, 19, 17, ink) + ell(46, 68, 24, 12, ink, "transform='rotate(-38 46 68)'")      # haunch, body leaning up
    body += poly([(46, 70), (66, 62), (68, 42), (66, 26), (54, 30), (50, 46)], ink)  # chest and neck
    body += ell(66, 22, 11, 8, ink, "transform='rotate(-48 66 22)'")                 # skull
    body += poly([(70, 18), (90, 3), (95, 8), (91, 12), (76, 26)], ink)             # muzzle to the sky
    body += poly([(56, 18), (57, 5), (64, 14)], ink) + poly([(61, 14), (65, 4), (70, 12)], ink)      # ears
    body += rect(57, 62, 9, 32, ink) + ell(62, 94, 9, 3.4, ink)                      # front legs
    body += ell(22, 94, 15, 4.5, ink) + stroke("M12 90Q0 84 3 70", ink, 7)           # hind paw, tail
    body += stroke("M8 80Q22 62 40 52Q54 44 56 28Q60 14 68 12L90 3", "#7bf0c8", .9, "stroke-opacity='.55'") + stroke("M6 93Q34 88 62 92", "#7bf0c8", .8, "stroke-opacity='.4'")
    return svg(100, 100, body, "xMidYMax meet")


C("wolf", wolf())


def aurora_crown() -> str:
    """The corona of an aurora: many thin rays that fan out of one point high above, long in the middle and short at the sides, brightest near the apex and fading outwards."""
    r = random.Random(8)
    cx, cy = 150, 14
    body = "<defs><radialGradient id='g' gradientUnits='userSpaceOnUse' cx='150' cy='14' r='196'><stop offset='.06' stop-color='#000' stop-opacity='.2'/><stop offset='.3' stop-color='#000' stop-opacity='1'/><stop offset='.72' stop-color='#000' stop-opacity='.5'/><stop offset='1' stop-color='#000' stop-opacity='0'/></radialGradient></defs>"
    count = 110
    rays = ""
    for k in range(count):
        a = math.radians(8 + 164 * (k + r.uniform(-.45, .45)) / (count - 1))
        ln = r.uniform(.45, 1) * 196 * (.55 + .45 * math.sin(math.pi * k / (count - 1)))
        half = math.radians(r.uniform(.12, .5))
        rays += f"<path fill-opacity='{n(r.uniform(.55, 1))}' d='M{pt(cx, cy, a - half * .3, 12)}L{pt(cx, cy, a - half, ln)}L{pt(cx, cy, a + half, ln)}L{pt(cx, cy, a + half * .3, 12)}z'/>"
    body += f"<g fill='url(#g)'>{rays}</g>"
    body += ell(cx, cy + 4, 34, 10, "url(#g)", "fill-opacity='.6'")
    return svg(300, 200, body, "xMidYMin meet")


C("auroraCrown", aurora_crown())


# ── Расплавленное Солнце: протуберанцы, лопнувшая корка с золотыми трещинами, лучи, золотой поток ──
def prominence() -> str:
    """A magnetic loop of plasma that stands up out of the surface: nested arches with a few strands that fall back."""
    body = ""
    for dx, top, width, op in ((0, 14, 7, 1), (10, 30, 5, .85), (20, 46, 3.2, .7)):
        body += stroke(f"M{22 + dx} 130C{22 + dx} {top - 6} {148 - dx} {top - 6} {148 - dx} 130", "#000", width, f"stroke-opacity='{op}'")
    r = random.Random(6)
    for _ in range(9):
        x = r.uniform(34, 136)
        body += stroke(f"M{n(x)} {n(26 + 40 * abs(x - 85) / 60)}Q{n(x + r.uniform(-8, 8))} {n(60)} {n(x + r.uniform(-14, 14))} {n(r.uniform(88, 118))}", "#000", r.uniform(.8, 1.8), "stroke-opacity='.65'")
    body += ell(85, 14, 16, 5.5, "#000", "fill-opacity='.8'") + "".join(circ(r.uniform(40, 130), r.uniform(4, 40), r.uniform(.8, 2), "#000") for _ in range(14))
    return svg(170, 130, body, "xMidYMax meet")


C("prominence", prominence())


def crust() -> str:
    """The surface of the sun as a cooling crust: dark plates with glowing gold seams, a hot rim on the top edge; the crust stands high at both sides and sinks in the middle, where the nickname and the title are (no seams there)."""
    w, h = 400, 80
    dip = lambda t: 70 - 54 * abs(2 * t - 1) ** 1.2      # noqa: E731
    top = ridge(w, dip, 7, [(130, 1), (52, .5), (24, .3)], 41, .8, 60)
    body = lingrad("p", [(0, "#2a1608", 1), (1, "#0a0502", 1)]) + radgrad("hot", [(0, "#ffd27a", .8), (1, "#ff6a1a", 0)]) + path(d_ridge(top, w, h), "url(#p)")
    seams = [jag([(0, 30), (40, 26), (84, 36), (126, 30)], 4, 3, 2), jag([(300, 32), (340, 24), (372, 34), (400, 28)], 4, 4, 2),
             jag([(30, 80), (46, 56), (84, 36)], 4, 5, 2), jag([(104, 80), (112, 58), (126, 30)], 3, 7, 2), jag([(332, 80), (320, 58), (340, 24)], 4, 9, 2), jag([(380, 80), (372, 58), (372, 34)], 3, 11, 1)]
    for pts in seams:
        d = "M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts)
        body += stroke(d, "#ff6a1a", 5, "stroke-opacity='.35'") + stroke(d, "#ffd27a", 1.8)
    body += "".join(ell(x, y, 22, 7, "url(#hot)", "fill-opacity='.7'") for x, y in ((64, 40), (352, 34), (112, 40)))
    body += stroke(d_smooth(top, closed=False), "#ff9a3a", 1.2, "stroke-opacity='.8'")
    return svg(w, h, body, "none")


C("crust", crust())


def sun_rays() -> str:
    """Straight rays of the solar corona around a hidden disc: many thin ones, a few long thick streamers; they fade towards their tips and shrink at the bottom (the nickname)."""
    r = random.Random(3)
    cx = cy = 150
    reach = lambda ang: min(1.0, max(.0, (abs(math.atan2(math.sin(ang - math.pi / 2), math.cos(ang - math.pi / 2))) - .4) / .7))      # noqa: E731
    body = "<defs><radialGradient id='g' gradientUnits='userSpaceOnUse' cx='150' cy='150' r='150'><stop offset='.44' stop-color='#000' stop-opacity='1'/><stop offset='.8' stop-color='#000' stop-opacity='.55'/><stop offset='1' stop-color='#000' stop-opacity='0'/></radialGradient></defs>"
    for k in range(72):
        a = math.tau * (k + r.uniform(-.3, .3)) / 72
        long = (k % 9 == 0)
        ln = 64 + ((r.uniform(120, 148) if long else r.uniform(80, 118)) - 64) * reach(a)
        if ln < 74:
            continue
        half = math.radians(1.6 if long else r.uniform(.3, .8))
        body += path(f"M{pt(cx, cy, a - half, 64)}L{pt(cx, cy, a, ln)}L{pt(cx, cy, a + half, 64)}z", "url(#g)")
    return svg(300, 300, body, "xMidYMid meet")


C("sunRays", sun_rays())
tide("goldFlow", 140, 6, "#ffc447", "#fff0c2", 50, .8)


# ── Лепестковый Вихрь: смерч лепестков, ветви сакуры, тории, порыв ветра, молния, огромный цветок ──
PETAL = "M0 1C-.9 .6-1.1-.5-.45-1Q-.18-.82 0-.55Q.18-.82 .45-1C1.1-.5 .9 .6 0 1z"      # a sakura petal of length 2 with the notch at the tip (pointing up)


def petal_def() -> str:
    """The petal and a five-petal flower (both without a fill: the `use` that places them brings the colour) defined once per picture."""
    flower_petals = "".join(f"<use href='#p' transform='translate({n(math.sin(math.radians(a)) * .85)} {n(-math.cos(math.radians(a)) * .85)}) rotate({a}) scale(.55)'/>" for a in range(0, 360, 72))
    return f"<defs><path id='p' d='{PETAL}'/><g id='f'>{flower_petals}<circle r='.22' fill='#7a1d4a'/></g></defs>"


def petal(x: float, y: float, ang: float, s: float, fill: str, op: float = 1) -> str:
    return f"<use href='#p' transform='translate({n(x)} {n(y)}) rotate({n(ang)}) scale({n(s)})' fill='{fill}' fill-opacity='{n(op)}'/>"


PINKS = ("#ffb0cf", "#ff8fbb", "#ffd0e4", "#f6a6ff", "#ff9ec4", "#ff7fb0")


def petal_vortex() -> str:
    """A tornado of petals: three arms of petals that sweep out of the middle and grow, a thin wind line along every arm, nothing near the middle (the avatar lives there)."""
    r = random.Random(12)
    cx = cy = 190
    body = petal_def()
    for arm in range(3):
        a0 = arm * math.tau / 3
        line = []
        for k in range(34):
            t = k / 33
            rad = 104 + 82 * t ** .9
            ang = a0 + t * 2.4
            line.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        body += stroke(d_smooth(line, closed=False), "#ffc2da", .9, "stroke-opacity='.28'")
        for k in range(46):
            t = min(1, max(0, (k + r.uniform(-.4, .4)) / 45))
            rad = 104 + 82 * t ** .9 + r.uniform(-9, 9)
            ang = a0 + t * 2.4 + r.uniform(-.08, .08)
            x, y = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
            tangent = math.degrees(ang) + 90 + r.uniform(-50, 50)
            body += petal(x, y, tangent, 2.6 + 4 * t * r.uniform(.7, 1.1), r.choice(PINKS), .95 - .3 * t ** 1.5)
    return svg(380, 380, body, "xMidYMid meet")


C("petalVortex", petal_vortex())


def flower(x: float, y: float, s: float, fill: str) -> str:
    return f"<use href='#f' transform='translate({n(x)} {n(y)}) scale({n(s)})' fill='{fill}' fill-opacity='.95'/>"


def sakura_branch(seed: int, mirrored: bool = False) -> str:
    """A bent bough of sakura that enters from the side of the stage: dark wood, thin twigs, clusters of blossoms and buds (the stage's storm bends it)."""
    r = random.Random(seed)
    w, h = 220, 200
    wood, rim = "#22101e", "#6a3358"
    body = petal_def()
    main = bezier((-6, 36), (70, 18), (126, 92), (208, 150), 17)
    body += poly(ribbon(main, [11 - 8.4 * i / 17 for i in range(18)]), wood)
    body += stroke(d_smooth([(x, y - 5 + 3 * i / 17) for i, (x, y) in enumerate(main[:15])], closed=False), rim, 1, "stroke-opacity='.55'")
    blossoms = []
    for i in (2, 4, 6, 8, 10, 12, 14):
        x, y = main[i]
        sign = -1 if i % 4 == 2 else 1
        end = (x + r.uniform(16, 34), y + sign * r.uniform(24, 46))
        twig = bezier((x, y), (x + 8, y + sign * 6), (end[0] - 10, end[1] - sign * 12), end, 8)
        body += poly(ribbon(twig, [3.4 - 2.6 * j / 8 for j in range(9)]), wood)
        blossoms += [end, twig[4]]
    blossoms += [main[16], main[13], main[9], main[5]]
    for x, y in blossoms:
        for _ in range(r.randint(2, 3)):
            body += flower(x + r.uniform(-9, 9), y + r.uniform(-9, 9), r.uniform(5, 8), r.choice(PINKS[:2] + PINKS[5:]))
        body += circ(x + r.uniform(-12, 12), y + r.uniform(-12, 12), r.uniform(1.8, 2.8), "#ff6fa8")
    for _ in range(7):
        body += petal(r.uniform(20, 210), r.uniform(60, 196), r.uniform(0, 360), r.uniform(2.4, 3.6), r.choice(PINKS), .9)
    if mirrored:
        body = flip(body, w)
    return svg(w, h, body, "xMidYMid meet")


C("branchL", sakura_branch(5))
C("branchR", sakura_branch(8, True))


def torii() -> str:
    """A far shrine gate: two pillars, the curved top beam, the tie beam, the plaque; a dark violet silhouette with a faint pink rim."""
    ink = "#241033"
    body = rect(22, 34, 8, 66, ink) + rect(90, 34, 8, 66, ink) + rect(16, 52, 88, 5, ink) + rect(55, 34, 10, 19, ink)
    body += path("M0 14Q60 24 120 14L112 26Q60 34 8 26z", ink) + rect(8, 28, 104, 5, ink)
    body += stroke("M0 14Q60 24 120 14", "#ff9ec4", .9, "stroke-opacity='.5'") + stroke("M22 34V100M90 34V100", "#ff9ec4", .6, "stroke-opacity='.3'")
    return svg(120, 100, body, "xMidYMax meet")


C("toriiFar", torii())


def gust() -> str:
    """A gust of wind: a few long pale curves that taper at both ends with petals riding them."""
    r = random.Random(3)
    body = "<defs><linearGradient id='f' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#ffd6e6' stop-opacity='0'/><stop offset='.5' stop-color='#ffd6e6' stop-opacity='.8'/><stop offset='1' stop-color='#ffd6e6' stop-opacity='0'/></linearGradient></defs>" + petal_def()
    for k, (y0, amp) in enumerate(((14, 8), (26, 10), (38, 7), (48, 9))):
        d = d_smooth([(0, y0 + 4), (50, y0 - amp), (110, y0 + amp), (160, y0 - amp * .6), (200, y0)], closed=False)
        body += stroke(d, "url(#f)", 1.1 + (k % 2) * .5)
    for x, y in ((40, 18), (78, 36), (120, 22), (150, 40), (176, 14), (100, 48)):
        body += petal(x, y, r.uniform(0, 360), r.uniform(3, 5), r.choice(PINKS), .95)
    return svg(200, 60, body, "xMidYMid meet")


C("gust", gust())


def bolt() -> str:
    """A fork of storm lightning: a wide violet glow around a thin white core and one branch."""
    pts = [(34, 0), (26, 46), (40, 70), (20, 128), (36, 152), (10, 236)]
    side = [(36, 152), (52, 176), (46, 206)]
    glow, core = d_smooth(pts, closed=False), d_smooth(pts, closed=False)
    body = stroke(glow, "#c06bd6", 9, "stroke-opacity='.3'") + stroke(glow, "#e8c8ff", 3.4, "stroke-opacity='.8'") + stroke(core, "#fff", 1.4)
    sd = d_smooth(side, closed=False)
    body += stroke(sd, "#c06bd6", 6, "stroke-opacity='.3'") + stroke(sd, "#e8c8ff", 2, "stroke-opacity='.8'") + stroke(sd, "#fff", .9)
    return svg(60, 240, body, "xMidYMin meet")


C("stormBolt", bolt())


def bloom() -> str:
    """A giant sakura blossom seen from above (a mask): five notched petals with a soft fill and a clear rim, one vein each, the stamens in the middle."""
    r = random.Random(2)
    body = petal_def()
    for k in range(5):
        a = k * 72
        px, py = 200 + math.sin(math.radians(a)) * 92, 200 - math.cos(math.radians(a)) * 92
        body += petal(px, py, a, 86, "#000", .42)
        body += f"<use href='#p' transform='translate({n(px)} {n(py)}) rotate({n(a)}) scale(86)' fill='none' stroke='#000' stroke-width='.02' stroke-opacity='.85'/>"
        body += stroke(f"M{n(200 + math.sin(math.radians(a)) * 30)} {n(200 - math.cos(math.radians(a)) * 30)}L{n(200 + math.sin(math.radians(a)) * 138)} {n(200 - math.cos(math.radians(a)) * 138)}", "#000", 1, "stroke-opacity='.4'")
    for k in range(18):
        a = r.uniform(0, math.tau)
        rad = r.uniform(16, 32)
        body += stroke(f"M200 200L{n(200 + rad * math.cos(a))} {n(200 + rad * math.sin(a))}", "#000", .8) + circ(200 + rad * math.cos(a), 200 + rad * math.sin(a), 2.4, "#000")
    return svg(400, 400, body, "xMidYMid meet")


C("stormBloom", bloom())


# ── Артефакт: трещины реальности, пилоны, шестигранное кольцо, дроны, осколки, прицельные уголки ──
def fracture() -> str:
    """The reality cracks: jagged cracks run out of the middle past the avatar, with side branches and a few loose facets (a mask: a soft wide stroke and a thin hard core)."""
    r = random.Random(21)
    cx = cy = 200
    angles = sorted(r.uniform(0, math.tau) for _ in range(11))
    body = ""
    for i, a in enumerate(angles):
        reach = r.uniform(150, 205)
        pts = [(cx + 84 * math.cos(a), cy + 84 * math.sin(a)), (cx + (84 + reach) / 2 * math.cos(a + .05), cy + (84 + reach) / 2 * math.sin(a + .05)), (cx + reach * math.cos(a), cy + reach * math.sin(a))]
        pts = jag(pts, 7, 100 + i, 3)
        d = "M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts)
        body += stroke(d, "#000", 4.4, "stroke-opacity='.22'") + stroke(d, "#000", 1.3)
        for k in range(r.randint(1, 3)):
            bx, by = pts[r.randint(2, len(pts) - 2)]
            ba = a + r.choice((-1, 1)) * r.uniform(.4, .9)
            bl = r.uniform(18, 52)
            side = jag([(bx, by), (bx + bl * math.cos(ba), by + bl * math.sin(ba))], 4, 200 + i * 3 + k, 2)
            body += stroke("M" + "L".join(f"{n(x)} {n(y)}" for x, y in side), "#000", 1, "stroke-opacity='.85'")
    for k in range(6):                                       # loose facets
        a = r.uniform(0, math.tau)
        rad = r.uniform(104, 170)
        x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
        facet = [(x + r.uniform(-16, 16), y + r.uniform(-16, 16)) for _ in range(4)]
        facet.sort(key=lambda p: math.atan2(p[1] - y, p[0] - x))
        body += poly(facet, "#000", "fill-opacity='.14'") + stroke(d_poly(facet), "#000", .9, "stroke-opacity='.6'")
    return svg(400, 400, body, "xMidYMid meet")


C("fracture", fracture())


def pylons() -> str:
    """Three monoliths that stand on the floor of the data world: dark prisms with a neon edge on the lit side, rings of light across them and a glowing cap."""
    body = ""
    for x, top, w in ((14, 40, 34), (58, 110, 30), (94, 170, 24)):
        body += lingrad(f"g{x}", [(0, "#07202c", 1), (1, "#03090f", 1)], 0, 0, 1, 0) + rect(x, top, w, 300 - top, f"url(#g{x})")
        body += rect(x + w - 2.4, top, 2.4, 300 - top, "#62f2e2", "fill-opacity='.8'") + rect(x, top, w, 3, "#c8fff8", "fill-opacity='.9'")
        for k in range(1, int((300 - top) / 38)):
            body += rect(x, top + k * 38, w, 1.2, "#62f2e2", "fill-opacity='.35'")
        body += rect(x + w * .3, top - 7, w * .4, 7, "#62f2e2", "fill-opacity='.9'")
    return svg(130, 300, body, "xMinYMax meet")


C("pylons", pylons())


def hex_path(cx: float, cy: float, r: float, rot: float = 0) -> str:
    return d_poly([(cx + r * math.cos(rot + math.tau * k / 6), cy + r * math.sin(rot + math.tau * k / 6)) for k in range(6)])


def hex_ring() -> str:
    """A ring of hexagonal force-field cells around the avatar, with two thin guide rings (a mask)."""
    cx = cy = 190
    body = stroke(f"M{190 + 156} 190A156 156 0 1 0 {190 - 156} 190A156 156 0 1 0 {190 + 156} 190z", "#000", 1, "stroke-opacity='.5'")
    body += stroke(f"M{190 + 132} 190A132 132 0 1 0 {190 - 132} 190A132 132 0 1 0 {190 + 132} 190z", "#000", .8, "stroke-opacity='.4'")
    for k in range(20):
        a = math.tau * k / 20
        x, y = cx + 144 * math.cos(a), cy + 144 * math.sin(a)
        body += stroke(hex_path(x, y, 11, a), "#000", 1.3, f"stroke-opacity='{.95 if k % 3 == 0 else .55}'")
        if k % 3 == 0:
            body += path(hex_path(x, y, 7, a), "#000", "fill-opacity='.35'")
        if k % 5 == 0:
            body += circ(x, y, 2, "#000")
    return svg(380, 380, body, "xMidYMid meet")


C("hexRing", hex_ring())


def drone() -> str:
    """A scout drone at the top of a round picture (the layer turns it around the avatar): a flattened body, two arms with rotors and a short scanning beam below."""
    body = "<defs><linearGradient id='b' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#000' stop-opacity='.7'/><stop offset='1' stop-color='#000' stop-opacity='0'/></linearGradient></defs>"
    cx, cy = 150, 12
    body += poly([(cx - 14, cy), (cx + 14, cy), (cx + 5, cy + 36), (cx - 5, cy + 36)], "url(#b)")
    body += path(d_poly([(cx - 9, cy - 4), (cx + 9, cy - 4), (cx + 13, cy + 1), (cx + 9, cy + 6), (cx - 9, cy + 6), (cx - 13, cy + 1)]), "#000")
    for sign in (-1, 1):
        body += stroke(f"M{cx + sign * 11} {cy}L{cx + sign * 25} {cy - 4}", "#000", 2) + ell(cx + sign * 27, cy - 5, 8, 1.8, "#000", "fill-opacity='.7'")
    return svg(300, 300, body, "xMidYMin meet")


C("drone", drone())


def chips() -> str:
    """Seven loose chips of reality: small polygons with a clear rim and a faint fill, scattered around the middle (a mask)."""
    r = random.Random(33)
    body = ""
    for k in range(7):
        a = math.tau * (k + r.uniform(-.25, .25)) / 7
        rad = r.uniform(130, 176)
        x, y = 200 + rad * math.cos(a), 200 + rad * math.sin(a)
        size = r.uniform(9, 20)
        pts = [(x + size * r.uniform(.5, 1.1) * math.cos(b), y + size * r.uniform(.5, 1.1) * math.sin(b)) for b in sorted(r.uniform(0, math.tau) for _ in range(r.randint(3, 5)))]
        body += poly(pts, "#000", "fill-opacity='.22'") + stroke(d_poly(pts), "#000", 1.3)
    return svg(400, 400, body, "xMidYMid meet")


C("chips", chips())


def brackets() -> str:
    """Four aiming corners with ticks, like the frame of a targeting screen (a mask; stretched over the whole stage)."""
    body = ""
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        x, y = 200 + sx * 188, 150 + sy * 138
        body += stroke(f"M{n(x)} {n(y - sy * 40)}V{n(y)}H{n(x - sx * 40)}", "#000", 2.2)
        body += stroke(f"M{n(x - sx * 8)} {n(y - sy * 8)}H{n(x - sx * 22)}M{n(x - sx * 8)} {n(y - sy * 8)}V{n(y - sy * 22)}", "#000", 1, "stroke-opacity='.6'") + circ(x - sx * 8, y - sy * 8, 2, "#000")
    return svg(400, 300, body, "none")


C("brackets", brackets())


# ── Лунный Лотос: тростник, жемчужные лотосы и листья, цапля, далёкий берег, облачко, журавли, кольцо из лепестков ──
def moon_reeds() -> str:
    """A bunch of tall reeds with three cattails and two broad blades, dark blue with a thin silver rim on the moon side."""
    r = random.Random(7)
    ink = "#141c34"
    body = ""
    for k in range(11):
        x0 = r.uniform(10, 118)
        lean = r.uniform(-34, 30)
        height = r.uniform(110, 262)
        tip = (x0 + lean, 280 - height)
        mid = (x0 + lean * .35, 280 - height * .5)
        body += stroke(f"M{n(x0)} 280Q{n(mid[0])} {n(mid[1])} {n(tip[0])} {n(tip[1])}", ink, r.uniform(1.4, 2.4))
        body += stroke(f"M{n(x0 + 1.5)} 280Q{n(mid[0] + 1.5)} {n(mid[1])} {n(tip[0] + 1.5)} {n(tip[1])}", "#a9bff0", .7, "stroke-opacity='.4'")
        if k % 3 == 0:
            ang = math.degrees(math.atan2(tip[0] - mid[0], mid[1] - tip[1]))
            body += ell(tip[0], tip[1] + 6, 3.4, 11, "#0f1630", f"transform='rotate({n(ang)} {n(tip[0])} {n(tip[1] + 6)})'") + stroke(f"M{n(tip[0] + 2.6)} {n(tip[1] - 2)}V{n(tip[1] + 12)}", "#a9bff0", .6, "stroke-opacity='.4'")
    for x0, dx, ln in ((30, -24, 170), (88, 30, 150)):
        body += path(f"M{x0} 280Q{x0 + dx * .3} {280 - ln * .6} {x0 + dx} {280 - ln}Q{x0 + dx * .5 + 7} {280 - ln * .5} {x0 + 8} 280z", ink)
    return svg(140, 280, body, "xMinYMax meet")


C("moonReeds", moon_reeds())


def pearl_lotus() -> str:
    """A pearl-white lotus that stands on the water: five pointed petals fanned from the base, a glowing heart, a ring of the water around."""
    body = lingrad("p", [(0, "#ffffff", 1), (1, "#aebff0", 1)]) + radgrad("h", [(0, "#ffffff", .9), (1, "#e4ecff", 0)])
    body += ell(50, 78, 38, 6, "none", "stroke='#e4ecff' stroke-opacity='.5' stroke-width='1'") + ell(50, 78, 26, 3.6, "none", "stroke='#e4ecff' stroke-opacity='.5' stroke-width='.8'")
    for a, sc in ((-70, .8), (70, .8), (-42, .95), (42, .95), (0, 1.1)):
        body += f"<path fill='url(#p)' stroke='#7f95d8' stroke-opacity='.75' stroke-width='.9' d='M50 74C38 58 38 36 50 18C62 36 62 58 50 74z' transform='rotate({a} 50 76) translate(50 76) scale({sc}) translate(-50 -76)'/>"
    body += ell(50, 62, 16, 22, "url(#h)")
    return svg(100, 90, body, "xMidYMax meet")


C("pearlLotus", pearl_lotus())


def moon_pads() -> str:
    """A strip of lily pads on dark water: round leaves with a notch and a silver rim, sometimes a bud on a stem (a picture for `st`: it is stretched over the layer)."""
    r = random.Random(11)
    body = ""
    for k in range(15):
        x = 14 + k * 26 + r.uniform(-8, 8)
        y = r.uniform(28, 56)
        rx, ry = r.uniform(14, 28), r.uniform(3.6, 6)
        a = r.uniform(0, math.tau)
        notch = f"M{n(x)} {n(y)}L{n(x + rx * math.cos(a))} {n(y + ry * math.sin(a) * 1.2)}"
        body += ell(x, y, rx, ry, "#1a2850", "fill-opacity='.92'") + ell(x, y, rx, ry, "none", "stroke='#a9bff0' stroke-opacity='.5' stroke-width='.8'") + stroke(notch, "#0b1226", 1.6, "stroke-opacity='.8'")
    for x in (60, 188, 332):
        body += stroke(f"M{x} 54Q{x + 3} 36 {x + 1} 22", "#16203a", 1.6) + ell(x + 1, 18, 4, 7, "#f4f8ff", "fill-opacity='.95'") + ell(x - 3, 21, 3, 6, "#cfdcff", "fill-opacity='.9' transform='rotate(-24 " + n(x - 3) + " 21)'") + ell(x + 5, 21, 3, 6, "#cfdcff", "fill-opacity='.9' transform='rotate(24 " + n(x + 5) + " 21)'")
    return svg(400, 70, body, "none")


C("moonPads", moon_pads())


def heron() -> str:
    """A heron that stands in the shallows: a long S-shaped neck, a dagger beak, a plume at the back of the head, one leg straight and the other folded."""
    ink = "#141c34"
    body = stroke("M44 90V138", ink, 2.4) + stroke("M54 92L58 112L52 122L56 138", ink, 1.8)
    body += ell(48, 78, 22, 11, ink, "transform='rotate(-18 48 78)'") + poly([(60, 82), (80, 96), (64, 90)], ink)
    body += stroke("M34 74Q24 60 36 46Q46 32 32 20", ink, 5.2) + ell(30, 17, 6.4, 3.8, ink, "transform='rotate(-24 30 17)'")
    body += poly([(24, 15), (2, 22), (24, 19)], ink) + stroke("M34 13Q44 8 52 11", ink, 1.2)
    body += stroke("M30 76Q46 66 66 80", "#a9bff0", .9, "stroke-opacity='.55'") + stroke("M34 74Q24 60 36 46Q46 32 32 20", "#a9bff0", .7, "stroke-opacity='.4'")
    return svg(80, 140, body, "xMidYMax meet")


C("heron", heron())


def moon_hills() -> str:
    """A far shore across the water: low dark hills with a few small pines on them (stretched over the width)."""
    w, h = 400, 50
    top = ridge(w, 34, 8, [(170, 1), (70, .5), (28, .2)], 5, .4, 70)
    body = path(d_ridge(top, w, h), "#0b1124") + stroke(d_smooth(top, closed=False), "#a9bff0", .8, "stroke-opacity='.3'")
    from scene_kit import pine
    for x, y, th in ((40, 22, 14), (62, 24, 11), (140, 20, 15), (250, 22, 13), (270, 24, 10), (350, 20, 14)):
        pts, (tx, ty, tw_, th_) = pine(x, y + 12, th, 8, 4)
        body += poly(pts, "#0b1124") + rect(tx, ty, tw_, th_, "#0b1124")
    return svg(w, h, body, "none")


C("moonHills", moon_hills())


def moon_cloud() -> str:
    """A long thin wisp of cloud that passes the moon (soft overlapping ellipses with a radial fade)."""
    body = radgrad("g", [(0, "#c9d6ff", .5), (1, "#c9d6ff", 0)])
    for cx, cy, rx, ry in ((60, 22, 56, 7), (120, 18, 70, 6), (190, 24, 60, 8), (250, 19, 46, 5)):
        body += ell(cx, cy, rx, ry, "url(#g)")
    return svg(300, 40, body, "xMidYMid meet")


C("moonCloud", moon_cloud())


def moon_cranes() -> str:
    """Five cranes in a V formation, each a few strokes of curved wings; they cross the moon at night."""
    body = ""
    for x, y, s in ((70, 20, 1), (50, 30, .85), (90, 30, .85), (30, 40, .7), (110, 40, .7)):
        body += stroke(f"M{n(x - 14 * s)} {n(y + 5 * s)}Q{n(x - 6 * s)} {n(y - 5 * s)} {n(x)} {n(y)}Q{n(x + 6 * s)} {n(y - 5 * s)} {n(x + 14 * s)} {n(y + 5 * s)}", "#e4ecff", 1.8 * s)
        body += stroke(f"M{n(x)} {n(y)}L{n(x + 2 * s)} {n(y + 6 * s)}", "#e4ecff", 1.4 * s)
    return svg(140, 50, body, "xMidYMid meet")


C("moonCranes", moon_cranes())


def lotus_halo() -> str:
    """A halo of two rings of pointed lotus petals (a mask): soft fill, clear rim, thin circles between."""
    body = ""
    for ring, (count, r0, r1, half, off) in enumerate(((12, 104, 196, 25, 0), (12, 90, 150, 15, 15))):
        for k in range(count):
            a = k * 360 / count + off
            body += f"<path fill='#000' fill-opacity='{.2 if ring == 0 else .3}' stroke='#000' stroke-opacity='{.75 if ring == 0 else .6}' stroke-width='1.1' d='M200 {200 - r0}Q{200 - half} {200 - (r0 + r1) / 2} 200 {200 - r1}Q{200 + half} {200 - (r0 + r1) / 2} 200 {200 - r0}z' transform='rotate({n(a)} 200 200)'/>"
    body += stroke(f"M{200 + 102} 200A102 102 0 1 0 {200 - 102} 200A102 102 0 1 0 {200 + 102} 200z", "#000", .9, "stroke-opacity='.5'")
    return svg(400, 400, body, "xMidYMid meet")


C("lotusHalo", lotus_halo())


# ── Прилив Рюдзина: дракон вокруг аватара с жемчужиной, столбы света, водоросли, дворец на дне, косяк карпов ──
def sstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def sea_dragon() -> str:
    """The sea dragon coils round the avatar for three quarters of a circle: teal body with a lighter belly, a gold ridge of spikes, scutes across the body, a gold fin on the tail; the head has horns, whiskers and chases a glowing pearl."""
    cx = cy = 180
    count = 74
    theta0, sweep = math.radians(-235), math.radians(270)

    def centre(t: float):
        a = theta0 + sweep * t
        rad = 126 + 13 * math.sin(math.tau * 3 * t + .6)
        return cx + rad * math.cos(a), cy + rad * math.sin(a)

    half = lambda t: 1.6 + 14.4 * sstep(t / .5) - 4.4 * sstep((t - .75) / .2)      # noqa: E731
    pts, out, tan, hw = [], [], [], []
    for i in range(count):
        t = i / (count - 1)
        p = centre(t)
        q = centre(min(1, t + .004))
        o = centre(max(0, t - .004))
        dx, dy = q[0] - o[0], q[1] - o[1]
        ln = math.hypot(dx, dy) or 1
        ox, oy = p[0] - cx, p[1] - cy
        ol = math.hypot(ox, oy) or 1
        pts.append(p); tan.append((dx / ln, dy / ln)); out.append((ox / ol, oy / ol)); hw.append(half(t))
    along = lambda i, k, m: (pts[i][0] + out[i][0] * hw[i] * k + tan[i][0] * m, pts[i][1] + out[i][1] * hw[i] * k + tan[i][1] * m)      # noqa: E731 (a point on the body: k across (+1 back, -1 belly), m along)
    outline = [along(i, 1, 0) for i in range(count)] + [along(i, -1, 0) for i in range(count - 1, -1, -1)]
    body = "<defs><radialGradient id='o' gradientUnits='userSpaceOnUse' cx='0' cy='0' r='11'><stop offset='0' stop-color='#fff'/><stop offset='.45' stop-color='#c8fbff' stop-opacity='.95'/><stop offset='1' stop-color='#52e6cc' stop-opacity='0'/></radialGradient></defs>"
    body += path(d_smooth(outline), "#0b5f66") + stroke(d_smooth(outline), "#52e6cc", .9, "stroke-opacity='.55'")
    belly = [along(i, -.38, 0) for i in range(count)]
    body += poly(ribbon(belly, [hw[i] * .48 for i in range(count)]), "#2fd8c0", "fill-opacity='.8'")
    body += stroke(d_smooth([along(i, .82, 0) for i in range(4, count)], closed=False), "#e9c45d", 1.3, "stroke-opacity='.9'")
    scutes = ""
    for i in range(3, count - 3, 2):
        a, b, m = along(i, .92, 0), along(i, -.92, 0), along(i, 0, hw[i] * .6)
        scutes += f"<path d='M{n(a[0])} {n(a[1])}Q{n(m[0])} {n(m[1])} {n(b[0])} {n(b[1])}'/>"
    body += f"<g fill='none' stroke='#07474d' stroke-opacity='.6' stroke-width='.8'>{scutes}</g>"
    spikes = ""
    for i in range(6, count - 5, 3):
        a, b, tip = along(i, .9, -2.4), along(i, .9, 2.4), along(i, .9 + (4 + hw[i] * .45) / hw[i], -4.4)
        spikes += f"<path d='M{n(a[0])} {n(a[1])}L{n(tip[0])} {n(tip[1])}L{n(b[0])} {n(b[1])}z'/>"
    body += f"<g fill='#e9c45d' fill-opacity='.92'>{spikes}</g>"
    for i in (int(count * .3), int(count * .62)):                    # two pairs of legs reach in towards the avatar
        base = along(i, -.7, 0)
        knee = (base[0] - out[i][0] * 11 + tan[i][0] * 8, base[1] - out[i][1] * 11 + tan[i][1] * 8)
        foot = (knee[0] - out[i][0] * 9 - tan[i][0] * 5, knee[1] - out[i][1] * 9 - tan[i][1] * 5)
        leg = f"M{n(base[0])} {n(base[1])}L{n(knee[0])} {n(knee[1])}L{n(foot[0])} {n(foot[1])}"
        body += stroke(leg, "#0b5f66", 6) + stroke(leg, "#52e6cc", 1, "stroke-opacity='.55'")
        for da in (-.7, 0, .7):
            ca = math.atan2(-out[i][1], -out[i][0]) + da
            body += stroke(f"M{n(foot[0])} {n(foot[1])}L{n(foot[0] + 6.5 * math.cos(ca))} {n(foot[1] + 6.5 * math.sin(ca))}", "#e9c45d", 1.6)
    tail = [along(0, 0, -m) for m in (0, 8, 15)]
    body += poly([tail[0], (tail[2][0] + out[0][0] * 8, tail[2][1] + out[0][1] * 8), tail[1], (tail[2][0] - out[0][0] * 7, tail[2][1] - out[0][1] * 7)], "#e9c45d", "fill-opacity='.9'")
    hx, hy = pts[-1]
    ang = math.degrees(math.atan2(tan[-1][1], tan[-1][0]))
    head = poly([(-6, -8), (8, -10), (20, -8), (31, -5), (38, -3), (39, 0), (36, 2), (24, 3), (33, 5), (28, 8), (14, 9), (2, 8), (-6, 6)], "#0e7f86", "stroke='#52e6cc' stroke-opacity='.7' stroke-width='.9'")
    head += path("M4 -9Q-6 -22-22 -24Q-10 -16-1 -7z", "#e9c45d") + path("M8 -9Q2 -18-8 -22Q0 -14 4 -8z", "#e9c45d", "fill-opacity='.85'")
    head += "".join(poly([(x, -8), (x - 9, -19), (x - 5, -8)], "#e9c45d", "fill-opacity='.85'") for x in (-4, -9, -14, -19))
    head += circ(14, -3, 2.3, "#e9c45d") + circ(14.4, -3, 1, "#07303a") + stroke("M8 -6.4L19 -6.4", "#e9c45d", 1) + circ(35, -2.4, 1, "#07303a")
    head += stroke("M33 -4Q52 -20 74 -8", "#e9c45d", 1.2, "stroke-opacity='.9'") + stroke("M35 2Q54 14 76 8", "#e9c45d", 1.2, "stroke-opacity='.9'") + stroke("M30 5Q40 16 52 18", "#e9c45d", .9, "stroke-opacity='.7'")
    head += f"<g transform='translate(60 -1)'><circle r='11' fill='url(#o)'/><path fill='none' stroke='#e9c45d' stroke-opacity='.7' stroke-width='1' d='M-9 4Q-4 -10 7 -6M9 -3Q4 10 -6 8'/></g>"
    body += f"<g transform='translate({n(hx)} {n(hy)}) rotate({n(ang)}) scale(1.45)'>{head}</g>"
    return svg(360, 360, body, "xMidYMid meet")


C("seaDragon", sea_dragon())


def shafts() -> str:
    """Shafts of light that fall slanting from the surface (a mask): wide soft beams that fade as they sink."""
    r = random.Random(17)
    body = lingrad("f", [(0, "#000", .95), (.6, "#000", .35), (1, "#000", 0)], 0, 0, 0, 300, True)
    beams = ""
    for k in range(7):
        top = 18 + k * 34 + r.uniform(-8, 8)
        lean = 44 + r.uniform(-12, 12)
        wide = r.uniform(10, 26)
        beams += f"<path fill-opacity='{n(r.uniform(.45, 1))}' d='M{n(top - 4)} 0L{n(top + 4)} 0L{n(top + lean + wide)} 300L{n(top + lean - wide)} 300z'/>"
    return svg(300, 300, body + f"<g fill='url(#f)'>{beams}</g>", "xMidYMin meet")


C("shafts", shafts())


def kelp() -> str:
    """Strands of kelp that stand up from the bottom and bend: dark teal ribbons with small leaves, the front ones lighter."""
    r = random.Random(23)
    body = ""
    for k, (x0, height, shade) in enumerate(((20, 250, "#062a30"), (46, 200, "#083a40"), (72, 240, "#062a30"), (98, 170, "#0a4a52"), (120, 210, "#083a40"))):
        phase = r.uniform(0, math.tau)
        center = [(x0 + 16 * math.sin(phase + i / 8 * 2.4) * (i / 8), 260 - height * i / 8) for i in range(9)]
        body += poly(ribbon(center, [5.4 - 3.8 * i / 8 for i in range(9)]), shade)
        for i in (2, 4, 6):
            x, y = center[i]
            body += ell(x + (9 if i % 4 == 2 else -9), y, 8, 2.6, shade, f"transform='rotate({-30 if i % 4 == 2 else 30} {n(x)} {n(y)})'")
    body += stroke("M0 259H140", "#0a4a52", 4, "stroke-opacity='.8'")
    return svg(140, 260, body, "xMinYMax meet")


C("kelp", kelp())


def palace_gate() -> str:
    """The dragon king's palace far down: a three-tier tower with up-turned roofs and a gate under it, dark blue with a few warm windows."""
    ink = "#0c3640"
    body = rect(14, 150, 112, 50, ink) + path("M52 200V176Q70 160 88 176V200z", "#04161b") + rect(0, 196, 140, 4, ink)
    for k in range(3):
        y = 150 - k * 40
        wide = 118 - k * 26
        x0 = 70 - wide / 2
        body += rect(x0 + 10, y - 26, wide - 20, 26, ink)
        body += path(f"M{n(x0 - 8)} {n(y - 22)}Q{n(70)} {n(y - 32)} {n(x0 + wide + 8)} {n(y - 22)}L{n(x0 + wide - 4)} {n(y - 16)}Q{n(70)} {n(y - 22)} {n(x0 + 4)} {n(y - 16)}z", ink)
        body += stroke(f"M{n(x0 - 8)} {n(y - 22)}Q{n(70)} {n(y - 32)} {n(x0 + wide + 8)} {n(y - 22)}", "#52e6cc", .8, "stroke-opacity='.5'")
        for j in range(3 - k if k < 2 else 1):
            body += rect(x0 + 18 + j * (wide - 36) / max(1, 2 - k if k < 2 else 1), y - 20, 5, 9, "#e9c45d", "fill-opacity='.85'")
    body += stroke("M70 40V16", ink, 3) + circ(70, 14, 3.4, "#e9c45d", "fill-opacity='.9'")
    return svg(140, 200, body, "xMidYMax meet")


C("palaceGate", palace_gate())


def koi_shoal() -> str:
    """A shoal of golden koi swimming to the right: a small loose group of fish seen from the side."""
    r = random.Random(5)
    body = ""
    for x, y, s, colour in ((110, 22, 1.1, "#e9c45d"), (84, 14, .9, "#ffb454"), (86, 32, .95, "#e9c45d"), (58, 24, .85, "#fff0c2"), (34, 14, .8, "#e9c45d"), (30, 34, .75, "#ffb454")):
        body += ell(x, y, 10 * s, 3.8 * s, colour, "fill-opacity='.9'") + poly([(x - 8 * s, y), (x - 17 * s, y - 5 * s), (x - 15 * s, y), (x - 17 * s, y + 5 * s)], colour, "fill-opacity='.8'")
        body += poly([(x - 1 * s, y - 3 * s), (x - 5 * s, y - 8 * s), (x - 7 * s, y - 3 * s)], colour, "fill-opacity='.7'") + circ(x + 6 * s, y - 1 * s, .9 * s, "#07303a")
    return svg(140, 50, body, "xMidYMid meet")


C("koiShoal", koi_shoal())


# ── Полуночная Комета: Млечный Путь, большая комета с двумя хвостами, холмы с наблюдателем, малая комета ──
def milky_way() -> str:
    """A band of the Milky Way across the sky: a soft glow, two dust lanes and a few hundred tiny stars that crowd along the band (stretched over the whole stage)."""
    r = random.Random(41)
    w, h = 400, 300
    body = radgrad("g", [(0, "#8fa2ff", .2), (.6, "#8fa2ff", .08), (1, "#8fa2ff", 0)])
    th = math.radians(-32)
    along, across = (math.cos(th), math.sin(th)), (-math.sin(th), math.cos(th))
    body += ell(200, 150, 250, 56, "url(#g)", f"transform='rotate(-32 200 150)'") + ell(150, 168, 120, 8, "#03050d", "fill-opacity='.45' transform='rotate(-32 150 168)'") + ell(270, 128, 90, 6, "#03050d", "fill-opacity='.4' transform='rotate(-32 270 128)'")
    stars = ""
    for _ in range(230):
        u, v = r.uniform(-.55, .55) * 460, r.gauss(0, 24)
        x, y = 200 + u * along[0] + v * across[0], 150 + u * along[1] + v * across[1]
        if 2 < x < w - 2 and 2 < y < h - 2:
            stars += f"<circle cx='{n(x)}' cy='{n(y)}' r='{n(r.choice((.5, .6, .7, .9, 1.2)))}' fill-opacity='{n(r.uniform(.25, .95))}'/>"
    body += f"<g fill='#e8edff'>{stars}</g>"
    for _ in range(9):
        u, v = r.uniform(-.45, .45) * 460, r.gauss(0, 30)
        x, y = 200 + u * along[0] + v * across[0], 150 + u * along[1] + v * across[1]
        body += circ(x, y, 3, "#cfe0ff", "fill-opacity='.16'") + circ(x, y, 1.1, "#fff")
    return svg(w, h, body, "none")


C("milkyWay", milky_way())


def great_comet() -> str:
    """The great comet: a bright coma and nucleus at the right end, a slender curved golden dust tail and a few thin straight blue ion tails that fade to the left."""
    hx, hy = 470, 56
    body = lingrad("ion", [(0, "#cfe4ff", .9), (.5, "#7aa4ff", .3), (1, "#7aa4ff", 0)], hx, 0, 40, 0, True)
    body += lingrad("dust", [(0, "#fff1c8", .62), (.5, "#f0cf98", .26), (1, "#f0cf98", 0)], hx, 0, 36, 0, True)
    body += radgrad("coma", [(0, "#ffffff", 1), (.25, "#dcebff", .8), (1, "#8fb4ff", 0)])
    body += path("M470 53C340 32 190 40 36 92L36 116C190 76 340 68 470 61z", "url(#dust)")
    body += path("M470 55C350 42 220 50 80 92L80 102C220 70 350 66 470 59z", "url(#dust)", "fill-opacity='.6'")
    for k in range(4):
        a = math.radians((k - 1.5) * 1.6)
        ln = 420 - abs(k - 1.5) * 50
        body += f"<path fill='url(#ion)' d='M{hx} {hy - .6}L{n(hx - ln * math.cos(a))} {n(hy - ln * math.sin(a) - .45)}L{n(hx - ln * math.cos(a))} {n(hy - ln * math.sin(a) + .45)}L{hx} {hy + .6}z'/>"
    body += circ(hx, hy, 30, "url(#coma)") + circ(hx, hy, 3.2, "#fff") + circ(hx, hy, 7, "#fff", "fill-opacity='.55'")
    return svg(520, 140, body, "xMaxYMid meet")


C("greatComet", great_comet())


def hill_left() -> str:
    """A dark hill in the bottom corner with a stargazer on top: a standing figure with a thin cold rim light beside a telescope on a tripod that points at the comet, and a small warm lantern on the ground."""
    ink = "#0b1124"
    body = lingrad("m", [(0, "#16204a", 1), (1, "#070b1a", 1)]) + radgrad("l", [(0, "#ffd08a", .9), (1, "#ffb454", 0)])
    body += path("M0 90V54Q30 34 70 38Q112 42 150 90z", "url(#m)") + stroke("M0 54Q30 34 70 38Q112 42 150 90", "#8fa2ff", 1, "stroke-opacity='.5'")
    rim = "#a9b6ff"
    body += circ(56, 12.5, 3.6, ink) + poly([(52, 16), (60.5, 16), (62, 37), (50, 37)], ink) + stroke("M53.5 36V46M58.5 36V46", ink, 2.4)
    body += stroke("M52.4 16.4L50.6 36", rim, .8, "stroke-opacity='.55'") + stroke("M52.8 10.6Q56 7.8 59.2 10.6", rim, .8, "stroke-opacity='.55'")
    body += stroke("M60 22L92 3", ink, 4.4) + stroke("M60 22L92 3", rim, .8, "stroke-opacity='.65'") + stroke("M76 13L70 40M76 13L84 40M76 13L77 40", ink, 1.6) + stroke("M76 13L84 40", rim, .6, "stroke-opacity='.5'")
    body += circ(68, 39, 7, "url(#l)") + rect(66.4, 36.4, 3.2, 3.4, "#ffd08a")
    return svg(150, 90, body, "xMinYMax meet")


C("hillL", hill_left())


def hill_right() -> str:
    """The other corner: a low hill with two small pines."""
    from scene_kit import pine
    ink = "#070b1a"
    body = path("M0 90Q40 56 90 58Q130 60 150 70V90z", ink) + stroke("M0 90Q40 56 90 58Q130 60 150 70", "#6a7bff", .9, "stroke-opacity='.4'")
    for x, base, th in ((102, 62, 24), (124, 66, 17)):
        pts, (tx, ty, tw_, th_) = pine(x, base, th, 14, 4)
        body += poly(pts, ink) + rect(tx, ty, tw_, th_, ink)
    return svg(150, 90, body, "xMaxYMax meet")


C("hillR", hill_right())


def mini_comet() -> str:
    """A small comet that crosses the sky: a bright head on the right and a tapering tail with a faint dust fan."""
    body = lingrad("t", [(0, "#cfe4ff", 0), (1, "#cfe4ff", .9)], 0, 0, 1, 0) + radgrad("h", [(0, "#ffffff", 1), (.4, "#dcebff", .8), (1, "#8fb4ff", 0)])
    body += path("M8 12L96 9.4L96 14.6z", "url(#t)") + path("M20 14L96 11L96 17Q60 22 20 14z", "url(#t)", "fill-opacity='.35'") + circ(100, 12, 9, "url(#h)") + circ(100, 12, 2.2, "#fff")
    return svg(120, 24, body, "xMaxYMid meet")


C("miniComet", mini_comet())


# ── Хроно-ткач: шестерни, циферблат со стрелками, маятник, песочные часы, нити времени ──
def gear_big() -> str:
    """A big clock gear (a mask): toothed rim, six spokes with round cut-outs, a hub; the layer turns it."""
    cx = cy = 150
    body = path(gear_d(cx, cy, 146, 130, 28, 104), "#000", "fill-rule='evenodd'")
    body += path(f"M{cx + 34} {cy}A34 34 0 1 0 {cx - 34} {cy}A34 34 0 1 0 {cx + 34} {cy}zM{cx + 12} {cy}A12 12 0 1 0 {cx - 12} {cy}A12 12 0 1 0 {cx + 12} {cy}z", "#000", "fill-rule='evenodd'")
    for k in range(6):
        a = k * 60
        body += f"<rect fill='#000' x='{cx - 6}' y='{cy - 108}' width='12' height='78' transform='rotate({a} {cx} {cy})'/>"
        body += f"<circle fill='#000' cx='{cx}' cy='{cy - 62}' r='9' transform='rotate({a + 30} {cx} {cy})'/>"
    body += stroke(f"M{cx + 76} {cy}A76 76 0 1 0 {cx - 76} {cy}A76 76 0 1 0 {cx + 76} {cy}z", "#000", 2.4, "stroke-opacity='.8'")
    return svg(300, 300, body, "xMidYMid meet")


C("gearBrass", gear_big())


def gear_small() -> str:
    """A small gear (a mask): twelve teeth, four spokes, a hub."""
    cx = cy = 60
    body = path(gear_d(cx, cy, 56, 46, 12, 36), "#000", "fill-rule='evenodd'")
    body += path(f"M{cx + 13} {cy}A13 13 0 1 0 {cx - 13} {cy}A13 13 0 1 0 {cx + 13} {cy}zM{cx + 5} {cy}A5 5 0 1 0 {cx - 5} {cy}A5 5 0 1 0 {cx + 5} {cy}z", "#000", "fill-rule='evenodd'")
    for k in range(4):
        body += f"<rect fill='#000' x='{cx - 3}' y='{cy - 40}' width='6' height='30' transform='rotate({k * 90} {cx} {cy})'/>"
    return svg(120, 120, body, "xMidYMid meet")


C("gearSmall", gear_small())


def clock_dial() -> str:
    """A clock dial that turns behind the avatar (a mask): the rim, sixty ticks with a long one every fifth, twelve diamond marks, two thin inner rings."""
    cx = cy = 190
    body = stroke(f"M{cx + 182} {cy}A182 182 0 1 0 {cx - 182} {cy}A182 182 0 1 0 {cx + 182} {cy}z", "#000", 2) + stroke(f"M{cx + 134} {cy}A134 134 0 1 0 {cx - 134} {cy}A134 134 0 1 0 {cx + 134} {cy}z", "#000", 1, "stroke-opacity='.6'")
    ticks = ""
    for k in range(60):
        a = math.tau * k / 60
        r0 = 160 if k % 5 == 0 else 170
        ticks += f"<path stroke-width='{2.4 if k % 5 == 0 else 1}' d='M{n(cx + r0 * math.cos(a))} {n(cy + r0 * math.sin(a))}L{n(cx + 180 * math.cos(a))} {n(cy + 180 * math.sin(a))}'/>"
    body += f"<g stroke='#000' stroke-linecap='round'>{ticks}</g>"
    for k in range(12):
        a = math.tau * k / 12
        x, y = cx + 148 * math.cos(a), cy + 148 * math.sin(a)
        body += path(d_poly([(x + 7 * math.cos(a), y + 7 * math.sin(a)), (x - 4 * math.sin(a), y + 4 * math.cos(a)), (x - 7 * math.cos(a), y - 7 * math.sin(a)), (x + 4 * math.sin(a), y - 4 * math.cos(a))]), "#000")
    return svg(380, 380, body, "xMidYMid meet")


C("clockDial", clock_dial())


def hand(name: str, length: float, width: float, bulb: float) -> None:
    """A clock hand that starts outside the avatar frame (r = 86) and ends in a spear point, with a round bead on it (a mask)."""
    cx = cy = 190
    pts = [(cx - width, cy - 86), (cx - width * .5, cy - length * .6), (cx, cy - length), (cx + width * .5, cy - length * .6), (cx + width, cy - 86)]
    C(name, svg(380, 380, poly(pts, "#000") + circ(cx, cy - length * .5, bulb, "#000"), "xMidYMid meet"))


hand("handMinute", 176, 5, 7)
hand("handHour", 118, 7, 9)


def pendulum() -> str:
    """A pendulum on a long rod (a mask): the pivot, the rod, a decorated bob."""
    body = circ(30, 5, 4.4, "#000") + stroke("M30 5V176", "#000", 2.2) + circ(30, 194, 22, "#000") + stroke("M30 172V176", "#000", 5)
    return svg(60, 220, body, "xMidYMin meet")


C("pendulum", pendulum())


def hourglass() -> str:
    """An hourglass on a brass frame: two caps and pillars, glass with a thin edge, sand above and below and a fine stream through the neck."""
    brass, sand = "#c9a14a", "#e8c36a"
    body = rect(10, 4, 60, 7, brass) + rect(10, 129, 60, 7, brass) + rect(14, 11, 4, 118, brass, "fill-opacity='.8'") + rect(62, 11, 4, 118, brass, "fill-opacity='.8'")
    glass = "M22 12Q22 50 38 68Q40 70 38 72Q22 90 22 128H58Q58 90 42 72Q40 70 42 68Q58 50 58 12z"
    body += path(glass, "#cfe8e4", "fill-opacity='.14'") + stroke(glass, "#cfe8e4", 1, "stroke-opacity='.6'")
    body += path("M26 34Q30 52 38 62H42Q50 52 54 34z", sand, "fill-opacity='.9'") + path("M24 128Q26 106 40 100Q54 106 56 128z", sand, "fill-opacity='.95'") + stroke("M40 66V100", sand, 1.1, "stroke-opacity='.9'")
    return svg(80, 140, body, "xMidYMax meet")


C("hourglass", hourglass())


def threads() -> str:
    """Golden threads of time: long strands that wave and cross over each other like a warp on a loom (a mask, stretched over the layer)."""
    r = random.Random(19)
    body = ""
    for k in range(9):
        y = 16 + k * 20
        amp = r.uniform(8, 18)
        ph = r.uniform(0, math.tau)
        pts = [(x, y + amp * math.sin(x / 400 * math.tau * r.choice((1.5, 2)) + ph)) for x in range(0, 401, 40)]
        body += stroke(d_smooth(pts, closed=False), "#000", r.uniform(.8, 1.6), f"stroke-opacity='{n(r.uniform(.4, 1))}'")
    return svg(400, 200, body, "none")


C("threads", threads())


# ── Сердце Звезды: столбы газа с молодыми звёздами, оболочка сверхновой, звёздный крест, искры рождения ──
def gas_pillar() -> str:
    """Three pillars of cold gas where stars are born: dark violet columns with ragged fingers at the top, a hot pink rim on the lit side and a young star on some of the tips."""
    r = random.Random(4)
    w, h = 120, 280
    body = lingrad("g", [(0, "#241040", 1), (1, "#0a0414", 1)])
    for cx, wd, top in ((34, 42, 50), (68, 30, 112), (94, 24, 166)):
        left = [(cx - wd * .72 - r.uniform(0, 5), y) for y in range(h, top + 34, -28)]
        tip = [(cx - wd / 2, top + 20), (cx - wd / 4, top + 2), (cx - wd / 8, top + 12), (cx, top - 6), (cx + wd / 8, top + 10), (cx + wd / 4, top - 2), (cx + wd / 2, top + 18)]
        right = [(cx + wd * .72 + r.uniform(0, 5), y) for y in range(top + 34, h + 1, 28)]
        pts = left + tip + right
        body += path(d_smooth(pts), "url(#g)")
        rim = d_smooth(tip[3:] + right[:4], closed=False)
        body += stroke(rim, "#ff6fb0", 4.2, "stroke-opacity='.22'") + stroke(rim, "#ff9ac8", 1.2, "stroke-opacity='.9'")
        for x, y in tip[1::2]:
            body += circ(x, y - 1, 3.4, "#ffb0d6", "fill-opacity='.35'") + circ(x, y - 1, 1.3, "#fff6c8")
    body += ell(60, 276, 70, 12, "#3a1860", "fill-opacity='.45'")
    return svg(w, h, body, "xMinYMax meet")


C("gasPillar", gas_pillar())


def nebula_shell() -> str:
    """The shell of an old supernova (a mask): thin filaments of gas, short arcs at different radii that curl a little."""
    r = random.Random(12)
    body = ""
    for _ in range(46):
        rad = r.uniform(146, 192)
        a0 = r.uniform(0, math.tau)
        span = r.uniform(.22, 1.0)
        bulge = r.uniform(-14, 14)
        mid = a0 + span / 2
        p0 = (200 + rad * math.cos(a0), 200 + rad * math.sin(a0))
        p1 = (200 + (rad + r.uniform(-8, 8)) * math.cos(a0 + span), 200 + (rad + r.uniform(-8, 8)) * math.sin(a0 + span))
        c = (200 + (rad + bulge) * math.cos(mid), 200 + (rad + bulge) * math.sin(mid))
        body += stroke(f"M{n(p0[0])} {n(p0[1])}Q{n(c[0])} {n(c[1])} {n(p1[0])} {n(p1[1])}", "#000", r.uniform(.8, 4.4), f"stroke-opacity='{n(r.uniform(.14, .6))}'")
    return svg(400, 400, body, "xMidYMid meet")


C("nebulaShell", nebula_shell())


def star_flare() -> str:
    """A diffraction cross of a very bright star (a mask): long rays up, left and right, a short one down (the nickname lives there), shorter diagonal rays, a thin ring."""
    body = ""
    for a, ln, wd in ((0, 146, 6), (90, 146, 6), (180, 64, 6), (270, 146, 6), (45, 92, 4.5), (135, 92, 4.5), (225, 56, 4.5), (315, 92, 4.5)):
        body += f"<path fill='#000' d='M{150 - wd} 150L150 {150 - ln}L{150 + wd} 150z' transform='rotate({a} 150 150)'/>"
    body += stroke("M210 150A60 60 0 1 0 90 150A60 60 0 1 0 210 150z", "#000", 1.2, "stroke-opacity='.7'") + circ(150, 150, 10, "#000")
    return svg(300, 300, body, "xMidYMid meet")


C("starFlare", star_flare())


def sparkles(name: str, seed: int) -> None:
    """Five four-point sparkles of different sizes scattered over the stage (stretched over the layer), pale gold."""
    r = random.Random(seed)
    body = "".join(path(star_d(r.uniform(30, 370), r.uniform(26, 274), size, .2), "#fff6c8", "fill-opacity='.95'") for size in (15, 11, 9, 7, 6))
    C(name, svg(400, 300, body, "none"))


sparkles("sparklesA", 31)
sparkles("sparklesB", 77)
