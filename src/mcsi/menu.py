"""The mc-server-installer menu (Textual): a front end for the background service.

The server runs in the background service, never in this program, so closing
the menu - or logging out - leaves the family's game running. Every action
here is a request to the service (mcsi.client); the service decides what is
allowed (only the server's owner may change it) and explains refusals, which
this shows as they come.

The 17 options of 14.x keep their order, wording and number keys; a two-digit
number is typed quickly (1 then 3 for 13).
"""

import os
import re
import shutil
import time

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, Footer, Header, Input, Label, Markdown, OptionList,
                             RichLog, Static, Switch, TextArea)
from textual.widgets.option_list import Option

from mcsi import client, migrate

REAL_HOME = os.environ.get("SNAP_REAL_HOME", os.path.expanduser("~"))
PLAYER_NAME = re.compile(r"^[A-Za-z0-9_]{3,16}$")  # the same rule as the service
EULA_URL = "https://aka.ms/MinecraftEULA"

OPTIONS = {
    1: "Download the latest server",
    2: "Agree to the Minecraft EULA",
    3: "Edit server settings (server.properties)",
    4: "Start the server with 2 GB of memory",
    5: "Start the server with 4 GB of memory",
    6: "Start the server with 6 GB of memory",
    7: "Start the server with 8 GB of memory",
    8: "Start the server with 16 GB of memory",
    9: "Read the README",
    10: "Back up your world now",
    11: "Start with a custom amount of memory",
    12: "Start with a custom server jar",
    13: "Stop the server",
    14: "Add a player to the whitelist",
    15: "Make a player an operator",
    16: "Remove a player's operator status",
    17: "Remove a player from the whitelist",
    18: "Specify server version (e.g. 26.2)",
}
START_RAM = {4: 2048, 5: 4096, 6: 6144, 7: 8192, 8: 16384}

README = f"""\
# Minecraft Server Installer

Your Minecraft server runs **in the background**, looked after by your
computer. You can close this window, or log out, and the server keeps
running. It also comes back by itself after the computer restarts, if it
was running before.

## Getting started

1. **Option 1** downloads the latest Minecraft server.
2. **Option 2** shows the Minecraft EULA. You must agree to it to run a server.
3. **Options 4 to 8** start the server with that much memory. 2 GB suits a
   few players; give it more for more players or a bigger world.
4. In Minecraft, choose **Multiplayer**, then **Add Server**, and type the
   address shown at the top of this window.

## Good to know

- **Who can play:** anyone at home, unless you choose otherwise. To allow
  only certain players, add them (option 14, or press **p**) and turn on the
  whitelist in Settings (press **s**). Do that before letting people join
  over the internet.
- **Operators** (option 15) can use cheats and server commands in the game.
- **Backups** (press **b**): daily while the server runs (the newest 7 are
  kept), before every update and restore, and whenever you choose option 10,
  which also puts a copy in your Home folder. Restore any of them from here.
- **Players** (press **p**) and **Settings** (press **s**): who can join,
  operators, the server name, memory, and whether the server starts with
  the computer.
- **A specific version** (option 18): for when the latest Minecraft has a
  problem. Everyone's game must be set to the same version.
- **Updates:** when a new Minecraft comes out, the top of this window says
  so. Press **u**: your world is backed up, then the server updates and
  restarts. Settings can go back to the previous version.
- **Console** (press **c**): the server's live log, and a box for server
  commands such as `say Dinner time!`.
- **Only the person who set up the server can change it.** Other people on
  this computer can open this menu and see how it is doing.
- The server's files are in `/var/snap/mc-server-installer/common/server`.

This is not an official Minecraft product and is not approved by or
associated with Mojang or Microsoft. Minecraft EULA: {EULA_URL}

Made by kz6fittycent - https://github.com/kz6fittycent/mc-server-installer
"""


def parse_memory(text):
    """'4G', '4096M', '4096' or '4 GB' to megabytes, or None."""
    value = text.strip().upper().replace(" ", "").removesuffix("B")
    try:
        if value.endswith("G"):
            return int(float(value[:-1]) * 1024)
        return int(value.removesuffix("M"))
    except ValueError:
        return None


