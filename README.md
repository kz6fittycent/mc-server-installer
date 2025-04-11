[![mc-server-installer](https://snapcraft.io//mc-server-installer/badge.svg)](https://snapcraft.io/mc-server-installer)[![🧪 Snap Builds](https://github.com/kz6fittycent/mc-server-installer/workflows/%F0%9F%A7%AA%20Snap%20Builds/badge.svg)](https://github.com/kz6fittycent/mc-server-installer/actions?query=workflow:"🧪+Snap+Builds")[![Periodic Builds and Scans](https://github.com/kz6fittycent/mc-server-installer/actions/workflows/periodic_builds.yml/badge.svg)](https://github.com/kz6fittycent/mc-server-installer/actions/workflows/periodic_builds.yml)

#### If you like what I'm doing, please consider supporting me on Patreon!
[![Patreon](https://img.shields.io/badge/Patreon-F96854?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/kz6fittycent)  

# MC-Server-Installer
A simple Snap package to download, configure, and run a Minecraft server via a Text User Interface (TUI). Built from scratch by [kz6fittycent](https://github.com/kz6fittycent) under the MIT License.

**Note**: This is not an officially supported or licensed application of Mojang. You must agree to the Minecraft End User License Agreement (EULA) to use this tool.

## Features
- Download the latest Minecraft server JAR.
- Agree to the EULA with a single step.
- Configure `server.properties` using `nano`.
- Run the server with preset or custom RAM settings.
- Manage players live: whitelist, grant/remove operator status.
- Backup your world and server files.
- Runs in a detached `tmux` session for background operation.

## Installation

### Prerequisites
- A Linux system with Snap support (e.g., Ubuntu, Fedora with Snap enabled).
- Internet access to download the server JAR.

### Install via Snap
```
sudo snap install mc-server-installer
sudo snap connect mc-server-installer:process-control
```
- `process-control`: Required for the snap to stop the server effectively.


### Source
Grab the source from [GitHub](https://github.com/kz6fittycent/mc-server-installer) to build or modify it yourself.

## Usage

1. **Launch the TUI**:
   ```
   mc-server-installer
   ```
   The TUI uses `dialog` to present a menu-driven interface.
   
   NOTE: Optionally, open a `screen` session to keep the snap running indefinitely (for more info about `screen` see: https://linuxize.com/post/how-to-use-linux-screen/). 

2. **First-Time Setup**:
   - Select **Option 1**: Download the latest server JAR (e.g., v1.20.4).
   - Select **Option 2**: Agree to the EULA (required once; generates `eula.txt`).

3. **Main Menu Options**:
   ```
   MINECRAFT SERVER INSTALLER MENU
   Installed version: <version>
   Select from the following options:
    1) Download latest (v<latest>) server.jar
    2) Agree to the EULA
    3) Edit the server.properties file
    4) Run MC server with max 2GB of RAM
    5) Run MC server with max 4GB of RAM
    6) Run MC server with max 6GB of RAM
    7) Run MC server with max 8GB of RAM
    8) Run MC server with max 16GB of RAM
    9) View README
   10) Back up your world
   11) Run custom RAM settings
   12) Run custom jar file and RAM settings
   13) Stop the server
   14) Add player to whitelist (live)
   15) Make player an operator (live)
   16) Remove player from operators (live)
   17) Add player to whitelist (offline)
   ```
   - Use arrow keys to navigate, **Enter** to select, or **Quit** to exit.

4. **Running the Server**:
   - Choose a run option (4–8, 11–12) to start the server in a `tmux` session.
   - Check `$HOME/snap/mc-server-installer/current/server.log` for output.

5. **Live Management**:
   - **Option 14**: Add a player to the whitelist while the server runs.
   - **Option 15**: Grant operator status to a player.
   - **Option 16**: Remove operator status from a player.
   - Commands are sent instantly; verify in `server.log`.

6. **Offline Whitelist**:
   - **Option 17**: Add a player to `whitelist.json` when the server is stopped.
   - Enable `white-list=true` in `server.properties` to enforce it.

7. **Stopping the Server**:
   - **Option 13**: Sends the `stop` command and cleans up the `tmux` session.

8. **Configuration**:
   - **Option 3**: Edit `server.properties` in `$HOME/snap/mc-server-installer/current`.
   - Customize ports, difficulty, etc., as needed.

9. **Backup**:
   - **Option 10**: Creates a `.tar.gz` backup in `$HOME`.

## Notes
- **Server Files**: Stored in `$HOME/snap/mc-server-installer/current`.
- **Updates**: Re-run Option 1 to download a new JAR; no EULA re-agreement needed unless the Snap is removed.
- **Custom RAM**: For Option 11, enter values like `4096M` (4GB). See [Minecraft Server Requirements](https://minecraft.gamepedia.com/Server/Requirements).
- **Custom JAR**: For Option 12, provide the full path (e.g., `$HOME/snap/mc-installer/current/custom.jar`).

## Troubleshooting
- **"Server must be running" Error**: Ensure you’ve started the server (Options 4–8, 11–12) before using live commands (14–16).
- **No Output**: Check `server.log` in `$HOME/snap/mc-server-installer/current`.

## Contributing
Fork the repo, make changes, and submit a pull request on [GitHub](https://github.com/kz6fittycent/mc-server-installer). Issues and suggestions welcome!
```
