"""Duct network: where the air goes.

Air is treated like water poured into the ducts, not like a pressure system:

* Every side of the air handler that has a duct leading somewhere gets the
  unit's full airflow (since 0.6: sides aren't split, so more sides = more air).
* Inside the ducts, air is shared out by destination. Every outlet (a register,
  or an open end dumping into the attic) wants an equal share, so at each
  junction the flow divides in proportion to how many outlets lie beyond each
  arm. An arm that leads nowhere (capped, or a dead end) takes nothing, so a
  junction costs nothing unless air actually goes through it. A volume damper
  (or a dampered junction's exit) set to x% open shrinks that branch's share to
  x%; at 0% it's shut, and the rest goes elsewhere.
* Open ends leak into the attic, except the unused arms of a junction (tee,
  cross, tapered or Y-branch): those count as capped.
* Travel costs a little: every tile loses a small fraction to friction, and
  each fitting loses more for the path the air takes through it (straight
  through a tee is cheap, turning into its branch is not). Losses come from the
  parts' loss coefficients K.
* An inline booster fan, pushing the way its arrow points, puts back part of
  the air lost upstream of it: 15% (T1), 30% (T2) or 45% (T3).

If ducts form a loop, air follows the shortest route from the air handler and
the closing link carries nothing.
"""

import math
from collections import deque
from dataclasses import dataclass, field

from . import config as C
from .parts import BY_ID, DIRS, abs_ports, damper_open, exit_open, rot_dir

# per-port K for square junctions, by where the air goes relative to where it came in:
# (straight through, 90-degree side branch, either outlet when fed into the side).
# Straight through costs the same as a plain galvanized duct.
STRAIGHT_K = 0.015
JUNCTION_K = {
    "tee": (STRAIGHT_K, 1.0, 0.75),
    "cross": (STRAIGHT_K, 1.15, 0.9),
}

JUNCTION_KINDS = ("tee", "tapered")   # T-Branch, 4-Way Cross, Y-Branch, Tapered Branches

LOSS_PER_K = 0.06        # fraction lost per unit of loss coefficient along a path
TRAVEL_LOSS = 0.006      # fraction lost per tile travelled (x4 in flex duct)


@dataclass
class Leak:
    tile: tuple
    dir: int
    cfm: float = 0.0


@dataclass
class Terminal:
    tile: tuple
    room: int
    cfm: float = 0.0


@dataclass
class Result:
    blower_free: float = 0.0
    ahu_flow: float = 0.0
    delivered: float = 0.0
    leaked: float = 0.0
    lost: float = 0.0
    boosted: float = 0.0
    static_pct: float = 0.0       # share of the blower's air lost along the way (%)
    outlets: int = 0              # sides of the air handler in use
    part_flow: dict = field(default_factory=dict)     # tile -> CFM through
    part_k: dict = field(default_factory=dict)        # tile -> total K
    connected: set = field(default_factory=set)       # tiles reachable from AHU
    leaks: list = field(default_factory=list)
    terminals: list = field(default_factory=list)
    room_cfm: dict = field(default_factory=dict)
    open_ports: dict = field(default_factory=dict)    # tile -> list of open dirs
    port_flow: dict = field(default_factory=dict)     # (tile, dir) -> CFM through that port
    tree: dict = field(default_factory=dict)          # tile -> [(child tile, out dir, CFM)] for particles
    inflow: dict = field(default_factory=dict)        # tile -> port the air comes in through


def _port_k(pdef, pl, d, inflow):
    """Half loss coefficient of port d of a placed part, given where air came in."""
    ports = abs_ports(pdef, pl["rot"])
    k = ports.get(d, 0.0)
    if inflow is None:
        return k
    if pdef.kind == "booster":
        return STRAIGHT_K
    if pdef.kind == "tapered":
        branch = rot_dir(pdef.branch, pl["rot"])
        taper = rot_dir(pdef.taper_from, pl["rot"])
        if d == branch and inflow != taper:
            k = 1.2   # taper facing the wrong way: behaves like a bad tee
    elif pdef.shape_id in JUNCTION_K:
        run_k, branch_k, bull_k = JUNCTION_K[pdef.shape_id]
        if d == inflow:
            k = STRAIGHT_K
        elif d == (inflow + 2) % 4:
            k = run_k
        elif (inflow + 2) % 4 in ports:
            k = branch_k
        else:
            k = bull_k    # fed into the side of a tee: both outlets are turns
    return k


