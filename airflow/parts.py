"""Duct part catalog.

Directions: 0=N, 1=E, 2=S, 3=W (screen up is north).
Every part is 1x1 tile. `ports` maps a direction (at rotation 0) to that
port's half loss coefficient K; a connection between two parts costs the sum
of both ports' K.

Terminal aim uses eighths: 0=N, 1=NE, 2=E ... 7=NW.
"""

from dataclasses import dataclass, field

N, E, S, W = 0, 1, 2, 3
DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]
EIGHTHS = [(0, -1), (0.7071, -0.7071), (1, 0), (0.7071, 0.7071),
           (0, 1), (-0.7071, 0.7071), (-1, 0), (-0.7071, -0.7071)]

REWARDS = 99  # unlock value for parts that come from the (not yet built) rewards track

CATEGORIES = ["STRAIGHT", "TURN", "INTERSECTION", "TRANSITION"]


@dataclass(frozen=True)
class PartDef:
    id: str
    name: str
    category: str
    price: float          # project-1 price; scales with project pay
    metal: float
    efficiency: int       # 1..5 bar on the card
    desc: str
    ports: dict           # dir (rot 0) -> half K
    kind: str = "duct"    # duct, cap, damper, booster, tee, tapered, terminal
    unlock: int = 1       # owned-project count needed
    # tee / tapered
    branch: int = -1      # branch port dir (rot 0)
    taper_from: int = -1  # tapered: inflow port that the taper faces
    # terminals
    sink_k: float = 0.0   # loss from register face into the room
    throws: tuple = ()    # throw dirs in eighths, relative to aim
    throw: float = 1.0    # throw length factor
    exit: float = 1.0     # face velocity factor
    wide: bool = False
    power: float = 1.0    # how hard a terminal blows into the room (4-way diffuser = 1.0)
    shape: str = ""       # drawing hint
    boost: float = 0.0    # inline fans: share of upstream losses won back
    base: str = ""        # dampered junctions: the junction they're built on (shape and physics)
    dampered: bool = False

    @property
    def shape_id(self):
        return self.base or self.id


def _p(**kw):
    return PartDef(**kw)


