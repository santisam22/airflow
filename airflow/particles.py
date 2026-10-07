"""Moving air you can see.

Duct particles are poured in at the air handler and flow along the ducts like
water, faster where more air flows. At each junction a particle picks where to
go in proportion to the airflow down each arm, so busy branches get more of
them. When one reaches a register it leaves as a room puff, blown in one of the
register's throw directions; puffs slow down, drift and swirl, bounce off walls
and fade. Particles that reach an open end spill out into the attic.
"""

import math
import random

import pygame

from .parts import BY_ID, DIRS, EIGHTHS, throw_dirs
from . import config as C

MAX_DUCT = 700
MAX_ROOM = 1100
DETAIL_RATE = [0.5, 1.0, 1.6]     # spawn multiplier for Air detail low / medium / high


class Particles:
    def __init__(self, seed=3):
        self.rng = random.Random(seed)
        self.duct = []     # [x, y, tx, ty, next_tile, speed, life] in tile units
        self.room = []     # [x, y, vx, vy, room, age, life]
        self.spawn_acc = 0.0
        self.plan = None
        self.net = None
        self.layout = None
        self.routes = {}
        self.speeds = {}

    # ------------------------------------------------------------ network changes
    def on_sim(self, plan, layout, net):
        if self.plan is not plan:
            self.duct.clear()
            self.room.clear()
        self.plan, self.layout, self.net = plan, layout, net
        # at each tile: weighted choices of where air goes next
        routes = {}
        sinks = {}
        for term in net.terminals:
            if term.cfm > 0.5:
                sinks.setdefault(term.tile, []).append(("room", term.tile, term.cfm))
        for leak in net.leaks:
            if leak.cfm > 0.5:
                sinks.setdefault(leak.tile, []).append(("leak", leak.dir, leak.cfm))
        for t, kids in net.tree.items():
            opts = [("duct", c, q) for c, _, q in kids if q > 0.5] + sinks.get(t, [])
            if opts:
                routes[t] = opts
        self.routes = routes
        self.speeds = {t: q for t, q in net.part_flow.items()}
        # particles on routes that no longer exist drain away
        self.duct = [p for p in self.duct if p[4] is None or p[4] in self.speeds or p[4] == "spill"]

    def _speed(self, tile):
        q = self.speeds.get(tile, 0.0)
        return 1.2 + 7.0 * min(1.0, q / C.DUCT_CFM_FOR_MAX)

    def _route(self, tile):
        opts = self.routes.get(tile)
        if not opts:
            return None
        total = sum(o[2] for o in opts)
        r = self.rng.random() * total
        for o in opts:
            r -= o[2]
            if r <= 0:
                return o
        return opts[-1]

    # ------------------------------------------------------------ per frame
    def update(self, dt, detail=1, room_speed=None):
        if self.net is None:
            return
        rng = self.rng
        plan = self.plan
        ahu = tuple(plan.ahu)
        # spawn at the air handler, in proportion to how much air it moves
        if self.net.ahu_flow > 0 and ahu in self.routes:
            self.spawn_acc += dt * DETAIL_RATE[detail] * (8 + 40 * self.net.ahu_flow / 415.0)
            while self.spawn_acc >= 1 and len(self.duct) < MAX_DUCT:
                self.spawn_acc -= 1
                self.duct.append(self._new_duct(ahu))
            self.spawn_acc = min(self.spawn_acc, 3)

        keep = []
        for p in self.duct:
            p[6] += dt
            if p[4] == "spill":                       # leaving an open end
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                if p[6] < 0.5:
                    keep.append(p)
                continue
            step = p[5] * dt
            while step > 0 and p[4] is not None:
                tx, ty = p[4][0] + 0.5 + p[7], p[4][1] + 0.5 + p[8]
                dx, dy = tx - p[0], ty - p[1]
                dist = math.hypot(dx, dy)
                if dist > step:
                    p[0] += dx / dist * step
                    p[1] += dy / dist * step
                    step = 0
                    break
                p[0], p[1] = tx, ty
                step -= dist
                here = p[4]
                p[5] = self._speed(here)
                o = self._route(here)
                if o is None:
                    p[4] = None
                elif o[0] == "duct":
                    p[4] = o[1]
                elif o[0] == "leak":
                    d = DIRS[o[1]]
                    p[4] = "spill"
                    p[2], p[3] = d[0] * 2.5, d[1] * 2.5
                    p[6] = 0.0
                    break
                else:                                  # out through a register
                    self._emit_room(here, rng)
                    p[4] = None
            if p[4] is not None and p[6] < 30:
                keep.append(p)
        self.duct = keep

        keep = []
        for p in self.room:
            p[5] += dt
            if p[5] > p[6]:
                continue
            # drag, then a gentle swirl so the air keeps moving
            drag = math.exp(-1.6 * dt)
            p[2] *= drag
            p[3] *= drag
            ang = 1.7 * math.sin(p[0] * 1.3 + p[5] * 0.9) + 1.7 * math.cos(p[1] * 1.1 - p[5] * 0.7)
            p[2] += math.cos(ang) * 0.9 * dt
            p[3] += math.sin(ang) * 0.9 * dt
            nx, ny = p[0] + p[2] * dt, p[1] + p[3] * dt
            if plan.room_at(int(math.floor(nx)), int(math.floor(p[1]))) != p[4]:
                p[2] = -p[2] * 0.5
                nx = p[0]
            if plan.room_at(int(math.floor(nx)), int(math.floor(ny))) != p[4]:
                p[3] = -p[3] * 0.5
                ny = p[1]
            p[0], p[1] = nx, ny
            keep.append(p)
        self.room = keep

    def _new_duct(self, ahu):
        p = [ahu[0] + 0.5, ahu[1] + 0.5, 0.0, 0.0, None, self._speed(ahu), 0.0,
             self.rng.uniform(-0.12, 0.12), self.rng.uniform(-0.12, 0.12)]
        o = self._route(ahu)
        p[4] = o[1] if o and o[0] == "duct" else None
        return p

    def _emit_room(self, tile, rng):
        pl = self.layout.get(tile)
        if not pl or len(self.room) >= MAX_ROOM:
            return
        pdef = BY_ID[pl["type"]]
        room = self.plan.room_at(*tile)
        if room < 0:
            return
        dirs = throw_dirs(pdef, pl.get("aim", 0))
        term = next((t for t in self.net.terminals if t.tile == tile), None)
        cfm = term.cfm if term else 0.0
        v0 = C.JET_V_PER_CFM * cfm * C.JET_K * pdef.power * C.TERMINAL_STRENGTH
        n = 1 if len(dirs) == 1 else 2
        for _ in range(n):
            e = rng.choice(dirs)
            dx, dy = EIGHTHS[e]
            spread = 0.55 if pdef.wide else 0.28
            a = math.atan2(dy, dx) + rng.uniform(-spread, spread)
            speed = (0.8 + 2.6 * min(2.0, v0)) * rng.uniform(0.7, 1.15) * pdef.throw ** 0.5
            ox = tile[0] + 0.5 + dx * 0.32 + (rng.uniform(-0.3, 0.3) * -dy if pdef.wide else 0)
            oy = tile[1] + 0.5 + dy * 0.32 + (rng.uniform(-0.3, 0.3) * dx if pdef.wide else 0)
            self.room.append([ox, oy, math.cos(a) * speed, math.sin(a) * speed, room, 0.0,
                              rng.uniform(1.6, 3.2)])

    # ------------------------------------------------------------ drawing
    def _layer(self, p, pv):
        """A transparent overlay the size of the plan, in real pixels."""
        T = pv.T * p.s
        w = max(1, int(self.plan.w * T) + 2)
        h = max(1, int(self.plan.h * T) + 2)
        lay = getattr(self, "_lay", None)
        if lay is None or lay.get_size() != (w, h):
            lay = pygame.Surface((w, h), pygame.SRCALPHA)
            self._lay = lay
        lay.fill((0, 0, 0, 0))
        return lay, T

    def _blit(self, p, pv, lay):
        x0, y0 = pv.origin()
        p.surf.blit(lay, (int(x0 * p.s), int(y0 * p.s)))

    def draw_room(self, p, pv):
        if not self.room:
            return
        lay, T = self._layer(p, pv)
        w = max(1, int(round(T * 0.05)))
        for q in self.room:
            k = q[5] / q[6]
            a = int(225 * (1 - k) * min(1.0, q[5] * 6))
            if a < 8:
                continue
            sx, sy = q[0] * T, q[1] * T
            ex, ey = sx - q[2] * T * 0.09, sy - q[3] * T * 0.09
            pygame.draw.line(lay, (255, 255, 255, a), (sx, sy), (ex, ey), w)
        self._blit(p, pv, lay)

    def draw_duct(self, p, pv):
        if not self.duct:
            return
        lay, T = self._layer(p, pv)
        r = max(1.5, T * 0.05)
        for q in self.duct:
            a = 200 if q[4] != "spill" else int(200 * max(0.0, 1 - q[6] / 0.5))
            pygame.draw.circle(lay, (255, 255, 255, a), (q[0] * T, q[1] * T), r)
        self._blit(p, pv, lay)
