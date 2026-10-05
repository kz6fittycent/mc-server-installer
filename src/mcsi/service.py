"""mc-server-installer background service.

Runs as a snap daemon (root, started by systemd at install and at boot) and
owns the Minecraft server: downloads it, starts it as the unprivileged
snap_daemon user, stops it cleanly, and answers requests from the menu over a
Unix socket - one JSON object per line, one reply per request. A request with
a "size" is followed by that many bytes of upload (a world, a jar).

Commands reach the server through its console (Java's stdin), which only this
service holds, and replies are read from its output. RCON stays off: vanilla
Minecraft binds RCON to the game's own address, so it cannot be kept to this
computer while the game is reachable by the family.

Because systemd runs it, the server keeps going when the person who started
it logs out (which is what killed the 14.x server, started from a login). It
remembers whether the server should be running, so a snap refresh or a
reboot brings it back.

Only the server's owner - the person who runs this computer - may change it:
the first account to make a change becomes the owner, and root can hand it
over (`sudo mc-server-installer.ctl set-owner NAME`). Anyone else gets
status only.

Inside the snap, root has no CAP_DAC_OVERRIDE, CAP_FOWNER or CAP_KILL: it
cannot write into, chmod, or signal anything that belongs to snap_daemon. So
the server folder stays root's (group snap_daemon, 0775), the service only
ever replaces files whole, and whatever must act on snap_daemon's own files or
processes runs as snap_daemon (as_daemon).
"""

import asyncio
import collections
import glob
import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import socket
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SNAP = os.environ["SNAP"]
COMMON = os.environ["SNAP_COMMON"]
SERVER_DIR = os.path.join(COMMON, "server")
BACKUP_DIR = os.path.join(COMMON, "backups")
INCOMING_DIR = os.path.join(COMMON, "incoming")
STATE_FILE = os.path.join(COMMON, "state.json")
PID_FILE = os.path.join(COMMON, "server.pid")
SOCKET_PATH = os.path.join(COMMON, "control.sock")

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
PROFILE_URL = "https://api.mojang.com/users/profiles/minecraft/"
STOP_GRACE = 120          # seconds to wait for the world to save on stop
CRASH_WINDOW = 600        # a second crash within this many seconds: give up
DEFAULT_RAM_MB = 2048
LOG_LINES = 1000          # console lines kept for the menu's console screen
BACKUPS_KEPT = 7          # of each automatic kind (daily, before-restore, before-update)
DAY = 86400
HOUSEKEEPING_FIRST = 60   # seconds after the service starts
HOUSEKEEPING_EVERY = 3600
STARTUP_WAIT = 120        # seconds a command waits for the server to finish starting

# Requests anyone on the computer may make; everything else is the owner's.
READ_ONLY = {"status", "log", "get-properties", "list-backups", "players"}

PLAYER_NAME = re.compile(r"^[A-Za-z0-9_]{3,16}$")
PROPERTY_KEY = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")
JAR_NAME = re.compile(r"^[A-Za-z0-9._\-]{1,64}\.jar$")
VERSION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\- ]{0,31}$")
BACKUP_NAME = re.compile(r"^backup-(manual|daily|before-restore|before-update)-[0-9-]+\.tar\.gz$")
LOG_PREFIX = re.compile(r"^\[\d\d:\d\d:\d\d\] \[[^\]]+\]: ")
# Server-thread lines only: chat is printed as "<name> text", so a player
# cannot fake these by typing them.
JOINED = re.compile(r"^\[\d\d:\d\d:\d\d\] \[Server thread/INFO\]: ([A-Za-z0-9_]{3,16}) joined the game$")
DONE = re.compile(r"^\[\d\d:\d\d:\d\d\] \[Server thread/INFO\]: Done \(")
LEFT = re.compile(r"^\[\d\d:\d\d:\d\d\] \[Server thread/INFO\]: ([A-Za-z0-9_]{3,16}) left the game$")


def log(message):
    print(message, flush=True)  # stdout goes to the journal (snap logs)


class Refused(Exception):
    """A request we turn down with a plain explanation for the menu."""


def daemon_ids():
    entry = pwd.getpwnam("snap_daemon")
    return entry.pw_uid, entry.pw_gid


