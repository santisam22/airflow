"""Animated air.

The solver gives steady flows. This module turns them into what you see:

* Ducts are filled with a live speed field, not a flat colour: a fast jet leaves
  the air handler, slow boundary layers grow along the walls as the air travels,
  bends push the fast air to the outer wall, and the core wobbles over time.
* Changes travel. When a duct opens, the air front moves down it at FRONT_SPEED
  tiles per second; when it's cut off, the air downstream winds down instead of
  vanishing.
* Rooms fill gradually. A new register starts as a small puff that spreads into
  a plume, cells further from the register fill later, and the plumes keep
  drifting slightly once settled.
"""

from collections import deque

import numpy as np
import pygame

from . import config as C
from .parts import BY_ID, DIRS, abs_ports, rot_dir
from .render import HW, _rot, body_poly
from .roomair import heat_rgba, speed_to_t, colormap

FRONT_SPEED = 9.0        # tiles/s an air front travels down a newly opened duct
RAMP_UP = 0.45           # s for a duct cell to come up to speed once the front arrives
DROP_SPEED = 30.0        # tiles/s a shut-off travels (pressure drops fast)
RAMP_DOWN = 0.9          # s for a duct cell to wind down
ROOM_TAU_UP = 0.45       # s, room air time constant right at a register...
ROOM_TAU_PER_TILE = 0.32  # ...plus this per tile of distance from it
ROOM_TAU_DOWN = 2.2      # s for room air to die away once its supply is cut

DETAIL_CELLS = [8, 12, 16]   # duct cells per tile for Air detail low / medium / high
DETAIL_HZ = [20, 30, 60]     # how often the animated layers redraw


def _smooth_noise(shape, scale, rng):
    """Smooth random field in [-1, 1]."""
    h, w = shape
    gh, gw = max(2, int(h / scale) + 2), max(2, int(w / scale) + 2)
    g = rng.uniform(-1, 1, (gh, gw))
    ys = np.linspace(0, gh - 1.001, h)
    xs = np.linspace(0, gw - 1.001, w)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    out = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    return out / max(1e-6, np.abs(out).max())