def describe_uptime(seconds):
    hours, minutes = divmod(seconds // 60, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def server_label(s):
    if s["jar"] != "server.jar":
        return f"your own server ({s['jar'].removeprefix('custom-')})"
    return f"Minecraft {s['version']}" if s["version"] else "Minecraft (from your old server)"


def memory_label(mb):
    return f"{mb // 1024} GB" if mb % 1024 == 0 else f"{mb} MB"


def status_text(s):
    """The status panel, from the service's status reply."""
    lines = []
    if s["running"] and not s.get("ready", True):
        lines.append(f"[b yellow]◐ Starting…[/]  {server_label(s)}  ·  ready to join in a minute "
                     "or so")
    elif s["running"]:
        players = s.get("players", [])
        who = f": {', '.join(players)}" if players else ""
        lines.append(f"[b green]● Running[/]  {server_label(s)}  ·  "
                     f"{len(players)} of {s.get('players_max', 20)} players{who}  ·  "
                     f"{memory_label(s['ram_mb'])} memory  ·  "
                     f"up {describe_uptime(s.get('uptime_s', 0))}")
    else:
        lines.append("[b]○ Stopped[/]" + (f"  {server_label(s)}" if s["downloaded"] else ""))
        if not s["downloaded"]:
            lines.append("Start here: press [b]1[/] to download the server.")
        elif not s["eula"]:
            lines.append("Next: press [b]2[/] to read and agree to the Minecraft EULA.")
        else:
            lines.append("Press [b]4[/] to start it.")
    if s.get("address"):
        port = "" if s["port"] == 25565 else f":{s['port']}"
        lines.append(f"Join from Minecraft at: [b]{s['address']}{port}[/]")
    if not s["you_may_change"]:
        lines.append(f"[yellow]You can watch this server; only {s['owner']} can change it.[/]")
    if s.get("pinned") and s.get("latest") and s.get("version") != s.get("latest"):
        world = f" (world \"{s['level']}\")" if s.get("level", "world") != "world" else ""
        lines.append(f"[dim]You chose Minecraft {s['version']}{world}. Minecraft {s['latest']} is "
                     "the latest: press 1 to switch to it.[/]")
    if s.get("update_available"):
        lines.append(f"[b cyan]Minecraft {s['update_available']} is available.[/] "
                     "Press [b]u[/] to update (your world is backed up first).")
    if s.get("last_backup"):
        lines.append(f"Last backup: {when(s['last_backup'])}")
    if s.get("problem"):
        lines.append(f"[b red]{s['problem']}[/]")
    return "\n".join(lines)


# --- dialogs ----------------------------------------------------------------

class Confirm(ModalScreen[bool]):
    def __init__(self, message, yes="Yes", no="Cancel"):
        super().__init__()
        self.message, self.yes, self.no = message, yes, no

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self.message)
            with Horizontal(classes="buttons"):
                yield Button(self.yes, variant="primary", id="yes")
                yield Button(self.no, id="no")

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == "yes")

    def key_escape(self):
        self.dismiss(False)


class Choose(ModalScreen[str | None]):
    """A question with a few labelled answers; dismisses with the chosen id (or None)."""

    def __init__(self, message, choices):
        super().__init__()
        self.message, self.choices = message, choices  # [(id, label, primary?)]

    def compose(self) -> ComposeResult:
        # The message scrolls and the answers stay visible, even in 80x24.
        with Vertical(classes="dialog tall"):
            with VerticalScroll(classes="form"):
                yield Static(self.message)
            for choice_id, label, primary in self.choices:
                yield Button(label, variant="primary" if primary else "default", id=choice_id,
                             classes="choice")
            yield Button("Cancel", id="cancel", classes="choice")

    def on_mount(self):
        self.query_one(Button).focus()

    def on_button_pressed(self, event):
        self.dismiss(None if event.button.id == "cancel" else event.button.id)

    def key_escape(self):
        self.dismiss(None)


class Ask(ModalScreen[str | None]):
    def __init__(self, question, placeholder=""):
        super().__init__()
        self.question, self.placeholder = question, placeholder

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self.question)
            yield Input(placeholder=self.placeholder, id="answer")
            with Horizontal(classes="buttons"):
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_input_submitted(self, event):
        self.dismiss(event.value.strip() or None)

    def on_button_pressed(self, event):
        value = self.query_one("#answer", Input).value.strip()
        self.dismiss(value or None if event.button.id == "ok" else None)

    def key_escape(self):
        self.dismiss(None)


class Properties(ModalScreen[str | None]):
    def __init__(self, text, note=None):
        super().__init__()
        self.text, self.note = text, note

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static("[b]Server settings[/] (server.properties). One setting per line: "
                         "setting=value. Changes apply the next time the server starts.")
            if self.note:
                yield Static(f"[yellow]{self.note}[/]")
            yield TextArea(self.text, id="properties")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event):
        self.dismiss(self.query_one(TextArea).text if event.button.id == "save" else None)

    def key_escape(self):
        self.dismiss(None)


class Help(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            with VerticalScroll():
                yield Markdown(README)
            yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event):
        self.dismiss(None)

    def key_escape(self):
        self.dismiss(None)


