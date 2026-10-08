"""Thin drawing layer: all game code works in logical points and the painter
scales to the real pixel surface (2x on Retina)."""

import os
import sys

import pygame

FONT_PATHS = {
    False: ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arial.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    True: ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
           os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arialbd.ttf"),
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def _font_file(bold):
    for p in FONT_PATHS[bold]:
        if os.path.exists(p):
            return p
    return None


LIGHT = {
    "bg": (246, 246, 244),
    "floor": (255, 255, 255),
    "grid": (236, 237, 240),
    "panel": (255, 255, 255),
    "panel2": (248, 249, 251),
    "border": (226, 228, 233),
    "text": (24, 26, 32),
    "muted": (120, 124, 135),
    "faint": (170, 174, 184),
    "wall": (22, 22, 26),
    "door": (190, 192, 198),
    "furn": (196, 198, 204),
    "furn_text": (160, 163, 172),
    "accent": (38, 72, 222),
    "accent_soft": (226, 233, 255),
    "green": (96, 200, 60),
    "red": (220, 52, 52),
    "outline": (28, 30, 38),
    "ghost": (205, 214, 236),
    "ghost_bad": (246, 180, 180),
    "tooltip": (255, 255, 255),
    "shadow": (0, 0, 0, 30),
}

DARK = {
    "bg": (20, 22, 27),
    "floor": (32, 35, 42),
    "grid": (40, 43, 51),
    "panel": (34, 37, 45),
    "panel2": (42, 46, 55),
    "border": (56, 60, 72),
    "text": (232, 234, 240),
    "muted": (150, 155, 168),
    "faint": (100, 105, 118),
    "wall": (226, 228, 234),
    "door": (88, 92, 104),
    "furn": (74, 78, 90),
    "furn_text": (110, 115, 128),
    "accent": (92, 128, 255),
    "accent_soft": (44, 54, 92),
    "green": (110, 210, 80),
    "red": (240, 80, 80),
    "outline": (10, 12, 16),
    "ghost": (70, 82, 120),
    "ghost_bad": (130, 60, 60),
    "tooltip": (44, 48, 58),
    "shadow": (0, 0, 0, 60),
}


class Painter:
    def __init__(self, surf, scale):
        self.surf = surf
        self.s = scale
        self._fonts = {}
        self._text_cache = {}
        self.theme = LIGHT

    def set_surface(self, surf, scale):
        if scale != self.s:
            self._fonts.clear()
            self._text_cache.clear()
        self.surf = surf
        self.s = scale

    # --------------------------------------------------------------- fonts
    def font(self, size, bold=False):
        key = (size, bold)
        f = self._fonts.get(key)
        if f is None:
            px = max(6, int(round(size * self.s)))
            path = _font_file(bold)
            f = pygame.font.Font(path, px) if path else pygame.font.Font(None, int(px * 1.3))
            if not path and bold:
                f.set_bold(True)
            self._fonts[key] = f
        return f

    def render_text(self, txt, size, color, bold=False):
        key = (txt, size, tuple(color), bold)
        img = self._text_cache.get(key)
        if img is None:
            if len(self._text_cache) > 4000:
                self._text_cache.clear()
            img = self.font(size, bold).render(txt, True, color)
            self._text_cache[key] = img
        return img

    def text_w(self, txt, size, bold=False):
        return self.font(size, bold).size(txt)[0] / self.s

    def text(self, txt, size, color, pos, anchor="topleft", bold=False):
        if not txt:
            return pygame.Rect(int(pos[0]), int(pos[1]), 0, 0)
        img = self.render_text(txt, size, color, bold)
        w, h = img.get_width() / self.s, img.get_height() / self.s
        x, y = pos
        if "right" in anchor:
            x -= w
        elif anchor in ("center", "midtop", "midbottom"):
            x -= w / 2
        if "bottom" in anchor:
            y -= h
        elif anchor in ("center", "midleft", "midright"):
            y -= h / 2
        self.surf.blit(img, (int(x * self.s), int(y * self.s)))
        return pygame.Rect(int(x), int(y), int(w), int(h))

    def wrap(self, txt, size, width, bold=False):
        words = txt.split()
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if self.text_w(t, size, bold) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    # --------------------------------------------------------------- shapes
    def _r(self, r):
        x, y, w, h = r
        s = self.s
        return pygame.Rect(int(round(x * s)), int(round(y * s)), int(round(w * s)), int(round(h * s)))

    def rect(self, color, r, width=0, radius=0):
        if len(color) == 4 and color[3] < 255:
            self.rect_alpha(color, r, radius)
            return
        pygame.draw.rect(self.surf, color, self._r(r),
                         width=max(1, int(round(width * self.s))) if width else 0,
                         border_radius=int(radius * self.s))

    def rect_alpha(self, color, r, radius=0):
        pr = self._r(r)
        if pr.w <= 0 or pr.h <= 0:
            return
        tmp = pygame.Surface(pr.size, pygame.SRCALPHA)
        pygame.draw.rect(tmp, color, tmp.get_rect(), border_radius=int(radius * self.s))
        self.surf.blit(tmp, pr.topleft)

    def line(self, color, a, b, width=1):
        s = self.s
        pygame.draw.line(self.surf, color, (a[0] * s, a[1] * s), (b[0] * s, b[1] * s),
                         max(1, int(round(width * s))))

    def circle(self, color, c, r, width=0):
        s = self.s
        pygame.draw.circle(self.surf, color, (c[0] * s, c[1] * s), max(1, r * s),
                           width=max(1, int(round(width * s))) if width else 0)

    def aacircle(self, color, c, r):
        s = self.s
        pygame.draw.aacircle(self.surf, color, (c[0] * s, c[1] * s), max(1, r * s))

    def poly(self, color, pts, width=0):
        s = self.s
        sp = [(x * s, y * s) for x, y in pts]
        if width:
            pygame.draw.polygon(self.surf, color, sp, max(1, int(round(width * s))))
        else:
            pygame.draw.polygon(self.surf, color, sp)

    def aapoly(self, color, pts):
        s = self.s
        sp = [(x * s, y * s) for x, y in pts]
        pygame.draw.polygon(self.surf, color, sp)
        pygame.draw.aalines(self.surf, color, True, sp)

    def blit(self, img, pos):
        self.surf.blit(img, (int(pos[0] * self.s), int(pos[1] * self.s)))

    def clip(self, r):
        self.surf.set_clip(self._r(r) if r else None)