def user_name(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def java_binary():
    found = sorted(glob.glob(os.path.join(SNAP, "usr/lib/jvm/java-*/bin/java")))
    if not found:
        raise RuntimeError("no Java found in the snap")
    return found[0]


def as_daemon(*command):
    """The argv prefix that runs a command as snap_daemon."""
    uid, gid = daemon_ids()
    return ["setpriv", f"--reuid={uid}", f"--regid={gid}", "--clear-groups",
            "--no-new-privs", "--", *command]


async def run_as_daemon(*command):
    helper = await asyncio.create_subprocess_exec(
        *as_daemon(*command), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": os.path.join(SNAP, "lib")})
    output, _ = await helper.communicate()
    return helper.returncode, output.decode(errors="replace")


class State:
    """What survives restarts: settings, owner, and whether the server should run."""

    def __init__(self):
        self.data = {"desired": "stopped", "ram_mb": DEFAULT_RAM_MB, "version": None,
                     "jar": "server.jar", "owner_uid": None, "migrated": False,
                     "autostart": True, "boot_id": None, "latest": None, "latest_checked": 0,
                     "previous_version": None, "pinned": False}
        try:
            with open(STATE_FILE) as f:
                self.data.update(json.load(f))
        except FileNotFoundError:
            pass
        self.data.pop("rcon_password", None)  # from the phase 1 prototype
        self.save()

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

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
        self.lines = collections.deque(maxlen=LOG_LINES)  # (sequence number, text)
        self.line_seq = 0
        self.online = []  # players, from the server's join/leave lines
        self.ready = asyncio.Event()  # set when the server says "Done" after starting

    @property
    def running(self):
        return self.process is not None and self.process.returncode is None

    # --- files ---------------------------------------------------------

    def properties(self):
        path = os.path.join(SERVER_DIR, "server.properties")
        values = {}
        try:
            with open(path) as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, value = line.rstrip("\n").split("=", 1)
                        values[key] = value
        except FileNotFoundError:
            pass
        return values

    def prepare_files(self):
        """server.properties with RCON off (see the module docstring)."""
        ensure_server_dir()
        props_path = os.path.join(SERVER_DIR, "server.properties")
        lines = []
        if os.path.exists(props_path):
            with open(props_path) as f:
                lines = f.read().splitlines()
        # Off even in a moved-over world that had it on: it would listen on
        # every network interface.
        if self.properties().get("enable-rcon") != "false":
            lines = [l for l in lines if not l.startswith("enable-rcon=")]
            lines.append("enable-rcon=false")
            write_file(props_path, "\n".join(lines) + "\n")

    # --- lifecycle -----------------------------------------------------

    async def start(self, ram_mb=None):
        if self.running:
            raise Refused("The server is already running.")
        if not await stop_leftover():
            raise Refused("An earlier copy of the server is still running and could not "
                          "be stopped. Restart the computer, then try again.")
        jar = self.state["jar"]
        if not os.path.exists(os.path.join(SERVER_DIR, jar)):
            raise Refused("Download the server first (option 1).")
        if not self.eula_accepted():
            raise Refused("Agree to the Minecraft EULA first (option 2).")
        ram_mb = int(ram_mb or self.state["ram_mb"])
        if ram_mb < 1024:
            raise Refused("The server needs at least 1024 MB (1 GB) of memory.")
        self.prepare_files()
        console_path = os.path.join(SERVER_DIR, "console.log")
        if os.path.exists(console_path) and os.stat(console_path).st_uid != 0:
            os.replace(console_path, console_path + ".old")
        self.process = await asyncio.create_subprocess_exec(
            *as_daemon(java_binary(), "-Xms128M", f"-Xmx{ram_mb}M", "-XX:+UseG1GC",
                       "-jar", jar, "nogui"),
            cwd=SERVER_DIR, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env={"PATH": os.environ.get("PATH", ""), "HOME": SERVER_DIR, "LANG": "C.UTF-8"})
        asyncio.create_task(self.pump(self.process, console_path))
        self.started_at = time.time()
        self.online = []
        self.ready = asyncio.Event()
        self.stopping = False
        self.problem = None
        self.state.update(desired="running", ram_mb=ram_mb)
        with open(PID_FILE, "w") as f:
            f.write(str(self.process.pid))
        log(f"server started: pid {self.process.pid}, {ram_mb} MB, {jar}")
        asyncio.create_task(self.watch(self.process))
        return {"ok": True, "pid": self.process.pid}

    async def pump(self, process, console_path):
        """Copy the server's output to console.log, the console screen, and
        anyone waiting for a reply. Always draining it also keeps Java from
        blocking on a full pipe."""
        with open(console_path, "ab") as console:
            while line := await process.stdout.readline():
                console.write(line)
                console.flush()
                text = line.decode(errors="replace").rstrip()
                self.line_seq += 1
                self.lines.append((self.line_seq, text))
                if not self.ready.is_set() and DONE.match(text):
                    self.ready.set()
                if match := JOINED.match(text):
                    self.online.append(match.group(1))
                elif (match := LEFT.match(text)) and match.group(1) in self.online:
                    self.online.remove(match.group(1))
                for queue in list(self.listeners):
                    queue.put_nowait(text)

    async def console_command(self, text, first_wait=3.0, settle=0.4, until=None):
        """Type a command into the server console; return the lines it printed.

        Replies are not marked as such, so this collects what the server
        prints until it goes quiet for `settle` seconds - or, with `until`,
        until a line contains that text.
        """
        if "\n" in text or "\r" in text:
            raise Refused("A command must be a single line.")
        # Typed while the server is still starting, a command's "reply" would be
        # whatever start-up line comes next - so wait until it is ready.
        deadline = time.monotonic() + STARTUP_WAIT
        while not self.ready.is_set():
            if not self.running:  # it stopped (or crashed) while starting
                raise Refused("The server is not running.")
            if time.monotonic() > deadline:
                raise Refused("The server is still starting. Try again in a minute.")
            await asyncio.sleep(0.5)
        if not self.running:
            raise Refused("The server is not running.")
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
                    if until and until in line:
                        break
                    timeout = first_wait if until else settle
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
                            f"(exit code {code}). Its last lines are in the console screen.")
            log("second crash in the window - not restarting")
            return
        self.last_crash = now
        log("restarting it once")
        try:
            await self.start()
        except Refused as error:
            self.problem = str(error)

    async def stop(self, remember=True):
        """Stop cleanly: 'stop' on the console, wait for the save, force only as a last resort.

        remember=False is for the service itself shutting down (snap refresh,
        reboot): the server should come back afterwards.
        """
        if remember:
            self.state.update(desired="stopped")
        if not self.running:
            return {"ok": True, "note": "The server was not running."}
        self.stopping = True
        process = self.process
        # Minecraft can occasionally turn a "stop" down ("An unexpected error
        # occurred while trying to execute that command", seen once when it
        # arrived the instant start-up finished). So: watch for it to take,
        # type it once more, then SIGTERM (which also saves), and only kill
        # as a last resort.
        how = await self.ask_to_stop(process)
        try:
            await asyncio.wait_for(process.wait(), STOP_GRACE)
        except asyncio.TimeoutError:
            log(f"server did not stop within {STOP_GRACE}s - killing it")
            await signal_server(process.pid, "KILL")
            await process.wait()
            how += "+kill"
        log(f"server stopped ({how})")
        return {"ok": True, "how": how}

    async def ask_to_stop(self, process):
        """Get the server to begin shutting down; return how it was asked."""
        queue = asyncio.Queue()
        self.listeners.append(queue)
        try:
            for attempt in ("console", "console-again"):
                try:
                    process.stdin.write(b"stop\n")
                    await process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    break
                deadline = time.monotonic() + 10
                while (left := deadline - time.monotonic()) > 0:
                    try:
                        line = await asyncio.wait_for(queue.get(), left)
                    except asyncio.TimeoutError:
                        break
                    if "Stopping server" in line or "Stopping the server" in line:
                        return attempt
                if process.returncode is not None:
                    return attempt
                log(f"'stop' did not take ({attempt})")
        finally:
            self.listeners.remove(queue)
        log("sending SIGTERM (Minecraft saves the world on it)")
        await signal_server(process.pid, "TERM")
        return "sigterm"

    def eula_accepted(self):
        try:
            with open(os.path.join(SERVER_DIR, "eula.txt")) as f:
                return "eula=true" in f.read()
        except FileNotFoundError:
            return False

    # --- requests ------------------------------------------------------

    def status(self, caller):
        owner = self.state["owner_uid"]
        props = self.properties()
        reply = {"ok": True, "running": self.running, "desired": self.state["desired"],
                 "version": self.state["version"], "jar": self.state["jar"],
                 "ram_mb": self.state["ram_mb"], "eula": self.eula_accepted(),
                 "downloaded": os.path.exists(os.path.join(SERVER_DIR, self.state["jar"])),
                 "migrated": self.state["migrated"], "problem": self.problem,
                 "owner": user_name(owner) if owner is not None else None,
                 "you": user_name(caller),
                 "you_may_change": caller == 0 or owner is None or caller == owner,
                 "address": lan_address(), "port": int(props.get("server-port") or 25565),
                 "motd": props.get("motd"), "white_list_on": props.get("white-list") == "true",
                 "autostart": self.state["autostart"], "update_available": self.update_available(),
                 "previous_version": self.state["previous_version"],
                 "pinned": self.state.get("pinned", False), "latest": self.state["latest"],
                 "can_roll_back": os.path.exists(os.path.join(SERVER_DIR, "server.jar.previous"))}
        backups = self.backups()
        reply["last_backup"] = backups[0]["time"] if backups else None
        if self.running:
            reply["pid"] = self.process.pid
            reply["uptime_s"] = int(time.time() - self.started_at)
            reply["ready"] = self.ready.is_set()
            reply["players"] = list(self.online)
            reply["players_max"] = int(props.get("max-players") or 20)
        return reply

    def console_log(self, since):
        if self.lines:
            return {"ok": True, "lines": [t for s, t in self.lines if s > since],
                    "seq": self.lines[-1][0]}
        try:  # not running since the service started: show the last run's end
            with open(os.path.join(SERVER_DIR, "console.log"), errors="replace") as f:
                tail = collections.deque(f, maxlen=200)
            return {"ok": True, "lines": [l.rstrip("\n") for l in tail], "seq": 0}
        except FileNotFoundError:
            return {"ok": True, "lines": [], "seq": 0}

    async def download(self, version=None):
        """The latest server, or a chosen version (option 18).

        A chosen version that is not the latest is "pinned": no update alerts
        for it until the latest is downloaded again. Switching to a chosen
        version backs the world up first and restarts a running server, since
        the point is to switch now (players' games must match it).
        """
        wanted = None if version in (None, "") else str(version).strip()
        if wanted is not None and not VERSION_NAME.match(wanted):
            raise Refused("Type a version like 26.2.")
        version, url, sha1 = await asyncio.to_thread(server_download, wanted)
        latest = version if wanted is None else (await asyncio.to_thread(server_download))[0]
        switching = wanted is not None and (version != self.state["version"]
                                            or self.state["jar"] != "server.jar")
        restart = False
        if switching:
            if self.has_world():
                await self.backup("before-update")
            restart = self.running
            if restart:
                await self.stop()
        ensure_server_dir()
        try:
            await asyncio.to_thread(fetch_verified, url, sha1, os.path.join(SERVER_DIR, "server.jar"))
        except Exception:
            if restart:  # leave the family's server as it was, not stopped
                await self.start()
            raise
        pinned = version != latest
        self.state.update(version=version, jar="server.jar", latest=latest,
                          latest_checked=time.time(), pinned=pinned)
        log(f"downloaded server {version}" + (" (chosen; pinned)" if pinned else ""))
        if restart:
            await self.start()
            note = "The server is restarting with it."
        else:
            note = "It is used the next time the server starts." if self.running else None
        return {"ok": True, "version": version, "note": note, "pinned": pinned}

    async def command(self, text):
        if not self.running:
            raise Refused("The server is not running.")
        return {"ok": True, "reply": await self.console_command(text.strip())}

    async def player(self, action, name):
        """Whitelist, op or deop a player - live when running, in the files when not."""
        if not PLAYER_NAME.match(name or ""):
            raise Refused("A Minecraft name is 3 to 16 letters, digits or underscores.")
        if self.running:
            command = {"whitelist": "whitelist add", "unwhitelist": "whitelist remove",
                       "op": "op", "deop": "deop"}[action]
            return {"ok": True, "reply": await self.console_command(f"{command} {name}")}
        filename = "ops.json" if action in ("op", "deop") else "whitelist.json"
        path = os.path.join(SERVER_DIR, filename)
        entries = await read_server_json(filename)
        entries = [e for e in entries if e.get("name", "").lower() != name.lower()]
        if action in ("deop", "unwhitelist"):
            write_file(path, json.dumps(entries, indent=2) + "\n")
            done = "is no longer an operator" if action == "deop" else "is off the whitelist"
            return {"ok": True, "reply": [f"{name} {done}"]}
        profile = await asyncio.to_thread(lookup_player, name)
        if profile is None:
            raise Refused(f"There is no Minecraft account called {name}.")
        entry = {"uuid": profile["uuid"], "name": profile["name"]}
        if action == "op":
            entry.update(level=4, bypassesPlayerLimit=False)
        entries.append(entry)
        write_file(path, json.dumps(entries, indent=2) + "\n")
        done = "added to the whitelist" if action == "whitelist" else "made an operator"
        return {"ok": True, "reply": [f"{profile['name']} {done} (applies when the server starts)"]}

    async def players(self):
        props = self.properties()
        return {"ok": True,
                "whitelist": sorted(e["name"] for e in await read_server_json("whitelist.json")),
                "ops": sorted(e["name"] for e in await read_server_json("ops.json")),
                "online": list(self.online) if self.running else [],
                "white_list_on": props.get("white-list") == "true"}

    def set_properties(self, values):
        """Set some server.properties values, keeping every other line."""
        ensure_server_dir()
        path = os.path.join(SERVER_DIR, "server.properties")
        lines = []
        if os.path.exists(path):
            with open(path) as f:
                lines = f.read().splitlines()
        for key, value in values.items():
            lines = [l for l in lines if not l.startswith(key + "=")]
            lines.append(f"{key}={value}")
        write_file(path, "\n".join(lines) + "\n")

    def settings(self, fields):
        """The Settings screen and the first-run walkthrough: name, whitelist, memory, autostart."""
        props = {}
        if "motd" in fields:
            motd = str(fields["motd"]).strip()
            if not motd or len(motd) > 59 or any(c in motd for c in "\r\n\\"):
                raise Refused("The server name is 1 to 59 characters on one line.")
            props["motd"] = motd
        if "white_list" in fields:
            on = "true" if fields["white_list"] else "false"
            props.update({"white-list": on, "enforce-whitelist": on})
        if "ram_mb" in fields:
            ram_mb = int(fields["ram_mb"])
            if ram_mb < 1024:
                raise Refused("The server needs at least 1024 MB (1 GB) of memory.")
            self.state.update(ram_mb=ram_mb)
        if "autostart" in fields:
            self.state.update(autostart=bool(fields["autostart"]))
        if props:
            self.set_properties(props)
        note = "Restart the server to use the new settings." if self.running and props else None
        return {"ok": True, "note": note}

    async def replace_world(self, archive, keep_jars):
        """Swap the server's files for an archive's (a moved-over world, a backup).

        The current files are kept beside it in COMMON, never deleted. With
        keep_jars the server jars come along (backups leave them out).
        """
        kept = None
        if os.path.isdir(SERVER_DIR) and os.listdir(SERVER_DIR):
            kept = os.path.join(COMMON, time.strftime("previous-%Y-%m-%d-%H%M%S"))
            # Renaming the folder itself only needs COMMON, which is root's;
            # the snap_daemon-owned contents come along untouched.
            os.rename(SERVER_DIR, kept)
        ensure_server_dir()
        if kept and keep_jars:
            for jar in os.listdir(kept):
                if jar.endswith(".jar") or jar == "server.jar.previous":
                    shutil.copy(os.path.join(kept, jar), os.path.join(SERVER_DIR, jar))
        code, output = await run_as_daemon("/usr/bin/python3", "-m", "mcsi.extract",
                                           archive, SERVER_DIR)
        if code != 0:
            raise Refused(f"The files could not be unpacked: {output.strip()[-300:]}")
        return kept, output.strip()

    async def restore(self, name):
        if not BACKUP_NAME.match(name or ""):
            raise Refused("There is no backup by that name.")
        archive = os.path.join(BACKUP_DIR, name)
        if not os.path.exists(archive):
            raise Refused("There is no backup by that name.")
        was_running = self.running
        safety = await self.backup("before-restore") if self.has_world() else None
        await self.stop()
        kept, _ = await self.replace_world(archive, keep_jars=True)
        log(f"restored {name}")
        if kept and safety:
            await remove_folder(kept)  # the safety backup holds the same files
        if was_running:
            await self.start()
        return {"ok": True, "safety_backup": safety and safety["name"]}

    async def check_for_update(self):
        try:
            version, _, _ = await asyncio.to_thread(latest_server)
        except Exception as error:  # offline: try again at the next check
            log(f"update check failed: {error}")
            return
        self.state.update(latest=version, latest_checked=time.time())

    def update_available(self):
        latest, current = self.state["latest"], self.state["version"]
        if (self.state["jar"] != "server.jar" or self.state.get("pinned")
                or not latest or latest == current):
            return None
        return latest

    async def update(self):
        """Back up, stop, get the new server (keeping the old one), start again."""
        await self.check_for_update()
        latest = self.update_available()
        if not latest:
            raise Refused("You already have the latest Minecraft server.")
        was_running = self.running
        old_version = self.state["version"]
        if self.has_world():
            await self.backup("before-update")
        await self.stop()
        jar = os.path.join(SERVER_DIR, "server.jar")
        if os.path.exists(jar):
            os.replace(jar, jar + ".previous")
        try:
            result = await self.download()
        except Exception:
            if os.path.exists(jar + ".previous"):
                os.replace(jar + ".previous", jar)
            if was_running:
                await self.start()
            raise
        self.state.update(previous_version=old_version)
        if was_running:
            await self.start()
        return {"ok": True, "version": result["version"]}

    async def rollback(self):
        """Go back to the server jar the last update replaced."""
        jar = os.path.join(SERVER_DIR, "server.jar")
        if not os.path.exists(jar + ".previous"):
            raise Refused("There is no previous Minecraft version to go back to.")
        was_running = self.running
        await self.stop()
        os.replace(jar, jar + ".swap")
        os.replace(jar + ".previous", jar)
        os.replace(jar + ".swap", jar + ".previous")
        self.state.update(version=self.state["previous_version"],
                          previous_version=self.state["version"], jar="server.jar")
        if was_running:
            await self.start()
        return {"ok": True, "version": self.state["version"]}

    def has_world(self):
        return any(os.path.isfile(os.path.join(SERVER_DIR, d, "level.dat"))
                   for d in os.listdir(SERVER_DIR)) if os.path.isdir(SERVER_DIR) else False

    def backups(self):
        ensure_backup_dir()
        found = []
        for name in os.listdir(BACKUP_DIR):
            match = BACKUP_NAME.match(name)
            if match:
                path = os.path.join(BACKUP_DIR, name)
                found.append({"name": name, "kind": match.group(1), "path": path,
                              "size": os.path.getsize(path), "time": os.path.getmtime(path)})
        return sorted(found, key=lambda b: b["time"], reverse=True)  # newest first

    def rotate(self, kind):
        """Keep the newest BACKUPS_KEPT of an automatic kind; manual ones are never deleted."""
        if kind == "manual":
            return
        for old in [b for b in self.backups() if b["kind"] == kind][BACKUPS_KEPT:]:
            os.unlink(old["path"])  # BACKUP_DIR is root's, so root may remove it
            log(f"removed old backup {old['name']}")

    async def housekeeping(self):
        """Once an hour: a daily backup while the server runs, and a daily update check."""
        await asyncio.sleep(HOUSEKEEPING_FIRST)
        while True:
            try:
                if time.time() - self.state["latest_checked"] > DAY:
                    await self.check_for_update()
                daily = [b for b in self.backups() if b["kind"] == "daily"]
                due = not daily or time.time() - daily[0]["time"] > DAY
                if self.running and due and time.time() - self.started_at > 30:
                    await self.backup("daily")
            except Exception as error:  # never let housekeeping take the service down
                log(f"housekeeping: {error!r}")
            await asyncio.sleep(HOUSEKEEPING_EVERY)

    def get_properties(self):
        try:
            with open(os.path.join(SERVER_DIR, "server.properties")) as f:
                return {"ok": True, "text": f.read()}
        except FileNotFoundError:
            return {"ok": True, "text": "", "note": "The server creates this file the first "
                    "time it starts. Start it once, then come back."}

    def put_properties(self, text):
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0]
            if "=" not in stripped or not PROPERTY_KEY.match(key):
                raise Refused(f"Line {number} is not a setting (setting=value): {line[:40]}")
        ensure_server_dir()
        write_file(os.path.join(SERVER_DIR, "server.properties"), text.rstrip("\n") + "\n")
        self.prepare_files()  # RCON stays off whatever was typed
        note = "Restart the server to use the new settings." if self.running else None
        return {"ok": True, "note": note}

    async def backup(self, kind="manual"):
        """A consistent copy of the world and settings, saved while the server runs."""
        ensure_backup_dir()
        if not os.path.isdir(SERVER_DIR) or not os.listdir(SERVER_DIR):
            raise Refused("There is nothing to back up yet.")
        name = time.strftime(f"backup-{kind}-%Y-%m-%d-%H%M%S.tar.gz")
        path = os.path.join(BACKUP_DIR, name)
        if self.running:
            await self.console_command("save-off")
            await self.console_command("save-all flush", first_wait=60, until="Saved the game")
        try:
            code, output = await run_as_daemon("/usr/bin/python3", "-m", "mcsi.pack",
                                               SERVER_DIR, path)
        finally:
            if self.running:
                await self.console_command("save-on")
        if code != 0:
            if os.path.exists(path + ".part"):
                os.unlink(path + ".part")  # BACKUP_DIR is root's, so root may remove it
            raise Refused(f"The backup could not be written: {output.strip()[-300:]}")
        log(f"backup written: {name}")
        self.rotate(kind)
        return {"ok": True, "path": path, "name": name, "size": os.path.getsize(path)}

    async def import_world(self, upload):
        """Replace the server's files with a moved-over 14.x world (a tar.gz)."""
        if self.running:
            raise Refused("Stop the server before moving a world over.")
        kept, output = await self.replace_world(upload, keep_jars=False)
        self.state.update(migrated=True, version=None, jar="server.jar", desired="stopped")
        if kept:
            log(f"world moved over; the previous files are in {kept}")
        return {"ok": True, "kept": kept, "note": output or None}

    def put_jar(self, upload, name):
        if not JAR_NAME.match(name or ""):
            raise Refused("A jar name is letters, digits, dots, dashes or underscores, ending in .jar.")
        jar = "custom-" + name
        ensure_server_dir()
        target = os.path.join(SERVER_DIR, jar)
        if os.path.lexists(target):
            os.unlink(target)
        os.chmod(upload, 0o644)
        os.replace(upload, target)
        self.state.update(jar=jar)
        return {"ok": True, "jar": jar}


