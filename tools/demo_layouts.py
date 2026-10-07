"""Reference layouts used by tests and snapshots."""


def _placer(g):
    def place(t, x, y, rot=0, aim=None):
        a = {"kind": "place", "type": t, "tile": (x, y), "rot": rot}
        if aim is not None:
            a["aim"] = aim
        g.apply(a)
    return place


def p1_demo(g):
    place = _placer(g)
    place("tee", 1, 4, 0)
    for x in range(2, 6):
        place("galv", x, 4)
    place("tee", 6, 4, 2)
    place("galv", 6, 3, 1)
    place("galv", 6, 2, 1)
    place("elbow90", 6, 1, 3)
    for x in (7, 8, 9):
        place("galv", x, 1)
    place("regboot", 10, 1, 0)
    place("elbow90", 7, 4, 0)
    place("galv", 7, 5, 1)
    place("galv", 7, 6, 1)
    place("elbow90", 7, 7, 2)
    place("galv", 8, 7)
    place("galv", 9, 7)
    place("regboot", 10, 7, 0)
    place("galv", 1, 5, 1)
    place("galv", 1, 6, 1)
    place("elbow90", 1, 7, 2)
    place("galv", 2, 7)
    place("galv", 3, 7)
    place("regboot", 4, 7, 0)


def p2_demo(g):
    place = _placer(g)
    place("tee", 6, 4, 0)
    place("galv", 5, 4)
    place("galv", 4, 4)
    place("diff4", 3, 4, 2)
    for y in (5, 6, 7):
        place("galv", 6, y, 1)
    place("regboot", 6, 8, 1, aim=6)
    place("tee", 8, 4, 0)
    for x in (9, 10, 11):
        place("galv", x, 4)
    place("diff4", 12, 4, 0)
    place("galv", 8, 5, 1)
    place("galv", 8, 6, 1)
    place("elbow90", 8, 7, 2)
    place("galv", 9, 7)
    place("tee", 10, 7, 0)
    place("angleboot", 10, 8, 1)
    for x in (11, 12, 13, 14):
        place("galv", x, 7)
    place("corner", 15, 7, 0, aim=0)
