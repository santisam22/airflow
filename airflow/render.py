"""Drawing the floor plan, ducts and air."""

import math

import numpy as np
import pygame

from . import config as C
from .parts import BY_ID, DAMPER_LEVELS, DIRS, EIGHTHS, abs_ports, throw_dirs
from .roomair import heat_rgba, speed_color

HW = 0.28  # half duct width (tiles)


def _rot(pt, rot):
    x, y = pt
    for _ in range(rot % 4):
        x, y = 1 - y, x
    return (x, y)


def _arc(cx, cy, r, a0, a1, n=10):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def body_poly(pdef):
    """Single outline polygon (unit tile, rotation 0) for the duct body."""
    a, b = 0.5 - HW, 0.5 + HW
    k = pdef.kind
    sh = pdef.shape
    if pdef.category == "TURN":
        if sh in ("round", "roundvaned"):
            outer = _arc(0, 1, 0.5 + HW, -math.pi / 2, 0)
            inner = _arc(0, 1, 0.5 - HW, 0, -math.pi / 2)
            return outer + inner
        if sh == "chamfer":
            c = 0.22
            return [(0, a), (b - c, a), (b, a + c), (b, 1), (a, 1), (a, b), (0, b)]
        return [(0, a), (b, a), (b, 1), (a, 1), (a, b), (0, b)]
    if k in ("tee", "tapered"):
        ports = set(pdef.ports)
        if ports == {0, 1, 2, 3}:
            return [(0, a), (a, a), (a, 0), (b, 0), (b, a), (1, a), (1, b), (b, b), (b, 1), (a, 1), (a, b), (0, b)]
        if pdef.id == "ybranch":
            return [(0, a), (a, a), (a, 0), (b, 0), (b, 1), (a, 1), (a, b), (0, b)]
        if pdef.id == "taperl":
            return [(0, a), (1, a), (1, b), (b, b), (b, 1), (a, 1), (0.08, b), (0, b)]
        if pdef.id == "taperr":
            return [(0, a), (1, a), (1, b), (0.92, b), (b, 1), (a, 1), (a, b), (0, b)]
        return [(0, a), (1, a), (1, b), (b, b), (b, 1), (a, 1), (a, b), (0, b)]
    if k == "cap":
        return [(0, a), (0.62, a), (0.62, b), (0, b)]
    if k == "terminal":
        return [(0, a), (0.5, a), (0.5, b), (0, b)]
    return [(0, a), (1, a), (1, b), (0, b)]


def flow_color(cfm, connected=True):
    if not connected:
        return speed_color(0.0)
    return speed_color(min(C.VMAX, cfm * C.VMAX / C.DUCT_CFM_FOR_MAX))


