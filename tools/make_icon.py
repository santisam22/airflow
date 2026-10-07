"""Draw the app icon (1024px PNG) with pygame. build_dmg.sh turns it into .icns."""

import math
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402

S = 1024
pygame.init()
surf = pygame.Surface((S, S), pygame.SRCALPHA)
pad = 100
pygame.draw.rect(surf, (38, 72, 222), (pad, pad, S - 2 * pad, S - 2 * pad), border_radius=190)
# duct run with a velocity gradient across the bottom
stops = [(52, 84, 230), (40, 200, 235), (90, 205, 70), (240, 200, 30), (235, 70, 50)]
y0, h = 640, 120
x0, x1 = pad + 90, S - pad - 90
for x in range(x0, x1):
    t = (x - x0) / (x1 - x0) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    f = t - i
    c = tuple(int(stops[i][k] * (1 - f) + stops[i + 1][k] * f) for k in range(3))
    pygame.draw.line(surf, c, (x, y0), (x, y0 + h))
pygame.draw.rect(surf, (15, 20, 40), (x0, y0, x1 - x0, h), width=14, border_radius=12)
# fan
cx, cy, r = S // 2, 400, 170
for k in range(3):
    a = k * 2 * math.pi / 3 - math.pi / 2
    pygame.draw.circle(surf, (255, 255, 255), (cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55), r * 0.48)
pygame.draw.circle(surf, (38, 72, 222), (cx, cy), 46)
pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 22)
pygame.image.save(surf, sys.argv[1])
