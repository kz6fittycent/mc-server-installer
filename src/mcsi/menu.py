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
import shutil
import time

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, Footer, Header, Input, Markdown, OptionList,
                             RichLog, Static, TextArea)
from textual.widgets.option_list import Option

from mcsi import client, migrate

REAL_HOME = os.environ.get("SNAP_REAL_HOME", os.path.expanduser("~"))
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
    17: "Add a player to the whitelist (server stopped)",
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

- **Who can play:** add your family with option 14. Turn on
  `white-list=true` in the settings (option 3) so only they can join.
- **Operators** (option 15) can use cheats and server commands in the game.
- **Backups:** option 10 saves a copy of your world, and puts one in your
  Home folder too.
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
    if s["running"]:
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


# --- the menu ---------------------------------------------------------------

class Menu(App):
    TITLE = "Minecraft Server Installer"
    CSS = """
    #status { padding: 1 2; border: round $accent; height: auto; }
    #menu { height: 1fr; margin: 0 1; }
    #hint { padding: 0 2; color: $text-muted; }
    .dialog { width: 72; height: auto; max-height: 90%; padding: 1 2;
              border: thick $accent; background: $surface; }
    .dialog.wide { width: 100; height: 90%; }
    .dialog TextArea { height: 1fr; }
    .dialog VerticalScroll { height: 1fr; }
    .buttons { height: auto; margin-top: 1; align-horizontal: right; }
    .buttons Button { margin-left: 2; }
    Confirm, Ask, Properties, Help { align: center middle; }
    #command { dock: bottom; }
    """
    BINDINGS = [
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

    # --- keys ---

    def on_key(self, event):
        if len(self.screen_stack) > 1 or not (event.character or "").isdigit():
            return
        self.digits += event.character
        if self.digit_timer:
            self.digit_timer.stop()
        # A second digit can still follow a 1 (10-17); anything else is complete.
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
        elif number in (14, 17):
            self.push_screen(Ask("Which Minecraft name should be allowed to join?"),
                             lambda name: name and self.player("whitelist", name))
        elif number == 15:
            self.push_screen(Ask("Which Minecraft name should become an operator? "
                                 "Operators can use cheats and server commands."),
                             lambda name: name and self.player("op", name))
        elif number == 16:
            self.push_screen(Ask("Which operator should go back to being a normal player?"),
                             lambda name: name and self.player("deop", name))

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
