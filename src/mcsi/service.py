"""mc-server-installer background service (2.0, phase 1 prototype).

Runs as a snap daemon (root, started by systemd at install and at boot) and
owns the Minecraft server: downloads it, starts it as the unprivileged
snap_daemon user, stops it cleanly, and answers requests from the menu over a
Unix socket - one JSON object per line, one reply per request.

Commands reach the server through its console (Java's stdin), which only this
service holds, and replies are read from its output. RCON stays off: vanilla
Minecraft binds RCON to the game's own address, so it cannot be kept to this
computer while the game is reachable by the family.

Because systemd runs it, the server keeps going when the person who started
it logs out (which is what killed the 1.x server, started from a login). It
remembers whether the server should be running, so a snap refresh or a
reboot brings it back.
"""

import asyncio
import glob
import hashlib
import json
import os
import pwd
import signal
import socket
import struct
import sys
import re
import time
import urllib.request

SNAP = os.environ["SNAP"]
COMMON = os.environ["SNAP_COMMON"]
SERVER_DIR = os.path.join(COMMON, "server")
STATE_FILE = os.path.join(COMMON, "state.json")
PID_FILE = os.path.join(COMMON, "server.pid")
SOCKET_PATH = os.path.join(COMMON, "control.sock")

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
STOP_GRACE = 120          # seconds to wait for the world to save on stop
CRASH_WINDOW = 600        # a second crash within this many seconds: give up
DEFAULT_RAM_MB = 2048


def log(message):
    print(message, flush=True)  # stdout goes to the journal (snap logs)


def daemon_ids():
    entry = pwd.getpwnam("snap_daemon")
    return entry.pw_uid, entry.pw_gid


def java_binary():
    found = sorted(glob.glob(os.path.join(SNAP, "usr/lib/jvm/java-*/bin/java")))
    if not found:
        raise RuntimeError("no Java found in the snap")
    return found[0]


class State:
    """What survives restarts: settings, and whether the server should run."""

    def __init__(self):
        self.data = {"desired": "stopped", "ram_mb": DEFAULT_RAM_MB, "version": None}
        try:
            with open(STATE_FILE) as f:
                self.data.update(json.load(f))
        except FileNotFoundError:
            pass
        self.save()

    def __getitem__(self, key):
        return self.data[key]

    def update(self, **changes):
        self.data.update(changes)
        self.save()

    def save(self):
        temp = STATE_FILE + ".tmp"
        with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(temp, STATE_FILE)