async def read_server_json(name):
    """A JSON file from the server folder ([] if missing or unreadable).

    Minecraft writes some files readable by snap_daemon only; root inside the
    snap cannot read past that, so fall back to reading it as snap_daemon.
    """
    path = os.path.join(SERVER_DIR, name)
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        return []
    except PermissionError:
        code, text = await run_as_daemon("/usr/bin/cat", path)
        if code != 0:
            return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    return data if isinstance(data, list) else []


async def remove_folder(path):
    """Delete a set-aside server folder (COMMON/previous-*).

    Its contents are mostly snap_daemon's, which root cannot delete here, so
    snap_daemon empties it (the folder itself is root's and group-writable),
    then root removes the empty folder from COMMON.
    """
    if not os.path.basename(path).startswith("previous-") or os.path.dirname(path) != COMMON:
        raise ValueError(f"not a set-aside server folder: {path}")
    code, output = await run_as_daemon("/usr/bin/find", path, "-mindepth", "1", "-delete")
    try:
        os.rmdir(path)
    except OSError as error:
        log(f"could not remove {path}: {error} {output.strip()[-200:]}")


def current_boot_id():
    with open("/proc/sys/kernel/random/boot_id") as f:
        return f.read().strip()


async def signal_server(pid, name):
    """Send a signal to the server as snap_daemon (root lacks CAP_KILL here)."""
    code, _ = await run_as_daemon("/usr/bin/kill", "-s", name, str(pid))
    return code == 0


