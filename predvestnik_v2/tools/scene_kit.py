"""Drawing kit of the skin scenes: a few helpers that turn points into silhouette SVGs and the registry the art files fill (tools/scene_art.py renders it).

A picture is a CSS background (data-URI), painted once and never animated by itself, so keep every drawing small: simple paths, no filters, no gradients that are not needed.
Two kinds: a coloured picture (`sil i-name`: the colour is baked in, a dark tone of its skin) and a mask (`sil m i-name`: any opaque fill, the colour comes from the layer).
"""
from __future__ import annotations

import math
import random

ARTS: dict[str, tuple[str, str]] = {}   # class name -> (file letter, css url(...))


def uri(svg_text: str) -> str:
    return 'url("data:image/svg+xml,' + svg_text.replace("<", "%3C").replace(">", "%3E").replace("#", "%23") + '")'


def svg(w: int, h: int, body: str, fit: str = "xMidYMax meet") -> str:
    return uri(f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}' preserveAspectRatio='{fit}'>{body}</svg>")


def n(v: float) -> str:
    return f"{v:.0f}" if abs(v - round(v)) < .05 else f"{v:.1f}"


def art(name: str, letter: str, value: str) -> None:
    assert name not in ARTS, f"duplicate art {name}"
    ARTS[name] = (letter, value)


def d_poly(points) -> str:
    return "M" + "L".join(f"{n(x)} {n(y)}" for x, y in points) + "z"


def poly(points, fill, extra="") -> str:
    return f"<path fill='{fill}' {extra} d='{d_poly(points)}'/>"


def path(d, fill, extra="") -> str:
    return f"<path fill='{fill}' {extra} d='{d}'/>"


def stroke(d, color, width, extra="") -> str:
    return f"<path fill='none' stroke='{color}' stroke-width='{n(width)}' stroke-linecap='round' stroke-linejoin='round' {extra} d='{d}'/>"


def ell(cx, cy, rx, ry, fill, extra="") -> str:
    return f"<ellipse fill='{fill}' {extra} cx='{n(cx)}' cy='{n(cy)}' rx='{n(rx)}' ry='{n(ry)}'/>"


def circ(cx, cy, r, fill, extra="") -> str:
    return f"<circle fill='{fill}' {extra} cx='{n(cx)}' cy='{n(cy)}' r='{n(r)}'/>"


def rect(x, y, w, h, fill, extra="") -> str:
    return f"<rect fill='{fill}' {extra} x='{n(x)}' y='{n(y)}' width='{n(w)}' height='{n(h)}'/>"


def d_smooth(points, closed=True) -> str:
    """Soft outline through the middles of a few points (quadratic curves): organic shapes out of a handful of numbers."""
    n = lambda v: f"{v:.0f}" if abs(v - round(v)) < .3 else f"{v:.1f}"   # noqa: E731 (a bigger shape needs less precision: shorter file)
    k = len(points)
    mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if closed:
        sx, sy = mid(points[-1], points[0])
        d = f"M{n(sx)} {n(sy)}"
        for i in range(k):
            c, m = points[i], mid(points[i], points[(i + 1) % k])
            d += f"Q{n(c[0])} {n(c[1])} {n(m[0])} {n(m[1])}"
        return d + "z"
    d = f"M{n(points[0][0])} {n(points[0][1])}"
    for i in range(1, k - 1):
        c, m = points[i], mid(points[i], points[i + 1])
        d += f"Q{n(c[0])} {n(c[1])} {n(m[0])} {n(m[1])}"
    return d + f"L{n(points[-1][0])} {n(points[-1][1])}"


def d_ridge(top, w, h) -> str:
    """A ground silhouette: the smooth line `top` (left to right) closed down to the bottom edge."""
    return d_smooth(top, closed=False) + f"L{n(w)} {n(h)}L0 {n(h)}z"


def ridge(w, base, amp, waves, seed=1, jag=0.0, steps=40, fade=None):
    """Points of a ridge line: a sum of sines [(wavelength, weight)...] around `base` (a number, or a function of x/w to bend the whole line), a little noise `jag`; `fade(x/w)` scales the height along x."""
    r = random.Random(seed)
    phase = [r.uniform(0, math.tau) for _ in waves]
    pts = []
    for i in range(steps + 1):
        x = w * i / steps
        y = sum(a * math.sin(x / wl * math.tau + p) for (wl, a), p in zip(waves, phase))
        y = (base(x / w) if callable(base) else base) - amp * (y + (r.random() - .5) * jag) * (fade(x / w) if fade else 1)
        pts.append((x, y))
    return pts


def dune_top(w, base, amp, count, seed=1, steps=30, fade=None):
    """Dunes: a skewed wave with a gentle windward side, a sharp crest and a steep leeward side."""
    r = random.Random(seed)
    pts = []
    shifts = [r.uniform(.8, 1.2) for _ in range(int(count) + 2)]
    for i in range(steps + 1):
        t = i / steps * count
        k = int(t)
        u = t - k
        h = (u / .72) ** 1.5 if u < .72 else (1 - (u - .72) / .28) ** 1.1
        y = base - amp * h * shifts[k] * (fade(i / steps) if fade else 1)
        pts.append((w * i / steps, y))
    return pts


def mirror(points, w):
    return [(w - x, y) for x, y in points][::-1]


def pine(x, base, h, w, tiers=5):
    top = base - h
    left, right = [], []
    for k in range(tiers):
        y0 = top + k * h * .78 / tiers
        y1 = top + (k + 1) * h * .78 / tiers + h * .06
        half = w * (.28 + .72 * (k + 1) / tiers) / 2
        inner = half * .55
        if k == 0:
            left.append((x, y0)); right.append((x, y0))
        left += [(x - inner * (.5 if k else .3), y0 + (y1 - y0) * .35), (x - half, y1)]
        right += [(x + inner * (.5 if k else .3), y0 + (y1 - y0) * .35), (x + half, y1)]
        if k < tiers - 1:
            left.append((x - half * .45, y1)); right.append((x + half * .45, y1))
    return left + right[::-1], (x - w * .05, base - h * .22, w * .1, h * .22)