class Server:
    def __init__(self, state):
        self.state = state
        self.process = None
        self.started_at = None
        self.stopping = False
        self.last_crash = None
        self.problem = None
        self.console_lock = asyncio.Lock()
        self.listeners = []

    @property
    def running(self):
        return self.process is not None and self.process.returncode is None

    # --- files ---------------------------------------------------------

    def prepare_files(self):
        """server.properties with RCON off, and a folder both sides can write.

        Inside a snap, root has no CAP_DAC_OVERRIDE: the service cannot write
        into a folder or file that belongs to snap_daemon. So the folder stays
        root's, group snap_daemon and group-writable (setgid is refused by the
        snap sandbox, so write_file sets the owner itself); Java creates its own
        files there, and the service only ever replaces files whole, never
        edits them in place.
        """
        ensure_server_dir()
        props_path = os.path.join(SERVER_DIR, "server.properties")
        props = {}
        lines = []
        if os.path.exists(props_path):
            with open(props_path) as f:
                lines = f.read().splitlines()
            for line in lines:
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    props[key] = value
        # Off even in a migrated world that had it on: it would listen on
        # every network interface (see the module docstring).
        wanted = {"enable-rcon": "false"}
        for key, value in wanted.items():
            if props.get(key) != value:
                lines = [l for l in lines if not l.startswith(key + "=")]
                lines.append(f"{key}={value}")
        write_file(props_path, "\n".join(lines) + "\n")

    # --- lifecycle -----------------------------------------------------

    async def start(self, ram_mb=None):
        if self.running:
            return {"ok": False, "error": "The server is already running."}
        if not await stop_leftover():
            return {"ok": False, "error": "An earlier copy of the server is still running "
                    "and could not be stopped. Restart the computer, then try again."}
        if not os.path.exists(os.path.join(SERVER_DIR, "server.jar")):
            return {"ok": False, "error": "Download the server first."}
        if not self.eula_accepted():
            return {"ok": False, "error": "The Minecraft EULA has not been accepted yet."}
        ram_mb = int(ram_mb or self.state["ram_mb"])
        self.prepare_files()
        uid, gid = daemon_ids()
        console_path = os.path.join(SERVER_DIR, "console.log")
        if os.path.exists(console_path) and os.stat(console_path).st_uid != 0:
            os.replace(console_path, console_path + ".old")
        self.process = await asyncio.create_subprocess_exec(
            "setpriv", f"--reuid={uid}", f"--regid={gid}", "--clear-groups",
            "--no-new-privs", "--",
            java_binary(), "-Xms128M", f"-Xmx{ram_mb}M", "-XX:+UseG1GC",
            "-jar", "server.jar", "nogui",
            cwd=SERVER_DIR, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env={"PATH": os.environ.get("PATH", ""), "HOME": SERVER_DIR, "LANG": "C.UTF-8"})
        asyncio.create_task(self.pump(self.process, console_path))
        self.started_at = time.time()
        self.stopping = False
        self.problem = None
        self.state.update(desired="running", ram_mb=ram_mb)
        with open(PID_FILE, "w") as f:
            f.write(str(self.process.pid))
        log(f"server started: pid {self.process.pid}, {ram_mb} MB")
        asyncio.create_task(self.watch(self.process))
        return {"ok": True, "pid": self.process.pid}

    async def pump(self, process, console_path):
        """Copy the server's output to console.log and to anyone waiting for a reply.

        Always draining it also keeps Java from blocking on a full pipe.
        """
        with open(console_path, "ab") as console:
            while line := await process.stdout.readline():
                console.write(line)
                console.flush()
                text = line.decode(errors="replace").rstrip()
                for queue in list(self.listeners):
                    queue.put_nowait(text)

    async def console_command(self, text, first_wait=3.0, settle=0.4):
        """Type a command into the server console; return the lines it printed.

        Replies are not marked as such, so this collects what the server
        prints until it goes quiet for `settle` seconds.
        """
        async with self.console_lock:
            queue = asyncio.Queue()
            self.listeners.append(queue)
            try:
                self.process.stdin.write(text.encode() + b"\n")
                await self.process.stdin.drain()
                lines = []
                timeout = first_wait
                while True:
                    try:
                        line = await asyncio.wait_for(queue.get(), timeout)
                    except asyncio.TimeoutError:
                        break
                    lines.append(LOG_PREFIX.sub("", line))
                    timeout = settle
                return lines
            finally:
                self.listeners.remove(queue)

    async def watch(self, process):
        code = await process.wait()
        if self.stopping or process is not self.process:
            return
        log(f"server exited by itself with code {code}")
        now = time.time()
        if self.last_crash and now - self.last_crash < CRASH_WINDOW:
            self.problem = (f"The server stopped twice within {CRASH_WINDOW // 60} minutes "
                            f"(exit code {code}). See console.log.")
            log("second crash in the window - not restarting")
            return
        self.last_crash = now
        log("restarting it once")
        await self.start()

    async def stop(self, remember=True):
        """Stop cleanly: 'stop' on the console, wait for the save, force only as a last resort.

        remember=False is for the service itself shutting down (snap refresh,
        reboot): the server should come back afterwards.
        """
        if not self.running:
            if remember:
                self.state.update(desired="stopped")
            return {"ok": True, "note": "The server was not running."}
        self.stopping = True
        if remember:
            self.state.update(desired="stopped")
        process = self.process
        try:
            process.stdin.write(b"stop\n")
            await process.stdin.drain()
            how = "console"
        except (BrokenPipeError, ConnectionResetError) as error:  # SIGTERM also saves
            log(f"console stop failed ({error}), sending SIGTERM")
            await signal_server(process.pid, "TERM")
            how = "sigterm"
        try:
            await asyncio.wait_for(process.wait(), STOP_GRACE)
        except asyncio.TimeoutError:
            log(f"server did not stop within {STOP_GRACE}s - killing it")
            await signal_server(process.pid, "KILL")
            await process.wait()
            how += "+kill"
        log(f"server stopped ({how})")
        return {"ok": True, "how": how}

    def eula_accepted(self):
        try:
            with open(os.path.join(SERVER_DIR, "eula.txt")) as f:
                return "eula=true" in f.read()
        except FileNotFoundError:
            return False

    # --- requests ------------------------------------------------------

    async def status(self):
        reply = {"ok": True, "running": self.running, "desired": self.state["desired"],
                 "version": self.state["version"], "ram_mb": self.state["ram_mb"],
                 "eula": self.eula_accepted(), "problem": self.problem}
        if self.running:
            reply["pid"] = self.process.pid
            reply["uptime_s"] = int(time.time() - self.started_at)
            reply["user"] = pwd.getpwuid(os.stat(f"/proc/{self.process.pid}").st_uid).pw_name
            lines = await self.console_command("list", first_wait=2.0)
            reply["players"] = next((l for l in lines if "players online" in l), None)
        return reply

    async def download(self):
        version, url, sha1 = await asyncio.to_thread(latest_server)
        ensure_server_dir()
        target = os.path.join(SERVER_DIR, "server.jar")
        await asyncio.to_thread(fetch_verified, url, sha1, target)
        self.state.update(version=version)
        log(f"downloaded server {version}")
        return {"ok": True, "version": version, "sha1": sha1}

    async def command(self, text):
        if not self.running:
            return {"ok": False, "error": "The server is not running."}
        return {"ok": True, "reply": await self.console_command(text)}


