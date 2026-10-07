# Airflow

A duct-building airflow puzzle game for Mac, inspired by DUCTWORKS on Roblox.
Python + pygame-ce + numpy. Single player. `AIRFLOW_SPEC.md` has the full design.

**Download:** https://santisam22.github.io/airflow/

## Releasing an update
1. Make the change, then bump `VERSION` in `airflow/config.py`.
2. Write a one-line summary on the first line of `WHATS_NEW.txt`. Players see it in the game after updating.
3. Build and publish:
   ```bash
   ./build.sh
   git add -A && git commit -m "Airflow <version>: <summary>"
   ./release.sh "Short title"
   ```

`build.sh` runs the play tests and builds `dist/Airflow.dmg`. It also writes `dist/Airflow-update.zip`
and `dist/update.json`, signed with the Ed25519 key in your login Keychain (`macos/sign_tool.swift`).
`release.sh` tags `v<version>`, pushes, and uploads those three files as a GitHub release.

Installed copies check `releases/latest/download/update.json` and offer **Install & Restart**.
The app refuses any update whose signature doesn't verify against `UPDATE_PUBLIC_KEY` in `airflow/config.py`.
The download page in `docs/` (GitHub Pages) always links to the latest release.

## Run from source
```bash
python3 -m venv .venv.nosync && .venv.nosync/bin/pip install -r requirements.txt
.venv.nosync/bin/python main.py
```
The environment lives in a `.nosync` folder so iCloud Drive doesn't sync it. Syncing it creates
" 2" duplicate files that break it.

## Layout
| File | What it does |
|---|---|
| `airflow/parts.py` | Part catalog: prices, metal, loss coefficients, throw patterns |
| `airflow/projects.py` | Houses / floor plans, rooms, doors, furniture |
| `airflow/network.py` | Duct network pressure/flow solver (fan curve, K losses, leaks) |
| `airflow/roomair.py` | Room air speed field, heatmap colours, coverage % |
| `airflow/state.py` | Game state, money, upgrades, actions, save/load, undo |
| `airflow/render.py` | Floor plan + duct drawing |
| `airflow/app.py` | Window, UI panels, input, update banner |
| `airflow/updater.py`, `airflow/ed25519.py` | Self-update: check, download, verify, swap, relaunch |
| `tools/snapshot.py` | Headless screenshots for visual checks |
| `tests/test_play.py` | Headless play-through driven by synthetic input |

All world changes go through `Game.apply(action)`, so a multiplayer layer can forward the same
actions over the network later. Saves live in `~/Library/Application Support/Airflow/`.

## License
MIT, see [LICENSE](LICENSE). Bundled components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Fan-made. Not affiliated with Roblox or the DUCTWORKS developer.
