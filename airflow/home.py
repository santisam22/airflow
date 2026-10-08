"""Home screen: shown at every launch over a blurred view of the current house.

Play, Settings, How to play and Quit live here, and so do updates: when one is out,
a card offers DOWNLOAD UPDATE (nothing downloads on its own). When the download is
verified, a banner drops down from the top: "Update x.y.z downloaded". The new
version is swapped in when the player clicks RESTART NOW, or when they quit.
"""

import math
import time

import pygame

from . import admin
from . import config as C
from .parts import fmt_money
from .projects import project

HOME_PAGES = ("main", "settings", "help")
BANNER_SECS = 4.5

CONTROLS = [
    ("B", "Build mode on / off"), ("R", "Rotate part"), ("T", "Aim a register"), ("F", "Adjust a damper"),
    ("Q", "Pick the hovered part"), ("X", "Remove mode"), ("Z", "Switch view"), ("Drag", "Select parts"),
    ("C / V", "Copy / paste"), ("Cmd Z", "Undo"), ("WASD", "Move the camera"), ("Scroll", "Zoom"),
    ("1-4", "Part categories"), ("Tab", "Cycle panels"), ("Esc", "Home screen"),
]

HOW_TO = [
    "Run Galvanized Duct out of the AHU (the air handler) toward each room.",
    "End every run in a room with a register or diffuser. Press T to aim it.",
    "Use T-Branches to split the air. Cap any open end, or it leaks into the attic.",
    "Each project pays per second by its air coverage. Spend it on upgrades and bigger houses.",
]