def ensure_server_dir():
    _, gid = daemon_ids()
    os.makedirs(SERVER_DIR, exist_ok=True)
    os.chown(SERVER_DIR, 0, gid)
    os.chmod(SERVER_DIR, 0o775)  # no setgid: the snap sandbox refuses it


def ensure_backup_dir():
    """Backups are written by snap_daemon (see mcsi.pack), into a folder root keeps."""
    _, gid = daemon_ids()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.chown(BACKUP_DIR, 0, gid)
    os.chmod(BACKUP_DIR, 0o775)


def write_file(path, text, mode=0o664):
    """Replace a file whole, owned by snap_daemon so Java can rewrite it too."""
    uid, gid = daemon_ids()
    temp = path + ".tmp"
    if os.path.lexists(temp):  # a leftover may already be snap_daemon's
        os.unlink(temp)
    with open(temp, "w") as f:
        f.write(text)
    # Mode first: once the file is snap_daemon's, root can no longer change it.
    os.chmod(temp, mode)
    os.chown(temp, uid, gid)
    os.replace(temp, path)


def lan_address():
    """This computer's address on the home network (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            return sock.getsockname()[0]
    except OSError:
        return None


def server_download(wanted=None):
    """(version, url, sha1) of a server jar from Mojang's list: the latest release, or `wanted`."""
    with urllib.request.urlopen(MANIFEST_URL, timeout=20) as r:
        manifest = json.load(r)
    version = wanted or manifest["latest"]["release"]
    entry = next((v for v in manifest["versions"] if v["id"] == version), None)
    if entry is None:
        raise Refused(f"There is no Minecraft version called {version}. "
                      f"Versions look like {manifest['latest']['release']}.")
    with urllib.request.urlopen(entry["url"], timeout=20) as r:
        details = json.load(r)
    server = details.get("downloads", {}).get("server")
    if not server:
        raise Refused(f"Mojang has no server download for Minecraft {version}.")
    return version, server["url"], server["sha1"]


