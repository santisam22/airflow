"""Global constants and tuning knobs."""

import os
import sys

APP_NAME = "Airflow"
VERSION = "0.6.0"

GITHUB_REPO = "santisam22/airflow"
WEBSITE = "https://santisam22.github.io/airflow/"
UPDATE_MANIFEST_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/update.json"
UPDATE_PUBLIC_KEY = "CO4ZGKlNm/0OZCAp0WH03fZtN9cB9gWFLSmAo5EVvuE="   # macos/sign_tool.swift pubkey

# Grid / rendering
TILE = 46            # base pixels per tile at zoom 1.0 (logical points)
CELLS = 4            # room-air simulation cells per tile edge

# Airflow physics (arbitrary but self-consistent units)
PMAX = 100.0             # blower shutoff pressure; static pressure % is P / PMAX
BASE_FREE_CFM = 290.0    # blower airflow at Blower Motor level 0 (was 415 before 0.4.1)
KSCALE = 3.0e-4          # resistance per unit loss coefficient K
OPEN_END_K = 1.0         # an open duct end dumping into the attic
AHU_PORT_K = 0.05
BOOSTER_GAIN = 30.0      # pressure added by an inline booster fan

# Duct colouring: CFM that maps to the top of the 2 m/s scale
DUCT_CFM_FOR_MAX = 300.0
VMAX = 2.0

# Room air
JET_V_PER_CFM = 0.026    # jet start speed (m/s) per CFM leaving a register face
TERMINAL_STRENGTH = 0.42 # how hard registers and diffusers blow (1.0 = the strength in 0.2-0.3)
JET_K = 0.4              # terminal jet speed per CFM (times its power)
THROW_BASE = 4.5         # jet reach, in room cells, plus...
THROW_PER_CFM = 0.13     # ...this per effective CFM in each jet
THROW_SPLIT = 0.5        # how much splitting air between more jets shortens each one
SPREAD_GAIN = 1.35       # how far air drifts through a room after leaving the jets
COVER_LO = 0.021         # below this speed a cell contributes 0 coverage (scaled with TERMINAL_STRENGTH)
COVER_HI = 0.105         # at/above this speed a cell is fully covered

STARTING_MONEY = 150.0
BASE_PAY = 20.0          # project 1 pay; part prices scale by pay / BASE_PAY

AUTOSAVE_SECONDS = 10.0


IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")
MOD_KEY = "Cmd" if IS_MAC else "Ctrl"      # shown in shortcut hints


def save_dir():
    if IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    elif IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    else:
        base = os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def save_path():
    return os.path.join(save_dir(), "save.json")