def forest(trees, w, h, fill, tiers=5):
    body = ""
    for x, th, tw in trees:
        pts, (tx, ty, tw_, th_) = pine(x, h, th, tw, tiers)
        body += poly(pts, fill) + rect(tx, ty, tw_, th_, fill)
    return svg(w, h, body)


def star_d(cx, cy, r, k=.22) -> str:
    """Four-point sparkle."""
    return d_poly([(cx, cy - r), (cx + r * k, cy - r * k), (cx + r, cy), (cx + r * k, cy + r * k), (cx, cy + r), (cx - r * k, cy + r * k), (cx - r, cy), (cx - r * k, cy - r * k)])


def gear_d(cx, cy, r_out, r_in, teeth, hole) -> str:
    pts = []
    for i in range(teeth):
        a = math.tau * i / teeth
        step = math.tau / teeth
        for da, rr in ((-.28, r_in), (-.16, r_out), (.16, r_out), (.28, r_in)):
            pts.append((cx + rr * math.cos(a + da * step * 1.8), cy + rr * math.sin(a + da * step * 1.8)))
    ring = d_poly(pts)
    return ring + f"M{n(cx + hole)} {n(cy)}A{n(hole)} {n(hole)} 0 1 0 {n(cx - hole)} {n(cy)}A{n(hole)} {n(hole)} 0 1 0 {n(cx + hole)} {n(cy)}z"


def bezier(p0, p1, p2, p3, count):
    """Points of a cubic Bézier curve."""
    out = []
    for i in range(count + 1):
        t = i / count
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0], u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def ribbon(center, radii):
    """A tapered body along a line (a dragon, a tail, a vine): the outline around `center` points with the half-width `radii` at each of them."""
    left, right = [], []
    for i, (x, y) in enumerate(center):
        a, b = center[max(i - 1, 0)], center[min(i + 1, len(center) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        left.append((x + nx * radii[i], y + ny * radii[i]))
        right.append((x - nx * radii[i], y - ny * radii[i]))
    return left + right[::-1]


def lingrad(gid: str, stops, x1=0, y1=0, x2=0, y2=1, user=False) -> str:
    """A linear gradient for a fill or a stroke, stops are (offset, colour, opacity); `user=True` takes the coordinates in the picture's own units."""
    units = " gradientUnits='userSpaceOnUse'" if user else ""
    body = "".join(f"<stop offset='{o}' stop-color='{c}' stop-opacity='{a}'/>" for o, c, a in stops)
    return f"<defs><linearGradient id='{gid}' x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}'{units}>{body}</linearGradient></defs>"


def radgrad(gid: str, stops, cx=.5, cy=.5, r=.5) -> str:
    body = "".join(f"<stop offset='{o}' stop-color='{c}' stop-opacity='{a}'/>" for o, c, a in stops)
    return f"<defs><radialGradient id='{gid}' cx='{cx}' cy='{cy}' r='{r}'>{body}</radialGradient></defs>"


def jag(points, amp, seed, splits=1):
    """Roughen a polyline: extra points between the given ones, pushed sideways by up to `amp` (rock, ice, a torn edge)."""
    r = random.Random(seed)
    out = [points[0]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        ln = math.hypot(x1 - x0, y1 - y0) or 1
        nx, ny = -(y1 - y0) / ln, (x1 - x0) / ln
        for s in range(1, splits + 1):
            t = s / (splits + 1)
            o = (r.random() - .5) * 2 * amp
            out.append((x0 + (x1 - x0) * t + nx * o, y0 + (y1 - y0) * t + ny * o))
        out.append((x1, y1))
    return out


def flip(body: str, w: int) -> str:
    """The same drawing mirrored left to right."""
    return f"<g transform='translate({w} 0) scale(-1 1)'>{body}</g>"


def tide(letter: str, name: str, width: int, amp: float, top: str, rim: str, depth: int = 40, opacity: float = .55) -> None:
    """A wave strip for a running `wave go` layer: the crest line and a fading body below it."""
    pts = []
    for i in range(0, width + 1, width // 12):
        x = i / width * math.tau
        pts.append((i, depth * .42 - amp * (math.sin(x) * .7 + math.sin(2 * x + 1.1) * .45)))
    crest = d_smooth(pts, closed=False)
    art(name, letter, svg(width, depth, lingrad("g", [(0, top, opacity), (1, top, 0)]) + path(crest + f"V{depth}H0z", "url(#g)") + stroke(crest, rim, 1.2, "stroke-opacity='.6'"), "none"))


def arc_d(cx, cy, r, a0, a1) -> str:
    """An SVG arc of a circle from angle a0 to a1 (radians, y down, clockwise)."""
    large = 1 if (a1 - a0) % math.tau > math.pi else 0
    return f"M{n(cx + r * math.cos(a0))} {n(cy + r * math.sin(a0))}A{n(r)} {n(r)} 0 {large} 1 {n(cx + r * math.cos(a1))} {n(cy + r * math.sin(a1))}"


def spiral_points(cx, cy, r0, r1, turns, a0=0.0, steps=48):
    """Points of a logarithmic spiral from radius r0 (angle a0) outwards to r1 after `turns` turns."""
    pts = []
    k = math.log(r1 / r0)
    for i in range(steps + 1):
        t = i / steps
        a = a0 + turns * math.tau * t
        r = r0 * math.exp(k * t)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