def latest_server():
    return server_download()


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
        raise Refused("The download was damaged (checksum mismatch). Nothing was changed.")
    os.chmod(partial, 0o644)
    os.replace(partial, target)


def lookup_player(name):
    """Mojang's id for a player name, or None if there is no such account."""
    try:
        with urllib.request.urlopen(PROFILE_URL + urllib.parse.quote(name), timeout=15) as r:
            if r.status != 200:
                return None
            data = json.load(r)
    except urllib.error.HTTPError as error:
        if error.code in (204, 404):
            return None
        raise
    raw = data["id"]
    uuid = f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return {"uuid": uuid, "name": data["name"]}


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
        # Root may not read another user's /proc/<pid>/cmdline here, but it
        # may stat the directory: a live process owned by snap_daemon with
        # the pid we recorded is our server.
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


async def receive_upload(reader, size):
    """Read `size` bytes after the request line into a file in INCOMING_DIR."""
    os.makedirs(INCOMING_DIR, mode=0o755, exist_ok=True)
    path = os.path.join(INCOMING_DIR, f"upload-{time.time_ns()}")
    remaining = size
    with open(path, "wb") as f:
        while remaining:
            chunk = await reader.read(min(remaining, 1 << 20))
            if not chunk:
                os.unlink(path)
                raise Refused("The upload was cut off.")
            f.write(chunk)
            remaining -= len(chunk)
    os.chmod(path, 0o644)  # snap_daemon unpacks worlds from here
    return path