def draw_part(p, pdef, placed, x0, y0, T, fill, outline, flow=0.0, theme=None, stage="both"):
    """Draw a part with its tile's top-left at (x0, y0) logical, tile size T.

    stage "outline" strokes the body only; "fill" paints over it. Drawing every
    part's outline first and then every fill makes connected runs seamless.
    """
    rot = placed.get("rot", 0)

    def tp(pt):
        u, v = _rot(pt, rot)
        return (x0 + u * T, y0 + v * T)

    lw = max(1.2, T * 0.045)
    poly = [tp(q) for q in body_poly(pdef)]
    if stage == "outline":
        p.poly(outline, poly, lw * 2)
        return
    p.poly(fill, poly)
    if stage == "both":
        p.poly(outline, poly, lw)

    k = pdef.kind
    if pdef.shape == "flex":
        for i in range(1, 7):
            u = i / 7
            p.line(outline, tp((u, 0.5 - HW + 0.04)), tp((u, 0.5 + HW - 0.04)), max(0.8, lw * 0.5))
    if pdef.shape in ("vaned", "roundvaned"):
        for i in range(3):
            o = 0.12 + i * 0.12
            p.line(outline, tp((0.5 - HW + o * 0.9, 0.5 - HW + 0.02)), tp((0.5 + HW - 0.02, 0.5 + HW - o * 0.9)),
                   max(0.8, lw * 0.5))
    if k == "cap":
        r = [tp((0.6, 0.5 - HW - 0.07)), tp((0.74, 0.5 - HW - 0.07)), tp((0.74, 0.5 + HW + 0.07)),
             tp((0.6, 0.5 + HW + 0.07))]
        p.poly(outline, r)
    elif k == "damper":
        lvl = placed.get("damper", 0)
        ang = [0.0, 0.5, 0.9, 1.25][lvl % 4]
        c = (0.5, 0.5)
        dx, dy = math.sin(ang) * 0.24, math.cos(ang) * 0.24
        p.line(outline, tp((c[0] - dx, c[1] - dy)), tp((c[0] + dx, c[1] + dy)), lw * 1.6)
        p.circle(outline, tp(c), T * 0.05)
    elif k == "booster":
        cx, cy = tp((0.5, 0.5))
        p.circle(fill, (cx, cy), T * 0.3)
        p.circle(outline, (cx, cy), T * 0.3, lw)
        tri = [tp((0.66, 0.5)), tp((0.4, 0.36)), tp((0.4, 0.64))]
        p.poly(outline, tri)
    elif k == "terminal":
        box = [tp((0.16, 0.16)), tp((0.84, 0.16)), tp((0.84, 0.84)), tp((0.16, 0.84))]
        face = theme["panel"] if theme else (255, 255, 255)
        p.poly(face, box)
        p.poly(fill, box, max(2.0, T * 0.09))
        p.poly(outline, box, lw)
        cx, cy = x0 + 0.5 * T, y0 + 0.5 * T
        aim = placed.get("aim", 2)
        if pdef.id == "bareboot":
            p.circle(outline, (cx, cy), T * 0.2, lw)
        elif pdef.id == "slot":
            dx, dy = EIGHTHS[aim]
            px, py = -dy, dx
            p.line(outline, (cx - px * T * 0.26, cy - py * T * 0.26), (cx + px * T * 0.26, cy + py * T * 0.26),
                   lw * 1.8)
            _arrow(p, outline, cx, cy, dx, dy, T, 0.26)
        elif pdef.id == "swirl":
            p.circle(outline, (cx, cy), T * 0.18, lw)
            for e in (0, 2, 4, 6):
                dx, dy = EIGHTHS[e]
                _arrow(p, outline, cx, cy, dx, dy, T, 0.3, small=True)
        else:
            for e in throw_dirs(pdef, aim):
                dx, dy = EIGHTHS[e]
                _arrow(p, outline, cx, cy, dx, dy, T, 0.27)


def _arrow(p, color, cx, cy, dx, dy, T, length, small=False):
    px, py = -dy, dx
    w = 0.08 if small else 0.11
    base = 0.06 if not small else 0.16
    tip = (cx + dx * T * length, cy + dy * T * length)
    b1 = (cx + dx * T * base + px * T * w, cy + dy * T * base + py * T * w)
    b2 = (cx + dx * T * base - px * T * w, cy + dy * T * base - py * T * w)
    p.poly(color, [tip, b1, b2])


def draw_ahu(p, theme, x0, y0, T, flow):
    color = flow_color(flow) if flow > 1 else (40, 70, 210)
    r = (x0 + T * 0.04, y0 + T * 0.04, T * 0.92, T * 0.92)
    p.rect(color, r, radius=T * 0.12)
    p.rect(theme["outline"], r, width=max(1.5, T * 0.05), radius=T * 0.12)
    size = max(8, int(T * 0.28))
    p.text("AHU", size, (255, 255, 255), (x0 + T / 2, y0 + T / 2), "center", bold=True)