PARTS = [
    # ---------------- STRAIGHT ----------------
    _p(id="galv", name="Galvanized Duct", category="STRAIGHT", price=5, metal=1, efficiency=4,
       desc="Rigid sheet-metal run. Very low friction per tile.",
       ports={W: 0.015, E: 0.015}),
    _p(id="flex", name="Flex Duct", category="STRAIGHT", price=3.1, metal=0.5, efficiency=2,
       desc="Cheap, light insulated flex. Corrugated walls add ~4x the friction.",
       ports={W: 0.06, E: 0.06}, unlock=2, shape="flex"),
    _p(id="cap", name="End Cap", category="STRAIGHT", price=2, metal=0.5, efficiency=5,
       desc="Seals a duct end. Open ends dump air into the attic!",
       ports={W: 0.0}, kind="cap"),
    _p(id="damper", name="Volume Damper", category="STRAIGHT", price=20, metal=1.5, efficiency=3,
       desc="Restricts how much air passes, in 10% steps down to fully shut. Click it to set it, or press F.",
       ports={W: 0.075, E: 0.075}, kind="damper", unlock=2),
    _p(id="booster", name="Inline Booster Fan T1", category="STRAIGHT", price=48, metal=2, efficiency=3,
       desc="Wins back 15% of the air lost before it. Air flows the way the arrow points.",
       ports={W: 0.05, E: 0.05}, kind="booster", unlock=4, boost=0.15),
    _p(id="booster2", name="Inline Booster Fan T2", category="STRAIGHT", price=130, metal=2.5, efficiency=4,
       desc="A stronger fan: wins back 30% of the air lost before it. Air flows the way the arrows point.",
       ports={W: 0.05, E: 0.05}, kind="booster", unlock=4, boost=0.30),
    _p(id="booster3", name="Inline Booster Fan T3", category="STRAIGHT", price=300, metal=3, efficiency=5,
       desc="The strongest fan: wins back 45% of the air lost before it. Air flows the way the arrows point.",
       ports={W: 0.05, E: 0.05}, kind="booster", unlock=4, boost=0.45),

    # ---------------- TURN ----------------
    _p(id="elbow90", name="Sharp 90° Elbow", category="TURN", price=6, metal=1, efficiency=1,
       desc="Square mitered turn. Flow separates at the inner corner: high loss.",
       ports={W: 0.6, S: 0.6}, shape="sharp"),
    _p(id="elbow45", name="Two 45° Elbows", category="TURN", price=14, metal=1.5, efficiency=3,
       desc="Two gentle 45° bends. Much less separation than a sharp 90.",
       ports={W: 0.18, S: 0.18}, shape="chamfer"),
    _p(id="elbowlr", name="Long-Radius Elbow", category="TURN", price=28, metal=2, efficiency=4,
       desc="Smooth curved elbow. Efficient, even turn.",
       ports={W: 0.1, S: 0.1}, unlock=2, shape="round"),
    _p(id="elbowvaned", name="Vaned Elbow", category="TURN", price=40, metal=2, efficiency=4,
       desc="Square elbow with turning vanes that steer the air round the corner.",
       ports={W: 0.08, S: 0.08}, unlock=REWARDS, shape="vaned"),
    _p(id="elbowlrvaned", name="Long-Radius Vaned Elbow", category="TURN", price=70, metal=2.5, efficiency=5,
       desc="The smoothest turn money can buy.",
       ports={W: 0.04, S: 0.04}, unlock=REWARDS, shape="roundvaned"),

    # ---------------- INTERSECTION ----------------
    _p(id="tee", name="T-Branch", category="INTERSECTION", price=10, metal=2, efficiency=1,
       desc="Square tee. Air slams the far wall and tumbles into the branch.",
       ports={W: 0.1, E: 0.1, S: 1.0}, kind="tee", branch=S),
    _p(id="cross", name="4-Way Cross", category="INTERSECTION", price=22, metal=2.5, efficiency=2,
       desc="Compact 4-way split. Cheap for its reach, but very turbulent.",
       ports={N: 0.5, E: 0.5, S: 0.5, W: 0.5}, kind="tee"),
    _p(id="taperl", name="Tapered Branch (Left)", category="INTERSECTION", price=35, metal=2.5, efficiency=4,
       desc="45° takeoff with the taper on the left. Guides air into the branch; face the taper toward the incoming flow.",
       ports={W: 0.08, E: 0.1, S: 0.3}, kind="tapered", branch=S, taper_from=W),
    _p(id="taperr", name="Tapered Branch (Right)", category="INTERSECTION", price=35, metal=2.5, efficiency=4,
       desc="45° takeoff with the taper on the right. Guides air into the branch; face the taper toward the incoming flow.",
       ports={W: 0.1, E: 0.08, S: 0.3}, kind="tapered", branch=S, taper_from=E),
    _p(id="ybranch", name="Y-Branch", category="INTERSECTION", price=60, metal=3, efficiency=5,
       desc="Splits flow evenly into two smooth 45° legs.",
       ports={W: 0.06, N: 0.15, S: 0.15}, kind="tee", unlock=REWARDS),

    # dampered junctions: click one to set how open each exit is (filled in below)

    # ---------------- TRANSITION (terminals) ----------------
    _p(id="bareboot", name="Bare Boot", category="TRANSITION", price=0, metal=0.5, efficiency=1,
       desc="For the not-so bright individuals.",
       ports={W: 0.05}, kind="terminal", sink_k=0.6, throws=(0, 2, 4, 6), throw=0.3, exit=0.45,
       shape="boot", power=0.28),
    _p(id="regboot", name="Register Boot", category="TRANSITION", price=8, metal=1, efficiency=1,
       desc="Basic boot + 1-way register. Cheap, but it lets less air through and throws it short. Press T to aim.",
       ports={W: 0.05}, kind="terminal", sink_k=1.6, throws=(0,), throw=0.8, exit=1.0, power=0.6),
    _p(id="angleboot", name="Angled Register Boot", category="TRANSITION", price=12, metal=1, efficiency=2,
       desc="Boot whose register throws air at a 45° angle. Aim it into corners. Press T to aim.",
       ports={W: 0.05}, kind="terminal", sink_k=1.4, throws=(1,), throw=1.0, exit=1.0, power=0.65),
    _p(id="reg2", name="2-Way Register", category="TRANSITION", price=18, metal=1.5, efficiency=3,
       desc="Throws air in two opposite directions. Press T to aim.",
       ports={W: 0.05}, kind="terminal", sink_k=1.2, throws=(0, 4), throw=0.9, exit=1.0, unlock=2, power=0.85),
    _p(id="corner", name="Corner Diffuser", category="TRANSITION", price=26, metal=1.5, efficiency=3,
       desc="2-way diffuser with its exits 90° apart. Great tucked into a room corner. Press T to aim.",
       ports={W: 0.05}, kind="terminal", sink_k=1.2, throws=(0, 2), throw=0.95, exit=1.0, unlock=2, power=0.85),
    _p(id="diff4", name="4-Way Ceiling Diffuser", category="TRANSITION", price=30, metal=2, efficiency=3,
       desc="Square louvered diffuser. Spreads air evenly in all four directions.",
       ports={W: 0.05}, kind="terminal", sink_k=1.0, throws=(0, 2, 4, 6), throw=0.8, exit=0.9, power=1.0),
    _p(id="slot", name="Linear Slot Diffuser", category="TRANSITION", price=52, metal=2, efficiency=4,
       desc="Long narrow slot. Throws a wide, far-reaching sheet of air. Press T to aim.",
       ports={W: 0.05}, kind="terminal", sink_k=1.0, throws=(0,), throw=1.7, exit=1.0, wide=True,
       unlock=3, power=1.45),
    _p(id="swirl", name="Swirl Diffuser", category="TRANSITION", price=140, metal=2.5, efficiency=5,
       desc="Spins air out in every direction for fast, even mixing.",
       ports={W: 0.05}, kind="terminal", sink_k=0.9, throws=(0, 1, 2, 3, 4, 5, 6, 7), throw=0.85,
       exit=0.8, unlock=4, power=1.15),
]