class Console(Screen):
    """The server's live log, and a box to type server commands."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back to the menu")]

    def __init__(self):
        super().__init__()
        self.seq = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="log", markup=False, highlight=False, max_lines=2000, wrap=True)
        yield Input(placeholder="Type a server command and press Enter, e.g. say Dinner time!",
                    id="command")
        yield Footer()

    def on_mount(self):
        self.query_one(Input).focus()
        self.poll()
        self.set_interval(1, self.poll)

    @work(thread=True, exclusive=True, group="log")
    def poll(self):
        try:
            reply = client.request("log", since=self.seq, timeout=10)
        except client.ServiceError:
            return
        if reply["lines"]:
            self.app.call_from_thread(self.show, reply["lines"])
        self.seq = reply["seq"]

    def show(self, lines):
        log = self.query_one(RichLog)
        for line in lines:
            log.write(line)

    def on_input_submitted(self, event):
        text = event.value.strip()
        event.input.value = ""
        if text:
            self.send(text)

    @work(thread=True)
    def send(self, text):
        try:
            client.request("command", text=text)
        except client.ServiceError as error:
            self.app.call_from_thread(self.app.notify, str(error), severity="error")


# --- phase 3 screens --------------------------------------------------------

def suggested_memory():
    """A memory amount for the server from this computer's RAM, and why."""
    try:
        with open("/proc/meminfo") as f:
            total_mb = int(next(l for l in f if l.startswith("MemTotal")).split()[1]) // 1024
    except (OSError, StopIteration, ValueError):
        return 2048, "a safe amount for a few players"
    # MemTotal reads a little under the installed size (a "4 GB" machine shows ~3.8 GB).
    for limit, suggest in ((3072, 1024), (6144, 2048), (12288, 3072), (24576, 4096)):
        if total_mb <= limit:
            break
    else:
        suggest = 6144
    return suggest, (f"this computer has {round(total_mb / 1024)} GB, and leaving the rest "
                     "free keeps it running smoothly")


def when(timestamp):
    return time.strftime("%d %b, %H:%M", time.localtime(timestamp))