class DuctGeometry:
    """Per-cell description of the duct network at R cells per tile."""

    def __init__(self, plan, layout, R):
        self.R = R
        W, H = plan.w * R, plan.h * R
        self.shape = (H, W)
        surf = pygame.Surface((W, H))
        surf.fill((0, 0, 0))
        for t, pl in layout.items():
            pdef = BY_ID[pl["type"]]
            pts = [((t[0] + u) * R, (t[1] + v) * R) for u, v in (_rot(q, pl["rot"]) for q in body_poly(pdef))]
            pygame.draw.polygon(surf, (255, 255, 255), pts)
        self.mask = pygame.surfarray.array_red(surf).T > 127
        ax, ay = plan.ahu
        self.ahu = np.zeros((H, W), dtype=bool)
        self.ahu[ay * R:(ay + 1) * R, ax * R:(ax + 1) * R] = True
        self.mask &= ~self.ahu
        flowable = self.mask | self.ahu

        # distance from the duct wall, 0 at the wall .. 1 at the centreline
        wd = np.zeros((H, W))
        m = flowable.copy()
        for _ in range(R):
            if not m.any():
                break
            wd[m] += 1
            e = m.copy()
            e[1:, :] &= m[:-1, :]
            e[:-1, :] &= m[1:, :]
            e[:, 1:] &= m[:, :-1]
            e[:, :-1] &= m[:, 1:]
            m = e
        half = max(1.0, HW * R)
        self.w = np.clip((wd - 0.5) / half, 0.02, 1.0)
        # outline: the outermost ring of duct cells (not where a duct meets the AHU)
        self.edge = self.mask & (wd <= max(1, R // 10))
        self.flowable = flowable

        # path distance from the air handler through the ducts, in tiles
        self.s = self.path_distance(self.ahu)          # inf where not reachable from the AHU
        self.s_finite = np.where(np.isfinite(self.s), self.s, 0.0)

        # which port (arm) of its part each cell belongs to, and bend skew
        self.cell_tiles = {}
        lin = (np.arange(R) + 0.5) / R
        U, V = np.meshgrid(lin, lin)          # local coords inside one tile
        self.bend = np.ones((H, W))
        self.arm = {}                          # tile -> list of (dir, bool mask RxR)
        for t, pl in layout.items():
            pdef = BY_ID[pl["type"]]
            ports = list(abs_ports(pdef, pl["rot"]).keys())
            if not ports:
                continue
            scores = np.stack([(U - 0.5) * DIRS[d][0] + (V - 0.5) * DIRS[d][1] for d in ports])
            best = np.argmax(scores, axis=0)
            centre = (np.abs(U - 0.5) < HW) & (np.abs(V - 0.5) < HW)
            arms = [(d, (best == i) & ~centre) for i, d in enumerate(ports)]
            arms.append((None, centre))
            self.arm[t] = arms
            if pdef.category == "TURN":
                # inner corner of the rot-0 elbow (ports W and S) is the tile's SW corner
                cx, cy = _rot((0.0, 1.0), pl["rot"])
                dd = np.hypot(U - cx, V - cy)
                outer = np.clip((dd - (0.5 - HW)) / (2 * HW), 0.0, 1.0)
                skew = 0.72 + 0.5 * outer
                self.bend[t[1] * R:(t[1] + 1) * R, t[0] * R:(t[0] + 1) * R] = skew

    def path_distance(self, seeds):
        """Distance in tiles through the ducts from any seed cell."""
        H, W = self.shape
        flowable = self.flowable
        dist = np.full((H, W), np.inf)
        q = deque()
        ys, xs = np.nonzero(seeds & flowable)
        for y, x in zip(ys, xs):
            dist[y, x] = 0.0
            q.append((y, x))
        while q:
            y, x = q.popleft()
            d = dist[y, x] + 1.0
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < H and 0 <= nx < W and flowable[ny, nx] and dist[ny, nx] == np.inf:
                    dist[ny, nx] = d
                    q.append((ny, nx))
        return dist / self.R

    def _ease(self, f, iters):
        """Average each duct cell with its duct neighbours, so flow changes blend smoothly."""
        m = self.mask.astype(float)
        f = f * m
        for _ in range(iters):
            acc = f.copy()
            cnt = m.copy()
            acc[1:, :] += f[:-1, :]; cnt[1:, :] += m[:-1, :]
            acc[:-1, :] += f[1:, :]; cnt[:-1, :] += m[1:, :]
            acc[:, 1:] += f[:, :-1]; cnt[:, 1:] += m[:, :-1]
            acc[:, :-1] += f[:, 1:]; cnt[:, :-1] += m[:, 1:]
            f = np.where(self.mask, acc / np.maximum(cnt, 1), 0.0)
        return f

    def target_speed(self, layout, net):
        """Steady-state speed (m/s) in every duct cell for these flows."""
        H, W = self.shape
        R = self.R
        cfm = np.zeros((H, W))
        for t, arms in self.arm.items():
            flows = [net.port_flow.get((t, d), 0.0) for d, _ in arms if d is not None]
            top = max(flows) if flows else 0.0
            block = cfm[t[1] * R:(t[1] + 1) * R, t[0] * R:(t[0] + 1) * R]
            for d, m in arms:
                block[m] = top if d is None else net.port_flow.get((t, d), 0.0)
        cfm = self._ease(cfm, max(2, int(R * 0.7)))           # speed changes over ~a tile at a junction
        v = cfm * C.VMAX / C.DUCT_CFM_FOR_MAX
        s = self.s_finite
        core = 1.0 + 0.35 * np.exp(-s / 2.2)                 # the jet out of the air handler
        decay = 0.85 + 0.15 * np.exp(-s / 10.0)              # friction slows long runs
        n = 0.08 + 0.42 * (1.0 - np.exp(-s / 4.0))           # boundary layer develops downstream
        prof = 0.3 + 0.7 * self.w ** n
        out = v * core * decay * prof * self.bend
        out[~self.mask] = 0.0
        return np.clip(out, 0.0, C.VMAX)


class FlowAnimator:
    def __init__(self):
        self.plan_num = None
        self.R = None
        self.geo = None
        self.t0 = 0.0
        self.u_from = None
        self.u_to = None
        self.delay = None
        self.ramp = None
        self.room = None
        self.room_target = None
        self.room_tau = None
        self.room_start = None
        self.room_cov = []
        self.total_cov = 0.0
        self.avg_speed = 0.0
        self._cov_at = -1.0
        self._frame_at = -1.0
        self._frame = None
        self.layout_key = None

    # ------------------------------------------------------------ changes
    def on_sim(self, game, t, detail=1):
        """Call after the network was re-solved (or the project/detail changed)."""
        plan = game.plan
        R = DETAIL_CELLS[detail]
        key = tuple(sorted((k, pl["type"], pl["rot"]) for k, pl in game.layout.items()))
        fresh = self.plan_num != plan.num or self.R != R
        if fresh or key != self.layout_key or self.geo is None:
            self.geo = DuctGeometry(plan, game.layout, R)
            self.layout_key = key
        H, W = self.geo.shape
        if fresh:
            self.plan_num = plan.num
            self.R = R
            self.u_disp = np.zeros((H, W))
            rng = np.random.default_rng(7 + plan.num)
            self.streaks = _smooth_noise((16, 160), 4.0, rng)     # (across the duct, along it)
            g = game.grid()
            self.room = np.zeros((g.H, g.W))
            self.room_n1 = _smooth_noise((g.H, g.W), C.CELLS * 2.2, rng)
            self.room_n2 = _smooth_noise((g.H, g.W), C.CELLS * 1.4, rng)
            self.room_cov = [0.0] * len(plan.rooms)
        if fresh or self.u_to is None or self.u_to.shape != (H, W):
            current = self.u_disp
        else:
            current = self.duct_speed(t)
        current = np.where(self.geo.mask, current, 0.0)
        self.u_from = current
        self.u_to = self.geo.target_speed(game.layout, game.net)
        up = self.u_to >= self.u_from
        s = self.geo.s_finite
        # a new front starts from wherever the air is already flowing, not from the AHU
        flowing = self.geo.ahu | (self.geo.mask & (self.u_from > 0.08))
        s_new = self.geo.path_distance(flowing)
        s_new = np.where(np.isfinite(s_new), s_new, s)
        self.delay = np.where(up, s_new / FRONT_SPEED, s / DROP_SPEED)
        self.ramp = np.where(up, RAMP_UP, RAMP_DOWN)
        self.t0 = t

        # rooms: target from the steady simulation; cells near a register fill first
        g = game.grid()
        self.room_target = game.speed.copy()
        c = g.c
        near = np.full(self.room_target.shape, 1e9)
        start = np.zeros(self.room_target.shape)
        for term in game.net.terminals:
            if term.cfm <= 1.0:
                continue
            ox, oy = (term.tile[0] + 0.5) * c, (term.tile[1] + 0.5) * c
            d = np.hypot(g.X - ox, g.Y - oy) / c
            # air reaches the register only when the duct front gets there
            ty, tx = int((term.tile[1] + 0.5) * self.R), int((term.tile[0] + 0.5) * self.R)
            arrive = 0.0
            if 0 <= ty < H and 0 <= tx < W:
                # the register box is not in the mask; use the closest duct cell's distance
                ys, xs = np.nonzero(self.geo.mask[max(0, ty - self.R):ty + self.R, max(0, tx - self.R):tx + self.R])
                if len(ys):
                    sub = self.geo.s_finite[max(0, ty - self.R):ty + self.R, max(0, tx - self.R):tx + self.R]
                    arrive = float(sub[ys, xs].max()) / FRONT_SPEED
            closer = d < near
            near = np.where(closer, d, near)
            start = np.where(closer, arrive, start)
        near = np.where(near > 1e8, 0.0, near)
        self.room_near = near
        self.room_tau = ROOM_TAU_UP + ROOM_TAU_PER_TILE * near
        self.room_start = t + start

    # ------------------------------------------------------------ per frame
    def duct_speed(self, t):
        w = np.clip((t - self.t0 - self.delay) / self.ramp, 0.0, 1.0)
        w = w * w * (3 - 2 * w)
        return self.u_from + (self.u_to - self.u_from) * w

    def update(self, t, dt, grid):
        if self.room is None or self.room_target is None:
            return
        up = self.room_target > self.room
        rate = np.where(up, dt / self.room_tau, dt / ROOM_TAU_DOWN)
        active = (~up) | (t >= self.room_start)
        self.room += (self.room_target - self.room) * np.clip(rate, 0.0, 1.0) * active
        if t - self._cov_at > 0.2:
            self.total_cov, self.room_cov, self.avg_speed = grid.coverage(self.room)
            self._cov_at = t

    def settle(self, t):
        """Jump straight to the steady state (tests and snapshots)."""
        if self.u_to is not None:
            self.u_from = self.u_to.copy()
            self.t0 = t - 100
        if self.room_target is not None:
            self.room = self.room_target.copy()
            self._cov_at = -1

    def frame(self, t, hz):
        """RGBA arrays for the duct field and the room heatmap, redrawn at most `hz` times a second."""
        if self.geo is None or self.u_to is None:
            return None
        if self._frame is not None and t - self._frame_at < 1.0 / hz:
            return self._frame
        g = self.geo
        u = self.duct_speed(t)
        s = g.s_finite
        # streaks carried along the duct with the air; calm in the jet, turbulent downstream
        amp = 0.26 * (1.0 - np.exp(-s / 2.5))
        tex = self.streaks
        th, tw = tex.shape
        fx = (s * 9.0 - t * 11.0) % tw
        fy = np.clip(g.w, 0.0, 1.0) * (th - 1.001)
        x0 = fx.astype(int) % tw          # (-tiny) % tw can round up to exactly tw
        y0 = np.clip(fy.astype(int), 0, th - 2)
        ax, ay = fx - x0, fy - y0
        x1 = (x0 + 1) % tw
        n = ((tex[y0, x0] * (1 - ax) + tex[y0, x1] * ax) * (1 - ay)
             + (tex[y0 + 1, x0] * (1 - ax) + tex[y0 + 1, x1] * ax) * ay)
        u = np.clip(u * (1.0 + amp * n), 0.0, C.VMAX)
        rgb = colormap(speed_to_t(u))
        duct = np.empty(u.shape + (4,), dtype=np.uint8)
        duct[..., :3] = (rgb * 255).astype(np.uint8)
        duct[..., 3] = np.where(g.mask & ~g.edge, 255, 0).astype(np.uint8)

        wob = 1.0 + 0.14 * (self.room_n1 * np.sin(0.8 * t) + self.room_n2 * np.cos(0.6 * t + 1.0))
        # waves of air rolling outward from every register, so the room is never still
        near = getattr(self, "room_near", None)
        if near is not None and near.shape == wob.shape:
            wob = wob * (1.0 + 0.13 * np.sin(2 * np.pi * (near / 1.4 - 0.75 * t) + 2.0 * self.room_n2))
        heat = heat_rgba(np.clip(self.room * wob, 0.0, C.VMAX))
        self._frame = (np.ascontiguousarray(duct), np.ascontiguousarray(heat), t)
        self._frame_at = t
        return self._frame