class HomeMixin:
    # ------------------------------------------------------------ state
    def init_home(self):
        self.screen = "home"
        self.home_page = "main"
        self._home_bg = None
        self._home_bg_at = -1.0
        self.banner = None              # (title, subtitle, started_at)
        self._announced = None
        self._first_play = True

    def play(self):
        self.screen = "game"
        self.home_page = "main"
        if self._first_play:
            self._first_play = False
            if not self.game.layout:
                self._toast("Pick a part below, then click the plan to place it. "
                            "Connect ducts from the AHU into rooms!", 6)

    def go_home(self):
        self.deselect()
        self.drag = None
        self.screen = "home"
        self.home_page = "main"
        try:
            self.game.save()
        except OSError:
            pass

    def quit_game(self):
        self.running = False

    def start_download(self):
        u = self.updater
        if u.state == "error":
            u.state = "idle"
        u.download()

    def restart_to_update(self):
        self.game.save()
        self.save_settings()
        self.updater.restart()

    def show_banner(self, title, subtitle=""):
        self.banner = (title, subtitle, time.time())

    def watch_updates(self):
        """Called every frame: announce a finished download once."""
        u = self.updater
        if u.state == "downloaded" and self._announced != u.downloaded_version:
            self._announced = u.downloaded_version
            self.show_banner(f"Update {u.downloaded_version} downloaded",
                             "Restart Airflow to start using it.")

    # ------------------------------------------------------------ drawing
    def draw_home(self):
        p, th = self.p, self.theme
        W, H = self.logical
        self._draw_home_bg()
        if self.home_page == "settings":
            self._home_settings()
        elif self.home_page == "help":
            self._home_help()
        else:
            self._home_main()
        self._home_update_card()
        p.text(f"{C.APP_NAME} {C.VERSION}", 10, th["muted"], (16, H - 14), "midleft")

    def _draw_home_bg(self):
        """The current house, live, blurred and dimmed (re-blurred ~12 times a second)."""
        now = self.t
        if self._home_bg is None or now - self._home_bg_at > 1 / 12 or \
                self._home_bg.get_size() != self.surf.get_size():
            saved_mouse, saved_toast, saved_buttons = self.mouse, self.toast, self.buttons
            self.mouse, self.toast = (-9999, -9999), None
            self.draw_game(ui=False)
            self.mouse, self.toast, self.buttons = saved_mouse, saved_toast, saved_buttons
            w, h = self.surf.get_size()
            small = pygame.transform.smoothscale(self.surf, (max(1, w // 12), max(1, h // 12)))
            small = pygame.transform.smoothscale(small, (max(1, w // 24), max(1, h // 24)))
            self._home_bg = pygame.transform.smoothscale(small, (w, h))
            self._home_bg_at = now
        self.surf.blit(self._home_bg, (0, 0))
        W, H = self.logical
        dim = (14, 15, 20, 150) if self.dark else (246, 246, 244, 150)
        self.p.rect_alpha(dim, (0, 0, W, H))

    def _panel(self, x, y, w, h):
        p, th = self.p, self.theme
        p.rect((0, 0, 0, 40), (x + 2, y + 6, w, h), radius=18)
        p.rect(th["panel"], (x, y, w, h), radius=18)
        p.rect(th["border"], (x, y, w, h), width=1, radius=18)

    def _big_button(self, r, label, cb, primary=False, hint=""):
        p, th = self.p, self.theme
        hov = self.button(r, cb)
        if primary:
            col = th["accent"]
            if hov:
                col = tuple(max(0, c - 22) for c in col)
            p.rect(col, r, radius=11)
            fg = (255, 255, 255)
        else:
            p.rect(th["border"] if hov else th["panel2"], r, radius=11)
            p.rect(th["border"], r, width=1, radius=11)
            fg = th["text"]
        p.text(label, 13, fg, (r[0] + r[2] / 2, r[1] + r[3] / 2), "center", bold=True)
        if hint:
            p.text(hint, 9, (210, 220, 255) if primary else th["muted"], (r[0] + r[2] - 14, r[1] + r[3] / 2),
                   "midright", bold=True)

    def _logo(self, cx, cy, size):
        p, th = self.p, self.theme
        p.rect(th["accent"], (cx - size / 2, cy - size / 2, size, size), radius=size * 0.24)
        r = size * 0.2
        for k in range(3):
            a = k * 2 * math.pi / 3 - math.pi / 2 + self.t * 0.6
            p.circle((255, 255, 255), (cx + math.cos(a) * r, cy + math.sin(a) * r), size * 0.16)
        p.circle(th["accent"], (cx, cy), size * 0.1)
        p.circle((255, 255, 255), (cx, cy), size * 0.045)

    def _home_main(self):
        p, th, g = self.p, self.theme, self.game
        W, H = self.logical
        pw, ph = 380, 418
        x, y = W / 2 - pw / 2, H / 2 - ph / 2 - 20
        self._panel(x, y, pw, ph)
        self._logo(W / 2, y + 62, 64)
        p.text(C.APP_NAME.upper(), 30, th["text"], (W / 2, y + 108), "midtop", bold=True)
        plan = project(g.current)
        started = bool(g.layout) or len(g.owned) > 1 or g.money > C.STARTING_MONEY + 1
        if started:
            sub = f"Project {plan.num}  •  {plan.name}  •  {fmt_money(g.money)}"
        else:
            sub = "Get the air where it needs to go."
        p.text(sub, 11, th["muted"], (W / 2, y + 148), "midtop")
        bx, bw, bh = x + 36, pw - 72, 46
        by = y + 186
        self._big_button((bx, by, bw, bh), "CONTINUE" if started else "PLAY", self.play, primary=True,
                         hint="ENTER")
        self._big_button((bx, by + bh + 12, bw, bh), "SETTINGS", lambda: self._open_page("settings"))
        self._big_button((bx, by + 2 * (bh + 12), bw, bh), "HOW TO PLAY", lambda: self._open_page("help"))
        self._big_button((bx, by + 3 * (bh + 12), bw, bh), "QUIT", self.quit_game, hint="CMD Q")

    def _open_page(self, page):
        self.home_page = page

    def _back(self, x, y):
        p, th = self.p, self.theme
        r = (x, y, 76, 28)
        hov = self.button(r, lambda: self._open_page("main"))
        p.rect(th["border"] if hov else th["panel2"], r, radius=8)
        p.text("←  BACK", 10, th["text"], (x + 38, y + 14), "center", bold=True)

    def _choice_row(self, x, y, w, label, options, cur, cb):
        p, th = self.p, self.theme
        p.text(label, 9, th["muted"], (x, y), bold=True)
        n = len(options)
        gap = 8
        bw = (w - gap * (n - 1)) / n
        for i, opt in enumerate(options):
            r = (x + i * (bw + gap), y + 18, bw, 34)
            act = i == cur
            hov = self.button(r, lambda i=i: cb(i))
            p.rect(th["accent"] if act else (th["border"] if hov else th["panel2"]), r, radius=8)
            p.text(opt, 11, (255, 255, 255) if act else th["text"], (r[0] + bw / 2, r[1] + 17), "center", bold=act)
        return y + 70

    def _home_settings(self):
        p, th = self.p, self.theme
        W, H = self.logical
        pw, ph = 460, 548
        x, y = W / 2 - pw / 2, max(12, H / 2 - ph / 2 - 20)
        self._panel(x, y, pw, ph)
        self._back(x + 20, y + 20)
        p.text("Settings", 22, th["text"], (W / 2, y + 22), "midtop", bold=True)
        ix, iw = x + 32, pw - 64
        yy = y + 80
        yy = self._choice_row(ix, yy, iw, "AIR DETAIL", ["LOW", "MEDIUM", "HIGH"], self.air_detail, self.set_detail)
        yy = self._choice_row(ix, yy, iw, "INTERFACE", ["PAPER WHITE", "DARK MODE"], 1 if self.dark else 0,
                              self.set_dark)
        # updates
        u = self.updater
        p.text("UPDATES", 9, th["muted"], (ix, yy), bold=True)
        if u.state == "checking":
            status = "Checking for updates…"
        elif u.state == "downloaded":
            status = f"Version {u.downloaded_version} is downloaded. Restart to install it."
        elif u.available:
            status = f"Version {u.available['version']} is available."
        elif u.last_result == "up_to_date":
            status = f"You're up to date ({C.VERSION})."
        elif u.last_result == "failed":
            status = "Couldn't reach GitHub."
        else:
            status = f"Version {C.VERSION}. Checks automatically every few hours."
        p.text(status, 11, th["text"], (ix, yy + 18))
        r = (ix, yy + 40, iw, 34)
        hov = self.button(r, lambda: self.updater.check(user=True))
        p.rect(th["border"] if hov else th["panel2"], r, radius=8)
        p.text("CHECK FOR UPDATES", 11, th["text"], (r[0] + iw / 2, r[1] + 17), "center", bold=True)
        yy += 96
        # reset
        p.text("SAVE", 9, th["muted"], (ix, yy), bold=True)
        p.text("Progress saves automatically.", 11, th["text"], (ix, yy + 18))
        r = (ix, yy + 40, iw, 34)
        hov = self.button(r, self.reset_save)
        armed = getattr(self, "_reset_armed", 0) > time.time()
        p.rect(th["red"] if (hov or armed) else th["panel"], r, radius=8)
        p.rect(th["red"], r, width=1, radius=8)
        p.text("CLICK AGAIN TO ERASE EVERYTHING" if armed else "RESET ALL PROGRESS", 11,
               (255, 255, 255) if (hov or armed) else th["red"], (r[0] + iw / 2, r[1] + 17), "center", bold=True)
        yy += 96
        self.admin_block(ix, yy, iw)

    def _home_help(self):
        p, th = self.p, self.theme
        W, H = self.logical
        pw, ph = 620, 520
        x, y = W / 2 - pw / 2, H / 2 - ph / 2 - 20
        self._panel(x, y, pw, ph)
        self._back(x + 20, y + 20)
        p.text("How to play", 22, th["text"], (W / 2, y + 22), "midtop", bold=True)
        ix, iw = x + 32, pw - 64
        yy = y + 74
        for i, line in enumerate(HOW_TO):
            p.circle(th["accent"], (ix + 10, yy + 9), 10)
            p.text(str(i + 1), 10, (255, 255, 255), (ix + 10, yy + 9), "center", bold=True)
            for j, ln in enumerate(p.wrap(line, 12, iw - 34)):
                p.text(ln, 12, th["text"], (ix + 30, yy + 1 + j * 17))
            yy += 17 * len(p.wrap(line, 12, iw - 34)) + 12
        yy += 6
        p.text("CONTROLS", 9, th["muted"], (ix, yy), bold=True)
        yy += 18
        col_w = iw / 2
        for i, (k, v) in enumerate(CONTROLS):
            cx = ix + (i % 2) * col_w
            cy = yy + (i // 2) * 24
            kw = p.text_w(k, 9, True) + 12
            p.rect(th["panel2"], (cx, cy, kw, 18), radius=5)
            p.rect(th["border"], (cx, cy, kw, 18), width=1, radius=5)
            p.text(k, 9, th["text"], (cx + kw / 2, cy + 9), "center", bold=True)
            p.text(v, 11, th["muted"], (cx + kw + 8, cy + 9), "midleft")

    def _home_update_card(self):
        """Bottom-right card: only shown when there's something to do."""
        u = self.updater
        info = u.available
        if not info and u.state not in ("downloaded", "error"):
            return
        if u.state == "error" and not info:
            return
        p, th = self.p, self.theme
        W, H = self.logical
        w, h = 330, 128
        x, y = W - w - 20, H - h - 20
        self._panel(x, y, w, h)
        ver = u.downloaded_version or (info or {}).get("version", "")
        notes = (info or {}).get("notes") or ""
        p.circle(th["green"] if u.state == "downloaded" else th["accent"], (x + 22, y + 24), 5)
        title = f"Update {ver} downloaded" if u.state == "downloaded" else f"Airflow {ver} is available"
        p.text(title, 13, th["text"], (x + 34, y + 24), "midleft", bold=True)
        if u.state == "error":
            body, col = u.message, th["red"]
        elif u.state == "downloaded":
            body, col = "Restart now, or it installs the next time you quit.", th["muted"]
        else:
            body, col = notes or "A new version of Airflow is ready to download.", th["muted"]
        lines = p.wrap(body, 10, w - 40)[:2]
        for i, ln in enumerate(lines):
            p.text(ln, 10, col, (x + 20, y + 42 + i * 14))
        r = (x + 20, y + h - 46, w - 40, 32)
        if u.state == "downloading":
            p.rect(th["panel2"], r, radius=8)
            p.rect(th["accent"], (r[0], r[1], r[2] * max(0.04, u.progress), r[3]), radius=8)
            p.text(f"DOWNLOADING… {u.progress * 100:.0f}%", 11, th["text"] if u.progress < 0.5 else (255, 255, 255),
                   (r[0] + r[2] / 2, r[1] + 16), "center", bold=True)
        elif u.state == "downloaded":
            self._big_button(r, "RESTART NOW", self.restart_to_update, primary=True)
        elif u.state == "restarting":
            p.rect(th["panel2"], r, radius=8)
            p.text("RESTARTING…", 11, th["text"], (r[0] + r[2] / 2, r[1] + 16), "center", bold=True)
        else:
            self._big_button(r, "TRY AGAIN" if u.state == "error" else "DOWNLOAD UPDATE", self.start_download,
                             primary=True)

    def draw_banner(self):
        """'Update x downloaded' drops down from the top, waits, then slides back up."""
        if not self.banner:
            return
        title, sub, t0 = self.banner
        age = time.time() - t0
        if age > BANNER_SECS:
            self.banner = None
            return
        p, th = self.p, self.theme
        W, _ = self.logical
        slide = 0.35
        if age < slide:
            k = 1 - (1 - age / slide) ** 3
        elif age > BANNER_SECS - slide:
            k = ((BANNER_SECS - age) / slide) ** 2
        else:
            k = 1.0
        w = max(p.text_w(title, 14, True), p.text_w(sub, 11)) + 76
        h = 58 if sub else 42
        x = W / 2 - w / 2
        y = -h - 10 + (h + 26) * k
        p.rect((0, 0, 0, 50), (x + 1, y + 4, w, h), radius=16)
        p.rect(th["green"], (x, y, w, h), radius=16)
        # check mark
        cx, cy = x + 30, y + h / 2
        p.circle((255, 255, 255), (cx, cy), 12)
        p.line(th["green"], (cx - 6, cy + 0.5), (cx - 1.5, cy + 5), 3)
        p.line(th["green"], (cx - 1.5, cy + 5), (cx + 6.5, cy - 4.5), 3)
        p.text(title, 14, (255, 255, 255), (x + 52, y + (14 if sub else h / 2)), "midleft" if not sub else "topleft",
               bold=True)
        if sub:
            p.text(sub, 11, (235, 255, 235), (x + 52, y + 33))

    # ------------------------------------------------------------ admin
    ADMIN_LOCKED = "Enter the admin key to unlock admin mode."
    ADMIN_ON = "Infinite money and metal, every part and house unlocked."

    def admin_block_height(self, w):
        text = self.ADMIN_ON if self.admin_key else self.ADMIN_LOCKED
        extra = 16 * (len(self.p.wrap(text, 11, w)) - 1)
        return (96 if not self.admin_key else 100) + extra

    def admin_block(self, x, y, w):
        """Admin section shared by both Settings screens. Returns its height."""
        p, th = self.p, self.theme
        p.text("ADMIN", 9, th["muted"], (x, y), bold=True)
        text = self.ADMIN_ON if self.admin_key else self.ADMIN_LOCKED
        lines = p.wrap(text, 11, w)
        for i, ln in enumerate(lines):
            p.text(ln, 11, th["text"], (x, y + 18 + 16 * i))
        y += 16 * (len(lines) - 1)
        if not self.admin_key:
            fw = w - 96
            fr = (x, y + 40, fw, 34)
            self.button(fr, self.focus_key)
            focus = self.key_focus
            p.rect(th["panel"], fr, radius=8)
            p.rect(th["accent"] if focus else th["border"], fr, width=1.5 if focus else 1, radius=8)
            shown = "\u2022" * len(self.key_text)
            if shown:
                p.text(shown, 13, th["text"], (fr[0] + 12, fr[1] + 17), "midleft")
            elif not focus:
                p.text("XXXX-XXXX-XXXX-XXXX", 11, th["faint"], (fr[0] + 12, fr[1] + 17), "midleft")
            if focus and int(self.t * 2) % 2 == 0:
                cx = fr[0] + 13 + (p.text_w(shown, 13) if shown else 0)
                p.line(th["text"], (cx, fr[1] + 9), (cx, fr[1] + 25), 1.5)
            br = (x + fw + 8, y + 40, 88, 34)
            hov = self.button(br, self.submit_key)
            col = th["accent"] if not hov else tuple(max(0, c - 22) for c in th["accent"])
            p.rect(col, br, radius=8)
            p.text("UNLOCK", 11, (255, 255, 255), (br[0] + 44, br[1] + 17), "center", bold=True)
            if self.key_error > time.time():
                p.text("That key isn't right.", 10, th["red"], (x, y + 80))
            return self.admin_block_height(w)
        on = self.admin_on
        half = (w - 8) / 2
        for i, (label, val) in enumerate((("OFF", False), ("ON", True))):
            r = (x + i * (half + 8), y + 40, half, 34)
            act = on == val
            hov = self.button(r, lambda v=val: self.set_admin(v))
            col = (th["red"] if val else th["accent"]) if act else (th["border"] if hov else th["panel2"])
            p.rect(col, r, radius=8)
            p.text(f"ADMIN MODE {label}", 11, (255, 255, 255) if act else th["text"], (r[0] + half / 2, r[1] + 17),
                   "center", bold=act)
        r = (x, y + 80, p.text_w("Forget admin key", 10) + 4, 16)
        hov = self.button(r, self.forget_key)
        p.text("Forget admin key", 10, th["text"] if hov else th["muted"], (x, y + 81))
        return self.admin_block_height(w)

    def focus_key(self):
        self.key_focus = True

    def submit_key(self):
        if admin.check(self.key_text):
            self.admin_key = admin.normalise(self.key_text)
            self.key_text = ""
            self.key_focus = False
            self.set_admin(True)
            self.show_banner("Admin mode unlocked", "Infinite money and metal, everything unlocked.")
        else:
            self.key_error = time.time() + 3
            self.key_text = ""

    def set_admin(self, on):
        self.admin_on = bool(on)
        self.game.admin = bool(self.admin_key and self.admin_on)
        self.game.dirty = True
        self.save_settings()

    def forget_key(self):
        self.admin_key = ""
        self.set_admin(False)

    def key_input(self, ev):
        """Typing into the admin key field. Returns True if the event was used."""
        if not self.key_focus:
            return False
        if ev.type == pygame.TEXTINPUT:
            if len(self.key_text) < 24:
                self.key_text += "".join(ch for ch in ev.text if ch.isalnum() or ch == "-")
            return True
        if ev.type == pygame.KEYDOWN:
            cmd = ev.mod & (pygame.KMOD_META | pygame.KMOD_CTRL)
            if ev.key == pygame.K_BACKSPACE:
                self.key_text = "" if cmd else self.key_text[:-1]
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.submit_key()
            elif ev.key == pygame.K_ESCAPE:
                self.key_focus = False
            elif cmd and ev.key == pygame.K_v:
                try:
                    from pygame import scrap
                    txt = scrap.get_text() or ""
                except Exception:
                    txt = ""
                self.key_text = (self.key_text + "".join(ch for ch in txt if ch.isalnum() or ch == "-"))[:24]
            elif cmd and ev.key == pygame.K_q:
                return False
            return True
        return False

    # ------------------------------------------------------------ input
    def home_key(self, k, cmd):
        if cmd and k == pygame.K_q:
            self.quit_game()
        elif k == pygame.K_ESCAPE:
            if self.home_page != "main":
                self.home_page = "main"
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) and self.home_page == "main":
            self.play()
