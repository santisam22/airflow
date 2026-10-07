# Airflow Game — Design Spec (v0.1)

Reference: DUCTWORKS (Roblox), studied from ItzVexo's 11-minute guide video.
Scope: **airflow/duct-building game only**. No music player, no coffee/hangout features, no multiplayer.
Everything below was read off the video's UI unless marked *(inferred)*, meaning it's my best guess at hidden behavior.

---

## 1. Core loop

1. You get a **project**: a top-down 2D floor plan of a house with rooms, walls and furniture, plus a fixed **Air Handler (AHU)**.
2. In **Build Mode**, place duct parts on a tile grid to route air from the AHU into the rooms.
3. Air is simulated live. Ducts are colored by air velocity, and a heatmap spreads through rooms from each register.
4. Each room gets an **air coverage %**. Project coverage is the overall %.
5. A project **pays $/s × coverage** (e.g. 60% of $20/s pays $11.9/s). Income from every project you own stacks passively.
6. Spend money on **upgrades** and on **buying the next project** (bigger house, more rooms, more metal, higher pay).

Constraint: each project has a **metal limit**. Every part costs money *and* metal, so the puzzle is getting the best coverage within the metal budget.

---

## 2. Screen layout

| Area | Contents |
|---|---|
| Top-left | Game title, "PROJECT 1 • STARTER COTTAGE • 3 rooms", **EXIT BUILD MODE (B)** button |
| Top-right stat bar | **MONEY** `$1127` · **INCOME (ALL PROJECTS)** `+$11.9/s` · **AIR COVERAGE** `60%` (with bar) · **DELIVERED AIR** `385 CFM` · **METAL USED** `31.5 / 32` (bar turns red near the limit) |
| Top-right tabs | **STATS · UPGRADES · PROJECTS · APPEARANCE**. Each opens a right-side panel. |
| Left edge | Vertical **velocity legend**: "VELOCITY MAGNITUDE (m/s)", 0.00 → 2.00, plus "AVG SPEED 0.09 m/s" with a marker on the scale |
| Center | Floor plan on a faint tile grid. Room labels show name + coverage % (e.g. "BEDROOM 53%"). |
| Bottom | Part palette: category tabs **STRAIGHT / TURN / INTERSECTION / TRANSITION**, part cards, and **ROTATE (R) / REMOVE (X) / DESELECT (RMB)** buttons |
| Bottom strip | Key hints (see §8) |

### Velocity color scale
A jet-style colormap (blue → cyan → green → yellow → orange → red) on a **non-linear** axis. The tick labels are 0, 0.03, 0.11, 0.22, 0.38, 0.57, 0.75, 1.0, 1.3, 1.7, 2.0 m/s, which fits roughly `v = 2.0 × t²` (t = 0..1 position on the bar). The same colormap is used for duct fill and the room heatmap.

---

## 3. Parts catalog

Each card shows: name, $ cost, metal cost, **EFFICIENCY** (1–5 segment bar), and a one-line description.
Prices **scale per project**: Project 2 prices are ≈ **3.25×** Project 1 (e.g. Galvanized $5 → $16, Register Boot $8 → $26). Metal costs don't change.

### STRAIGHT
| Part | P1 $ | P2 $ | Metal | Eff. | Description / behavior |
|---|---|---|---|---|---|
| Galvanized Duct | 5 | 16 | 1 | 4/5 | Rigid sheet-metal run. Very low friction per tile. K = 0.03 per tile. |
| Flex Duct | — | 10 | 0.5 | 2/5 | Cheap, light insulated flex. Corrugated walls add ~4× the friction. *(unlocks P2)* |
| End Cap | 2 | 7 | 0.5 | 5/5 | Seals a duct end. Open ends dump air into the attic! |
| Volume Damper | — | 65 | 1.5 | 3/5 | Restricts how much air passes. Press F (or click with no part selected) to throttle a branch. *(unlocks P2)* |
| Inline Booster Fan | — | ? | ? | ? | *(unlocks P4)*. Adds pressure mid-run *(inferred)*. |

### TURN
| Part | P1 $ | P2 $ | Metal | Eff. | Description |
|---|---|---|---|---|---|
| Sharp 90° Elbow | 6 | ~20 | 1 | 1/5 | Square mitered turn. Flow separates at the inner corner: high loss. |
| Two 45° Elbows | 14 | ~46 | 1.5 | 3/5 | Two gentle 45° bends. Much less separation than a sharp 90. (Takes a diagonal footprint.) |
| Long-Radius Elbow | — | 91 | 2 | 4/5 | Smooth curved elbow. Efficient, even turn. *(unlocks P2)* |
| Vaned Elbow | — | ? | ? | ? | *(locked: firm rewards track)* |
| Long-Radius Vaned Elbow | — | ? | ? | ? | *(locked: firm rewards track)* |

