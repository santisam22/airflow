"""Duct network solver.

The duct layout becomes a graph:
  * one node per placed part, plus the AHU node
  * an edge for every pair of facing ports (resistance from both ports' K)
  * sink edges to ground (pressure 0) for registers (into a room) and open
    duct ends (into the attic)
  * the blower: a fixed shutoff pressure PMAX behind a fan resistance chosen so
    that, with nothing attached, it would move its free-air CFM.

Every edge has a quadratic loss dP = R * Q * |Q|. We solve by repeatedly
linearising (g = 1 / (R |Q|)) and solving the resulting nodal pressure system.
"""

from dataclasses import dataclass, field

import numpy as np

from . import config as C
from .parts import BY_ID, DIRS, abs_ports, damper_k, rot_dir


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
    static_pct: float = 0.0
    part_flow: dict = field(default_factory=dict)     # tile -> CFM through
    part_k: dict = field(default_factory=dict)        # tile -> total K
    connected: set = field(default_factory=set)       # tiles reachable from AHU
    leaks: list = field(default_factory=list)
    terminals: list = field(default_factory=list)
    room_cfm: dict = field(default_factory=dict)
    open_ports: dict = field(default_factory=dict)    # tile -> list of open dirs


def solve(plan, layout, blower_level=0, liner_level=0):
    """layout: dict (x, y) -> placed dict {type, rot, aim, damper}."""
    res = Result()
    q_free = C.BASE_FREE_CFM * (1.0 + 0.10 * blower_level)
    res.blower_free = q_free
    friction = max(0.05, 1.0 - 0.05 * liner_level)
    ahu = tuple(plan.ahu)

    tiles = [ahu] + [t for t in layout.keys() if t != ahu]
    index = {t: i for i, t in enumerate(tiles)}
    n = len(tiles)

    def ports_of(t):
        if t == ahu:
            return {d: C.AHU_PORT_K for d in range(4)}
        pl = layout[t]
        pdef = BY_ID[pl["type"]]
        ports = abs_ports(pdef, pl["rot"])
        if pdef.kind == "damper":
            k = damper_k(pl.get("damper", 0))
            ports = {d: k for d in ports}
        return ports

    port_map = {t: ports_of(t) for t in tiles}

    # --- build edges -----------------------------------------------------
    edges = []   # [a, b, dir_from_a, dir_from_b]
    sinks = []   # [node, K, kind, payload]
    adj = {i: [] for i in range(n)}
    for t in tiles:
        ports = port_map[t]
        pl = layout.get(t)
        pdef = BY_ID[pl["type"]] if pl else None
        for d in ports:
            dx, dy = DIRS[d]
            nb = (t[0] + dx, t[1] + dy)
            opp = (d + 2) % 4
            if nb in port_map and opp in port_map[nb]:
                if index[t] < index[nb]:
                    edges.append([index[t], index[nb], d, opp])
                    adj[index[t]].append(index[nb])
                    adj[index[nb]].append(index[t])
            elif t == ahu:
                continue  # unused AHU outlets are closed
            elif pdef is not None and pdef.kind == "cap":
                continue  # a cap seals itself
            else:
                sinks.append([index[t], C.OPEN_END_K, "leak", Leak(t, d)])
                res.open_ports.setdefault(t, []).append(d)
        if pdef is not None and pdef.kind == "terminal":
            room = plan.room_at(*t)
            sinks.append([index[t], pdef.sink_k, "room", Terminal(t, room)])

    # reachability from AHU
    seen = {0}
    stack = [0]
    while stack:
        i = stack.pop()
        for j in adj[i]:
            if j not in seen:
                seen.add(j)
                stack.append(j)
    res.connected = {tiles[i] for i in seen}

    # --- static per-port K, tapered branches adjust per iteration ---------
    def port_k(t, d, inflow_dir):
        k = port_map[t][d]
        pl = layout.get(t)
        if pl is None:
            return k
        pdef = BY_ID[pl["type"]]
        if pdef.kind == "tapered" and inflow_dir is not None:
            branch = rot_dir(pdef.branch, pl["rot"])
            taper = rot_dir(pdef.taper_from, pl["rot"])
            if d == branch and inflow_dir != taper:
                k = 1.2   # taper facing the wrong way: behaves like a bad tee
        return k

    gains = np.zeros(len(edges))
    for ei, (a, b, da, db) in enumerate(edges):
        # booster: air pushed out of its E port (rot applied); gain on edges
        for node, dnode, sign in ((a, da, -1.0), (b, db, 1.0)):
            t = tiles[node]
            pl = layout.get(t)
            if pl and BY_ID[pl["type"]].kind == "booster":
                out_dir = rot_dir(1, pl["rot"])
                # Q_ab = g (Pa - Pb + G); positive G pushes a -> b
                if dnode == out_dir:
                    gains[ei] += C.BOOSTER_GAIN * 0.5 * (-sign)
                else:
                    gains[ei] += C.BOOSTER_GAIN * 0.5 * sign

    inflow = {}  # node -> dir of largest inflow
    r_fan = C.PMAX / (q_free * q_free)

    def edge_r():
        r = np.empty(len(edges))
        for ei, (a, b, da, db) in enumerate(edges):
            ka = port_k(tiles[a], da, inflow.get(a))
            kb = port_k(tiles[b], db, inflow.get(b))
            r[ei] = C.KSCALE * friction * max(ka + kb, 0.01)
        return r

    sink_r = np.array([C.KSCALE * friction * max(s[1], 0.01) for s in sinks]) if sinks else np.zeros(0)

    q_e = np.full(len(edges), 30.0)
    q_s = np.full(len(sinks), 30.0)
    q_src = 30.0
    P = np.zeros(n)
    flows_e = np.zeros(len(edges))
    flows_s = np.zeros(len(sinks))
    flow_src = 0.0

    for it in range(70):
        r_e = edge_r()
        g_e = 1.0 / (r_e * np.maximum(q_e, 0.05))
        g_s = 1.0 / (sink_r * np.maximum(q_s, 0.05)) if len(sinks) else g_s_empty()
        g_src = 1.0 / (r_fan * max(q_src, 0.05))

        A = np.zeros((n, n))
        bvec = np.zeros(n)
        for ei, (a, b, _, _) in enumerate(edges):
            g = g_e[ei]
            A[a, a] += g
            A[b, b] += g
            A[a, b] -= g
            A[b, a] -= g
            bvec[a] -= g * gains[ei]
            bvec[b] += g * gains[ei]
        for si, s in enumerate(sinks):
            A[s[0], s[0]] += g_s[si]
        A[0, 0] += g_src
        bvec[0] += g_src * C.PMAX
        A[np.diag_indices(n)] += 1e-9
        P = np.linalg.solve(A, bvec)

        flows_e = np.array([g_e[ei] * (P[a] - P[b] + gains[ei]) for ei, (a, b, _, _) in enumerate(edges)])
        flows_s = np.array([g_s[si] * P[s[0]] for si, s in enumerate(sinks)])
        flow_src = g_src * (C.PMAX - P[0])

        new_e = np.abs(flows_e)
        new_s = np.abs(flows_s)
        delta = abs(abs(flow_src) - q_src)
        q_e = 0.5 * q_e + 0.5 * new_e
        q_s = 0.5 * q_s + 0.5 * new_s
        q_src = 0.5 * q_src + 0.5 * abs(flow_src)

        # largest inflow per node (for tapered branches)
        best = {}
        for ei, (a, b, da, db) in enumerate(edges):
            f = flows_e[ei]
            if f > 0:   # a -> b, enters b through db
                if f > best.get(b, (0, None))[0]:
                    best[b] = (f, db)
            elif f < 0:
                if -f > best.get(a, (0, None))[0]:
                    best[a] = (-f, da)
        inflow = {k: v[1] for k, v in best.items()}
        if it > 20 and delta < 0.01:
            break

    # --- results ----------------------------------------------------------
    through = np.zeros(n)
    for ei, (a, b, _, _) in enumerate(edges):
        through[a] += abs(flows_e[ei])
        through[b] += abs(flows_e[ei])
    for si, s in enumerate(sinks):
        through[s[0]] += abs(flows_s[si])
    through[0] += abs(flow_src)
    through *= 0.5

    for i, t in enumerate(tiles):
        res.part_flow[t] = float(through[i])
        res.part_k[t] = float(sum(port_map[t].values()))
    res.part_flow[ahu] = float(abs(flow_src))
    for si, s in enumerate(sinks):
        f = max(0.0, float(flows_s[si]))
        if s[2] == "leak":
            s[3].cfm = f
            res.leaked += f
            res.leaks.append(s[3])
        else:
            s[3].cfm = f
            res.delivered += f
            res.terminals.append(s[3])
            res.room_cfm[s[3].room] = res.room_cfm.get(s[3].room, 0.0) + f
            pl = layout[s[3].tile]
            res.part_k[s[3].tile] += BY_ID[pl["type"]].sink_k
    res.ahu_flow = float(abs(flow_src))
    res.static_pct = float(max(0.0, P[0]) / C.PMAX * 100.0)
    return res


def g_s_empty():
    return np.zeros(0)
