"""Render the game headlessly to PNGs for visual checks.

    python tools/snapshot.py out_dir
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame  # noqa: E402

from airflow import config as C  # noqa: E402

C.save_path = lambda: os.path.join(sys.argv[1], "test_save.json")

from airflow.app import App  # noqa: E402
from airflow.state import Game  # noqa: E402
from tools.demo_layouts import p1_demo, p2_demo  # noqa: E402


def shot(app, name, mouse=None):
    if mouse:
        app.mouse = mouse
        app.hover_tile = app.pv.tile_at(*mouse)
    for _ in range(240):              # let the air arrive, then settle it
        app.update(1 / 60)
    app.anim.settle(app.t)
    app.update(0.016)
    app.draw()
    pygame.image.save(app.surf, os.path.join(sys.argv[1], name))


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    app = App(headless=(1400, 860))
    app.game = Game()
    app.toast = None
    app.screen = "game"
    shot(app, "01_empty.png")
    app.game.money = 5000
    p1_demo(app.game)
    app.game.dirty = True
    app.version += 1
    app.update(0.016)
    app.draw()
    # hover a register for the tooltip
    tx, ty = app.pv.tile_xy((10, 1))
    T = app.pv.T
    shot(app, "02_p1_built.png", (tx + T / 2, ty + T / 2))
    app.selected = "galv"
    gx, gy = app.pv.tile_xy((5, 6))
    shot(app, "03_ghost.png", (gx + T / 2, gy + T / 2))
    app.selected = None
    app.panel = "UPGRADES"
    shot(app, "04_upgrades.png", (5, 5))
    app.panel = "PROJECTS"
    app.category = 3
    shot(app, "05_projects.png", (5, 5))
    app.game.money = 1e6
    app.act({"kind": "buy_project", "num": 2})
    p2_demo(app.game)
    app.game.dirty = True
    app.panel = "STATS"
    app.update(0.016)
    app.draw()
    shot(app, "06_p2.png", (5, 5))
    app.dark = True
    shot(app, "07_dark.png", (5, 5))
    for n in (3, 4):
        app.act({"kind": "buy_project", "num": n})
        app.dark = False
        app.update(0.016)
        app.draw()
        shot(app, f"08_p{n}_empty.png", (5, 5))
    print("ok")


if __name__ == "__main__":
    main()
