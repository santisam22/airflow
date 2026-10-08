"""Game state. Every change to the world goes through `apply(action)` so a
future multiplayer layer can forward the same actions over the network."""

import json
import os
import time

from . import config as C
from .network import solve
from .parts import BY_ID, DAMPER_LEVELS, default_aim, price_at
from .projects import PROJECTS, project
from .roomair import RoomGrid

UPGRADES = [
    # id, title, effect text, max level, base cost
    ("blower", "BLOWER MOTOR", "+10% furnace airflow per level", 18, 1000.0),
    ("liner", "SMOOTH DUCT LINER", "-5% fitting & duct friction per level", 12, 1750.0),
    ("service", "SERVICE CONTRACTS", "+13% income per level", 18, 2500.0),
    ("material", "MATERIAL SOURCING", "+1 metal limit per level", 20, 2000.0),
]
UPG = {u[0]: u for u in UPGRADES}


def upgrade_cost(uid, level):
    base = UPG[uid][4]
    raw = base * (level + 1) ** 2.5
    # 3 significant figures
    mag = 10 ** max(0, len(str(int(raw))) - 3)
    return float(round(raw / mag) * mag)


class ActionError(Exception):
    pass


class Game:
    def __init__(self):
        self.money = C.STARTING_MONEY
        self.upgrades = {u[0]: 0 for u in UPGRADES}
        self.owned = [1]
        self.current = 1
        self.layouts = {1: {}}
        self.coverage = {1: 0.0}
        self.undo_stack = []
        self.dirty = True
        self.grids = {}
        self.net = None
        self.speed = None
        self.room_cov = []
        self.total_cov = 0.0
        self.avg_speed = 0.0
        self.admin = False      # admin mode: everything free, no metal limit, all unlocks (not saved)

    # ------------------------------------------------------------ helpers
    @property
    def plan(self):
        return project(self.current)

    @property
    def layout(self):
        return self.layouts.setdefault(self.current, {})

    def metal_limit(self, num=None):
        p = project(num or self.current)
        return p.metal + self.upgrades["material"]

    def metal_used(self, num=None):
        lay = self.layouts.get(num or self.current, {})
        return sum(BY_ID[pl["type"]].metal for pl in lay.values())

    def price(self, pid):
        if self.admin:
            return 0.0
        return price_at(BY_ID[pid], self.plan.pay)

    def unlocked(self, pid):
        return self.admin or len(self.owned) >= BY_ID[pid].unlock

    def metal_ok(self, extra):
        return self.admin or self.metal_used() + extra <= self.metal_limit() + 1e-9

    def can_afford(self, cost):
        return self.admin or self.money >= cost - 1e-9

    def income_mult(self):
        return 1.0 + 0.13 * self.upgrades["service"]

    def project_income(self, num):
        return project(num).pay * self.coverage.get(num, 0.0) * self.income_mult()

    def total_income(self):
        return sum(self.project_income(n) for n in self.owned)

    def grid(self):
        if self.current not in self.grids:
            self.grids[self.current] = RoomGrid(self.plan)
        return self.grids[self.current]

    # ------------------------------------------------------------ simulation
    def simulate(self):
        self.net = solve(self.plan, self.layout, self.upgrades["blower"], self.upgrades["liner"])
        g = self.grid()
        self.speed = g.compute(self.layout, self.net)
        self.total_cov, self.room_cov, self.avg_speed = g.coverage()
        self.coverage[self.current] = self.total_cov
        self.dirty = False

    def tick(self, dt):
        if self.dirty:
            self.simulate()
        self.money += self.total_income() * dt

    # ------------------------------------------------------------ actions
    def _snapshot(self):
        lay = {k: dict(v) for k, v in self.layout.items()}
        self.undo_stack.append((self.current, lay, self.money))
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)

    def can_place(self, pid, tile):
        p = self.plan
        x, y = tile
        if not (0 <= x < p.w and 0 <= y < p.h):
            return "Outside the house"
        if tuple(p.ahu) == tuple(tile):
            return "That's the air handler"
        if not self.unlocked(pid):
            return "Part is locked"
        old = self.layout.get(tuple(tile))
        refund_m = BY_ID[old["type"]].metal if old else 0.0
        refund_d = self.price(old["type"]) if old else 0.0
        if not self.metal_ok(BY_ID[pid].metal - refund_m):
            return f"Metal limit reached for this project ({self.metal_limit()})"
        if not self.can_afford(self.price(pid) - refund_d):
            return "Not enough money"
        return None

    def apply(self, action, record=True):
        """Apply one action dict. Raises ActionError with a user-facing reason."""
        kind = action["kind"]
        if kind == "place":
            tile = tuple(action["tile"])
            pid = action["type"]
            err = self.can_place(pid, tile)
            if err:
                raise ActionError(err)
            old = self.layout.get(tile)
            if old and old["type"] == pid and old["rot"] == action.get("rot", 0) \
                    and old.get("aim") == action.get("aim", old.get("aim")):
                return
            if record:
                self._snapshot()
            if old:
                self.money += self.price(old["type"])
            self.money -= self.price(pid)
            pdef = BY_ID[pid]
            rot = action.get("rot", 0) % 4
            pl = {"type": pid, "rot": rot}
            if pdef.kind == "terminal":
                pl["aim"] = action.get("aim", default_aim(pdef, rot)) % 8
            if pdef.kind == "damper":
                pl["damper"] = action.get("damper", 0)
            self.layout[tile] = pl
        elif kind == "remove":
            tiles = [tuple(t) for t in action["tiles"] if tuple(t) in self.layout]
            if not tiles:
                return
            if record:
                self._snapshot()
            for t in tiles:
                self.money += self.price(self.layout[t]["type"])
                del self.layout[t]
        elif kind == "paste":
            items = action["items"]  # list of (tile, placed)
            total_d = sum(self.price(pl["type"]) for _, pl in items)
            total_m = sum(BY_ID[pl["type"]].metal for _, pl in items)
            refund_d = sum(self.price(self.layout[tuple(t)]["type"]) for t, _ in items if tuple(t) in self.layout)
            refund_m = sum(BY_ID[self.layout[tuple(t)]["type"]].metal for t, _ in items if tuple(t) in self.layout)
            p = self.plan
            for t, pl in items:
                if not (0 <= t[0] < p.w and 0 <= t[1] < p.h) or tuple(t) == tuple(p.ahu):
                    raise ActionError("Paste doesn't fit there")
                if not self.unlocked(pl["type"]):
                    raise ActionError("Contains a locked part")
            if not self.metal_ok(total_m - refund_m):
                raise ActionError(f"Metal limit reached for this project ({self.metal_limit()})")
            if not self.can_afford(total_d - refund_d):
                raise ActionError("Not enough money")
            if record:
                self._snapshot()
            self.money += refund_d - total_d
            for t, pl in items:
                self.layout[tuple(t)] = dict(pl)
        elif kind == "aim":
            t = tuple(action["tile"])
            pl = self.layout.get(t)
            if not pl or BY_ID[pl["type"]].kind != "terminal":
                raise ActionError("Hover a register to aim it")
            pl["aim"] = (pl.get("aim", 0) + 2) % 8
        elif kind == "damper":
            t = tuple(action["tile"])
            pl = self.layout.get(t)
            if not pl or BY_ID[pl["type"]].kind != "damper":
                raise ActionError("Hover a volume damper to throttle it")
            pl["damper"] = (pl.get("damper", 0) + 1) % len(DAMPER_LEVELS)
        elif kind == "rotate_placed":
            t = tuple(action["tile"])
            pl = self.layout.get(t)
            if not pl:
                return
            if record:
                self._snapshot()
            pl["rot"] = (pl["rot"] + 1) % 4
            if "aim" in pl:
                pl["aim"] = (pl["aim"] + 2) % 8
        elif kind == "upgrade":
            uid = action["id"]
            lvl = self.upgrades[uid]
            if lvl >= UPG[uid][3]:
                raise ActionError("Already maxed")
            cost = 0.0 if self.admin else upgrade_cost(uid, lvl)
            if not self.can_afford(cost):
                raise ActionError("Not enough money")
            self.money -= cost
            self.upgrades[uid] = lvl + 1
        elif kind == "downgrade":
            uid = action["id"]
            lvl = self.upgrades[uid]
            if lvl <= 0:
                return
            if uid == "material" and not self.admin:
                for num in self.owned:
                    if self.metal_used(num) > project(num).metal + lvl - 1:
                        raise ActionError("A project is using that metal")
            self.upgrades[uid] = lvl - 1
            if not self.admin:
                self.money += upgrade_cost(uid, lvl - 1) * 0.5
        elif kind == "buy_project":
            num = action["num"]
            p = project(num)
            if num in self.owned:
                return
            if not p.playable:
                raise ActionError("This house isn't built yet")
            if num != max(self.owned) + 1 and not self.admin:
                raise ActionError("Finish the previous project first")
            cost = 0.0 if self.admin else p.buy
            if not self.can_afford(cost):
                raise ActionError("Not enough money")
            self.money -= cost
            self.owned.append(num)
            self.layouts.setdefault(num, {})
            self.coverage.setdefault(num, 0.0)
            self.current = num
        elif kind == "goto_project":
            num = action["num"]
            if num not in self.owned:
                raise ActionError("You don't own that project")
            self.current = num
        else:
            raise ActionError(f"Unknown action {kind}")
        self.dirty = True

    def undo(self):
        while self.undo_stack:
            num, lay, money = self.undo_stack.pop()
            if num != self.current:
                continue
            self.layouts[num] = lay
            self.money = money
            self.dirty = True
            return True
        return False

    # ------------------------------------------------------------ persistence
    def to_json(self):
        return {
            "version": C.VERSION,
            "saved_at": time.time(),
            "money": self.money,
            "upgrades": self.upgrades,
            "owned": self.owned,
            "current": self.current,
            "coverage": {str(k): v for k, v in self.coverage.items()},
            "layouts": {str(num): [[list(t), pl] for t, pl in lay.items()]
                        for num, lay in self.layouts.items()},
        }

    def save(self, path=None):
        path = path or C.save_path()
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.to_json(), fh)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path=None):
        path = path or C.save_path()
        g = cls()
        if not os.path.exists(path):
            return g
        try:
            with open(path) as fh:
                d = json.load(fh)
            g.money = float(d.get("money", g.money))
            for k, v in d.get("upgrades", {}).items():
                if k in g.upgrades:
                    g.upgrades[k] = int(v)
            g.owned = [int(n) for n in d.get("owned", [1])] or [1]
            g.current = int(d.get("current", 1))
            if g.current not in g.owned:
                g.current = g.owned[0]
            g.coverage = {int(k): float(v) for k, v in d.get("coverage", {}).items()}
            g.layouts = {}
            for num, items in d.get("layouts", {}).items():
                lay = {}
                for t, pl in items:
                    if pl.get("type") in BY_ID:
                        lay[tuple(t)] = pl
                g.layouts[int(num)] = lay
            for n in g.owned:
                g.layouts.setdefault(n, {})
        except Exception:
            return cls()
        return g

    def reset(self):
        self.__init__()
