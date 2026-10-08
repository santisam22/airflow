"""Admin mode: unlocked with a key typed into Settings.

Only a salted PBKDF2 hash of the key lives here (the repo is public). The key
itself is kept outside the repo, in Private.nosync/admin_key.txt on the
developer's Mac. Admin mode makes everything free, removes the metal limit and
unlocks every part and house.
"""

import hashlib
import hmac

_SALT = bytes.fromhex("8c30fd4d9c57104d9ede0cd008a641e5")
_HASH = "148b2d0d0b1e5589985a2e66f4c51292cb4afaed4882f5508565fcc79ab12eab"
_ROUNDS = 200_000


def normalise(key):
    return "".join(ch for ch in key.upper() if ch.isalnum())


def check(key):
    k = normalise(key)
    if len(k) != 16:
        return False
    k = "-".join(k[i:i + 4] for i in range(0, 16, 4))
    digest = hashlib.pbkdf2_hmac("sha256", k.encode(), _SALT, _ROUNDS).hex()
    return hmac.compare_digest(digest, _HASH)