def solve(plan, layout, blower_level=0, liner_level=0):
    """layout: dict (x, y) -> placed dict {type, rot, aim, damper}."""
    res = Result()
    q_free = C.BASE_FREE_CFM * (1.0 + 0.10 * blower_level)
    res.blower_free = q_free
    friction = max(0.05, 1.0 - 0.05 * liner_level)
    ahu = tuple(plan.ahu)

    def ports(t):
        if t == ahu:
            return set(range(4))
        pl = layout[t]
        return set(abs_ports(BY_ID[pl["type"]], pl["rot"]).keys())

    def neighbour(t, d):
        nb = (t[0] + DIRS[d][0], t[1] + DIRS[d][1])
        if nb in layout or nb == ahu:
            if (d + 2) % 4 in ports(nb):
                return nb
        return None

    # --- shortest-route tree from the air handler -----------------------
    parent = {ahu: None}
    inflow = {ahu: None}            # port the air enters each part through
    children = {ahu: []}            # tile -> [(out dir, child)]
    order = [ahu]
    q = deque([ahu])
    while q:
        t = q.popleft()
        for d in sorted(ports(t)):
            if d == inflow[t]:
                continue
            nb = neighbour(t, d)
            if nb is None or nb in parent:
                continue
            parent[nb] = t
            inflow[nb] = (d + 2) % 4
            children[nb] = []
            children[t].append((d, nb))
            order.append(nb)
            q.append(nb)
    res.connected = set(parent)
    res.inflow = dict(inflow)

    # --- outlets: registers and open ends ------------------------------
    sinks = {t: [] for t in parent}   # tile -> [("room", None) | ("leak", dir)]
    for t in parent:
        if t == ahu:
            continue
        pl = layout[t]
        pdef = BY_ID[pl["type"]]
        if pdef.kind == "terminal":
            sinks[t].append(("room", None))
        if pdef.kind == "cap" or pdef.kind in JUNCTION_KINDS:
            continue    # an unused arm on a junction is treated as capped
        for d in ports(t):
            if d == inflow[t] or neighbour(t, d) is not None:
                continue
            if any(c_d == d for c_d, _ in children[t]):
                continue
            sinks[t].append(("leak", d))
            res.open_ports.setdefault(t, []).append(d)
    # open ends on parts not reachable from the AHU are still drawn as open
    for t, pl in layout.items():
        if t in parent:
            continue
        for d in ports(t):
            if neighbour(t, d) is None and BY_ID[pl["type"]].kind not in ("cap",) + JUNCTION_KINDS:
                res.open_ports.setdefault(t, []).append(d)

    # --- demand: how many outlets lie beyond each part (dampers shrink it)
    weight = {}

    def arm(t, d, c):
        """Demand down the arm leaving t through port d, after that exit's damper."""
        if t == ahu:
            return weight[c]
        pl = layout[t]
        return weight[c] * exit_open(BY_ID[pl["type"]], pl, d)

    for t in reversed(order):
        w = float(len(sinks[t])) + sum(arm(t, d, c) for d, c in children[t])
        if t != ahu and BY_ID[layout[t]["type"]].kind == "damper":
            w *= damper_open(layout[t])
        weight[t] = w

    def path_loss(t, d_out):
        """Fraction lost carrying air across part t from its inlet to port d_out (None = into its own outlet)."""
        if t == ahu:
            return 0.0
        pl = layout[t]
        pdef = BY_ID[pl["type"]]
        k_in = _port_k(pdef, pl, inflow[t], inflow[t])
        if pdef.kind == "terminal":
            k_out = pdef.sink_k
        elif d_out is None:
            k_out = 0.0
        else:
            k_out = _port_k(pdef, pl, d_out, inflow[t])
        travel = TRAVEL_LOSS * (4.0 if pdef.id == "flex" else 1.0)
        return 1.0 - math.exp(-(LOSS_PER_K * (k_in + k_out) + travel) * friction)

    # --- pour the air in -----------------------------------------------
    live_sides = [(d, c) for d, c in children[ahu] if weight[c] > 0]
    res.outlets = len(live_sides)
    flow_in = {t: 0.0 for t in parent}
    lost_in = {t: 0.0 for t in parent}
    if live_sides:
        for d, c in live_sides:              # every live side gets the full airflow
            flow_in[c] = q_free
            res.port_flow[(ahu, d)] = q_free
        res.ahu_flow = q_free * len(live_sides)
    res.part_flow[ahu] = res.ahu_flow
    res.tree[ahu] = [(c, d, flow_in[c]) for d, c in live_sides]

    for t in order:
        if t == ahu:
            continue
        qin, lost = flow_in[t], lost_in[t]
        pl = layout[t]
        pdef = BY_ID[pl["type"]]
        if pdef.kind == "booster" and qin > 0:
            if inflow[t] == rot_dir(3, pl["rot"]):          # air enters behind the fan
                gain = pdef.boost * lost
                qin += gain
                lost -= gain
                res.boosted += gain
        res.part_flow[t] = qin
        res.port_flow[(t, inflow[t])] = qin
        res.tree[t] = []
        w_total = len(sinks[t]) + sum(arm(t, d, c) for d, c in children[t])
        if qin <= 0 or w_total <= 0:
            continue
        for kind, d in sinks[t]:
            part = qin / w_total
            loss = path_loss(t, d if kind == "leak" else None)
            out = part * (1.0 - loss)
            res.lost += part * loss
            if kind == "leak":
                res.leaks.append(Leak(t, d, out))
                res.leaked += out
                res.port_flow[(t, d)] = out
            else:
                room = plan.room_at(*t)
                res.terminals.append(Terminal(t, room, out))
                res.delivered += out
                res.room_cfm[room] = res.room_cfm.get(room, 0.0) + out
        for d, c in children[t]:
            a = arm(t, d, c)
            if a <= 0:
                continue
            frac = a / w_total
            part = qin * frac
            loss = path_loss(t, d)
            out = part * (1.0 - loss)
            res.lost += part * loss
            flow_in[c] = out
            lost_in[c] = lost * frac + part * loss
            res.port_flow[(t, d)] = out
            res.tree[t].append((c, d, out))

    # terminals that get nothing still exist for the stats/tooltips
    seen = {term.tile for term in res.terminals}
    for t, pl in layout.items():
        if BY_ID[pl["type"]].kind == "terminal" and t not in seen:
            res.terminals.append(Terminal(t, plan.room_at(*t), 0.0))
    for t, pl in layout.items():
        pdef = BY_ID[pl["type"]]
        res.part_k[t] = float(sum(abs_ports(pdef, pl["rot"]).values())) + \
            (pdef.sink_k if pdef.kind == "terminal" else 0.0)
        res.part_flow.setdefault(t, 0.0)
    res.static_pct = 100.0 * res.lost / res.ahu_flow if res.ahu_flow else 0.0
    return res