async def signal_server(pid, name):
    """Send a signal to the server as snap_daemon.

    Inside the snap, root lacks CAP_KILL and may not signal another user's
    process; snap_daemon may signal its own. Returns True if it was sent.
    """
    uid, gid = daemon_ids()
    helper = await asyncio.create_subprocess_exec(
        "setpriv", f"--reuid={uid}", f"--regid={gid}", "--clear-groups", "--no-new-privs",
        "--", "/usr/bin/kill", "-s", name, str(pid))
    return await helper.wait() == 0


LOG_PREFIX = re.compile(r"^\[\d\d:\d\d:\d\d\] \[[^\]]+\]: ")


def ensure_server_dir():
    _, gid = daemon_ids()
    os.makedirs(SERVER_DIR, exist_ok=True)
    os.chown(SERVER_DIR, 0, gid)
    os.chmod(SERVER_DIR, 0o775)  # no setgid: the snap sandbox refuses it


def write_file(path, text, mode=0o664):
    """Replace a file whole, owned by snap_daemon so Java can rewrite it too."""
    uid, gid = daemon_ids()
    temp = path + ".tmp"
    if os.path.lexists(temp):  # a leftover may already be snap_daemon's
        os.unlink(temp)
    with open(temp, "w") as f:
        f.write(text)
    # Mode first: once the file is snap_daemon's, root (without CAP_FOWNER
    # inside a snap) can no longer change it.
    os.chmod(temp, mode)
    os.chown(temp, uid, gid)
    os.replace(temp, path)


def latest_server():
    with urllib.request.urlopen(MANIFEST_URL, timeout=20) as r:
        manifest = json.load(r)
    release = manifest["latest"]["release"]
    entry = next(v for v in manifest["versions"] if v["id"] == release)
    with urllib.request.urlopen(entry["url"], timeout=20) as r:
        details = json.load(r)
    server = details["downloads"]["server"]
    return release, server["url"], server["sha1"]


def fetch_verified(url, sha1, target):
    """Download to a temporary file; only a jar matching Mojang's SHA-1 replaces the old one."""
    partial = target + ".part"
    digest = hashlib.sha1()
    with urllib.request.urlopen(url, timeout=60) as r, open(partial, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 16), b""):
            digest.update(chunk)
            f.write(chunk)
    if digest.hexdigest() != sha1:
        os.unlink(partial)
        raise RuntimeError("The download was damaged (checksum mismatch). Nothing was changed.")
    os.replace(partial, target)


