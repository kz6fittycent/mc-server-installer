"""Phase 1 test client: talks to the background service the way the menu will.

    mc-server-installer.ctl status | download | accept-eula | start [RAM_MB]
                            | stop | command TEXT... | upnp-probe
"""

import json
import os
import socket
import sys

SOCKET_PATH = os.path.join(os.environ["SNAP_COMMON"], "control.sock")


def request(payload, timeout=300):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(SOCKET_PATH)
        sock.sendall((json.dumps(payload) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    name, rest = argv[0], argv[1:]
    payload = {"cmd": name}
    if name == "start" and rest:
        payload["ram_mb"] = int(rest[0])
    elif name == "command":
        payload["text"] = " ".join(rest)
    try:
        reply = request(payload)
    except (FileNotFoundError, ConnectionRefusedError):
        print("The background service is not running.", file=sys.stderr)
        return 1
    except PermissionError as error:
        print(f"Not allowed to talk to the service: {error}", file=sys.stderr)
        return 1
    print(json.dumps(reply, indent=2))
    return 0 if reply.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
