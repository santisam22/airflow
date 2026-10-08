"""Headless play-through: drives the real App with synthetic input events."""
import os, sys, tempfile
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pygame
from airflow import config as C
TMP = tempfile.mkdtemp()
C.save_path = lambda: os.path.join(TMP, "save.json")
from airflow.app import App
from airflow.state import Game


def frame(app):
    app.update(0.016); app.draw()


def center(app, t):
    x, y = app.pv.tile_xy(t)
    return (x + app.pv.T / 2, y + app.pv.T / 2)


def click(app, pos, button=1):
    app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))
    frame(app)


def key(app, k, mod=0):
    app.handle(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode=""))
    frame(app)


def find_button(app, pred):
    for r, cb in app.buttons:
        if pred(r, cb):
            return r.center
    raise AssertionError("button not found")


def main():
    app = App(headless=(1400, 860))
    app.game = Game(); app.toast = None
    frame(app)
    g = app.game
    # every launch opens on the home screen; PLAY enters the game
    assert app.screen == "home"
    click(app, find_button(app, lambda r, cb: cb == app.play))
    assert app.screen == "game"
    # Esc with nothing selected goes back home; Enter plays again
    key(app, pygame.K_ESCAPE); assert app.screen == "home"
    click(app, find_button(app, lambda r, cb: getattr(cb, "__name__", "") == "<lambda>" and r.w > 200 and r.y < 500
                           and r.y > app.logical[1] / 2 - 100))
    assert app.home_page == "settings", app.home_page
    key(app, pygame.K_ESCAPE); assert app.home_page == "main"
    key(app, pygame.K_RETURN); assert app.screen == "game"
    app.toast = None; frame(app)
    # select Galvanized Duct by clicking its card
    card = app._palette_area.x + 50, app._palette_area.y + 40
    click(app, card)
    assert app.selected == "galv", app.selected
    # drag a horizontal run from (1,4) to (4,4)
    a = center(app, (1, 4)); b = center(app, (4, 4))
    app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=a, rel=(0, 0), buttons=(0, 0, 0)))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=a, button=1))
    app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=b, rel=(1, 0), buttons=(1, 0, 0)))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=b, button=1))
    frame(app)
    assert all((x, 4) in g.layout for x in range(1, 5)), g.layout.keys()
    assert all(g.layout[(x, 4)]["rot"] % 2 == 0 for x in range(1, 5))
    assert g.net.leaked > 100, "open end should leak"
    # vertical drag orients pieces vertically
    a = center(app, (6, 1)); b = center(app, (6, 3))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=a, button=1))
    app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=b, rel=(0, 1), buttons=(1, 0, 0)))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=b, button=1))
    frame(app)
    assert g.layout[(6, 2)]["rot"] % 2 == 1 and g.layout[(6, 1)]["rot"] % 2 == 1
    # pick a register boot via category key 4, place at (5,4)
    key(app, pygame.K_4)
    assert app.category == 3
    click(app, (app._palette_area.x + 214 + 8 + 50, app._palette_area.y + 40))
    assert app.selected == "regboot", app.selected
    click(app, center(app, (5, 4)))
    assert g.layout[(5, 4)]["type"] == "regboot"
    assert g.net.delivered > 100 and g.net.leaked < 1, (g.net.delivered, g.net.leaked)
    assert g.total_cov > 0.05
    # air takes time to arrive: right after placing, the room is still empty...
    assert app.disp_total < g.total_cov
    # ...then the duct front reaches the register and the room fills
    for _ in range(int(6 / 0.016)):
        app.update(0.016)
    frame(app)
    assert app.disp_total > 0.6 * g.total_cov, (app.disp_total, g.total_cov)
    R = app.anim.R
    cy, cx = int(4.5 * R), int(3.5 * R)
    assert app.anim.duct_speed(app.t)[cy, cx] > 0.3, "duct should be flowing"
    # aim with T while hovering
    app.selected = None
    app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=center(app, (5, 4)), rel=(0, 0), buttons=(0, 0, 0)))
    aim0 = g.layout[(5, 4)]["aim"]; key(app, pygame.K_t)
    assert g.layout[(5, 4)]["aim"] == (aim0 + 2) % 8
    # remove mode X then click
    money = g.money
    key(app, pygame.K_x); assert app.remove_mode
    click(app, center(app, (6, 2)))
    assert (6, 2) not in g.layout and g.money > money
    # undo restores it
    key(app, pygame.K_z, pygame.KMOD_META)
    assert (6, 2) in g.layout
    # RMB click deselects remove mode
    click(app, center(app, (8, 8)), button=3)
    assert not app.remove_mode
    # drag-select + copy + paste
    a = center(app, (0.0, 3.6)); b = center(app, (2, 4))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(a[0] + 30, a[1] - 15), button=1))
    app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=b, rel=(1, 1), buttons=(1, 0, 0)))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=b, button=1))
    assert app.selection, "selection empty"
    key(app, pygame.K_c); key(app, pygame.K_v)
    assert app.paste_mode
    n_before = len(g.layout)
    click(app, center(app, (2, 7)))
    assert len(g.layout) > n_before
    # panels: upgrades + buy project
    g.money = 100000
    key(app, pygame.K_TAB)  # cycles
    app.panel = "UPGRADES"; frame(app)
    btn = find_button(app, lambda r, cb: r.w > 150 and r.h == 26)
    click(app, btn)
    assert g.upgrades["blower"] == 1, g.upgrades
    app.panel = "PROJECTS"; frame(app)
    app.buy(2); frame(app)
    assert g.current == 2 and 2 in g.owned
    assert g.unlocked("flex") and not g.unlocked("slot")
    # save / load roundtrip
    g.save()
    g2 = Game.load()
    assert g2.owned == g.owned and g2.layouts[1] == g.layouts[1] and abs(g2.money - g.money) < 1e-6
    # resize: re-layout without errors
    app.logical = (1100, 700); app.surf = pygame.Surface((2200, 1400)); app.p.set_surface(app.surf, 2.0)
    frame(app)
    # every panel and view mode draws
    for pn in ("STATS", "UPGRADES", "PROJECTS", "SETTINGS", None):
        app.panel = pn; frame(app)
    for _ in range(3):
        key(app, pygame.K_z)
    app.dark = True; frame(app)
    # updates: download is manual, from the home screen; finishing shows the banner
    u = app.updater
    u.available = {"version": "9.9.9", "url": "x", "signature": "x", "notes": "Test notes"}
    app.go_home(); frame(app)
    btn = find_button(app, lambda r, cb: cb == app.start_download)
    started = []
    u.download = lambda: started.append(1)
    click(app, btn)
    assert started, "DOWNLOAD UPDATE should start the download"
    u.state, u.progress = "downloading", 0.4; frame(app)
    u.state, u.downloaded_version = "downloaded", "9.9.9"
    frame(app)
    assert app.banner and app.banner[0] == "Update 9.9.9 downloaded", app.banner
    find_button(app, lambda r, cb: cb == app.restart_to_update)
    frame(app)
    assert app.banner[0] == "Update 9.9.9 downloaded"   # announced once, not re-triggered
    # admin mode: a wrong key is refused...
    from airflow import admin
    app.home_page = "settings"; app.banner = None; frame(app)
    click(app, find_button(app, lambda r, cb: cb == app.focus_key))
    assert app.key_focus
    app.handle(pygame.event.Event(pygame.TEXTINPUT, text="WRONG-KEYS-HERE-1234"))
    key(app, pygame.K_b)                      # typing doesn't trigger game hotkeys
    key(app, pygame.K_RETURN)
    assert not app.admin_key and app.key_error > 0 and not app.game.admin
    # ...the real one (kept outside the repo) unlocks it
    kp = os.path.join(os.path.dirname(__file__), "..", "Private.nosync", "admin_key.txt")
    if os.path.exists(kp):
        real = [w for w in open(kp).read().split() if w.count("-") == 3][0]
        click(app, find_button(app, lambda r, cb: cb == app.focus_key))
        app.handle(pygame.event.Event(pygame.TEXTINPUT, text=real.lower()))
        key(app, pygame.K_RETURN)
        assert app.admin_key and app.game.admin
        app.set_admin(False); assert not app.game.admin
    # admin rules: free, no metal limit, everything unlocked, any house
    g2 = Game(); g2.admin = True
    assert g2.unlocked("swirl") and g2.unlocked("ybranch") and g2.price("galv") == 0
    g2.money = 0
    for x in range(1, 14):
        for y2 in range(0, 9):
            if (x, y2) != tuple(g2.plan.ahu):
                g2.apply({"kind": "place", "type": "galv", "tile": (x, y2), "rot": 0})
    assert g2.metal_used() > g2.metal_limit()
    g2.apply({"kind": "upgrade", "id": "blower"}); assert g2.upgrades["blower"] == 1 and g2.money == 0
    g2.apply({"kind": "buy_project", "num": 4}); assert 4 in g2.owned and g2.money == 0
    print("all play tests passed")


if __name__ == "__main__":
    main()
