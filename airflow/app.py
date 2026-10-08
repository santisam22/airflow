"""Window, UI panels and input handling."""

import json
import math
import os
import sys
import time

import numpy as np
import pygame

from . import config as C
from .painter import DARK, LIGHT, Painter
from .parts import (BY_ID, CATEGORIES, DIRS, REWARDS, abs_ports, by_category, damper_open, default_aim,
                    exit_open, fmt_money, fmt_price)
from .projects import PROJECTS, project, room_count
from .render import PlanView, draw_part, draw_plan, flow_color
from .roomair import colormap, speed_to_t
from .state import UPGRADES, ActionError, Game, upgrade_cost
from .updater import Updater, whats_new_after_update
from .anim import DETAIL_CELLS, DETAIL_HZ, FlowAnimator
from .home import HomeMixin
from . import admin

TOP_H = 66
TABS_H = 30
LEGEND_W = 66
PANEL_W = 300
BOTTOM_H = 158
HINT_H = 24

EFF_COLORS = {1: (52, 84, 230), 2: (40, 170, 235), 3: (80, 200, 70), 4: (240, 200, 30), 5: (230, 60, 60)}
PANELS = ["STATS", "UPGRADES", "PROJECTS", "SETTINGS"]
STRAIGHTS = {"galv", "flex"}


