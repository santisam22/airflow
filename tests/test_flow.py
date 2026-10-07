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

    # 2. the unit's full airflow goes out, split equally between connected sides
    g = game()
    place(g, "galv", 1, 4); place(g, "regboot", 2, 4, 0)
    g.simulate(); n = g.net
    assert n.outlets == 1 and abs(n.part_flow[(1, 4)] - n.blower_free) < 1e-6
    place(g, "galv", 0, 3, 1); place(g, "regboot", 0, 2, 3)
    g.simulate(); n = g.net
    assert n.outlets == 2
    assert abs(n.part_flow[(1, 4)] - n.blower_free / 2) < 1e-6
    assert abs(n.part_flow[(0, 3)] - n.blower_free / 2) < 1e-6

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

    # 4. air is lost travelling, and a fan wins back 15% of what was lost before it
    g = game()
    for x in range(1, 13):
        place(g, "galv", x, 4)
    place(g, "regboot", 13, 4, 0)
    g.simulate(); before = g.net.delivered
    lost_upstream = g.net.blower_free - g.net.part_flow[(6, 4)]
    place(g, "booster", 6, 4, 0)
    g.simulate(); n = g.net
    assert n.delivered > before
    assert abs(n.boosted - 0.15 * lost_upstream) < 0.5, (n.boosted, lost_upstream)

    # 5. open duct ends leak into the attic, but a junction's unused arm acts capped
    g = game()
    place(g, "galv", 1, 4); place(g, "tee", 2, 4, 0); place(g, "regboot", 3, 4, 0)
    g.simulate(); n = g.net
    assert n.leaked == 0 and not n.leaks and abs(n.delivered - straight_run(game(), False).delivered) < 30
    g = game()
    place(g, "galv", 1, 4); place(g, "tee", 2, 4, 0); place(g, "regboot", 3, 4, 0); place(g, "galv", 2, 5, 1)
    g.simulate(); n = g.net
    assert n.leaked > 50 and n.delivered > 50, (n.leaked, n.delivered)   # a duct stub off the arm does leak
    assert abs(n.blower_free - 290.0) < 1e-6

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
    print("all flow tests passed")


if __name__ == "__main__":
    main()
