"""Unpack a moved-over world into the server folder. Runs as snap_daemon.

    python3 -m mcsi.extract ARCHIVE.tar.gz DEST

The service runs this as snap_daemon (see as_daemon in service.py) so the
world's files belong to the user the server runs as. The "data" filter
refuses absolute paths, "..", links pointing outside DEST and device files,
and drops set-uid bits - the archive comes from a user's home folder.
"""

import os
import sys
import tarfile


def main(archive, dest):
    os.umask(0o002)  # group snap_daemon may write too, like the server's own files
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest, filter="data")
    worlds = [d for d in os.listdir(dest) if os.path.isfile(os.path.join(dest, d, "level.dat"))]
    print("worlds: " + (", ".join(sorted(worlds)) or "none"))


if __name__ == "__main__":
    main(*sys.argv[1:3])
