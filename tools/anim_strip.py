"""Film the airflow animation headlessly as a contact sheet.

    python tools/anim_strip.py out_dir
Writes build_up.jpg (air arriving after a layout is placed), cut.jpg (a branch cut off
and reconnected) and pipe_zoom.jpg (one duct over consecutive frames).
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame  # noqa: E402

from airflow import config as C  # noqa: E402

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
C.save_path = lambda: os.path.join(OUT, "anim_save.json")

from airflow.app import App  # noqa: E402
from airflow.state import Game  # noqa: E402
from tools.demo_layouts import p1_demo  # noqa: E402

FPS = 30


def run_to(app, t_target):
    while app.t < t_target - 1e-6:
        app.update(1.0 / FPS)


def grab(app, region=None):
    app.draw()
    img = app.surf.copy()
    if region:
        img = img.subsurface(region).copy()
    return img


def sheet(name, shots, cols, scale):
    w, h = shots[0][1].get_size()
    tw, th = int(w * scale), int(h * scale)
    rows = (len(shots) + cols - 1) // cols
    out = pygame.Surface((tw * cols, th * rows))
    out.fill((0, 0, 0))
    font = pygame.font.Font(None, 30)
    for i, (label, img) in enumerate(shots):
        x, y = (i % cols) * tw, (i // cols) * th
        out.blit(pygame.transform.smoothscale(img, (tw, th)), (x, y))
        pygame.draw.rect(out, (0, 0, 0), (x, y, tw, th), 2)
        lab = font.render(label, True, (255, 255, 255), (0, 0, 0))
        out.blit(lab, (x + 4, y + 4))
    pygame.image.save(out, os.path.join(OUT, name))


def main():
    app = App(headless=(1400, 860))
    app.game = Game()
    app.toast = None
    app.screen = "game"
    app.panel = None
    app.update(1 / FPS)
    app.draw()
    pv = app.pv
    s = app.scale
    x0, y0 = pv.origin()
    plan_rect = pygame.Rect(int(x0 * s) - 6, int(y0 * s) - 6,
                            int(app.game.plan.w * pv.T * s) + 12, int(app.game.plan.h * pv.T * s) + 12)

    # 1. place a whole layout and watch the air arrive
    app.game.money = 5000
    p1_demo(app.game)
    app.game.dirty = True
    t0 = app.t
    shots = []
    for dtv in (0.0, 0.15, 0.3, 0.5, 0.75, 1.0, 1.4, 2.0, 3.0, 4.5, 6.5, 9.0):
        run_to(app, t0 + dtv + 1 / FPS)
        shots.append((f"+{dtv:.2f}s", grab(app, plan_rect)))
    sheet("build_up.jpg", shots, 3, 0.42)

    # 2. cut the bathroom branch, then reconnect it
    run_to(app, app.t + 4)
    pl = dict(app.game.layout[(8, 7)])
    app.act({"kind": "remove", "tiles": [(8, 7)]})
    t1 = app.t
    shots = []
    for dtv in (0.0, 0.3, 0.6, 1.0, 2.0, 4.0):
        run_to(app, t1 + dtv + 1 / FPS)
        shots.append((f"cut +{dtv:.1f}s", grab(app, plan_rect)))
    app.act({"kind": "place", "type": pl["type"], "tile": (8, 7), "rot": pl["rot"]})
    t2 = app.t
    for dtv in (0.0, 0.3, 0.6, 1.0, 2.0, 4.0):
        run_to(app, t2 + dtv + 1 / FPS)
        shots.append((f"reconnect +{dtv:.1f}s", grab(app, plan_rect)))
    sheet("cut.jpg", shots, 3, 0.42)

    # 3. one duct over consecutive frames (the core wobbles)
    run_to(app, app.t + 3)
    ax, ay = pv.tile_xy((0, 3.4))
    zoom = pygame.Rect(int(ax * s), int(ay * s), int(8 * pv.T * s), int(2.4 * pv.T * s))
    shots = []
    for i in range(8):
        run_to(app, app.t + 0.2)
        shots.append((f"{i * 0.2:.1f}s", grab(app, zoom)))
    sheet("pipe_zoom.jpg", shots, 2, 0.6)
    print("ok")


if __name__ == "__main__":
    main()