async def main():
    ensure_server_dir()
    state = State()
    server = Server(state)
    boot_id = current_boot_id()
    booted = state["boot_id"] is not None and state["boot_id"] != boot_id
    state.update(boot_id=boot_id)

    async def handle(reader, writer):
        upload = None
        try:
            request = json.loads(await reader.readline())
            name = request.get("cmd")
            caller = peer_uid(writer)
            if name not in READ_ONLY:
                owner = state["owner_uid"]
                if owner is None and caller != 0:
                    state.update(owner_uid=caller)
                    log(f"{user_name(caller)} is now the server's owner")
                elif caller not in (0, owner):
                    raise Refused(f"Only {user_name(owner)} can change this server.")
                log(f"request {name!r} from {user_name(caller)}")
            if request.get("size"):
                upload = await receive_upload(reader, int(request["size"]))

            if name == "status":
                reply = server.status(caller)
            elif name == "log":
                reply = server.console_log(int(request.get("since", 0)))
            elif name == "download":
                reply = await server.download(request.get("version"))
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
            elif name in ("whitelist", "unwhitelist", "op", "deop"):
                reply = await server.player(name, request.get("name"))
            elif name == "players":
                reply = await server.players()
            elif name == "settings":
                reply = server.settings({k: v for k, v in request.items()
                                         if k in ("motd", "white_list", "ram_mb", "autostart")})
            elif name == "restore":
                reply = await server.restore(request.get("name"))
            elif name == "update":
                reply = await server.update()
            elif name == "rollback":
                reply = await server.rollback()
            elif name == "get-properties":
                reply = server.get_properties()
            elif name == "put-properties":
                reply = server.put_properties(request["text"])
            elif name == "backup":
                reply = await server.backup()
            elif name == "list-backups":
                reply = {"ok": True, "backups": server.backups()}
            elif name == "import-world":
                reply = await server.import_world(upload)
            elif name == "put-jar":
                reply = server.put_jar(upload, request.get("name"))
                upload = None  # moved into place
            elif name == "use-jar":
                if not os.path.exists(os.path.join(SERVER_DIR, request.get("jar", ""))):
                    raise Refused("That jar is not on the server.")
                state.update(jar=request["jar"])
                reply = {"ok": True}
            elif name == "set-owner":
                if caller != 0:
                    raise Refused("Changing the owner takes sudo.")
                state.update(owner_uid=pwd.getpwnam(request["user"]).pw_uid)
                reply = {"ok": True, "owner": request["user"]}
            else:
                raise Refused(f"Unknown request {name!r}.")
        except Refused as error:
            reply = {"ok": False, "error": str(error)}
        except Exception as error:
            log(f"request failed: {error!r}")
            reply = {"ok": False, "error": f"Something went wrong: {error}"}
        finally:
            if upload and os.path.exists(upload):
                os.unlink(upload)
        try:
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
            writer.close()
        except (ConnectionResetError, BrokenPipeError):
            pass  # the menu went away before the answer; the request still ran

    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    listener = await asyncio.start_unix_server(handle, SOCKET_PATH, limit=1 << 20)
    os.chmod(SOCKET_PATH, 0o666)  # every local user may ask; only the owner may change
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
        # A new boot id means the computer restarted (rather than a snap
        # refresh or a service restart, which always bring the server back).
        if booted and not state["autostart"]:
            log("the computer restarted and 'start with the computer' is off - leaving it stopped")
            state.update(desired="stopped")
        else:
            log("the server was running before - starting it again")
            try:
                await server.start()
            except Refused as error:
                server.problem = str(error)
                log(f"could not start it: {error}")
    asyncio.create_task(server.housekeeping())

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