class PlanView:
    """Camera + cached heat surface for the current plan."""

    def __init__(self):
        self.zoom = 1.0
        self.ox = 0.0   # logical offset of plan origin inside the viewport
        self.oy = 0.0
        self.view = pygame.Rect(0, 0, 100, 100)
        self.heat_key = None
        self.heat_img = None
        self.fitted_for = None

    @property
    def T(self):
        return C.TILE * self.zoom

    def fit(self, plan, view):
        self.view = view
        tz = min(view.w / (plan.w * C.TILE), view.h / (plan.h * C.TILE)) * 0.9
        self.zoom = max(0.3, min(3.0, tz))
        self.ox = (view.w - plan.w * self.T) / 2
        self.oy = (view.h - plan.h * self.T) / 2
        self.fitted_for = plan.num

    def origin(self):
        return self.view.x + self.ox, self.view.y + self.oy

    def tile_at(self, mx, my):
        x0, y0 = self.origin()
        return (int(math.floor((mx - x0) / self.T)), int(math.floor((my - y0) / self.T)))

    def tile_xy(self, t):
        x0, y0 = self.origin()
        return x0 + t[0] * self.T, y0 + t[1] * self.T

    def zoom_at(self, factor, mx, my):
        old = self.T
        self.zoom = max(0.3, min(3.5, self.zoom * factor))
        k = self.T / old
        x0, y0 = self.origin()
        self.ox = (mx - self.view.x) - (mx - x0) * k
        self.oy = (my - self.view.y) - (my - y0) * k

    def heat_surface(self, speed, version, scale):
        T = self.T
        key = (version, round(T, 3), scale, speed.shape)
        if key != self.heat_key:
            rgba = np.ascontiguousarray(heat_rgba(speed))
            h, w = speed.shape
            small = pygame.image.frombuffer(rgba.tobytes(), (w, h), "RGBA").convert_alpha()
            # two-step upscale keeps the blobs smooth
            mid = pygame.transform.smoothscale(small, (w * 4, h * 4))
            cells_px = T * scale / C.CELLS
            size = (max(1, int(w * cells_px)), max(1, int(h * cells_px)))
            self.heat_img = pygame.transform.smoothscale(mid, size)
            self.heat_key = key
        return self.heat_img


