"""The airflow rules, checked directly against the network model."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from airflow import config as C
from airflow.state import Game


def game():
    g = Game(); g.money = 1e9; g.owned = [1, 2, 3, 4]
    return g


def place(g, t, x, y, r=0, aim=None):
    a = {"kind": "place", "type": t, "tile": (x, y), "rot": r}
    if aim is not None:
        a["aim"] = aim
    g.apply(a)


def straight_run(g, with_cross):
    place(g, "galv", 1, 4)
    if with_cross:
        place(g, "cross", 2, 4); place(g, "cap", 2, 3, 3); place(g, "cap", 2, 5, 1)
    else:
        place(g, "galv", 2, 4)
    for x in range(3, 6):
        place(g, "galv", x, 4)
    place(g, "regboot", 6, 4, 0)
    g.simulate()
    return g.net


def main():
    # 1. a junction whose side arms go nowhere costs nothing extra
    a, b = straight_run(game(), False), straight_run(game(), True)
    assert abs(a.delivered - b.delivered) < 0.01, (a.delivered, b.delivered)

    # 2. every connected side of the unit gets its full airflow (not split)
    g = game()
    place(g, "galv", 1, 4); place(g, "regboot", 2, 4, 0)
    g.simulate(); n = g.net
    assert n.outlets == 1 and abs(n.part_flow[(1, 4)] - n.blower_free) < 1e-6
    place(g, "galv", 0, 3, 1); place(g, "regboot", 0, 2, 3)
    g.simulate(); n = g.net
    assert n.outlets == 2 and abs(n.ahu_flow - 2 * n.blower_free) < 1e-6
    assert abs(n.part_flow[(1, 4)] - n.blower_free) < 1e-6
    assert abs(n.part_flow[(0, 3)] - n.blower_free) < 1e-6

    # 3. a junction splits by how many outlets lie beyond each arm
    g = game()
    place(g, "galv", 1, 4); place(g, "galv", 2, 4); place(g, "cross", 3, 4)
    place(g, "diff4", 3, 3, 3); place(g, "diff4", 3, 5, 1)
    for x in range(4, 9):
        place(g, "galv", x, 4)
    place(g, "tee", 9, 4, 1); place(g, "angleboot", 9, 3, 3, aim=1); place(g, "angleboot", 9, 5, 1, aim=3)
    g.simulate(); n = g.net
    run, side = n.port_flow[((3, 4), 1)], n.port_flow[((3, 4), 0)]
    assert 1.9 < run / side < 2.3, (run, side)     # two outlets ahead vs one to each side
    cfms = [t.cfm for t in n.terminals]
    assert max(cfms) / min(cfms) < 1.15, cfms        # air reaches every register about equally

    # 4. air is lost travelling; fans win back 15% / 30% / 45% of what was lost before them
    for fan, share in (("booster", 0.15), ("booster2", 0.30), ("booster3", 0.45)):
        g = game()
        for x in range(1, 13):
            place(g, "galv", x, 4)
        place(g, "regboot", 13, 4, 0)
        g.simulate(); before = g.net.delivered
        lost_upstream = g.net.blower_free - g.net.part_flow[(6, 4)]
        place(g, fan, 6, 4, 0)
        g.simulate(); n = g.net
        assert n.delivered > before
        assert abs(n.boosted - share * lost_upstream) < 0.5, (fan, n.boosted, lost_upstream)
    from airflow.parts import BY_ID, price_at
    assert BY_ID["booster"].price < BY_ID["booster2"].price < BY_ID["booster3"].price

    # 5. open duct ends leak into the attic, but a junction's unused arm acts capped
    g = game()
    place(g, "galv", 1, 4); place(g, "tee", 2, 4, 0); place(g, "regboot", 3, 4, 0)
    g.simulate(); n = g.net
    assert n.leaked == 0 and not n.leaks and abs(n.delivered - straight_run(game(), False).delivered) < 30
    g = game()
    place(g, "galv", 1, 4); place(g, "tee", 2, 4, 0); place(g, "regboot", 3, 4, 0); place(g, "galv", 2, 5, 1)
    g.simulate(); n = g.net
    assert n.leaked > 50 and n.delivered > 50, (n.leaked, n.delivered)   # a duct stub off the arm does leak
    assert abs(n.blower_free - 290.0 * 0.87) < 1e-6           # Normal difficulty
    g.easy = True; g.simulate()
    assert abs(g.net.blower_free - 290.0) < 1e-6              # Easy: the full unit

    # 6. single-arrow registers are weaker than multi-way and premium diffusers
    def coverage(pid):
        g = game()
        for x in range(1, 4):
            place(g, "galv", x, 4)
        place(g, pid, 4, 4, 0)
        g.simulate()
        return g.room_cov[0], float(g.speed.max())
    reg, diff4, swirl = coverage("regboot"), coverage("diff4"), coverage("swirl")
    assert reg[0] < diff4[0] <= swirl[0], (reg, diff4, swirl)
    assert coverage("slot")[1] > diff4[1]
    # 7. volume damper: 10% steps, fully shut is allowed and sends the air elsewhere
    def damper_layout(open_frac):
        g = game()
        place(g, "galv", 1, 4); place(g, "tee", 2, 4, 1)       # ports N, S, W
        place(g, "damper", 2, 3, 1); place(g, "regboot", 2, 2, 3)
        place(g, "galv", 2, 5, 1); place(g, "regboot", 2, 6, 1)
        g.apply({"kind": "set_open", "tile": (2, 3), "port": None, "value": open_frac})
        g.simulate()
        n = g.net
        return n.part_flow[(2, 3)], n.part_flow[(2, 5)]
    full, other_full = damper_layout(1.0)
    half, other_half = damper_layout(0.5)
    shut, other_shut = damper_layout(0.0)
    assert abs(full - other_full) / full < 0.05
    assert shut == 0 and other_shut > other_half > other_full
    assert abs(half / (half + other_half) - 1 / 3) < 0.03          # 0.5 : 1 demand
    g = game(); place(g, "damper", 1, 4)
    seen = []
    for _ in range(11):
        g.apply({"kind": "damper", "tile": (1, 4)})
        seen.append(g.layout[(1, 4)]["open"])
    assert seen[:10] == [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0] and seen[10] == 1.0, seen

    # 8. dampered junctions: each exit has its own setting
    g = game()
    place(g, "galv", 1, 4); place(g, "galv", 2, 4); place(g, "cross_d", 3, 4)
    place(g, "regboot", 3, 3, 3); place(g, "regboot", 3, 5, 1); place(g, "galv", 4, 4); place(g, "regboot", 5, 4, 0)
    g.simulate(); n = g.net
    flows = [n.port_flow[((3, 4), d)] for d in (0, 1, 2)]
    turn = flows[0] / flows[1]               # side exits lose a little more than straight through
    assert 0.85 < turn < 1.0 and abs(flows[0] - flows[2]) < 1e-6, flows
    total_in = n.part_flow[(3, 4)]
    g.apply({"kind": "set_open", "tile": (3, 4), "port": 0, "value": 0.0})     # shut the north exit
    g.apply({"kind": "set_open", "tile": (3, 4), "port": 2, "value": 0.5})     # south half open
    g.simulate(); n = g.net
    north, east, south = (n.port_flow.get(((3, 4), d), 0.0) for d in (0, 1, 2))
    assert north == 0 and abs(south / east - 0.5 * turn) < 0.02, (north, east, south)
    assert abs(n.part_flow[(3, 4)] - total_in) < 1e-6 and east + south > sum(flows) * 0.97   # nothing wasted
    # rotating the part keeps each exit's setting with its own port
    g.apply({"kind": "rotate_placed", "tile": (3, 4)})
    assert g.layout[(3, 4)]["exits"] == {"0": 0.0, "2": 0.5}
    print("all flow tests passed")


if __name__ == "__main__":
    main()