### INTERSECTION
| Part | P1 $ | P2 $ | Metal | Eff. | Description |
|---|---|---|---|---|---|
| T-Branch | 10 | 33 | 2 | 1/5 | Square tee. Air slams the far wall and tumbles into the branch. |
| 4-Way Cross | — | 72 | 2.5 | 2/5 | Compact 4-way split. Cheap for its reach, but very turbulent. |
| Tapered Branch (Left) | — | 114 | 2.5 | 4/5 | 45° takeoff with the taper on the left. Guides air into the branch; face the taper toward incoming flow. |
| Tapered Branch (Right) | — | 114 | 2.5 | 4/5 | Mirror of the above. |
| Y-Branch | — | ? | ? | ? | *(won at Project #10, firm rewards track)* |

### TRANSITION (terminals that deliver air into a room)
| Part | P1 $ | P2 $ | Metal | Eff. | Description |
|---|---|---|---|---|---|
| Bare Boot | FREE | FREE | 0.5 | 1/5 | "For the not-so bright individuals." Open boot, no register. |
| Register Boot | 8 | 26 | 1 | 1/5 | Basic boot + 1-way register. Cheap, but it lets less air through and throws it short. **T to aim.** |
| Angled Register Boot | 12 | 39 | 1 | 2/5 | Throws air at a 45° angle. Aim it into corners. T to aim. |
| 2-Way Register | — | 59 | 1.5 | 3/5 | Throws air in two opposite directions. T to aim. *(P2)* |
| Corner Diffuser | — | 85 | 1.5 | 3/5 | 2-way diffuser with exits 90° apart. Great tucked into a room corner. T to aim. *(P2)* |
| 4-Way Ceiling Diffuser | 30 | 98 | 2 | 3/5 | Square louvered diffuser. Spreads air evenly in all four directions. *(unlocks P3 in P1; available P2)* |
| Linear Slot Diffuser | — | ~170 | ? | ? | *(unlocks P3)* |
| Swirl Diffuser | — | ~455 | ? | ? | *(unlocks P4)* |

Locked cards show "🔒 Unlocks with Project #N • <name>".

---

## 4. Airflow simulation

What the UI shows:
- **Blower (free air): 415 CFM** on P1. This is the AHU output with no restriction.
- **Moving through ducts / Delivered to rooms / Leaking into attic** (CFM).
- **Static pressure: N% of blower max**. It goes up as the system gets more restrictive.
- **Registers connected: N** and **Average room air speed (m/s)**.
- Every part has a **loss coefficient K** (galvanized straight: K = 0.03).
- Any **open duct end** gets a red ❗ marker and leaks: "Open end leaking 275 CFM! Add an End Cap." Unconnected AHU outlets also show ❗.
- Duct segments that aren't connected to the AHU are drawn **solid dark blue** (no flow).
- Placing a part previews a ghost outline; invalid placements tint red.

### Proposed model *(inferred, to be tuned until it looks/feels like the original)*
1. **Duct network = graph.** Nodes are part ports; edges are parts with resistance `R = K_total × friction_multiplier / A²`.
2. **Blower curve:** `ΔP(Q) = P_max × (1 − (Q / Q_free)²)`, with `Q_free = 415 CFM × (1 + 0.10 × blower_level)`.
3. Solve flows with an iterative pressure solve (Hardy-Cross style, or a small linear system each tick). Splits at tees are weighted by the downstream resistance plus the tee's branch K (square T sends less air to the branch than a tapered takeoff).
4. **Open ends** are terminals with very low resistance into "attic" (counted as leakage). **End caps** close the node.
5. **Registers/diffusers** are terminals with their own K. They inject their CFM into the room grid at the register tile, in their aim direction(s).
6. **Room air field:** a per-tile 2D velocity field. Each terminal emits a jet with throw length proportional to its exit velocity. Spread it with a few diffusion/advection passes that walls block. Doorway gaps let air into neighboring rooms (the video shows heat bleeding into adjacent rooms). Display it as the smooth heatmap.
7. **Room coverage %** = share of a room's floor tiles whose speed is above a threshold (≈0.1 m/s), possibly weighted. Project coverage = area-weighted average across rooms.

---

## 5. Inspector / hover tooltips
Hover a part to see a tooltip (also mirrored in the Stats panel's INSPECTOR box):
- Name, "Airflow through: 275 CFM", "Loss coefficient K = 0.03", plus red warnings ("Open end leaking … Add an End Cap.").
- Terminals: "4-Way Ceiling Diffuser · Airflow through: 143 CFM · Into the room: 143 CFM (T to aim)".
- Hover a room to see "Living Room · Air coverage: 0%".

---

## 6. Panels

**STATS**: AIR COVERAGE big %, "This project pays $11.9/s of its $20.0/s"; AIRFLOW block (as in §4); INSPECTOR; ROOMS list with a coverage bar + % for each room (bars colored by %).

**UPGRADES** (global, each card has a level bar, a "−1" button and an "UPGRADE $X" button):
| Upgrade | Effect | Max | First cost | 2nd cost |
|---|---|---|---|---|
| Blower Motor | +10% furnace airflow per level | 18 | $1000 | $7200 |
| Smooth Duct Liner | −5% fitting & duct friction per level | 12 | $1750 | ? |
| Service Contracts | +13% income per level | 18 | $2500 | ? |
| Material Sourcing | +1 metal limit per level | 20 | $2000 | $10.9K |

**PROJECTS**: list of jobs. Each shows size, rooms, metal limit, pay at 100%, and its current coverage/earnings. Buttons: CURRENT JOB / GO TO PROJECT / BUY $X / LOCKED.
| # | Name | Size | Rooms | Metal | Pays @100% | Buy |
|---|---|---|---|---|---|---|
| 1 | Starter Cottage | 14×9 | 3 | 33 | $20/s | — |
| 2 | Suburban Ranch | 18×11 | 5 | 51 | $65/s | $1250 |
| 3 | Hillside Bungalow | 20×12 | 8 | 73 | $140/s | $12.5K |
| 4 | Family Home | 24×14 | 8 | 81 | $225/s | ? |
| 5 | Lakeside Villa | 28×16 | 11 | 114 | $325/s | ? |
| 6 | Two-Story Colonial | 2 floors, 22×12 | 11 | 121 | $415/s | ? |
| 7 | Maple Grove Farmhouse | 2 floors, 26×14 | 15 | 161 | $500/s | ? |
| 8 | Hillcrest Manor | 2 floors, 30×16 | 18 | 221 | $590/s | ? |
| 9 | Harbor Brownstone | 3 floors, 32×17 | 23 | 301 | $675/s | ? |
| 10+ | ? | | | | | |
(Metal limit shown in-game is 32 for P1 vs 33 listed. The listing probably includes +1 from Material Sourcing.)

**APPEARANCE**: Air detail (Low / Medium / High), Interface theme (Paper White / Dark Mode), Glass frost slider, custom color presets.

---

## 7. Placement rules
- Grid-snapped, rotatable (R) parts. Ports must line up to connect.
- Ducts can run over furniture (furniture is just drawn underneath); walls block room air but **not** ducts (ducts run in the attic).
- Terminals (boots/registers/diffusers) sit inside a room and deliver to the room they're in.
- Removing (X) refunds money and metal *(inferred)*.
- Drag-select multiple parts; C/V to copy/paste.

## 8. Controls
`B` build mode · `R` rotate · `T` aim register · `F` damper · `Q` pick part (eyedropper) · `X` remove · `Z` view · `Drag` select · `C/V` copy/paste · `WASD` move camera · `RMB` pan / drop (deselect) · `Scroll` zoom · `1–4` part categories · `Tab` panels

---

## 9. Build plan (Python 3.14 + pygame-ce + numpy, packaged as a .dmg)
- **v0.1 (done):** Projects 1–4 playable, all non-reward parts, network solver, room heatmap, coverage and income, Stats/Upgrades/Projects/Appearance panels, autosave, undo, copy/paste, DMG build.
- **Next:** tune the air spread against more footage, Projects 5–9 floor plans (multi-floor), the rewards track (Vaned elbows, Y-Branch), sound effects, an update channel.
- **Later:** multiplayer, built on the existing `Game.apply(action)` layer.

Deviations from the original (on purpose or unknown):
- Upgrade costs past level 1 follow `base × (level+1)^2.5`, since the real curve isn't visible. "-1" refunds 50%.
- Projects 3–4 floor plans are original designs that match the listed size and room counts.
- Reward-track parts are shown locked.

Open questions to answer by playing (or more video):
- Exact coverage threshold, and whether doorway bleed counts toward the neighbor room.
- Project 3+ buy prices; upgrade cost curves past level 1.
- What the "firm's rewards track" is.
