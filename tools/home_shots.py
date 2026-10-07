"""Headless screenshots of the home screen states: python tools/home_shots.py out_dir"""
import os, sys, time
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pygame
from airflow import config as C
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
C.save_path = lambda: os.path.join(OUT, "s.json")
from airflow.app import App
from airflow.state import Game
from tools.demo_layouts import p1_demo


def shot(app, name, steps=40):
    for _ in range(steps):
        app.update(1 / 30)
    app.draw()
    pygame.image.save(app.surf, os.path.join(OUT, name))


app = App(headless=(1400, 860))
app.game = Game(); app.game.money = 5000; p1_demo(app.game); app.game.dirty = True
app.toast = None; app.banner = None
shot(app, "1_home.png", 120)
u = app.updater
u.available = {"version": "0.4.0", "url": "x", "signature": "x",
               "notes": "Bigger houses and a new Swirl Diffuser."}
shot(app, "2_update.png", 3)
u.state, u.progress = "downloading", 0.62
shot(app, "3_downloading.png", 3)
u.state, u.downloaded_version = "downloaded", "0.4.0"
app.watch_updates(); app.banner = (app.banner[0], app.banner[1], time.time() - 0.6)
shot(app, "4_downloaded.png", 1)
app.home_page = "settings"; app.banner = None
shot(app, "5_settings.png", 2)
app.home_page = "help"
shot(app, "6_help.png", 2)
app.home_page = "main"; app.dark = True
shot(app, "7_home_dark.png", 10)
app.dark = False; app.screen = "game"; app.panel = None
shot(app, "8_game_menu.png", 2)
print("ok")