class App(HomeMixin):
    def __init__(self, headless=False):
        pygame.init()
        pygame.key.set_repeat(0)
        self.headless = headless
        self.window = None
        if headless:
            size = headless if isinstance(headless, tuple) else (1400, 860)
            pygame.display.set_mode((1, 1))
            self.scale = 2.0
            self.logical = size
            self.surf = pygame.Surface((int(size[0] * 2), int(size[1] * 2)))
        else:
            self._open_window()
        self.p = Painter(self.surf, self.scale)
        self.game = Game.load()
        self.pv = PlanView()
        self.clock = pygame.time.Clock()
        self.version = 0
        self.last_save = time.time()

        # UI state
        self.category = 0
        self.selected = None          # part id
        self.ghost_rot = 0
        self.ghost_aim = None
        self.remove_mode = False
        self.build_mode = True
        self.panel = "STATS"
        self.view_mode = 0            # 0 all, 1 ducts only, 2 air only
        self.dark = False
        self.air_detail = 1
        self.palette_scroll = 0.0
        self.buttons = []
        self.toast = None
        self.mouse = (0, 0)
        self.drag = None              # dict describing current drag
        self.selection = set()
        self.clipboard = None
        self.paste_mode = False
        self.hover_tile = None
        self.running = True
        self.updater = Updater()
        self.anim = FlowAnimator()
        self._ui_cache = {}
        self.t = 0.0                  # animation clock (seconds)
        self._anim_dirty = True
        self.easy = False             # difficulty (Normal by default)
        self.admin_key = ""           # set once a correct admin key has been entered
        self.admin_on = False
        self.popup = None             # tile whose damper window is open
        self.key_text = ""            # what's typed in the admin key field
        self.key_focus = False
        self.key_error = 0.0
        self.load_settings()
        self.init_home()
        news = whats_new_after_update()
        if news:
            v, notes = news
            self.show_banner(f"Updated to Airflow {v}", notes)

    # ------------------------------------------------------------ settings file
    def _settings_path(self):
        return os.path.join(os.path.dirname(C.save_path()), "settings.json")   # next to the save

    def load_settings(self):
        try:
            with open(self._settings_path()) as fh:
                d = json.load(fh)
            self.dark = bool(d.get("dark", False))
            self.air_detail = max(0, min(2, int(d.get("air_detail", 1))))
            self.easy = d.get("difficulty", "normal") == "easy"
            key = d.get("admin_key") or ""
            if key and admin.check(key):          # re-checked on every launch
                self.admin_key = key
                self.admin_on = bool(d.get("admin_on", False))
        except (OSError, ValueError, TypeError):
            pass
        self.game.admin = bool(self.admin_key and self.admin_on)
        self.game.easy = self.easy

    def save_settings(self):
        try:
            with open(self._settings_path(), "w") as fh:
                json.dump({"dark": self.dark, "air_detail": self.air_detail,
                           "difficulty": "easy" if self.easy else "normal",
                           "admin_key": self.admin_key, "admin_on": self.admin_on}, fh)
        except OSError:
            pass

    # ------------------------------------------------------------ window
    def _open_window(self):
        dw, dh = (1440, 900)
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                dw, dh = sizes[0]
        except Exception:
            pass
        w = int(min(1440, max(1000, dw - 60)))
        h = int(min(900, max(680, dh - 90)))
        try:
            self.window = pygame.Window(C.APP_NAME, (w, h), resizable=True, allow_high_dpi=True)
            self.window.minimum_size = (1000, 640)
            self._set_window_icon()
            self._refresh_surface()
        except Exception:
            self.window = None
            screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            pygame.display.set_caption(C.APP_NAME)
            self.surf = screen
            self.scale = 1.0
            self.logical = (w, h)

    def _set_window_icon(self):
        """The fan, for the title bar and the Windows taskbar (macOS uses the app's .icns)."""
        S = 64
        ic = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.draw.rect(ic, (38, 72, 222), (2, 2, S - 4, S - 4), border_radius=14)
        c, r = S / 2, S * 0.24
        for k in range(3):
            a = k * 2 * math.pi / 3 - math.pi / 2
            pygame.draw.circle(ic, (255, 255, 255), (c + math.cos(a) * r * 0.55, c + math.sin(a) * r * 0.55), r * 0.48)
        pygame.draw.circle(ic, (38, 72, 222), (c, c), S * 0.066)
        pygame.draw.circle(ic, (255, 255, 255), (c, c), S * 0.031)
        try:
            self.window.set_icon(ic)
        except Exception:
            pass

    def _refresh_surface(self):
        if self.window is None:
            self.surf = pygame.display.get_surface()
            self.logical = self.surf.get_size()
            self.scale = 1.0
        else:
            self.surf = self.window.get_surface()
            lw, lh = self.window.size
            self.scale = self.surf.get_width() / max(1, lw)
            self.logical = (lw, lh)
        if hasattr(self, "p"):
            self.p.set_surface(self.surf, self.scale)

    def _flip(self):
        if self.window is not None:
            self.window.flip()
        elif not self.headless:
            pygame.display.flip()

    # ------------------------------------------------------------ helpers
    @property
    def theme(self):
        return DARK if self.dark else LIGHT

    def _toast(self, msg, secs=2.5):
        self.toast = (msg, time.time() + secs)

    def act(self, action):
        try:
            self.game.apply(action)
            self.version += 1
            return True
        except ActionError as e:
            self._toast(str(e))
            return False

    def layout_rects(self):
        W, H = self.logical
        panel_open = self.panel is not None
        bottom = BOTTOM_H + HINT_H if self.build_mode else HINT_H
        right = PANEL_W + 20 if panel_open else 14
        view = pygame.Rect(LEGEND_W + 8, TOP_H + TABS_H + 6, W - LEGEND_W - 8 - right,
                           H - TOP_H - TABS_H - 12 - bottom)
        return {
            "view": view,
            "panel": pygame.Rect(W - PANEL_W - 12, TOP_H + TABS_H + 6, PANEL_W, H - TOP_H - TABS_H - 12 - bottom),
            "bottom": pygame.Rect(8, H - bottom, W - 16, BOTTOM_H - 8),
            "hints": pygame.Rect(0, H - HINT_H, W, HINT_H),
        }

    def button(self, rect, cb, hover_ok=True):
        self.buttons.append((pygame.Rect(rect), cb))
        return pygame.Rect(rect).collidepoint(self.mouse)

    # ------------------------------------------------------------ main loop
    def run(self):
        import os
        smoke = os.environ.get("AIRFLOW_SMOKE")   # path: run ~3 s, save a screenshot, quit
        start = time.time()
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            for ev in pygame.event.get():
                self.handle(ev)
            self.update(dt)
            self.draw()
            self._flip()
            if smoke and time.time() - start > 3:
                pygame.image.save(self.surf, smoke)
                self.running = False
        self.game.save()
        self.save_settings()
        if self.updater.staged:
            self.updater.apply(relaunch=False)   # installs once the game has exited
        pygame.quit()

    def update(self, dt):
        if not self.headless:
            self.updater.tick()
            if self.updater.ready_to_quit:
                self.running = False
        self.watch_updates()
        was_dirty = self.game.dirty
        self.game.tick(min(dt, 0.25))
        self.t += min(dt, 0.1)
        if was_dirty:
            self.version += 1
        if was_dirty or self._anim_dirty or self.anim.plan_num != self.game.current:
            if self.game.net is not None:
                self.anim.on_sim(self.game, self.t, self.air_detail)
                self._anim_dirty = False
        self.anim.update(self.t, min(dt, 0.1), self.game.grid())
        if time.time() - self.last_save > C.AUTOSAVE_SECONDS:
            try:
                self.game.save()
            except OSError:
                pass
            self.last_save = time.time()

    def _mouse_in(self, r):
        return tuple(self.mouse) if r.collidepoint(self.mouse) else None

    def cached(self, name, rect, key, draw):
        """Draw `draw()` into `rect`, or reuse the last picture (and its buttons) if `key` is unchanged."""
        s = self.scale
        pr = pygame.Rect(int(rect.x * s), int(rect.y * s), int(rect.w * s) + 1, int(rect.h * s) + 1)
        pr = pr.clip(self.surf.get_rect())
        hit = self._ui_cache.get(name)
        if hit and hit[0] == key and hit[1].get_size() == pr.size:
            self.surf.blit(hit[1], pr.topleft)
            self.buttons.extend(hit[2])
            return
        n = len(self.buttons)
        draw()
        if pr.w > 0 and pr.h > 0:
            self._ui_cache[name] = (key, self.surf.subsurface(pr).copy(), self.buttons[n:])

    # what the player sees: coverage as the air actually fills the rooms
    @property
    def disp_total(self):
        return self.anim.total_cov if self.anim.room_target is not None else self.game.total_cov

    @property
    def disp_rooms(self):
        return self.anim.room_cov if self.anim.room_target is not None else self.game.room_cov

    @property
    def disp_avg(self):
        return self.anim.avg_speed if self.anim.room_target is not None else self.game.avg_speed

    # ------------------------------------------------------------ drawing
    def draw(self):
        self.p.theme = self.theme
        self.buttons = []
        if self.screen == "home":
            self.draw_home()
        else:
            self.draw_game()
        self.draw_banner()

    def draw_game(self, ui=True):
        th = self.theme
        self.p.theme = th
        p = self.p
        W, H = self.logical
        rects = self.layout_rects()
        view = rects["view"]
        if self.pv.fitted_for != self.game.current or self.pv.view.size != view.size:
            if self.pv.fitted_for != self.game.current:
                self.pv.fit(self.game.plan, view)
            else:
                self.pv.view = view
        self.pv.view = view

        p.rect(th["bg"], (0, 0, W, H))
        show_heat = self.view_mode in (0, 2)
        show_ducts = self.view_mode in (0, 1)
        frame = self.anim.frame(self.t, DETAIL_HZ[self.air_detail])
        draw_plan(p, th, self.game, self.pv, show_heat, show_ducts, self.version, anim_frame=frame,
                  duct_cells=DETAIL_CELLS[self.air_detail], room_cov=self.disp_rooms)
        if ui:
            self.draw_overlays(view)
        # The UI around the plan barely changes, so each part is redrawn only when its
        # inputs change (or a few times a second for live numbers) and reused otherwise.
        W, H = self.logical
        tick = int(time.time() * 8)
        base = (W, H, self.dark, self.scale, self.game.admin)
        u = self.updater
        self.cached("legend", pygame.Rect(0, view.y, view.x, view.h + 4),
                    base + (tuple(view), round(self.disp_avg, 2)), lambda: self.draw_legend(view))
        top = pygame.Rect(0, 0, W, TOP_H + TABS_H + 4)
        self.cached("top", top, base + (tick, self.build_mode, self.panel, self._mouse_in(top),
                                        bool(u.available), u.state, self.game.current), self.draw_topbar)
        if self.panel:
            pr = rects["panel"].inflate(8, 10)
            self.cached("panel", pr, base + (tick, self.panel, self._mouse_in(pr), self.key_focus, self.key_text,
                                             self.air_detail, self.easy, self.settings_scroll_y(),
                                             self.panel_scroll_y(), u.state),
                        lambda: self.draw_panel(rects["panel"]))
        if self.build_mode:
            br = rects["bottom"].inflate(8, 10)
            self.cached("palette", br, base + (self.category, round(self.palette_scroll), self.selected,
                                               self.remove_mode, self._mouse_in(br), len(self.game.owned),
                                               self.game.current), lambda: self.draw_palette(rects["bottom"]))
        self.cached("hints", rects["hints"], base, lambda: self.draw_hints(rects["hints"]))
        if ui:
            if self.popup is None:
                self.draw_tooltip(view)
            self.draw_popup(view)
            self.draw_toast(view)

    def draw_overlays(self, view):
        p, th, pv, g = self.p, self.theme, self.pv, self.game
        T = pv.T
        p.clip(view)
        # selection
        for t in self.selection:
            x, y = pv.tile_xy(t)
            p.rect((60, 110, 255, 60), (x, y, T, T))
            p.rect(th["accent"], (x, y, T, T), width=1.5)
        if self.drag and self.drag.get("kind") == "select":
            (ax, ay), (bx, by) = self.drag["start"], self.mouse
            r = (min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay))
            p.rect((60, 110, 255, 40), r)
            p.rect(th["accent"], r, width=1)
        ht = self.hover_tile
        if ht and view.collidepoint(self.mouse) and self.build_mode and self._in_plan(ht):
            x, y = pv.tile_xy(ht)
            if self.paste_mode and self.clipboard:
                for (dx, dy), pl in self.clipboard:
                    t = (ht[0] + dx, ht[1] + dy)
                    tx, ty = pv.tile_xy(t)
                    ok = self._in_plan(t) and t != tuple(g.plan.ahu)
                    draw_part(p, BY_ID[pl["type"]], pl, tx, ty, T, th["ghost"] if ok else th["ghost_bad"],
                              th["muted"], theme=th)
            elif self.remove_mode:
                p.rect((230, 60, 60, 70), (x, y, T, T))
                p.rect(th["red"], (x, y, T, T), width=2)
            elif self.selected:
                pdef = BY_ID[self.selected]
                rot = self.smart_rot(self.selected, ht)
                aim = self.ghost_aim if (self.ghost_aim is not None and rot == self.ghost_rot) \
                    else default_aim(pdef, rot)
                pl = {"type": self.selected, "rot": rot, "aim": aim}
                bad = g.can_place(self.selected, ht)
                draw_part(p, pdef, pl, x, y, T, th["ghost_bad"] if bad else th["ghost"], th["muted"], theme=th)
            else:
                p.rect(th["accent"], (x, y, T, T), width=1.2)
        p.clip(None)

    def draw_legend(self, view):
        p, th = self.p, self.theme
        x = 14
        top = view.y + 4
        p.text("VELOCITY", 9, th["text"], (x, top), bold=True)
        p.text("MAGNITUDE (m/s)", 7, th["muted"], (x, top + 11), bold=True)
        bar_top = top + 30
        bar_h = max(120, view.h - 90)
        bw = 12
        steps = 80
        for i in range(steps):
            t = 1 - i / steps
            rgb = tuple(int(c * 255) for c in colormap(np.array([t]))[0])
            p.rect(rgb, (x, bar_top + bar_h * i / steps, bw, bar_h / steps + 1))
        p.rect(th["border"], (x, bar_top, bw, bar_h), width=1, radius=3)
        for v in (2.0, 1.7, 1.3, 1.0, 0.75, 0.57, 0.38, 0.22, 0.11, 0.03, 0.0):
            t = float(speed_to_t(v))
            yy = bar_top + bar_h * (1 - t)
            p.line(th["muted"], (x + bw, yy), (x + bw + 4, yy), 1)
            p.text(f"{v:.2f}" if v < 1 else f"{v:.1f}", 8, th["muted"], (x + bw + 6, yy), "midleft")
        avg = self.disp_avg
        yy = bar_top + bar_h * (1 - float(speed_to_t(avg)))
        p.rect(th["outline"], (x - 3, yy - 2, bw + 6, 4), radius=2)
        p.text("AVG SPEED", 8, th["text"], (x, bar_top + bar_h + 10), bold=True)
        p.text(f"{avg:.2f} m/s", 9, th["text"], (x, bar_top + bar_h + 21))

    def draw_topbar(self):
        p, th, g = self.p, self.theme, self.game
        W, _ = self.logical
        p.rect(th["panel"], (0, 0, W, TOP_H))
        p.line(th["border"], (0, TOP_H), (W, TOP_H), 1)
        # logo
        p.rect(th["accent"], (16, 12, 40, 40), radius=10)
        cx, cy = 36, 32
        for k in range(3):
            a = k * 2 * math.pi / 3 - math.pi / 2
            p.circle((255, 255, 255), (cx + math.cos(a) * 8, cy + math.sin(a) * 8), 6.5)
        p.circle(th["accent"], (cx, cy), 4)
        p.text(C.APP_NAME.upper(), 20, th["text"], (66, 12), bold=True)
        plan = g.plan
        p.text(f"PROJECT {plan.num}  •  {plan.name.upper()}  •  {len(plan.rooms)} rooms", 11,
               th["muted"], (67, 38))

        # build-mode button sits under the title bar
        bx, by = 16, TOP_H + 4
        label = "EXIT BUILD MODE" if self.build_mode else "ENTER BUILD MODE"
        bw = p.text_w(label, 10, True) + 44
        hov = self.button((bx, by, bw, 22), self.toggle_build)
        p.rect(th["accent"] if self.build_mode else th["green"], (bx, by, bw, 22), radius=6)
        p.text(label, 10, (255, 255, 255), (bx + 12, by + 11), "midleft", bold=True)
        p.text("B", 10, (210, 220, 255), (bx + bw - 12, by + 11), "midright", bold=True)
        # back to the home screen (a dot means an update is waiting there)
        mx = bx + bw + 8
        mw = p.text_w("MENU", 10, True) + p.text_w("ESC", 9) + 34
        hov = self.button((mx, by, mw, 22), self.go_home)
        p.rect(th["border"] if hov else th["panel2"], (mx, by, mw, 22), radius=6)
        p.rect(th["border"], (mx, by, mw, 22), width=1, radius=6)
        p.text("MENU", 10, th["text"], (mx + 12, by + 11), "midleft", bold=True)
        p.text("ESC", 9, th["muted"], (mx + mw - 12, by + 11), "midright")
        u = self.updater
        if u.available or u.state == "downloaded":
            p.circle(th["panel"], (mx + mw - 1, by + 1), 6)
            p.circle(th["green"] if u.state == "downloaded" else th["red"], (mx + mw - 1, by + 1), 4.5)

        # stats
        stats = [
            ("MONEY", "\u221e  ADMIN" if g.admin else fmt_money(g.money), None),
            ("INCOME (ALL PROJECTS)", f"+${g.total_income():.1f}/s", None),
            ("AIR COVERAGE", f"{self.disp_total * 100:.0f}%", (self.disp_total, th["green"])),
            ("DELIVERED AIR", f"{g.net.delivered:.0f} CFM" if g.net else "0 CFM", None),
            ("METAL USED", f"{g.metal_used():g} / \u221e" if g.admin else f"{g.metal_used():g} / {g.metal_limit()}",
             (g.metal_used() / max(1, g.metal_limit()),
              th["red"] if g.metal_used() >= g.metal_limit() - 1 else th["accent"])),
        ]
        x = W - 16
        widths = [96, 150, 110, 112, 104]
        for (title, val, bar), w in reversed(list(zip(stats, widths))):
            x -= w
            p.text(title, 9, th["muted"], (x, 14))
            p.text(val, 17, th["text"], (x, 28), bold=True)
            if bar:
                frac, col = bar
                p.rect(th["border"], (x, 52, w - 18, 3), radius=2)
                p.rect(col, (x, 52, (w - 18) * max(0.0, min(1.0, frac)), 3), radius=2)
            if title != "MONEY":
                p.line(th["border"], (x - 10, 14), (x - 10, 54), 1)

        # panel tabs
        tx = W - 12
        for name in reversed(PANELS):
            tw = p.text_w(name, 10, True) + 22
            tx -= tw + 4
            active = self.panel == name
            r = (tx, TOP_H + 5, tw, 21)
            hov = self.button(r, lambda n=name: self.toggle_panel(n))
            p.rect(th["accent"] if active else (th["panel2"] if not hov else th["border"]), r, radius=6)
            p.text(name, 10, (255, 255, 255) if active else th["muted"], (tx + tw / 2, TOP_H + 15.5), "center",
                   bold=True)

    # ------------------------------------------------------------ right panel
    def draw_panel(self, r):
        p, th = self.p, self.theme
        p.rect(th["shadow"], (r.x + 2, r.y + 3, r.w, r.h), radius=12)
        p.rect(th["panel"], r, radius=12)
        p.rect(th["border"], r, width=1, radius=12)
        title = self.panel.title()
        p.text(title, 15, th["text"], (r.x + 16, r.y + 14), bold=True)
        close = (r.right - 34, r.y + 10, 24, 24)
        self.button(close, lambda: self.toggle_panel(None))
        p.text("×", 20, th["muted"], (close[0] + 12, close[1] + 11), "center")
        p.line(th["border"], (r.x, r.y + 44), (r.right, r.y + 44), 1)
        inner = pygame.Rect(r.x + 12, r.y + 54, r.w - 24, r.h - 64)
        p.clip(inner)
        getattr(self, "panel_" + self.panel.lower())(inner)
        p.clip(None)

    def card(self, x, y, w, h):
        p, th = self.p, self.theme
        p.rect(th["panel2"], (x, y, w, h), radius=10)
        p.rect(th["border"], (x, y, w, h), width=1, radius=10)

    def panel_stats(self, r):
        p, th, g = self.p, self.theme, self.game
        n = g.net
        x, y, w = r.x, r.y, r.w
        self.card(x, y, w, 92)
        p.text("AIR COVERAGE", 9, th["muted"], (x + 12, y + 10), bold=True)
        p.text(f"{self.disp_total * 100:.0f}%", 30, th["text"], (x + 12, y + 24), bold=True)
        earn = g.project_income(g.current)
        full = g.plan.pay * g.income_mult()
        p.text(f"This project pays ${earn:.1f}/s of its ${full:.1f}/s", 11, th["text"], (x + 12, y + 66))
        y += 102
        lines = []
        if n:
            lines = [
                (f"Air handler: {n.blower_free:.0f} CFM per side", th["text"]),
                (f"Moving through ducts: {n.ahu_flow:.0f} CFM", th["text"]),
                (f"Delivered to rooms: {n.delivered:.0f} CFM", th["text"]),
                (f"Sides of the unit in use: {n.outlets} (full airflow each)" if n.outlets
                 else "Sides of the unit in use: 0", th["text"]),
                (f"Lost along the ducts: {n.lost:.0f} CFM ({n.static_pct:.0f}%)", th["text"]),
                (f"Registers connected: {sum(1 for t in n.terminals if t.cfm > 0.5)}", th["text"]),
                (f"Average room air speed: {self.disp_avg:.2f} m/s", th["text"]),
            ]
            if n.boosted > 0.5:
                lines.append((f"Won back by fans: {n.boosted:.0f} CFM", th["green"]))
            if n.leaked > 0.5:
                lines.append((f"Leaking into attic: {n.leaked:.0f} CFM", th["red"]))
        hh = 30 + 17 * len(lines)
        self.card(x, y, w, hh)
        p.text("AIRFLOW", 9, th["muted"], (x + 12, y + 10), bold=True)
        for i, (t, col) in enumerate(lines):
            p.text(t, 11, col, (x + 12, y + 27 + 17 * i))
        y += hh + 10
        insp = self.inspect_lines()
        hh = 34 + 16 * max(1, len(insp))
        self.card(x, y, w, hh)
        p.text("INSPECTOR", 9, th["muted"], (x + 12, y + 10), bold=True)
        if not insp:
            p.text("Hover any part or room to inspect it.", 11, th["text"], (x + 12, y + 28))
        yy = y + 28
        for t, col, bold in insp:
            for ln in p.wrap(t, 11, w - 24, bold):
                p.text(ln, 11, col, (x + 12, yy), bold=bold)
                yy += 16
        y += max(hh, yy - y + 8) + 10
        rooms = g.plan.rooms
        hh = 32 + 22 * len(rooms)
        self.card(x, y, w, hh)
        p.text("ROOMS", 9, th["muted"], (x + 12, y + 10), bold=True)
        for i, (name, *_ ) in enumerate(rooms):
            rc = self.disp_rooms
            cov = rc[i] if i < len(rc) else 0.0
            yy = y + 30 + 22 * i
            p.text(name, 11, th["text"], (x + 12, yy))
            bx = x + w * 0.48
            bw = w * 0.34
            p.rect(th["border"], (bx, yy + 4, bw, 7), radius=4)
            col = tuple(int(c * 255) for c in colormap(np.array([0.25 + 0.55 * cov]))[0])
            p.rect(col, (bx, yy + 4, bw * cov, 7), radius=4)
            p.text(f"{cov * 100:.0f}%", 11, th["text"], (x + w - 12, yy), "topright")

    def panel_upgrades(self, r):
        p, th, g = self.p, self.theme, self.game
        x, y, w = r.x, r.y, r.w
        effects = {
            "blower": lambda l: f"Airflow x{1 + 0.1 * l:.2f}",
            "liner": lambda l: f"Friction x{max(0.05, 1 - 0.05 * l):.2f}",
            "service": lambda l: f"Income x{1 + 0.13 * l:.2f}",
            "material": lambda l: f"Metal limit +{l}",
        }
        for uid, title, eff, mx, _ in UPGRADES:
            lvl = g.upgrades[uid]
            self.card(x, y, w, 112)
            p.text(title, 9, th["muted"], (x + 12, y + 10), bold=True)
            p.text(eff, 11, th["text"], (x + 12, y + 26))
            p.text(f"Level {lvl} / {mx}  •  {effects[uid](lvl)}", 11, th["text"], (x + 12, y + 42))
            seg_w = (w - 24) / mx
            for i in range(mx):
                p.rect(th["green"] if i < lvl else th["border"], (x + 12 + i * seg_w, y + 61, seg_w - 2, 4), radius=2)
            # -1 button
            r1 = (x + 12, y + 74, 44, 26)
            self.button(r1, lambda u=uid: self.act({"kind": "downgrade", "id": u}))
            p.rect(th["panel"], r1, radius=6)
            p.rect(th["border"], r1, width=1, radius=6)
            p.text("-1", 11, th["muted"], (r1[0] + 22, r1[1] + 13), "center", bold=True)
            r2 = (x + 62, y + 74, w - 74, 26)
            if lvl >= mx:
                p.rect(th["border"], r2, radius=6)
                p.text("MAXED", 11, th["muted"], (r2[0] + r2[2] / 2, r2[1] + 13), "center", bold=True)
            else:
                cost = 0.0 if g.admin else upgrade_cost(uid, lvl)
                ok = g.can_afford(cost)
                hov = self.button(r2, lambda u=uid: self.act({"kind": "upgrade", "id": u}))
                col = th["green"] if ok else th["border"]
                if ok and hov:
                    col = tuple(max(0, c - 25) for c in col)
                p.rect(col, r2, radius=6)
                p.text("UPGRADE  FREE" if g.admin else f"UPGRADE  {fmt_money(cost)}", 11, (255, 255, 255) if ok else th["muted"],
                       (r2[0] + r2[2] / 2, r2[1] + 13), "center", bold=True)
            y += 122

    def panel_projects(self, r):
        p, th, g = self.p, self.theme, self.game
        x, y, w = r.x, r.y - self.panel_scroll_y(), r.w
        nxt = max(g.owned) + 1
        for pr in PROJECTS:
            owned = pr.num in g.owned
            cur = pr.num == g.current
            h = 108 if owned else 96
            if y + h > r.y - 10 and y < r.bottom + 10:
                self.card(x, y, w, h)
                if cur:
                    p.rect(th["green"], (x, y, w, h), width=1.5, radius=10)
                p.text(f"PROJECT {pr.num}  •  {pr.name.upper()}", 9, th["muted"], (x + 12, y + 10), bold=True)
                size = f"{pr.w} x {pr.h}"
                if pr.floors > 1:
                    size = f"{pr.floors} floors  •  " + size
                metal = pr.metal + g.upgrades["material"]
                p.text(f"{size}  •  {room_count(pr)} rooms  •  metal limit {metal}", 11, th["text"],
                       (x + 12, y + 26))
                p.text(f"Pays ${pr.pay:.0f}/s at 100% coverage" if pr.pay >= 100 else
                       f"Pays ${pr.pay:.1f}/s at 100% coverage", 11, th["text"], (x + 12, y + 42))
                by = y + 62
                if owned:
                    cov = g.coverage.get(pr.num, 0.0)
                    p.text(f"Coverage {cov * 100:.0f}%  •  earning ${g.project_income(pr.num):.1f}/s", 11,
                           th["text"], (x + 12, y + 58))
                    p.rect(th["border"], (x + 12, y + 75, w - 24, 3), radius=2)
                    p.rect(th["green"], (x + 12, y + 75, (w - 24) * cov, 3), radius=2)
                    by = y + 82
                br = (x + 12, by, w - 24, 22)
                if cur:
                    p.rect(th["border"], br, radius=6)
                    p.text("CURRENT JOB", 10, th["muted"], (br[0] + br[2] / 2, by + 11), "center", bold=True)
                elif owned:
                    hov = self.button(br, lambda n=pr.num: self.goto(n))
                    p.rect(th["accent_soft"] if not hov else th["accent"], br, radius=6)
                    p.text("GO TO PROJECT", 10, th["accent"] if not hov else (255, 255, 255),
                           (br[0] + br[2] / 2, by + 11), "center", bold=True)
                elif pr.playable and (pr.num == nxt or g.admin):
                    ok = g.can_afford(0.0 if g.admin else pr.buy)
                    hov = self.button(br, lambda n=pr.num: self.buy(n))
                    col = th["green"] if ok else th["border"]
                    if ok and hov:
                        col = tuple(max(0, c - 25) for c in col)
                    p.rect(col, br, radius=6)
                    p.text("GET IT FREE" if g.admin else f"BUY  {fmt_money(pr.buy)}", 10, (255, 255, 255) if ok else th["muted"],
                           (br[0] + br[2] / 2, by + 11), "center", bold=True)
                else:
                    p.rect(th["border"], br, radius=6)
                    label = "LOCKED" if pr.playable else "COMING SOON"
                    p.text(label, 10, th["muted"], (br[0] + br[2] / 2, by + 11), "center", bold=True)
            y += h + 10
        self._projects_content_h = y + self.panel_scroll_y() - r.y

    def panel_scroll_y(self):
        return getattr(self, "_proj_scroll", 0.0)

    def panel_settings(self, r):
        p, th = self.p, self.theme
        x, y, w = r.x, r.y - self.settings_scroll_y(), r.w
        top = y

        def choice(label, options, cur, cb, y):
            self.card(x, y, w, 72)
            p.text(label, 9, th["muted"], (x + 12, y + 10), bold=True)
            n = len(options)
            bw = (w - 24 - 6 * (n - 1)) / n
            for i, opt in enumerate(options):
                br = (x + 12 + i * (bw + 6), y + 30, bw, 28)
                act = i == cur
                hov = self.button(br, lambda i=i: cb(i))
                p.rect(th["accent"] if act else (th["border"] if hov else th["panel"]), br, radius=6)
                p.text(opt, 10, (255, 255, 255) if act else th["text"], (br[0] + bw / 2, br[1] + 14), "center",
                       bold=act)
            return y + 82

        y = choice("AIR DETAIL", ["LOW", "MEDIUM", "HIGH"], self.air_detail, self.set_detail, y)
        y = choice("INTERFACE", ["PAPER WHITE", "DARK"], 1 if self.dark else 0, self.set_dark, y)
        y = choice("DIFFICULTY", ["EASY", "NORMAL"], 0 if self.easy else 1, self.set_difficulty, y)

        # updates
        u = self.updater
        self.card(x, y, w, 100)
        p.text("UPDATES", 9, th["muted"], (x + 12, y + 10), bold=True)
        if u.state == "checking":
            status = "Checking\u2026"
        elif u.state == "downloaded":
            status = f"Version {u.downloaded_version} is downloaded."
        elif u.available:
            status = f"Version {u.available['version']} is available."
        elif u.last_result == "up_to_date":
            status = f"You're up to date ({C.VERSION})."
        elif u.last_result == "failed":
            status = "Couldn't reach GitHub."
        else:
            status = f"Version {C.VERSION}."
        p.text(status, 11, th["text"], (x + 12, y + 28))
        br = (x + 12, y + 56, w - 24, 30)
        if u.state == "downloaded":
            hov = self.button(br, self.restart_to_update)
            label = "RESTART TO INSTALL"
        elif u.available:
            hov = self.button(br, self.go_home)
            label = "DOWNLOAD ON THE HOME SCREEN"
        else:
            hov = self.button(br, lambda: self.updater.check(user=True))
            label = "CHECK FOR UPDATES"
        p.rect(th["accent"] if hov else th["accent_soft"], br, radius=6)
        p.text(label, 10, (255, 255, 255) if hov else th["accent"], (br[0] + br[2] / 2, br[1] + 15), "center",
               bold=True)
        y += 110

        # reset
        self.card(x, y, w, 96)
        p.text("SAVE", 9, th["muted"], (x + 12, y + 10), bold=True)
        p.text("Progress saves automatically.", 11, th["text"], (x + 12, y + 28))
        br = (x + 12, y + 52, w - 24, 30)
        hov = self.button(br, self.reset_save)
        armed = getattr(self, "_reset_armed", 0) > time.time()
        p.rect(th["red"] if (hov or armed) else th["panel"], br, radius=6)
        p.rect(th["red"], br, width=1, radius=6)
        p.text("CLICK AGAIN TO ERASE EVERYTHING" if armed else "RESET ALL PROGRESS", 10,
               (255, 255, 255) if (hov or armed) else th["red"], (br[0] + br[2] / 2, br[1] + 15), "center", bold=True)
        y += 106

        # admin
        h = 26 + self.admin_block_height(w - 24)
        self.card(x, y, w, h)
        self.admin_block(x + 12, y + 10, w - 24)
        y += h + 10
        self._settings_content_h = y - top

    def settings_scroll_y(self):
        return getattr(self, "_settings_scroll", 0.0)

    # ------------------------------------------------------------ bottom palette
    def draw_palette(self, r):
        p, th, g = self.p, self.theme, self.game
        p.rect(th["shadow"], (r.x + 2, r.y + 3, r.w, r.h), radius=12)
        p.rect(th["panel"], r, radius=12)
        p.rect(th["border"], r, width=1, radius=12)
        # category tabs
        tx = r.x + 12
        p.rect(th["panel2"], (tx - 4, r.y + 8, 4 * 104 + 6, 24), radius=7)
        for i, cat in enumerate(CATEGORIES):
            br = (tx, r.y + 10, 102, 20)
            act = i == self.category
            hov = self.button(br, lambda i=i: self.set_category(i))
            if act:
                p.rect(th["accent"], br, radius=6)
            p.text(cat, 9, (255, 255, 255) if act else (th["text"] if hov else th["muted"]),
                   (br[0] + 51, br[1] + 10), "center", bold=True)
            tx += 104
        # right buttons
        bx = r.right - 12
        for label, key, cb, on in (("DESELECT", "RMB", self.deselect, False),
                                    ("REMOVE", "X", self.toggle_remove, self.remove_mode),
                                    ("ROTATE", "R", self.rotate, False)):
            bw = p.text_w(label, 9, True) + p.text_w(key, 9) + 26
            bx -= bw + 6
            br = (bx, r.y + 9, bw, 22)
            hov = self.button(br, cb)
            p.rect(th["red"] if on else (th["border"] if hov else th["panel2"]), br, radius=6)
            p.text(label, 9, (255, 255, 255) if on else th["text"], (br[0] + 10, br[1] + 11), "midleft", bold=True)
            p.text(key, 9, (255, 220, 220) if on else th["muted"], (br[0] + br[2] - 9, br[1] + 11), "midright")

        # cards
        parts = by_category(CATEGORIES[self.category])
        area = pygame.Rect(r.x + 8, r.y + 40, r.w - 16, r.h - 48)
        cw, gap = 214, 8
        total = len(parts) * (cw + gap) - gap
        max_scroll = max(0, total - area.w)
        self.palette_scroll = max(0.0, min(self.palette_scroll, max_scroll))
        self._palette_area = area
        self._palette_max = max_scroll
        p.clip(area)
        x = area.x - self.palette_scroll
        for pdef in parts:
            self.draw_card(pdef, pygame.Rect(int(x), area.y, cw, area.h))
            x += cw + gap
        p.clip(None)
        if max_scroll > 0:
            frac = self.palette_scroll / max_scroll
            track = (area.x, area.bottom + 2, area.w, 3)
            p.rect(th["border"], track, radius=2)
            kw = area.w * area.w / total
            p.rect(th["muted"], (area.x + (area.w - kw) * frac, area.bottom + 2, kw, 3), radius=2)

    def draw_card(self, pdef, r):
        p, th, g = self.p, self.theme, self.game
        unlocked = g.unlocked(pdef.id)
        sel = self.selected == pdef.id
        hov = r.collidepoint(self.mouse) and self._palette_area.collidepoint(self.mouse)
        if unlocked:
            self.buttons.append((r.clip(self._palette_area), lambda pid=pdef.id: self.select_part(pid)))
        bg = th["accent_soft"] if sel else (th["panel2"] if not hov else th["border"])
        p.rect(bg, r, radius=10)
        p.rect(th["accent"] if sel else th["border"], r, width=1.5 if sel else 1, radius=10)
        icon = (r.x + 8, r.y + 10, 56, 56)
        p.rect(th["panel"], icon, radius=6)
        p.rect(th["border"], icon, width=1, radius=6)
        # line drawing of the part, open where ducts connect (like the original's cards)
        placed = {"type": pdef.id, "rot": 0, "aim": 2, "open": 0.6, "_joined": list(pdef.ports)}
        T = 40
        ink = th["outline"] if not self.dark else th["text"]
        ix, iy = icon[0] + 8, icon[1] + 8
        draw_part(p, pdef, placed, ix, iy, T, th["panel"], ink, theme=th, stage="stroke")
        draw_part(p, pdef, placed, ix, iy, T, th["panel"], ink, theme=th, stage="deco")
        tx = r.x + 72
        tw = r.w - 80
        fade = th["faint"]
        p.text(pdef.name, 11, th["text"] if unlocked else fade, (tx, r.y + 9), bold=True)
        if unlocked:
            price = g.price(pdef.id)
            p.text(fmt_price(price), 11, th["text"], (tx, r.y + 25), bold=True)
            pw = p.text_w(fmt_price(price), 11, True)
            p.text(f"{pdef.metal:g} metal", 10, th["muted"], (tx + pw + 7, r.y + 26))
            p.text("EFFICIENCY", 7, th["muted"], (tx, r.y + 44), bold=True)
            for i in range(5):
                col = EFF_COLORS[pdef.efficiency] if i < pdef.efficiency else th["border"]
                p.rect(col, (tx + 46 + i * 11, r.y + 45, 9, 4), radius=2)
            lines = p.wrap(pdef.desc, 9, tw)
            maxl = max(1, int((r.h - 60) // 11))
            if len(lines) > maxl:
                lines = lines[:maxl]
                lines[-1] = lines[-1].rstrip(".,") + "\u2026"
            for i, ln in enumerate(lines):
                p.text(ln, 9, th["muted"], (tx, r.y + 57 + i * 11))
        else:
            if pdef.unlock == REWARDS:
                l1, l2 = "Rewards track", "Coming in a later update"
            else:
                pr = project(pdef.unlock)
                l1, l2 = f"Unlocks with Project #{pr.num}", pr.name
            cx = tx + tw / 2 + 6
            p.text(l1, 10, th["text"], (cx, r.y + 44), "center", bold=True)
            p.text(l2, 9, th["muted"], (tx + tw / 2, r.y + 60), "center")
            # padlock
            lx, ly = cx - p.text_w(l1, 10, True) / 2 - 9, r.y + 45
            p.rect((230, 170, 40), (lx - 5, ly - 3, 10, 8), radius=2)
            p.rect((230, 170, 40), (lx - 3.5, ly - 8, 7, 7), width=1.6, radius=3)

    def draw_hints(self, r):
        p, th = self.p, self.theme
        hints = [("B", "build"), ("R", "rotate"), ("T", "aim register"), ("F", "damper"), ("Q", "pick part"),
                 ("X", "remove"), ("Z", "view"), ("Drag", "select"), ("C / V", "copy / paste"), ("WASD", "move"),
                 ("RMB", "pan / drop"), ("Scroll", "zoom"), ("1-4", "categories"), ("Tab", "panels"),
                 (f"{C.MOD_KEY} Z", "undo")]
        widths = [p.text_w(k, 8, True) + 10 + p.text_w(v, 9) + 16 for k, v in hints]
        x = r.centerx - sum(widths) / 2
        cy = r.y + r.h / 2
        for (k, v), w in zip(hints, widths):
            kw = p.text_w(k, 8, True) + 8
            p.rect(th["panel"], (x, cy - 7, kw, 14), radius=4)
            p.rect(th["border"], (x, cy - 7, kw, 14), width=1, radius=4)
            p.text(k, 8, th["text"], (x + kw / 2, cy), "center", bold=True)
            p.text(v, 9, th["muted"], (x + kw + 4, cy), "midleft")
            x += w

    # ------------------------------------------------------------ tooltip / toast
    def inspect_lines(self):
        g = self.game
        t = self.hover_tile
        if not t or not self._in_plan(t) or not self.pv.view.collidepoint(self.mouse):
            return []
        n = g.net
        if tuple(t) == tuple(g.plan.ahu):
            return [("Air Handler", self.theme["text"], True),
                    (f"Blower free air: {n.blower_free:.0f} CFM" if n else "", self.theme["text"], False),
                    (f"Pushing: {n.ahu_flow:.0f} CFM" if n else "", self.theme["text"], False)]
        pl = g.layout.get(tuple(t))
        th = self.theme
        if pl:
            pdef = BY_ID[pl["type"]]
            flow = n.part_flow.get(tuple(t), 0.0) if n else 0.0
            out = [(pdef.name, th["text"], True), (f"Airflow through: {flow:.0f} CFM", th["text"], False),
                   (f"Loss coefficient K = {n.part_k.get(tuple(t), 0):.2f}" if n else "", th["text"], False)]
            if pdef.kind == "terminal":
                into = next((x.cfm for x in n.terminals if x.tile == tuple(t)), 0.0) if n else 0.0
                out[2] = (f"Into the room: {into:.0f} CFM  (T to aim)", th["text"], False)
            if pdef.kind == "damper":
                out.append((f"Damper {damper_open(pl) * 100:.0f}% open  (click to adjust)", th["text"], False))
            if pdef.dampered:
                opens = [exit_open(pdef, pl, d) for d in abs_ports(pdef, pl["rot"]) if not n or d != n.inflow.get(tuple(t))]
                out.append(("Exits: " + ", ".join(f"{v * 100:.0f}%" for v in opens) + " open  (click to adjust)",
                            th["text"], False))
            if n:
                for leak in n.leaks:
                    if leak.tile == tuple(t) and leak.cfm >= 1:
                        out.append((f"Open end leaking {leak.cfm:.0f} CFM! Add an End Cap.", th["red"], False))
                if tuple(t) not in n.connected:
                    out.append(("Not connected to the air handler.", th["red"], False))
            return out
        room = g.plan.room_at(*t)
        if room >= 0:
            rc = self.disp_rooms
            cov = rc[room] if room < len(rc) else 0
            return [(g.plan.rooms[room][0], th["text"], True), (f"Air coverage: {cov * 100:.0f}%", th["text"], False)]
        return []

    def draw_tooltip(self, view):
        if self.drag or not view.collidepoint(self.mouse):
            return
        lines = [l for l in self.inspect_lines() if l[0]]
        if not lines:
            return
        p, th = self.p, self.theme
        w = max(p.text_w(t, 11, b) for t, _, b in lines) + 24
        w = min(w, 280)
        wrapped = []
        for t, col, b in lines:
            for ln in p.wrap(t, 11, w - 24, b):
                wrapped.append((ln, col, b))
        h = 14 + 16 * len(wrapped)
        x, y = self.mouse[0] + 16, self.mouse[1] + 14
        W, H = self.logical
        if x + w > view.right:
            x = self.mouse[0] - w - 10
        if y + h > view.bottom:
            y = self.mouse[1] - h - 10
        p.rect(th["shadow"], (x + 1, y + 2, w, h), radius=8)
        p.rect(th["tooltip"], (x, y, w, h), radius=8)
        p.rect(th["border"], (x, y, w, h), width=1, radius=8)
        for i, (t, col, b) in enumerate(wrapped):
            p.text(t, 11, col, (x + 12, y + 7 + 16 * i), bold=b)

    # ------------------------------------------------------------ damper window
    DIR_NAMES = ["North", "East", "South", "West"]
    DIR_ARROWS = ["\u2191", "\u2192", "\u2193", "\u2190"]

    def popup_rows(self):
        """[(label, abs dir or None, part port or None, open fraction, CFM)] for the open window."""
        t = self.popup
        pl = self.game.layout.get(t) if t else None
        if not pl:
            return None
        pdef = BY_ID[pl["type"]]
        n = self.game.net
        if pdef.kind == "damper":
            return [("Open", None, None, damper_open(pl), n.part_flow.get(t, 0.0) if n else 0.0)]
        if not pdef.dampered:
            return None
        inflow = n.inflow.get(t) if n else None
        rows = []
        for d_abs in sorted(abs_ports(pdef, pl["rot"])):
            if d_abs == inflow:
                continue
            d0 = (d_abs - pl["rot"]) % 4
            cfm = n.port_flow.get((t, d_abs), 0.0) if n else 0.0
            rows.append((f"{self.DIR_ARROWS[d_abs]}  {self.DIR_NAMES[d_abs]} exit", d_abs, d0,
                         exit_open(pdef, pl, d_abs), cfm))
        return rows

    def popup_rect(self, view):
        rows = self.popup_rows() or []
        w, h = 318, 52 + 50 * len(rows) + 8
        tx, ty = self.pv.tile_xy(self.popup)
        T = self.pv.T
        x = tx + T + 10
        if x + w > view.right - 6:
            x = tx - w - 10
        y = max(view.y + 6, min(ty + T / 2 - h / 2, view.bottom - h - 6))
        x = max(view.x + 6, x)
        return pygame.Rect(int(x), int(y), w, h)

    def draw_popup(self, view):
        rows = self.popup_rows()
        if rows is None:
            self.popup = None
            return
        p, th = self.p, self.theme
        r = self.popup_rect(view)
        pl = self.game.layout[self.popup]
        pdef = BY_ID[pl["type"]]
        # outline the part being edited
        tx, ty = self.pv.tile_xy(self.popup)
        p.rect(th["accent"], (tx, ty, self.pv.T, self.pv.T), width=2, radius=4)
        p.rect(th["shadow"], (r.x + 2, r.y + 4, r.w, r.h), radius=12)
        p.rect(th["panel"], r, radius=12)
        p.rect(th["border"], r, width=1, radius=12)
        p.text(pdef.name, 12, th["text"], (r.x + 14, r.y + 12), bold=True)
        p.text("How open each exit is" if pdef.dampered else "How open the damper is", 9, th["muted"],
               (r.x + 14, r.y + 30))
        close = (r.right - 30, r.y + 8, 22, 22)
        self.button(close, self.close_popup)
        p.text("\u00d7", 18, th["muted"], (close[0] + 11, close[1] + 10), "center")
        y = r.y + 52
        if not rows:
            p.text("Connect it to the air handler first.", 11, th["text"], (r.x + 14, y + 6))
        for label, d_abs, d0, val, cfm in rows:
            p.text(label, 11, th["text"], (r.x + 14, y + 2), bold=True)
            p.text(f"{val * 100:.0f}% open  \u2022  {cfm:.0f} CFM", 10, th["muted"], (r.right - 14, y + 3),
                   "topright")
            # SHUT, then ten segments for 10%..100%
            sx, sy = r.x + 14, y + 20
            shut = (sx, sy, 40, 18)
            hov = self.button(shut, lambda d0=d0: self.set_open(d0, 0.0))
            closed = val <= 0.0
            p.rect(th["red"] if closed else (th["border"] if hov else th["panel2"]), shut, radius=5)
            p.text("SHUT", 8, (255, 255, 255) if closed else th["text"], (sx + 20, sy + 9), "center", bold=True)
            seg_x = sx + 46
            seg_w = (r.right - 14 - seg_x - 9 * 3) / 10
            for i in range(10):
                v = (i + 1) / 10
                sr = (seg_x + i * (seg_w + 3), sy, seg_w, 18)
                hov = self.button(sr, lambda d0=d0, v=v: self.set_open(d0, v))
                on = val >= v - 1e-6
                col = th["accent"] if on else (th["border"] if hov else th["panel2"])
                p.rect(col, sr, radius=4)
                if i in (4, 9):
                    p.text(f"{int(v * 100)}", 7, (255, 255, 255) if on else th["muted"],
                           (sr[0] + seg_w / 2, sy + 9), "center", bold=True)
            y += 50

    def set_open(self, port, value):
        self.act({"kind": "set_open", "tile": self.popup, "port": port, "value": value})

    def close_popup(self):
        self.popup = None

    def open_popup(self, tile):
        pl = self.game.layout.get(tuple(tile)) if tile else None
        if pl and (BY_ID[pl["type"]].kind == "damper" or BY_ID[pl["type"]].dampered):
            self.popup = tuple(tile)
            return True
        return False

    def draw_toast(self, view):
        if not self.toast:
            return
        msg, until = self.toast
        left = until - time.time()
        if left <= 0:
            self.toast = None
            return
        p = self.p
        w = p.text_w(msg, 11, True) + 30
        x = view.centerx - w / 2
        y = view.y + 8
        alpha = int(235 * min(1.0, left / 0.4))
        p.rect((30, 32, 40, alpha), (x, y, w, 26), radius=13)
        p.text(msg, 11, (255, 255, 255), (view.centerx, y + 13), "center", bold=True)

    # ------------------------------------------------------------ commands
    def toggle_build(self):
        self.build_mode = not self.build_mode
        if not self.build_mode:
            self.deselect()

    def toggle_panel(self, name):
        self.panel = None if (name is None or self.panel == name) else name

    def set_category(self, i):
        self.category = i
        self.palette_scroll = 0

    def select_part(self, pid):
        if not self.game.unlocked(pid):
            return
        if self.selected == pid:
            self.selected = None
            return
        self.selected = pid
        self.remove_mode = False
        self.paste_mode = False
        self.ghost_aim = None
        self.category = CATEGORIES.index(BY_ID[pid].category)

    def deselect(self):
        self.selected = None
        self.remove_mode = False
        self.paste_mode = False
        self.selection.clear()

    def toggle_remove(self):
        if self.selection:
            self.act({"kind": "remove", "tiles": list(self.selection)})
            self.selection.clear()
            return
        self.remove_mode = not self.remove_mode
        if self.remove_mode:
            self.selected = None
            self.paste_mode = False

    def rotate(self):
        if self.selected:
            self.ghost_rot = (self.ghost_rot + 1) % 4
            if self.ghost_aim is not None:
                self.ghost_aim = (self.ghost_aim + 2) % 8
        elif self.paste_mode and self.clipboard:
            self.clipboard = [((-dy, dx), dict(pl, rot=(pl["rot"] + 1) % 4,
                                               **({"aim": (pl["aim"] + 2) % 8} if "aim" in pl else {})))
                              for (dx, dy), pl in self.clipboard]
        elif self.hover_tile and tuple(self.hover_tile) in self.game.layout:
            self.act({"kind": "rotate_placed", "tile": self.hover_tile})

    def aim(self):
        if self.selected and BY_ID[self.selected].kind == "terminal":
            pdef = BY_ID[self.selected]
            cur = self.ghost_aim if self.ghost_aim is not None else default_aim(pdef, self.ghost_rot)
            self.ghost_aim = (cur + 2) % 8
        elif self.hover_tile:
            self.act({"kind": "aim", "tile": self.hover_tile})

    def damper(self):
        if not self.hover_tile:
            return
        pl = self.game.layout.get(tuple(self.hover_tile))
        if pl and BY_ID[pl["type"]].dampered:
            self.open_popup(self.hover_tile)
        else:
            self.act({"kind": "damper", "tile": self.hover_tile})

    def pick(self):
        t = self.hover_tile
        pl = self.game.layout.get(tuple(t)) if t else None
        if pl:
            if self.selected != pl["type"]:
                self.select_part(pl["type"])
            self.ghost_rot = pl["rot"]
            self.ghost_aim = pl.get("aim")

    def copy(self):
        if not self.selection:
            self._toast("Drag to select parts first")
            return
        xs = [t[0] for t in self.selection]
        ys = [t[1] for t in self.selection]
        ox, oy = min(xs), min(ys)
        self.clipboard = [((t[0] - ox, t[1] - oy), dict(self.game.layout[t]))
                          for t in self.selection if t in self.game.layout]
        self._toast(f"Copied {len(self.clipboard)} parts. Press V to paste.")

    def paste(self):
        if not self.clipboard:
            self._toast("Nothing copied yet")
            return
        self.paste_mode = True
        self.selected = None
        self.remove_mode = False

    def goto(self, n):
        self.act({"kind": "goto_project", "num": n})
        self.deselect()

    def buy(self, n):
        if self.act({"kind": "buy_project", "num": n}):
            self._toast(f"Welcome to {project(n).name}! New parts unlocked.", 4)
            self.deselect()

    def set_detail(self, i):
        self.air_detail = i
        self.version += 1
        self._anim_dirty = True
        self.save_settings()

    def set_difficulty(self, i):
        self.easy = i == 0
        self.game.easy = self.easy
        self.game.dirty = True
        self.save_settings()

    def set_dark(self, i):
        self.dark = bool(i)
        self.save_settings()

    def reset_save(self):
        if getattr(self, "_reset_armed", 0) > time.time():
            self.game.reset()
            self.game.admin = bool(self.admin_key and self.admin_on)
            self.game.easy = self.easy
            self.game.save()
            self.pv.fitted_for = None
            self.deselect()
            self._toast("Progress reset")
            self._reset_armed = 0
        else:
            self._reset_armed = time.time() + 3

    # ------------------------------------------------------------ input
    def _in_plan(self, t):
        pl = self.game.plan
        return t is not None and 0 <= t[0] < pl.w and 0 <= t[1] < pl.h

    def smart_rot(self, pid, t):
        """Single-port parts (registers, caps) turn to face an adjoining duct."""
        pdef = BY_ID[pid]
        if len(pdef.ports) != 1 or t is None:
            return self.ghost_rot
        g = self.game
        base = next(iter(pdef.ports))

        def connects(rot):
            d = (base + rot) % 4
            nb = (t[0] + DIRS[d][0], t[1] + DIRS[d][1])
            if nb == tuple(g.plan.ahu):
                return True
            pl = g.layout.get(nb)
            return bool(pl) and (d + 2) % 4 in abs_ports(BY_ID[pl["type"]], pl["rot"])

        if connects(self.ghost_rot):
            return self.ghost_rot
        for r in range(4):
            if connects(r):
                return r
        return self.ghost_rot

    def place_at(self, t, drag_dir=None):
        if not self._in_plan(t):
            return
        rot = self.smart_rot(self.selected, t)
        if rot != self.ghost_rot and self.ghost_aim is not None:
            self.ghost_aim = None
        if self.selected in STRAIGHTS and drag_dir is not None:
            rot = 0 if drag_dir[0] != 0 else 1
            self.ghost_rot = rot
        pdef = BY_ID[self.selected]
        a = {"kind": "place", "type": self.selected, "tile": t, "rot": rot}
        if pdef.kind == "terminal":
            a["aim"] = self.ghost_aim if self.ghost_aim is not None else default_aim(pdef, rot)
        self.act(a)

    def handle(self, ev):
        t = ev.type
        if self.key_input(ev):
            return
        if t == pygame.QUIT:
            self.running = False
        elif t in (getattr(pygame, "WINDOWSIZECHANGED", -1), getattr(pygame, "WINDOWRESIZED", -1),
                   getattr(pygame, "VIDEORESIZE", -1), getattr(pygame, "WINDOWDISPLAYCHANGED", -1)):
            self._refresh_surface()
        elif t == pygame.MOUSEMOTION:
            self.mouse = ev.pos
            self.hover_tile = self.pv.tile_at(*ev.pos)
            self.on_drag(ev)
        elif t == pygame.MOUSEBUTTONDOWN:
            self.mouse = ev.pos
            self.hover_tile = self.pv.tile_at(*ev.pos)
            if ev.button == 1:
                self.on_left_down(ev.pos)
            elif ev.button == 3:
                self.drag = {"kind": "pan", "start": ev.pos, "last": ev.pos, "moved": 0.0}
        elif t == pygame.MOUSEBUTTONUP:
            if ev.button == 1 and self.drag and self.drag["kind"] == "select":
                self.finish_select(ev.pos)
            if ev.button == 3 and self.drag and self.drag["kind"] == "pan" and self.drag["moved"] < 4:
                self.deselect()
            if ev.button in (1, 3):
                self.drag = None
        elif t == pygame.MOUSEWHEEL:
            self.on_wheel(ev)
        elif t == pygame.KEYDOWN:
            self.on_key(ev)

    def on_left_down(self, pos):
        self.key_focus = False          # clicking anywhere else leaves the key field
        for r, cb in reversed(self.buttons):
            if r.collidepoint(pos):
                cb()
                return
        if self.screen != "game":
            return
        if self.popup is not None:
            inside = self.popup_rect(self.pv.view).collidepoint(pos)
            self.popup = None           # a click outside the window closes it
            if inside:
                return
            if self.pv.view.collidepoint(pos) and self.open_popup(self.pv.tile_at(*pos)) and not self.selected:
                return
            return
        rects = self.layout_rects()
        if self.panel and rects["panel"].collidepoint(pos):
            return
        if self.build_mode and rects["bottom"].collidepoint(pos):
            return
        if not self.pv.view.collidepoint(pos) or not self.build_mode:
            if self.pv.view.collidepoint(pos):
                self.drag = {"kind": "pan", "start": pos, "last": pos, "moved": 10.0}
            return
        tile = self.pv.tile_at(*pos)
        if self.paste_mode and self.clipboard:
            items = [((tile[0] + dx, tile[1] + dy), pl) for (dx, dy), pl in self.clipboard]
            self.act({"kind": "paste", "items": items})
            return
        if self.remove_mode:
            self.act({"kind": "remove", "tiles": [tile]})
            self.drag = {"kind": "remove", "last": tile}
            return
        if self.selected:
            self.place_at(tile)
            self.drag = {"kind": "place", "last": tile}
            return
        if self.open_popup(tile):
            return
        self.selection.clear()
        self.drag = {"kind": "select", "start": pos}

    def on_drag(self, ev):
        d = self.drag
        if not d or self.screen != "game":
            return
        if d["kind"] == "pan":
            dx, dy = ev.pos[0] - d["last"][0], ev.pos[1] - d["last"][1]
            d["moved"] += abs(dx) + abs(dy)
            d["last"] = ev.pos
            self.pv.ox += dx
            self.pv.oy += dy
        elif d["kind"] in ("place", "remove"):
            tile = self.pv.tile_at(*ev.pos)
            if tile != d["last"]:
                # fill every tile between (fast drags skip tiles)
                lx, ly = d["last"]
                steps = max(abs(tile[0] - lx), abs(tile[1] - ly))
                for i in range(1, steps + 1):
                    tx = lx + round((tile[0] - lx) * i / steps)
                    ty = ly + round((tile[1] - ly) * i / steps)
                    step_dir = (tx - lx, ty - ly)
                    if d["kind"] == "place":
                        if self.selected in STRAIGHTS:
                            # re-orient the previous straight to the drag axis too
                            prev = self.game.layout.get((lx, ly))
                            want = 0 if step_dir[0] != 0 else 1
                            if prev and prev["type"] in STRAIGHTS and prev["rot"] % 2 != want and \
                                    d.get("count", 0) == 0:
                                self.place_at((lx, ly), step_dir)
                        self.place_at((tx, ty), step_dir)
                        d["count"] = d.get("count", 0) + 1
                    else:
                        self.act({"kind": "remove", "tiles": [(tx, ty)]})
                    lx, ly = tx, ty
                d["last"] = tile

    def finish_select(self, pos):
        (ax, ay) = self.drag["start"]
        bx, by = pos
        if abs(bx - ax) + abs(by - ay) < 5:
            return
        t0 = self.pv.tile_at(min(ax, bx), min(ay, by))
        t1 = self.pv.tile_at(max(ax, bx), max(ay, by))
        self.selection = {t for t in self.game.layout
                          if t0[0] <= t[0] <= t1[0] and t0[1] <= t[1] <= t1[1]}
        if self.selection:
            self._toast(f"{len(self.selection)} selected  •  C copy  •  X remove")

    def on_wheel(self, ev):
        if self.screen != "game":
            return
        rects = self.layout_rects()
        if self.build_mode and rects["bottom"].collidepoint(self.mouse):
            self.palette_scroll -= (ev.precise_y if hasattr(ev, "precise_y") else ev.y) * 40
            self.palette_scroll += (ev.precise_x if hasattr(ev, "precise_x") else ev.x) * 40
            return
        if self.panel == "SETTINGS" and rects["panel"].collidepoint(self.mouse):
            mx = max(0, getattr(self, "_settings_content_h", 0) - (rects["panel"].h - 64))
            self._settings_scroll = max(0.0, min(mx, self.settings_scroll_y() - ev.precise_y * 30))
            return
        if self.panel == "PROJECTS" and rects["panel"].collidepoint(self.mouse):
            mx = max(0, getattr(self, "_projects_content_h", 0) - (rects["panel"].h - 64))
            self._proj_scroll = max(0.0, min(mx, self.panel_scroll_y() - ev.precise_y * 30))
            return
        if self.pv.view.collidepoint(self.mouse):
            y = ev.precise_y if hasattr(ev, "precise_y") else ev.y
            self.pv.zoom_at(1.0 + 0.1 * max(-3, min(3, y)), *self.mouse)
            self.version += 1

    def on_key(self, ev):
        k = ev.key
        mods = ev.mod
        cmd = mods & (pygame.KMOD_META | pygame.KMOD_CTRL)
        if cmd and k == pygame.K_z:
            if self.game.undo():
                self.version += 1
                self._toast("Undo")
            return
        if self.screen != "game":
            self.home_key(k, cmd)
            return
        if cmd and k == pygame.K_q:
            self.running = False
            return
        if cmd:
            return
        if k == pygame.K_b:
            self.toggle_build()
        elif k == pygame.K_r:
            self.rotate()
        elif k == pygame.K_t:
            self.aim()
        elif k == pygame.K_f:
            self.damper()
        elif k == pygame.K_q:
            self.pick()
        elif k == pygame.K_x:
            self.toggle_remove()
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
            if self.selection:
                self.act({"kind": "remove", "tiles": list(self.selection)})
                self.selection.clear()
            elif self.hover_tile:
                self.act({"kind": "remove", "tiles": [self.hover_tile]})
        elif k == pygame.K_z:
            self.view_mode = (self.view_mode + 1) % 3
            self._toast(["Showing ducts + air", "Showing ducts only", "Showing air only"][self.view_mode])
        elif k == pygame.K_c:
            self.copy()
        elif k == pygame.K_v:
            self.paste()
        elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            self.set_category(k - pygame.K_1)
        elif k == pygame.K_TAB:
            i = PANELS.index(self.panel) + 1 if self.panel else 0
            self.panel = PANELS[i] if i < len(PANELS) else None
        elif k == pygame.K_ESCAPE:
            if self.popup is not None:
                self.popup = None
            elif self.selected or self.remove_mode or self.paste_mode or self.selection:
                self.deselect()
            else:
                self.go_home()
        elif k in (pygame.K_w, pygame.K_UP):
            self.pv.oy += 60
        elif k in (pygame.K_s, pygame.K_DOWN):
            self.pv.oy -= 60
        elif k in (pygame.K_a, pygame.K_LEFT):
            self.pv.ox += 60
        elif k in (pygame.K_d, pygame.K_RIGHT):
            self.pv.ox -= 60
        elif k == pygame.K_HOME:
            self.pv.fitted_for = None


def main():
    App().run()
