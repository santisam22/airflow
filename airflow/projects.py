"""Project (house) definitions and floor plans.

Rooms are tile rectangles (x, y, w, h) that must tile the whole plan.
Doors open one tile edge of wall:
  ("v", x, y) -> the vertical wall line at x, between tiles (x-1, y) and (x, y)
  ("h", x, y) -> the horizontal wall line at y, between tiles (x, y-1) and (x, y)
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Plan:
    num: int
    name: str
    w: int
    h: int
    pay: float
    metal: int
    buy: float
    ahu: tuple
    rooms: list
    doors: list
    playable: bool = True
    floors: int = 1
    furniture: list = field(default_factory=list)
    tile_room: np.ndarray = None

    def __post_init__(self):
        if not self.playable:
            return
        tr = -np.ones((self.h, self.w), dtype=int)
        for i, (_, x, y, w, h) in enumerate(self.rooms):
            tr[y:y + h, x:x + w] = i
        assert (tr >= 0).all(), f"rooms do not tile plan {self.name}"
        self.tile_room = tr
        if not self.furniture:
            for name, x, y, w, h in self.rooms:
                self.furniture.extend(furnish(name, x, y, w, h))

    def room_at(self, tx, ty):
        if 0 <= tx < self.w and 0 <= ty < self.h:
            return int(self.tile_room[ty, tx])
        return -1

    @property
    def room_names(self):
        return [r[0] for r in self.rooms]

    def door_set(self):
        return {tuple(d) for d in self.doors}


def furnish(name, x, y, w, h):
    """Decorative furniture from a per-room template (fractions of the room)."""
    n = name.lower()
    out = []

    def add(label, fx, fy, fw, fh, shape="rect"):
        out.append((label, x + fx * w, y + fy * h, fw * w, fh * h, shape))

    if "living" in n:
        add("TV", 0.12, 0.03, 0.42, 0.07)
        add("COFFEE TABLE", 0.18, 0.55, 0.36, 0.14)
        add("SOFA", 0.12, 0.82, 0.5, 0.13)
        add("", 0.04, 0.9, 0.08, 0.07, "circle")
        add("", 0.7, 0.85, 0.07, 0.06, "circle")
    elif "kitchen" in n:
        add("COUNTER", 0.06, 0.04, 0.6, 0.12)
        add("FRIDGE", 0.8, 0.04, 0.14, 0.16)
        add("ISLAND", 0.25, 0.45, 0.4, 0.16)
    elif "dining" in n:
        add("DINING", 0.3, 0.35, 0.4, 0.3)
        add("", 0.42, 0.24, 0.16, 0.07, "chair")
        add("", 0.42, 0.69, 0.16, 0.07, "chair")
        add("", 0.22, 0.42, 0.06, 0.16, "chair")
        add("", 0.72, 0.42, 0.06, 0.16, "chair")
    elif "bath" in n:
        add("VANITY", 0.06, 0.06, 0.34, 0.16)
        add("TUB", 0.72, 0.06, 0.24, 0.84, "round")
        add("TOILET", 0.4, 0.74, 0.16, 0.22, "round")
    elif "office" in n:
        add("DESK", 0.15, 0.08, 0.6, 0.16)
        add("", 0.38, 0.3, 0.14, 0.12, "circle")
        add("SHELF", 0.82, 0.4, 0.12, 0.5)
    elif "bed" in n:
        add("BED", 0.25, 0.08, 0.5, 0.62)
        add("", 0.1, 0.08, 0.1, 0.1, "circle")
        add("", 0.8, 0.08, 0.1, 0.1, "circle")
        add("DRESSER", 0.86, 0.3, 0.1, 0.45)
    elif "hall" in n:
        add("", 0.02, 0.2, 0.03, 0.6, "circle")
    return out


PROJECTS = [
    Plan(1, "Starter Cottage", 14, 9, pay=20, metal=32, buy=0, ahu=(0, 4),
         rooms=[("Living Room", 0, 0, 8, 9), ("Bedroom", 8, 0, 6, 5), ("Bathroom", 8, 5, 6, 4)],
         doors=[("v", 8, 2), ("v", 8, 7)]),
    Plan(2, "Suburban Ranch", 18, 11, pay=65, metal=50, buy=1250, ahu=(7, 4),
         rooms=[("Living Room", 0, 0, 7, 5), ("Master Bedroom", 7, 0, 11, 5), ("Kitchen", 0, 5, 7, 6),
                ("Bedroom", 7, 5, 6, 6), ("Bathroom", 13, 5, 5, 6)],
         doors=[("v", 7, 2), ("h", 3, 5), ("h", 10, 5), ("v", 13, 8), ("v", 7, 8)]),
    Plan(3, "Hillside Bungalow", 20, 12, pay=140, metal=72, buy=12500, ahu=(12, 5),
         rooms=[("Living Room", 0, 0, 7, 6), ("Dining", 7, 0, 6, 5), ("Kitchen", 13, 0, 7, 5),
                ("Hallway", 7, 5, 13, 2), ("Bedroom", 0, 6, 7, 6), ("Bathroom", 7, 7, 4, 5),
                ("Bedroom 2", 11, 7, 5, 5), ("Office", 16, 7, 4, 5)],
         doors=[("v", 7, 5), ("v", 7, 2), ("v", 13, 2), ("h", 9, 5), ("h", 16, 5), ("v", 7, 6),
                ("h", 8, 7), ("h", 13, 7), ("h", 18, 7)]),
    Plan(4, "Family Home", 24, 14, pay=225, metal=80, buy=60000, ahu=(9, 7),
         rooms=[("Living Room", 0, 0, 9, 7), ("Kitchen", 9, 0, 7, 7), ("Dining", 16, 0, 8, 7),
                ("Hallway", 0, 7, 24, 2), ("Master Bedroom", 0, 9, 8, 5), ("Bathroom", 8, 9, 4, 5),
                ("Bedroom 2", 12, 9, 6, 5), ("Bedroom 3", 18, 9, 6, 5)],
         doors=[("v", 9, 3), ("v", 16, 3), ("h", 4, 7), ("h", 12, 7), ("h", 20, 7), ("h", 4, 9),
                ("h", 10, 9), ("h", 15, 9), ("h", 21, 9)]),
    # Listed in the original; floor plans not built yet.
    Plan(5, "Lakeside Villa", 28, 16, pay=325, metal=113, buy=0, ahu=(0, 0), rooms=[], doors=[],
         playable=False),
    Plan(6, "Two-Story Colonial", 22, 12, pay=415, metal=120, buy=0, ahu=(0, 0), rooms=[], doors=[],
         playable=False, floors=2),
    Plan(7, "Maple Grove Farmhouse", 26, 14, pay=500, metal=160, buy=0, ahu=(0, 0), rooms=[], doors=[],
         playable=False, floors=2),
    Plan(8, "Hillcrest Manor", 30, 16, pay=590, metal=220, buy=0, ahu=(0, 0), rooms=[], doors=[],
         playable=False, floors=2),
    Plan(9, "Harbor Brownstone", 32, 17, pay=675, metal=300, buy=0, ahu=(0, 0), rooms=[], doors=[],
         playable=False, floors=3),
]

ROOM_COUNTS = {5: 11, 6: 11, 7: 15, 8: 18, 9: 23}


def project(num):
    return PROJECTS[num - 1]


def room_count(p):
    return len(p.rooms) if p.playable else ROOM_COUNTS.get(p.num, 0)
