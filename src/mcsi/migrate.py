"""Finding a 14.x server in the user's snap folder and packing it to move over.

14.x kept everything in $SNAP_USER_DATA (~/snap/mc-server-installer/<rev>/),
which snapd copies forward on every refresh, so the menu - running as that
person, in the new revision - can read it there. The service, as root, cannot
read people's home folders, so the menu packs the files and sends them.
"""

import os
import tarfile
import tempfile
import time

OLD_DIR = os.environ.get("SNAP_USER_DATA", os.path.expanduser("~"))
MARKER = os.path.join(OLD_DIR, ".moved-to-15")
SKIP = {"libraries", "versions", "logs", "crash-reports", "server.jar"}
SIGNS = ("server.properties", "eula.txt", "whitelist.json", "ops.json")


def find_old_server():
    """A description of the 14.x server here, or None if there is none (or it was moved)."""
    if os.path.exists(MARKER) or not os.path.isdir(OLD_DIR):
        return None
    entries = os.listdir(OLD_DIR)
    worlds = sorted(d for d in entries if os.path.isfile(os.path.join(OLD_DIR, d, "level.dat")))
    if not worlds and not any(name in entries for name in SIGNS):
        return None
    last = max((os.path.getmtime(os.path.join(OLD_DIR, w, "level.dat")) for w in worlds),
               default=None)
    size = 0
    for name in entries:
        if name in SKIP or name.startswith("."):
            continue
        for root, _, files in os.walk(os.path.join(OLD_DIR, name)):
            size += sum(os.path.getsize(os.path.join(root, f)) for f in files
                        if not os.path.islink(os.path.join(root, f)))
        if os.path.isfile(os.path.join(OLD_DIR, name)):
            size += os.path.getsize(os.path.join(OLD_DIR, name))
    return {"path": OLD_DIR, "worlds": worlds, "last_played": last, "size": size}


def pack_old_server():
    """Pack the old server's world and settings into a temporary tar.gz; return its path."""
    handle, path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(handle)
    with tarfile.open(path, "w:gz") as tar:
        for name in sorted(os.listdir(OLD_DIR)):
            if name in SKIP or name.startswith(".") or name.endswith((".tar.gz", ".jar")):
                continue
            tar.add(os.path.join(OLD_DIR, name), arcname=name)
    return path


def mark_moved():
    with open(MARKER, "w") as f:
        f.write(time.strftime("Moved to the 15.0 background service on %Y-%m-%d %H:%M\n"))
