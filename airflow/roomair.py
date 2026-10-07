"""Room air field: a per-cell air speed map built from register jets, then
spread by diffusion that walls block (doors let it through).

Coverage per cell ramps from 0 at COVER_LO m/s to 1 at COVER_HI m/s.
"""

import math

import numpy as np

from . import config as C
from .parts import BY_ID, EIGHTHS, throw_dirs


class RoomGrid:
    def __init__(self, plan):
        c = C.CELLS
        self.plan = plan
        self.c = c
        self.W = plan.w * c
        self.H = plan.h * c
        self.room = np.kron(plan.tile_room, np.ones((c, c), dtype=int))
        open_r = self.room[:, :-1] == self.room[:, 1:]
        open_d = self.room[:-1, :] == self.room[1:, :]
        for kind, x, y in plan.doors:
            if kind == "v":
                open_r[y * c:(y + 1) * c, x * c - 1] = True
            else:
                open_d[y * c - 1, x * c:(x + 1) * c] = True
        self.open_r = open_r.astype(float)
        self.open_d = open_d.astype(float)
        ys, xs = np.mgrid[0:self.H, 0:self.W]
        self.X = xs + 0.5
        self.Y = ys + 0.5
        self.n_rooms = len(plan.rooms)
        self.room_masks = [self.room == i for i in range(self.n_rooms)]
        self.room_cells = np.array([m.sum() for m in self.room_masks], dtype=float)
        cnt = np.ones((self.H, self.W))
        cnt[:, :-1] += self.open_r
        cnt[:, 1:] += self.open_r
        cnt[:-1, :] += self.open_d
        cnt[1:, :] += self.open_d
        self.cnt = cnt

    def diffuse(self, f, iters):
        o_r, o_d = self.open_r, self.open_d
        for _ in range(iters):
            acc = f.copy()
            acc[:, :-1] += f[:, 1:] * o_r
            acc[:, 1:] += f[:, :-1] * o_r
            acc[:-1, :] += f[1:, :] * o_d
            acc[1:, :] += f[:-1, :] * o_d
            f = acc / self.cnt
        return f

    def _stop_distance(self, ox, oy, dx, dy, room):
        """Distance (cells) a jet travels before it hits another room's wall."""
        s = 0.0
        step = 0.5
        limit = max(self.W, self.H) * 1.5
        while s < limit:
            s += step
            cx = int(math.floor(ox + dx * s))
            cy = int(math.floor(oy + dy * s))
            if cx < 0 or cy < 0 or cx >= self.W or cy >= self.H:
                return s - step
            if self.room[cy, cx] != room:
                return s - step
        return limit

    def compute(self, layout, net):
        f = np.zeros((self.H, self.W))
        c = self.c
        for term in net.terminals:
            if term.cfm <= 0.01 or term.room < 0:
                continue
            pl = layout[term.tile]
            pdef = BY_ID[pl["type"]]
            dirs = throw_dirs(pdef, pl.get("aim", 0))
            ox = (term.tile[0] + 0.5) * c
            oy = (term.tile[1] + 0.5) * c
            q_dir = term.cfm / max(1, len(dirs))
            v0 = min(C.VMAX, C.JET_V_PER_CFM * q_dir * pdef.exit * (1.0 + 0.15 * (len(dirs) - 1)) ** 0.5)
            v0 *= C.TERMINAL_STRENGTH
            L = pdef.throw * (4.5 + 0.11 * q_dir) * c / 4.0
            mask = self.room_masks[term.room]
            for e in dirs:
                dx, dy = EIGHTHS[e]
                stop = self._stop_distance(ox, oy, dx, dy, term.room)
                rx = self.X - ox
                ry = self.Y - oy
                s = rx * dx + ry * dy
                lat = np.abs(-rx * dy + ry * dx)
                sp = np.maximum(s, 0.0)
                sig0 = 1.6 if pdef.wide else 0.7
                sig = sig0 + (0.55 if pdef.wide else 0.42) * sp
                along = np.exp(-sp / max(L, 0.5))
                # jets that hit a wall pile up and spread along it
                wall = np.clip((sp - stop) / 3.0, 0.0, None)
                jet = v0 * along * np.exp(-(lat * lat) / (2 * sig * sig)) * np.exp(-wall * 1.5)
                jet *= (s > -1.5)
                f = np.maximum(f, jet * mask)
            # local blob at the register itself
            d2 = (self.X - ox) ** 2 + (self.Y - oy) ** 2
            f = np.maximum(f, v0 * 0.6 * np.exp(-d2 / (2 * (0.9 * c / 4) ** 2 * 4)) * mask)

        # general room mixing: a faint floor of air in rooms that receive air
        base = np.zeros((self.H, self.W))
        for room, cfm in net.room_cfm.items():
            if room >= 0 and self.room_cells[room] > 0:
                per = cfm / (self.room_cells[room] / (c * c))
                base += self.room_masks[room] * min(0.07, 0.0012 * per)
        f = np.maximum(f, base)
        spread = self.diffuse(f, 10 * c)
        f = np.maximum(f, spread * 1.35)
        self.speed = np.clip(f, 0.0, C.VMAX)
        return self.speed

    def coverage(self, speed=None):
        speed = self.speed if speed is None else speed
        cov_cells = np.clip((speed - C.COVER_LO) / (C.COVER_HI - C.COVER_LO), 0.0, 1.0)
        rooms = []
        for i, m in enumerate(self.room_masks):
            rooms.append(float(cov_cells[m].mean()) if self.room_cells[i] else 0.0)
        total = float(cov_cells.mean())
        avg_speed = float(speed.mean())
        return total, rooms, avg_speed


# --- colour map --------------------------------------------------------------
_STOPS = np.array([
    [0.00, 0.12, 0.20, 0.78],
    [0.12, 0.10, 0.45, 0.98],
    [0.28, 0.10, 0.78, 0.95],
    [0.45, 0.22, 0.82, 0.42],
    [0.60, 0.90, 0.90, 0.20],
    [0.76, 1.00, 0.58, 0.10],
    [1.00, 0.88, 0.10, 0.10],
])


def speed_to_t(v):
    """Non-linear legend: v = VMAX * t^2."""
    return np.sqrt(np.clip(np.asarray(v, dtype=float) / C.VMAX, 0.0, 1.0))


def colormap(t):
    t = np.clip(np.asarray(t, dtype=float), 0.0, 1.0)
    out = np.empty(t.shape + (3,))
    for ch in range(3):
        out[..., ch] = np.interp(t, _STOPS[:, 0], _STOPS[:, ch + 1])
    return out


def speed_color(v):
    rgb = colormap(speed_to_t(v))
    return tuple(int(x * 255) for x in rgb.reshape(-1, 3)[0])


def heat_rgba(speed):
    rgb = colormap(speed_to_t(speed))
    alpha = np.clip(speed / 0.09, 0.0, 1.0) ** 0.9 * 0.92
    rgba = np.empty(speed.shape + (4,), dtype=np.uint8)
    rgba[..., :3] = (rgb * 255).astype(np.uint8)
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    return rgba
