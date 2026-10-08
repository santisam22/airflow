"""Windows self-update: signature checks and the rename-swap.

Signs with a throwaway test key (generated here), never the real release key.
On Windows it also checks that a running .exe can be renamed, which the swap needs.
"""
import base64
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from airflow import config as C
from airflow import ed25519 as E
from airflow import updater as U


def _encode(pt):
    x, y, z, _ = pt
    zi = E._inv(z)
    x, y = x * zi % E._P, y * zi % E._P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def keypair():
    seed = secrets.token_bytes(32)
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return (a, h[32:]), _encode(E._mul(a, E._B))


def sign(priv, pub, msg):
    a, prefix = priv
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % E._L
    R = _encode(E._mul(r, E._B))
    k = int.from_bytes(hashlib.sha512(R + pub + msg).digest(), "little") % E._L
    return R + ((r + k * a) % E._L).to_bytes(32, "little")


def main():
    priv, pub = keypair()
    C.UPDATE_PUBLIC_KEY = base64.b64encode(pub).decode()

    exe_bytes = b"MZ fake airflow " + secrets.token_bytes(4096)
    sha = hashlib.sha256(exe_bytes).hexdigest()
    sig = base64.b64encode(sign(priv, pub, U.windows_message("9.9.9", sha))).decode()
    info = {"version": "9.9.9", "win_sha256": sha, "win_signature": sig}

    U.verify_windows(info, sha)                                     # good update passes
    for bad, why in ((dict(info, version="9.9.10"), "claims another version"),
                     (dict(info, win_sha256="0" * 64), "different file")):
        try:
            U.verify_windows(bad, sha if why != "different file" else "0" * 64)
            raise AssertionError(f"accepted an update that {why}")
        except RuntimeError:
            pass
    try:
        U.verify_windows(info, hashlib.sha256(exe_bytes + b"x").hexdigest())
        raise AssertionError("accepted a tampered file")
    except RuntimeError:
        pass

    # the swap: running file -> .old, new file takes its name
    d = tempfile.mkdtemp()
    exe = os.path.join(d, "Airflow.exe")
    open(exe, "wb").write(b"old version")
    open(exe + ".new", "wb").write(exe_bytes)
    assert U.swap_windows(exe, exe + ".new", relaunch=False)
    assert open(exe, "rb").read() == exe_bytes and open(exe + ".old", "rb").read() == b"old version"
    assert not os.path.exists(exe + ".new")

    if os.name == "nt":
        # Windows lets you rename a running program (this is what the update relies on)
        prog = os.path.join(d, "running.exe")
        shutil.copy(sys.executable, prog)
        p = subprocess.Popen([prog, "-c", "import time; time.sleep(30)"])
        time.sleep(1.5)
        try:
            os.rename(prog, prog + ".old")
            ok = True
        except OSError as e:
            ok = e
        p.kill(); p.wait()
        assert ok is True, f"couldn't rename a running exe: {ok}"
        print("windows: renaming a running exe works")
    print("all update tests passed")


if __name__ == "__main__":
    main()
