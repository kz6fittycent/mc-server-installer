"""Pack the server's world and settings into a backup. Runs as snap_daemon.

    python3 -m mcsi.pack SERVER_DIR ARCHIVE.tar.gz

Minecraft saves some world files (level.dat) readable by their owner only,
and root inside the snap cannot read past that, so the service runs this as
snap_daemon, the user the server runs as (see as_daemon in service.py).
"""

import os
import sys
import tarfile

# Not part of a backup or a moved-over world: Mojang re-downloads libraries/
# and versions/ from the jar, and logs are only logs.
NOT_WORLD = {"logs", "libraries", "versions", "crash-reports", "console.log",
             "console.log.old", "server.jar", "server.jar.part"}


def main(server_dir, archive):
    partial = archive + ".part"
    with tarfile.open(partial, "w:gz") as tar:
        for entry in sorted(os.listdir(server_dir)):
            if entry in NOT_WORLD or entry.endswith(".tmp"):
                continue
            tar.add(os.path.join(server_dir, entry), arcname=entry)
    os.chmod(partial, 0o644)  # the owner's menu copies it to their Home folder
    os.replace(partial, archive)
    print(os.path.getsize(archive))


if __name__ == "__main__":
    main(*sys.argv[1:3])
