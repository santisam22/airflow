"""Self-updating, same scheme as Inbox.

Checks update.json on the latest GitHub release (shortly after launch and every
6 hours). When a newer version exists the game shows a banner. Installing
downloads Airflow-update.zip and refuses it unless its Ed25519 signature
verifies against UPDATE_PUBLIC_KEY, it unpacks to an Airflow.app with the same
bundle ID, a higher version and an intact code signature. Then a small helper
script waits for the game to quit, swaps the app and relaunches it.
"""

import base64
import json
import os
import plistlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

from . import config as C
from .ed25519 import verify

CHECK_EVERY = 6 * 3600


def is_newer(a, b):
    pa = [int(x) if x.isdigit() else 0 for x in str(a).split(".")]
    pb = [int(x) if x.isdigit() else 0 for x in str(b).split(".")]
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return pa > pb


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def app_bundle():
    """Path of the running Airflow.app, or None when running from source."""
    if not getattr(sys, "frozen", False):
        return None
    path = os.path.realpath(sys.executable)
    while path and path != "/":
        if path.endswith(".app"):
            return path
        path = os.path.dirname(path)
    return None


class Updater:
    def __init__(self):
        self.manifest_url = os.environ.get("AIRFLOW_UPDATE_MANIFEST", C.UPDATE_MANIFEST_URL)
        self.available = None        # dict from update.json
        self.state = "idle"          # idle, checking, downloading, restarting, error
        self.message = ""
        self.last_check = 0.0
        self.last_result = None      # "up_to_date" | "available" | "failed"
        self._lock = threading.Lock()
        self.ready_to_quit = False
        self.progress = 0.0
        self.staged = None             # (current app, new app, work dir) once downloaded
        self.downloaded_version = None

    # ------------------------------------------------------------ checking
    def tick(self):
        """Call every frame; starts a background check when one is due."""
        now = time.time()
        if self.state == "idle" and self.available is None:
            due = (self.last_check == 0 and now - _START > 5) or (self.last_check and now - self.last_check > CHECK_EVERY)
            if due:
                self.check()

    def check(self, user=False):
        if self.state in ("checking", "downloading", "restarting"):
            return
        self.state = "checking"
        self.last_check = time.time()
        threading.Thread(target=self._check, args=(user,), daemon=True).start()

    def _check(self, user):
        try:
            req = urllib.request.Request(self.manifest_url, headers={"Cache-Control": "no-cache",
                                                                     "User-Agent": f"Airflow/{C.VERSION}"})
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
                info = json.loads(r.read().decode("utf-8"))
            for k in ("version", "url", "signature"):
                if k not in info:
                    raise ValueError("bad manifest")
            if is_newer(info["version"], C.VERSION):
                self.available = info
                self.last_result = "available"
            else:
                self.last_result = "up_to_date"
            self.state = "idle"
        except Exception:
            self.last_result = "failed"
            self.state = "idle"
            if user:
                self.message = "Couldn't check for updates. Check your internet connection and try again."

    # ------------------------------------------------------------ downloading
    # The player starts the download from the home screen. A verified download is
    # staged; it replaces the app when the player restarts (or quits) the game.
    def download(self):
        if not self.available or self.state in ("downloading", "downloaded", "restarting"):
            return
        if not C.IS_MAC:
            # self-installing is Mac-only; on Windows the new version comes from the website
            import webbrowser
            webbrowser.open(C.WEBSITE)
            self.message = "Opened the download page in your browser."
            return
        app = app_bundle()
        if app is None:
            return self._error("Updates install into the packaged app. You're running from source.")
        if "/AppTranslocation/" in app or app.startswith("/Volumes/"):
            return self._error("Move Airflow into your Applications folder, open it from there, then update.")
        folder = os.path.dirname(app)
        if not os.access(folder, os.W_OK):
            return self._error(f"Airflow can't replace itself in {folder}. Download the update from the website instead.")
        self.state = "downloading"
        self.progress = 0.0
        self.message = f"Downloading Airflow {self.available['version']}…"
        threading.Thread(target=self._download, args=(dict(self.available), app), daemon=True).start()

    def _error(self, msg):
        self.state = "error"
        self.message = msg

    def _download(self, info, app):
        try:
            work = os.path.join(tempfile.gettempdir(), f"airflow-update-{uuid.uuid4().hex}")
            os.makedirs(work)
            zpath = os.path.join(work, "update.zip")
            req = urllib.request.Request(info["url"], headers={"User-Agent": f"Airflow/{C.VERSION}"})
            with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as r, open(zpath, "wb") as fh:
                if r.status != 200:
                    raise RuntimeError("The download failed. Check your internet connection and try again.")
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    b = r.read(1 << 18)
                    if not b:
                        break
                    fh.write(b)
                    got += len(b)
                    if total:
                        self.progress = min(0.99, got / total)

            pub = base64.b64decode(C.UPDATE_PUBLIC_KEY)
            sig = base64.b64decode(info["signature"])

            def chunks():
                with open(zpath, "rb") as fh:
                    while True:
                        b = fh.read(1 << 20)
                        if not b:
                            return
                        yield b

            if not verify(pub, sig, chunks()):
                raise RuntimeError("This update's signature doesn't match Airflow's. It was not installed.")

            subprocess.run(["/usr/bin/ditto", "-x", "-k", zpath, work], check=True, capture_output=True)
            new_app = os.path.join(work, "Airflow.app")
            with open(os.path.join(new_app, "Contents", "Info.plist"), "rb") as fh:
                plist = plistlib.load(fh)
            with open(os.path.join(app, "Contents", "Info.plist"), "rb") as fh:
                cur = plistlib.load(fh)
            if plist.get("CFBundleIdentifier") != cur.get("CFBundleIdentifier") or \
                    not is_newer(plist.get("CFBundleShortVersionString", "0"), C.VERSION):
                raise RuntimeError("The downloaded update isn't a newer version of Airflow. It was not installed.")
            res = subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", new_app],
                                 capture_output=True)
            if res.returncode != 0:
                raise RuntimeError("The update's code signature is broken. It was not installed.")

            self.staged = (app, new_app, work)
            self.downloaded_version = info["version"]
            self.progress = 1.0
            self.state = "downloaded"
            self.message = f"Update {info['version']} downloaded"
        except Exception as e:
            msg = str(e) if isinstance(e, RuntimeError) else \
                "The update couldn't be downloaded. Try again, or download it from the website."
            self._error(msg)

    def apply(self, relaunch):
        """Hand the staged update to a helper that swaps it in once the game exits."""
        if not self.staged:
            return False
        app, new_app, work = self.staged
        script = os.path.join(work, "swap.sh")
        with open(script, "w") as fh:
            fh.write(_SWAP)
        os.chmod(script, 0o755)
        subprocess.Popen(["/bin/sh", script, str(os.getpid()), app, new_app, work, "1" if relaunch else "0"],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.staged = None
        return True

    def restart(self):
        if self.apply(relaunch=True):
            self.state = "restarting"
            self.message = "Restarting Airflow…"
            self.ready_to_quit = True


# Waits for the game to exit, swaps the bundle (keeping the old one until the new
# one is in place), then relaunches.
_SWAP = """#!/bin/sh
PID="$1"; APP="$2"; NEW="$3"; WORK="$4"; RELAUNCH="$5"
LOG="$HOME/Library/Logs/Airflow/update.log"
mkdir -p "$(dirname "$LOG")"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
log "waiting for Airflow ($PID) to quit"
for i in $(seq 1 300); do kill -0 "$PID" 2>/dev/null || break; sleep 0.1; done
OLD="$WORK/Airflow-old.app"
if ! mv "$APP" "$OLD"; then log "could not move the old app"; exit 1; fi
if mv "$NEW" "$APP"; then
  rm -rf "$OLD"
  log "installed $(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")"
else
  mv "$OLD" "$APP"
  log "swap failed, kept the old app"
fi
if [ "$RELAUNCH" = "1" ]; then
  sleep 0.5
  for i in 1 2 3 4 5; do
    if open "$APP"; then log "relaunched"; break; fi
    log "open failed (try $i)"; sleep 1
  done
fi
rm -rf "$WORK"
"""

_START = time.time()


def whats_new_after_update():
    """Return (version, notes) once after the app was updated, else None."""
    marker = os.path.join(C.save_dir(), "last_version.txt")
    prev = None
    try:
        with open(marker) as fh:
            prev = fh.read().strip()
    except OSError:
        pass
    try:
        with open(marker, "w") as fh:
            fh.write(C.VERSION)
    except OSError:
        pass
    if prev and is_newer(C.VERSION, prev):
        notes = ""
        app = app_bundle()
        if app:
            try:
                with open(os.path.join(app, "Contents", "Info.plist"), "rb") as fh:
                    notes = plistlib.load(fh).get("AirflowWhatsNew", "")
            except Exception:
                pass
        return C.VERSION, notes
    return None