def _dampered(base):
    b = next(p for p in PARTS if p.id == base)
    return PartDef(**{**b.__dict__, "id": base + "_d", "name": "Dampered " + b.name,
                      "price": round(b.price * 1.6 + 8, 1), "metal": b.metal + 0.5,
                      "desc": "Has a damper on every exit. Click it to set how open each exit is (0-100%).",
                      "unlock": max(b.unlock, 2), "base": base, "dampered": True})


_at = PARTS.index(next(p for p in PARTS if p.id == "ybranch")) + 1
PARTS[_at:_at] = [_dampered(b) for b in ("tee", "cross", "taperl", "taperr", "ybranch")]

BY_ID = {p.id: p for p in PARTS}


def by_category(cat):
    return [p for p in PARTS if p.category == cat]


def rot_dir(d, r):
    return (d + r) % 4


def abs_ports(pdef, rot):
    """Port dirs -> half K, after rotation."""
    return {rot_dir(d, rot): k for d, k in pdef.ports.items()}


def default_aim(pdef, rot):
    """Terminals throw away from their inlet by default (in eighths)."""
    inlet = rot_dir(next(iter(pdef.ports)), rot)
    return ((inlet + 2) % 4) * 2


def throw_dirs(pdef, aim):
    return [(aim + t) % 8 for t in pdef.throws]


DAMPER_LEVELS = [1.0, 0.7, 0.45, 0.25]   # pre-0.6 saves stored one of these as "damper"


def damper_open(pl):
    """How open a Volume Damper is, 0.0 (shut) .. 1.0 (open), in 10% steps."""
    if "open" in pl:
        return max(0.0, min(1.0, round(float(pl["open"]) * 10) / 10))
    return round(DAMPER_LEVELS[pl.get("damper", 0) % len(DAMPER_LEVELS)] * 10) / 10


def exit_open(pdef, pl, d_abs):
    """How open a dampered junction's exit (an absolute direction) is."""
    if not pdef.dampered:
        return 1.0
    d0 = (d_abs - pl.get("rot", 0)) % 4      # stored by the part's own (unrotated) port
    v = pl.get("exits", {}).get(str(d0), 1.0)
    return max(0.0, min(1.0, round(float(v) * 10) / 10))


def damper_k(level):
    f = DAMPER_LEVELS[level % len(DAMPER_LEVELS)]
    return 0.075 / (f * f)


def price_at(pdef, pay):
    """Price scales with project pay. Rounded half-up to whole dollars beyond P1."""
    raw = pdef.price * pay / 20.0
    if pay <= 20.0:
        return round(raw, 1)
    return float(int(raw + 0.5))


def fmt_price(v):
    if v <= 0:
        return "FREE"
    if v >= 1000:
        return fmt_money(v)
    if v >= 100:
        return f"${v:.0f}"
    return f"${v:.1f}"


def fmt_money(v):
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.2f}M"
    if v >= 1e4:
        return f"${v / 1e3:.1f}K"
    return f"${v:.0f}"
