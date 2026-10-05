"""Talking to the background service, for the menu and the ctl test client."""

import json
import os
import socket

SOCKET_PATH = os.path.join(os.environ.get("SNAP_COMMON", "/var/snap/mc-server-installer/common"),
                           "control.sock")


class ServiceError(Exception):
    """The service is unreachable, or turned a request down (its words)."""


def request(cmd, upload=None, timeout=600, **fields):
    """Send one request; return the reply dict. `upload` is a file path to send along."""
    payload = {"cmd": cmd, **fields}
    source = None
    if upload:
        try:  # open it first, so a file we cannot read is not blamed on the service
            source = open(upload, "rb")
            payload["size"] = os.fstat(source.fileno()).st_size
        except OSError as error:
            raise ServiceError(f"Could not read {upload}: {error.strerror or error}")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(SOCKET_PATH)
            sock.sendall((json.dumps(payload) + "\n").encode())
            if source:
                sock.sendfile(source)
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
    except (FileNotFoundError, ConnectionRefusedError):
        raise ServiceError("The background service is not running. Try: sudo snap start mc-server-installer")
    except socket.timeout:
        raise ServiceError("The background service did not answer in time.")
    except OSError as error:
        raise ServiceError(f"Could not reach the background service: {error.strerror or error}")
    finally:
        if source:
            source.close()
    try:
        reply = json.loads(data)
    except ValueError:
        raise ServiceError("The background service gave an answer this menu does not understand.")
    if not reply.get("ok"):
        raise ServiceError(reply.get("error", "The request failed."))
    return reply