class Setup(Screen):
    """First run: one question per step, then download, start, and how to join."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Leave setup for now")]
    STEPS = ("welcome", "eula", "name", "memory", "players", "ready", "working", "done")

    def __init__(self, status):
        super().__init__()
        self.status = status
        self.step = 0
        self.answers = {}
        self.memory, self.memory_reason = suggested_memory()

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="setup"):
            yield Static(id="step-text")
            yield Input(id="step-input")
            with Horizontal(classes="buttons"):
                yield Button("Next", variant="primary", id="next")
                yield Button("Back", id="back")
        yield Footer()

    def on_mount(self):
        self.show()

    def show(self):
        name = self.STEPS[self.step]
        text = self.query_one("#step-text", Static)
        field = self.query_one("#step-input", Input)
        next_button = self.query_one("#next", Button)
        back_button = self.query_one("#back", Button)
        field.display = name in ("name", "memory", "players")
        back_button.display = name not in ("welcome", "working", "done")
        next_button.display = name != "working"
        next_button.label = {"eula": "I agree", "ready": "Set it up", "done": "Go to the menu"}.get(name, "Next")
        if name == "welcome":
            text.update("[b]Welcome![/]\n\nThis sets up a Minecraft server on this computer, so your "
                        "family can play together in one world.\n\nIt takes about two minutes. The "
                        "server then runs in the background: you can close this window, and it keeps "
                        "going.")
        elif name == "eula":
            text.update("[b]The Minecraft EULA[/]\n\nTo run a Minecraft server you must agree to the "
                        f"Minecraft End User License Agreement:\n\n  {EULA_URL}\n\nOpen that link in a "
                        "web browser and read it. Press [b]I agree[/] if you agree to it.")
        elif name == "name":
            text.update("[b]Name your server[/]\n\nThis is what your family sees in their Minecraft "
                        "server list.")
            field.value = self.answers.get("motd", f"{self.status['you']}'s Minecraft server")[:59]
        elif name == "memory":
            text.update(f"[b]Memory[/]\n\nWe suggest [b]{memory_label(self.memory)}[/]: "
                        f"{self.memory_reason}. You can change this later in Settings.")
            field.value = self.answers.get("memory", memory_label(self.memory).replace(" ", ""))
            field.placeholder = "for example 2G or 4096M"
        elif name == "players":
            text.update("[b]Who can play?[/]\n\nLeave this empty and anyone at home can join - "
                        "that's how most families use it.\n\nOr, to allow only certain players, type "
                        "their Minecraft names, separated by commas. The [b]first name[/] becomes the "
                        "operator, who can use cheats and server commands in the game. You can change "
                        "this later (press p).")
            field.value = self.answers.get("players", "")
            field.placeholder = "for example Steve, Alex"
        elif name == "ready":
            names = self.answers["names"]
            players = (f"only {', '.join(names)} (operator: {names[0]})" if names
                       else "anyone at home can join")
            text.update(f"[b]Ready[/]\n\nServer name: {self.answers['motd']}\nMemory: "
                        f"{memory_label(self.answers['ram_mb'])}\nPlayers: {players}"
                        "\n\nThis downloads the latest Minecraft server and starts it.")
        if field.display:
            field.focus()
        else:
            next_button.focus()

    def on_input_submitted(self, event):
        self.next()

    def on_button_pressed(self, event):
        if event.button.id == "back":
            self.step -= 1
            self.show()
        else:
            self.next()

    def next(self):
        name = self.STEPS[self.step]
        value = self.query_one("#step-input", Input).value.strip()
        if name == "done":
            self.app.pop_screen()
            return
        if name == "name":
            if not value or len(value) > 59:
                self.notify("Type a name of up to 59 characters.", severity="error")
                return
            self.answers["motd"] = value
        elif name == "memory":
            ram_mb = parse_memory(value)
            if not ram_mb or ram_mb < 1024:
                self.notify("Type an amount like 2G or 4096M (at least 1G).", severity="error")
                return
            self.answers.update(memory=value, ram_mb=ram_mb)
        elif name == "players":
            names = [n.strip() for n in value.split(",") if n.strip()]
            bad = [n for n in names if not PLAYER_NAME.match(n)]
            if bad:
                self.notify("Minecraft names are 3 to 16 letters, digits or underscores. "
                            f"Not valid: {', '.join(bad)}", severity="error", timeout=8)
                return
            self.answers.update(players=value, names=names)
        self.step += 1
        self.show()
        if self.STEPS[self.step] == "working":
            self.set_up()

    @work(thread=True)
    def set_up(self):
        lines = []

        def say(line):
            lines.append(line)
            self.app.call_from_thread(self.query_one("#step-text", Static).update,
                                      "[b]Setting up…[/]\n\n" + "\n".join(lines))
        a = self.answers
        try:
            client.request("accept-eula"); say("✓ Agreed to the Minecraft EULA")
            # Naming players turns the whitelist on; otherwise anyone at home can join.
            client.request("settings", motd=a["motd"], white_list=bool(a["names"]), ram_mb=a["ram_mb"])
            say("✓ Saved the server name and memory")
            if not a["names"]:
                say("✓ Anyone at home can join")
            for number, player in enumerate(a["names"]):
                client.request("whitelist", name=player)
                if number == 0:
                    client.request("op", name=player)
                say(f"✓ {player} can play" + (" (operator)" if number == 0 else ""))
            say("… Downloading the Minecraft server")
            version = client.request("download")["version"]
            say(f"✓ Downloaded Minecraft {version}")
            client.request("start", ram_mb=a["ram_mb"]); say("✓ Started the server")
        except client.ServiceError as error:
            say(f"[b red]✗ {error}[/]\n\nPress Escape to go to the menu; you can carry on from there.")
            return
        status = client.request("status")
        port = "" if status["port"] == 25565 else f":{status['port']}"
        self.app.call_from_thread(self.finish, status.get("address"), port)

    def finish(self, address, port):
        self.step = self.STEPS.index("done")
        self.show()
        self.query_one("#step-text", Static).update(
            "[b green]Your server is running![/]\n\nIt is ready to join in a minute or so. On each "
            "computer that should play:\n\n  1. Open Minecraft and choose [b]Multiplayer[/]\n"
            f"  2. Choose [b]Add Server[/] and type  [b]{address}{port}[/]\n  3. Join!\n\n"
            "You can close this window any time. The server keeps running in the background.")


class Players(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Asking the server…", id="players-text")
            # Two rows, so every button fits an 80-column terminal.
            with Horizontal(classes="buttons"):
                yield Button("Add player", variant="primary", id="whitelist")
                yield Button("Remove player", id="unwhitelist")
            with Horizontal(classes="buttons"):
                yield Button("Make operator", id="op")
                yield Button("Remove operator", id="deop")
                yield Button("Close", id="close")

    def on_mount(self):
        self.load()

    @work(thread=True, exclusive=True)
    def load(self):
        try:
            p = client.request("players")
        except client.ServiceError as error:
            text = f"[b red]{error}[/]"
        else:
            text = ("[b]Players[/]\n\n"
                    f"Allowed to join: {', '.join(p['whitelist']) or 'nobody yet'}\n"
                    f"Operators: {', '.join(p['ops']) or 'none'}\n"
                    f"Playing now: {', '.join(p['online']) or 'nobody'}\n\n"
                    + ("Only the allowed players can join (the whitelist is on)." if p["white_list_on"]
                       else "Anyone at home can join. To allow only the players listed above, "
                            "turn on the whitelist in Settings (s)."))
        self.app.call_from_thread(self.query_one("#players-text", Static).update, text)

    def on_button_pressed(self, event):
        action = event.button.id
        if action == "close":
            self.dismiss(None)
            return
        question = {"whitelist": "Which Minecraft name should be allowed to join?",
                    "unwhitelist": "Which player should no longer be allowed to join?",
                    "op": "Which player should become an operator? Operators can use cheats "
                          "and server commands.",
                    "deop": "Which operator should go back to being a normal player?"}[action]
        self.app.push_screen(Ask(question), lambda name: name and self.change(action, name))

    @work(thread=True)
    def change(self, action, name):
        try:
            reply = client.request(action, name=name)
            self.app.call_from_thread(self.app.notify, "\n".join(reply.get("reply") or []) or "Done.")
        except client.ServiceError as error:
            self.app.call_from_thread(self.app.notify, str(error), severity="error", timeout=8)
        self.load()

    def key_escape(self):
        self.dismiss(None)


class Backups(ModalScreen[None]):
    KINDS = {"manual": "backed up by you", "daily": "daily", "before-restore": "before a restore",
             "before-update": "before an update"}

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static("[b]Backups[/]  Daily backups happen while the server runs; the newest 7 "
                         "are kept. Backups you make are never deleted.")
            yield OptionList(id="backup-list")
            with Horizontal(classes="buttons"):
                yield Button("Back up now", variant="primary", id="backup")
                yield Button("Restore", id="restore")
                yield Button("Copy to Home", id="copy")
                yield Button("Close", id="close")

    def on_mount(self):
        self.backups = []
        self.load()

    @work(thread=True, exclusive=True)
    def load(self):
        try:
            self.backups = client.request("list-backups")["backups"]
        except client.ServiceError as error:
            self.app.call_from_thread(self.app.notify, str(error), severity="error")
            return
        self.app.call_from_thread(self.fill)

    def fill(self):
        listing = self.query_one(OptionList)
        listing.clear_options()
        for b in self.backups:
            listing.add_option(Option(f"{when(b['time'])}  ·  {self.KINDS.get(b['kind'], b['kind'])}"
                                      f"  ·  {b['size'] / 1048576:.1f} MB", id=b["name"]))
        if not self.backups:
            listing.add_option(Option("No backups yet", disabled=True))

    def chosen(self):
        listing = self.query_one(OptionList)
        if listing.highlighted is None or not self.backups:
            self.notify("Choose a backup in the list first.", severity="warning")
            return None
        return self.backups[listing.highlighted]

    def on_button_pressed(self, event):
        action = event.button.id
        if action == "close":
            self.dismiss(None)
        elif action == "backup":
            self.app.backup()
            self.set_timer(3, self.load)
        elif action == "copy" and (b := self.chosen()):
            self.copy_home(b)
        elif action == "restore" and (b := self.chosen()):
            self.app.push_screen(Confirm(
                f"Restore the backup from [b]{when(b['time'])}[/]?\n\nThe world goes back to how it "
                "was then. Your world as it is now is backed up first, so you can come back to it. "
                "If the server is running it restarts; anyone playing is disconnected.",
                yes="Restore"), lambda yes: yes and self.restore(b))

    @work(thread=True)
    def restore(self, backup):
        self.app.call_from_thread(self.app.notify, "Restoring… this can take a minute.")
        try:
            client.request("restore", name=backup["name"])
        except client.ServiceError as error:
            self.app.call_from_thread(self.app.notify, str(error), severity="error", timeout=10)
            return
        self.app.call_from_thread(self.app.notify, f"Restored the backup from {when(backup['time'])}.",
                                  timeout=10)
        self.load()

    @work(thread=True)
    def copy_home(self, backup):
        try:
            shutil.copy(backup["path"], os.path.join(REAL_HOME, backup["name"]))
        except OSError as error:
            self.app.call_from_thread(self.app.notify, f"Could not copy it: {error.strerror}",
                                      severity="error")
            return
        self.app.call_from_thread(self.app.notify, f"Copied {backup['name']} to your Home folder.")

    def key_escape(self):
        self.dismiss(None)


class Settings(ModalScreen[None]):
    def __init__(self, status):
        super().__init__()
        self.status = status

    def compose(self) -> ComposeResult:
        s = self.status
        # The form scrolls and the buttons stay put, so Save is reachable even
        # in an 80x24 terminal.
        with Vertical(classes="dialog tall"):
            yield Static("[b]Settings[/]")
            with VerticalScroll(classes="form"):
                yield Label("Server name (shown in Minecraft's server list)")
                yield Input(s.get("motd") or "", id="motd")
                yield Label("Memory for the server, for example 4G")
                yield Input(memory_label(s["ram_mb"]).replace(" ", ""), id="memory")
                with Horizontal(classes="switch-row"):
                    yield Switch(s["white_list_on"], id="white_list")
                    yield Label("Only allowed players can join (whitelist)")
                with Horizontal(classes="switch-row"):
                    yield Switch(s["autostart"], id="autostart")
                    yield Label("Start the server when the computer starts")
                if s.get("can_roll_back"):
                    yield Button(f"Go back to Minecraft {s.get('previous_version') or 'previous version'}",
                                 id="rollback")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Close", id="close")

    def on_button_pressed(self, event):
        if event.button.id == "close":
            self.dismiss(None)
        elif event.button.id == "rollback":
            app = self.app
            self.dismiss(None)  # first, so the question below is not what gets closed
            app.push_screen(Confirm(
                "Go back to the previous Minecraft version? Players' games must match the "
                "server's version to join."), lambda yes: yes and app.ask_service(
                    "rollback", "Going back…", lambda r: f"Now on Minecraft {r['version']}."))
        elif event.button.id == "save":
            ram_mb = parse_memory(self.query_one("#memory", Input).value)
            if not ram_mb or ram_mb < 1024:
                self.notify("Type a memory amount like 2G or 4096M (at least 1G).", severity="error")
                return
            self.app.ask_service(
                "settings", done=lambda r: "Settings saved. " + (r.get("note") or ""),
                motd=self.query_one("#motd", Input).value.strip(), ram_mb=ram_mb,
                white_list=self.query_one("#white_list", Switch).value,
                autostart=self.query_one("#autostart", Switch).value)
            self.dismiss(None)

    def key_escape(self):
        self.dismiss(None)


# --- the menu ---------------------------------------------------------------

class Menu(App):
    TITLE = "Minecraft Server Installer"
    ENABLE_COMMAND_PALETTE = False  # one less thing for beginners to wonder about
    CSS = """
    #status { padding: 1 2; border: round $accent; height: auto; }
    #menu { height: 1fr; margin: 0 1; }
    #hint { padding: 0 2; color: $text-muted; }
    .dialog { width: 72; max-width: 96%; height: auto; max-height: 90%; padding: 1 2;
              border: thick $accent; background: $surface; }
    .dialog.wide { width: 100; height: 90%; }
    .dialog.tall { height: 90%; }
    .dialog.tall .form { height: 1fr; }
    .dialog TextArea { height: 1fr; }
    .dialog VerticalScroll { height: 1fr; }
    .buttons { height: auto; margin-top: 1; align-horizontal: right; }
    .buttons Button { margin-left: 1; }
    Confirm, Ask, Choose, Properties, Help, Players, Backups, Settings { align: center middle; }
    .choice { width: 100%; margin-top: 1; }
    .setup { width: 100%; max-width: 80; height: auto; margin: 1 2; padding: 1 2;
             border: round $accent; }
    .setup Input { margin-top: 1; }
    .switch-row { height: auto; margin-top: 1; }
    .switch-row Label { padding: 1 1; }
    #backup-list { height: 1fr; }
    #command { dock: bottom; }
    """
    BINDINGS = [
        Binding("p", "players", "Players"),
        Binding("b", "backups", "Backups"),
        Binding("s", "settings", "Settings"),
        Binding("u", "update", "Update", show=False),
        Binding("c", "console", "Console"),
        Binding("m", "move", "Move old world", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit (server keeps running)"),
    ]

    def __init__(self):
        super().__init__()
        self.status = None
        self.digits = ""
        self.digit_timer = None
        self.old_server = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Asking the background service…", id="status")
        yield OptionList(*(Option(f"{n:>2}  {label}", id=str(n)) for n, label in OPTIONS.items()),
                         id="menu")
        yield Static("You can close this window any time (press q). "
                     "The server keeps running in the background.", id="hint")
        yield Footer()

    def on_mount(self):
        self.query_one(OptionList).focus()
        self.refresh_status()
        self.set_interval(2, self.refresh_status)
        self.first_look()

    # --- status ---

    @work(thread=True, exclusive=True, group="status")
    def refresh_status(self):
        try:
            status = client.request("status", timeout=10)
            text = status_text(status)
        except client.ServiceError as error:
            status, text = None, f"[b red]{error}[/]"
        self.status = status
        self.call_from_thread(self.query_one("#status", Static).update, text)

    @work(thread=True)
    def first_look(self):
        """Offer to move a 14.x world over, once, to the person who may."""
        try:
            status = client.request("status", timeout=10)
            self.old_server = migrate.find_old_server()
        except (client.ServiceError, OSError):
            return
        if self.old_server and not status["migrated"] and status["you_may_change"]:
            self.call_from_thread(self.action_move)
        elif (not status["downloaded"] and not status["eula"] and not status["migrated"]
              and status["you_may_change"]):
            self.call_from_thread(self.push_screen, Setup(status))

    # --- keys ---

    def on_key(self, event):
        if len(self.screen_stack) > 1 or not (event.character or "").isdigit():
            return
        self.digits += event.character
        if self.digit_timer:
            self.digit_timer.stop()
        # A second digit can still follow a 1 (10-18); anything else is complete.
        if self.digits == "1":
            self.digit_timer = self.set_timer(0.8, self.run_digits)
        else:
            self.run_digits()

    def run_digits(self):
        number, self.digits = int(self.digits), ""
        if number in OPTIONS:
            self.query_one(OptionList).highlighted = number - 1
            self.choose(number)

    def on_option_list_option_selected(self, event):
        self.choose(int(event.option_id))

    # --- actions ---

    @work(thread=True)
    def ask_service(self, cmd, doing=None, done=None, **fields):
        """Make a request; say what is happening and how it went."""
        if doing:
            self.call_from_thread(self.notify, doing, timeout=4)
        try:
            reply = client.request(cmd, **fields)
        except client.ServiceError as error:
            self.call_from_thread(self.notify, str(error), severity="error", timeout=10)
            return None
        try:
            message = done(reply) if callable(done) else done
        except (KeyError, TypeError):  # an unexpected reply must not take the menu down
            message = "Done."
        if message:
            self.call_from_thread(self.notify, message, timeout=8)
        self.call_from_thread(self.refresh_status)
        return reply

    def choose(self, number):
        if number == 1:
            self.ask_service("download", "Downloading the latest server…",
                             lambda r: f"Downloaded Minecraft {r['version']}. " + (r.get("note") or ""))
        elif number == 2:
            self.push_screen(Confirm(
                "[b]The Minecraft EULA[/]\n\nTo run a Minecraft server you must agree to the "
                f"Minecraft End User License Agreement:\n\n  {EULA_URL}\n\n"
                "Open that link in a web browser and read it. Do you agree to it?",
                yes="I agree", no="Not now"),
                lambda agreed: agreed and self.ask_service(
                    "accept-eula", done="Thank you. You can start the server now (option 4)."))
        elif number == 3:
            self.edit_properties()
        elif number in START_RAM:
            self.start(START_RAM[number])
        elif number == 9:
            self.push_screen(Help())
        elif number == 10:
            self.backup()
        elif number == 11:
            self.push_screen(Ask("How much memory should the server have? For example 4G, "
                                 "or 4096M. At least 1G.", "4G"), self.start_custom)
        elif number == 12:
            self.push_screen(Ask("The full path to your server jar, for example "
                                 "~/Downloads/paper.jar", "~/"), self.use_jar)
        elif number == 13:
            self.push_screen(Confirm("Stop the server? Anyone playing will be disconnected. "
                                     "The world is saved first."),
                             lambda yes: yes and self.ask_service(
                                 "stop", "Saving the world and stopping…", "The server has stopped."))
        elif number == 14:
            self.push_screen(Ask("Which Minecraft name should be allowed to join?"),
                             lambda name: name and self.player("whitelist", name))
        elif number == 18:
            self.push_screen(Ask("Specify server version (e.g. 26.2):", "26.2"), self.choose_version)
        elif number == 17:
            self.push_screen(Ask("Which player should no longer be allowed to join?"),
                             lambda name: name and self.player("unwhitelist", name))
        elif number == 15:
            self.push_screen(Ask("Which Minecraft name should become an operator? "
                                 "Operators can use cheats and server commands."),
                             lambda name: name and self.player("op", name))
        elif number == 16:
            self.push_screen(Ask("Which operator should go back to being a normal player?"),
                             lambda name: name and self.player("deop", name))

    @work(thread=True)
    def choose_version(self, version):
        """Option 18: check the version, then ask how to treat the world if it is at risk."""
        if not version:
            return
        try:
            check = client.request("version-check", version=version)
        except client.ServiceError as error:
            self.call_from_thread(self.notify, str(error), severity="error", timeout=10)
            return
        version = check["version"]
        players_note = (f"Everyone's Minecraft must be version {version} to join. In the Minecraft "
                        f"Launcher: Installations → New installation → Version {version}.")
        if check["has_world"] and check["older_than_world"]:
            played = check["world_version"] or "a newer version"
            self.call_from_thread(self.push_screen, Choose(
                f"[b]Minecraft {version} is older than the version your world was last played "
                f"on ({played}).[/]\n\nOpening a world in an older version damages it: things "
                "like chests and furnaces can lose what is in them, and parts of the world can be "
                "lost. Going back to the newer version does not repair it.\n\n"
                f"{players_note}\n\nYour world is backed up first either way.",
                [("new", f"Start a new world for {version} (your world is kept for later)", True),
                 ("keep", "Use my world anyway", False)]),
                lambda world: world and self.switch_version(version, world))
        else:
            self.call_from_thread(self.push_screen, Confirm(
                f"Switch the server to Minecraft [b]{version}[/]?\n\n{players_note}\n\n"
                "If the server is running, it restarts. You won't be nagged to update while "
                "you're on a version you chose; option 1 goes back to the latest.", yes="Switch"),
                lambda yes: yes and self.switch_version(version, None))

    def switch_version(self, version, world):
        self.ask_service("download", f"Backing up and getting Minecraft {version}…",
                         lambda r: f"Now on Minecraft {r['version']}. " + (r.get("note") or ""),
                         version=version, **({"world": world} if world else {}))

    def start(self, ram_mb):
        self.ask_service("start", "Starting the server…",
                         "The server is starting. It is ready to join in a minute or so.",
                         ram_mb=ram_mb)

    def start_custom(self, answer):
        if answer is None:
            return
        ram_mb = parse_memory(answer)
        if not ram_mb or ram_mb < 1024:
            self.notify("Type an amount like 4G or 4096M (at least 1G).", severity="error")
            return
        self.start(ram_mb)

    def player(self, action, name):
        self.ask_service(action, done=lambda r: "\n".join(r.get("reply") or []) or "Done.",
                         name=name)

    @work(thread=True)
    def use_jar(self, path):
        if not path:
            return
        if path.startswith("~"):
            path = REAL_HOME + path[1:]
        if not os.path.isfile(path):
            self.call_from_thread(self.notify, f"There is no file at {path}", severity="error")
            return
        self.call_from_thread(self.notify, "Copying your jar to the server…")
        try:
            client.request("put-jar", upload=path, name=os.path.basename(path))
        except client.ServiceError as error:
            self.call_from_thread(self.notify, str(error), severity="error", timeout=10)
            return
        except OSError as error:
            self.call_from_thread(self.notify, f"Could not read {path}: {error}", severity="error")
            return
        self.call_from_thread(self.choose, 11)

    @work(thread=True)
    def edit_properties(self):
        try:
            reply = client.request("get-properties")
        except client.ServiceError as error:
            self.call_from_thread(self.notify, str(error), severity="error")
            return
        self.call_from_thread(
            self.push_screen, Properties(reply["text"], reply.get("note")),
            lambda text: text is not None and self.ask_service(
                "put-properties", done=lambda r: "Settings saved. " + (r.get("note") or ""),
                text=text))

    @work(thread=True)
    def backup(self):
        self.call_from_thread(self.notify, "Backing up your world…")
        try:
            reply = client.request("backup")
        except client.ServiceError as error:
            self.call_from_thread(self.notify, str(error), severity="error", timeout=10)
            return
        message = f"Backed up: {reply['name']}."
        try:
            shutil.copy(reply["path"], os.path.join(REAL_HOME, reply["name"]))
            message += " A copy is in your Home folder."
        except OSError as error:
            message += f" (Could not copy it to your Home folder: {error.strerror})"
        self.call_from_thread(self.notify, message, timeout=10)

    def action_players(self):
        self.push_screen(Players())

    def action_backups(self):
        self.push_screen(Backups())

    def action_settings(self):
        if self.status:
            self.push_screen(Settings(self.status))

    def action_update(self):
        latest = self.status and self.status.get("update_available")
        if not latest:
            self.notify("You have the latest Minecraft server.")
            return
        self.push_screen(Confirm(
            f"Update the server to Minecraft {latest}?\n\nYour world is backed up first. If the "
            "server is running it restarts, so anyone playing is disconnected for a minute. "
            "Everyone's Minecraft must be updated to the same version to join.",
            yes="Update"), lambda yes: yes and self.ask_service(
                "update", "Backing up and updating… this can take a few minutes.",
                lambda r: f"Updated to Minecraft {r['version']}."))

    def action_console(self):
        self.push_screen(Console())

    def action_help(self):
        self.push_screen(Help())

    def action_move(self):
        old = self.old_server or migrate.find_old_server()
        if not old:
            self.notify("There is no server from the old version to move over.")
            return
        worlds = ", ".join(old["worlds"]) or "your settings"
        when = (time.strftime("%d %B %Y", time.localtime(old["last_played"]))
                if old["last_played"] else "unknown")
        running = self.status and self.status["running"]
        self.push_screen(Confirm(
            "[b]Your world from the old version was found.[/]\n\n"
            f"World: {worlds} (last played {when}, {old['size'] // (1024 * 1024)} MB)\n\n"
            "Move it to the new background server? Your whitelist, operators and settings "
            "come too. The original stays where it is, as a backup."
            + ("\n\n[yellow]The server will be stopped first.[/]" if running else ""),
            yes="Move it", no="Not now"), self.move_world)

    @work(thread=True)
    def move_world(self, yes):
        if not yes:
            return
        try:
            if self.status and self.status["running"]:
                self.call_from_thread(self.notify, "Stopping the server first…")
                client.request("stop")
            self.call_from_thread(self.notify, "Packing your world…")
            archive = migrate.pack_old_server()
            try:
                self.call_from_thread(self.notify, "Moving it to the server…")
                client.request("import-world", upload=archive)
            finally:
                os.unlink(archive)
        except client.ServiceError as error:
            self.call_from_thread(self.notify, str(error), severity="error", timeout=12)
            return
        except OSError as error:  # reading the old files
            self.call_from_thread(self.notify, f"Could not pack your world: {error}",
                                  severity="error", timeout=12)
            return
        migrate.mark_moved()
        self.old_server = None
        self.call_from_thread(
            self.notify, "Your world has moved over. Press 1 to get the latest server, "
            "then 4 to start it.", timeout=12)
        self.call_from_thread(self.refresh_status)


def main():
    Menu().run()


if __name__ == "__main__":
    main()
