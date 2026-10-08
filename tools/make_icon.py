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
# fan
cx, cy, r = S // 2, S // 2, 250
for k in range(3):
    a = k * 2 * math.pi / 3 - math.pi / 2
    pygame.draw.circle(surf, (255, 255, 255), (cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55), r * 0.48)
pygame.draw.circle(surf, (38, 72, 222), (cx, cy), 68)
pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 32)
pygame.image.save(surf, sys.argv[1])