def upnp_probe():
    """Phase 1 risk check: can the service send SSDP discovery from inside the snap?"""
    request = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
               "MAN: \"ssdp:discover\"\r\nMX: 2\r\n"
               "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(3)
    try:
        sock.sendto(request.encode(), ("239.255.255.250", 1900))
    except OSError as error:
        return {"ok": False, "sent": False, "error": str(error)}
    replies = []
    try:
        while True:
            data, address = sock.recvfrom(4096)
            replies.append(address[0])
    except socket.timeout:
        pass
    finally:
        sock.close()
    return {"ok": True, "sent": True, "routers_found": replies}


async def stop_leftover():
    """Stop a server a previous run of the service left behind.

    With stop-mode: sigterm, systemd signals only the service. If the service
    itself ever dies (a bug, or systemd's stop timeout), Java keeps running,
    and a fresh service must not start a second one on the same port.
    Returns True when no leftover server is running any more.
    """
    try:
        with open(PID_FILE) as f:
            pid = int(f.read())
        # Inside the snap, root may not read another user's /proc/<pid>/cmdline,
        # but it may stat the directory: a live process owned by snap_daemon
        # with the pid we recorded is our server.
        if os.stat(f"/proc/{pid}").st_uid != daemon_ids()[0]:
            return True
    except (FileNotFoundError, ValueError):
        return True
    # Its console belonged to the service that died, so SIGTERM it: Minecraft
    # saves the world on SIGTERM (a marker block survived this in phase 1).
    log(f"found a server left running (pid {pid}) - stopping it (SIGTERM saves the world)")
    if not await signal_server(pid, "TERM"):
        log("could not signal it")
        return False
    for _ in range(STOP_GRACE):
        if not os.path.exists(f"/proc/{pid}"):
            log("leftover server stopped")
            return True
        await asyncio.sleep(1)
    log("leftover server did not stop - killing it")
    await signal_server(pid, "KILL")
    await asyncio.sleep(2)
    return not os.path.exists(f"/proc/{pid}")


def peer_uid(writer):
    sock = writer.get_extra_info("socket")
    creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


async def main():
    ensure_server_dir()
    state = State()
    server = Server(state)

    async def handle(reader, writer):
        try:
            request = json.loads(await reader.readline())
            name = request.get("cmd")
            log(f"request {name!r} from uid {peer_uid(writer)}")
            if name == "status":
                reply = await server.status()
            elif name == "download":
                reply = await server.download()
            elif name == "accept-eula":
                ensure_server_dir()
                write_file(os.path.join(SERVER_DIR, "eula.txt"),
                           "# Accepted in mc-server-installer (https://aka.ms/MinecraftEULA)\neula=true\n")
                reply = {"ok": True}
            elif name == "start":
                reply = await server.start(request.get("ram_mb"))
            elif name == "stop":
                reply = await server.stop()
            elif name == "command":
                reply = await server.command(request["text"])
            elif name == "upnp-probe":
                reply = await asyncio.to_thread(upnp_probe)
            else:
                reply = {"ok": False, "error": f"unknown request {name!r}"}
        except Exception as error:
            reply = {"ok": False, "error": str(error)}
        writer.write((json.dumps(reply) + "\n").encode())
        await writer.drain()
        writer.close()

    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    listener = await asyncio.start_unix_server(handle, SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)  # any local user's menu may talk to it (open question in the design)
    log(f"listening on {SOCKET_PATH}")

    try:
        clear = await stop_leftover()
    except Exception as error:  # never let this crash-loop the service
        log(f"could not check for a leftover server: {error}")
        clear = False
    if not clear:
        server.problem = ("An earlier copy of the server is still running and could not be "
                          "stopped. Restart the computer, then open the menu again.")
        log("not starting a second server")
    elif state["desired"] == "running":
        log("the server was running before - starting it again")
        result = await server.start()
        if not result["ok"]:
            log(f"could not start it: {result['error']}")

    finished = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, finished.set)
    await finished.wait()

    log("service stopping (refresh, reboot or snap stop) - saving the world first")
    listener.close()
    await server.stop(remember=False)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