def draw_plan(p, theme, game, pv, show_heat=True, show_ducts=True, version=0):
    plan = game.plan
    T = pv.T
    x0, y0 = pv.origin()
    W, H = plan.w * T, plan.h * T

    p.clip(pv.view)
    # floor + grid
    p.rect(theme["floor"], (x0, y0, W, H))
    for i in range(1, plan.w):
        p.line(theme["grid"], (x0 + i * T, y0), (x0 + i * T, y0 + H), 1)
    for j in range(1, plan.h):
        p.line(theme["grid"], (x0, y0 + j * T), (x0 + W, y0 + j * T), 1)

    # furniture
    fsz = max(6, min(11, int(T * 0.17)))
    for label, fx, fy, fw, fh, shape in plan.furniture:
        r = (x0 + fx * T, y0 + fy * T, fw * T, fh * T)
        if shape == "circle":
            c = (r[0] + r[2] / 2, r[1] + r[3] / 2)
            rad = min(r[2], r[3]) / 2
            p.circle(theme["furn"], c, rad, 1.5)
            p.circle(theme["furn"], c, rad * 0.4)
        elif shape == "chair":
            p.rect(theme["furn"], r, radius=3)
        else:
            rad = min(r[2], r[3]) * (0.45 if shape == "round" else 0.12)
            p.rect(theme["furn"], r, width=1.5, radius=rad)
            if shape == "rect" and r[2] > 20 and r[3] > 10:
                inset = min(r[2], r[3]) * 0.14
                p.rect(theme["grid"], (r[0] + inset, r[1] + inset, r[2] - 2 * inset, r[3] - 2 * inset),
                       width=1, radius=rad * 0.6)
        if label and T > 18:
            p.text(label, fsz, theme["furn_text"], (r[0] + r[2] / 2, r[1] + r[3] / 2), "center")

    # air
    if show_heat and game.speed is not None:
        img = pv.heat_surface(game.speed, version, p.s)
        p.blit(img, (x0, y0))

    # walls
    wall_w = max(2.0, T * 0.09)
    doors = plan.door_set()
    tr = plan.tile_room
    for y in range(plan.h):
        for x in range(1, plan.w):
            if tr[y, x] != tr[y, x - 1]:
                a, b = (x0 + x * T, y0 + y * T), (x0 + x * T, y0 + (y + 1) * T)
                if ("v", x, y) in doors:
                    p.line(theme["door"], a, b, max(1.5, wall_w * 0.35))
                else:
                    p.line(theme["wall"], (a[0], a[1] - wall_w / 2), (b[0], b[1] + wall_w / 2), wall_w)
    for y in range(1, plan.h):
        for x in range(plan.w):
            if tr[y, x] != tr[y - 1, x]:
                a, b = (x0 + x * T, y0 + y * T), (x0 + (x + 1) * T, y0 + y * T)
                if ("h", x, y) in doors:
                    p.line(theme["door"], a, b, max(1.5, wall_w * 0.35))
                else:
                    p.line(theme["wall"], (a[0] - wall_w / 2, a[1]), (b[0] + wall_w / 2, b[1]), wall_w)
    ow = wall_w * 1.3
    p.rect(theme["wall"], (x0 - ow / 2, y0 - ow / 2, W + ow, H + ow), width=ow)

    # ducts
    net = game.net
    if show_ducts:
        items = []
        for t, pl in game.layout.items():
            pdef = BY_ID[pl["type"]]
            flow = net.part_flow.get(t, 0.0) if net else 0.0
            conn = net is not None and t in net.connected
            items.append((pdef, pl, pv.tile_xy(t), flow_color(flow, conn), flow))
        for stage in ("outline", "fill"):
            for pdef, pl, (tx, ty), fill, flow in items:
                draw_part(p, pdef, pl, tx, ty, T, fill, theme["outline"], flow, theme, stage=stage)

    # room labels (over the ducts so they stay readable)
    lsz = max(8, min(14, int(T * 0.24)))
    for i, (name, rx, ry, rw, rh) in enumerate(plan.rooms):
        cx, cy = x0 + (rx + rw / 2) * T, y0 + (ry + rh / 2) * T
        cov = game.room_cov[i] if i < len(game.room_cov) else 0.0
        label = name.upper()
        lw_ = p.text_w(label, lsz, True)
        p.rect(theme["floor"] + (170,), (cx - lw_ / 2 - 5, cy - lsz * 1.35, lw_ + 10, lsz * 2.6), radius=5)
        p.text(label, lsz, theme["text"], (cx, cy - lsz * 0.15), "midbottom", bold=True)
        p.text(f"{cov * 100:.0f}%", lsz, theme["text"], (cx, cy + lsz * 0.05), "midtop")

    if show_ducts:
        ax, ay = pv.tile_xy(plan.ahu)
        draw_ahu(p, theme, ax, ay, T, net.ahu_flow if net else 0.0)
        p.text("AIR HANDLER", max(8, min(15, int(T * 0.26))), theme["text"],
               (ax + T / 2, ay - T * 0.08), "midbottom", bold=True)
        if net:
            for leak in net.leaks:
                if leak.cfm < 1.0:
                    continue
                dx, dy = DIRS[leak.dir]
                lx, ly = pv.tile_xy(leak.tile)
                c = (lx + T * (0.5 + dx * 0.5), ly + T * (0.5 + dy * 0.5))
                rr = max(5, T * 0.2)
                p.circle((255, 255, 255), c, rr + 1.5)
                p.circle(theme["red"], c, rr)
                p.text("!", int(rr * 1.5), (255, 255, 255), c, "center", bold=True)
    p.clip(None)
