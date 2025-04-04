[![mc-server-installer](https://snapcraft.io//mc-server-installer/badge.svg)](https://snapcraft.io/mc-server-installer)[![🧪 Snap Builds](https://github.com/kz6fittycent/mc-server-installer/workflows/%F0%9F%A7%AA%20Snap%20Builds/badge.svg)](https://github.com/kz6fittycent/mc-server-installer/actions?query=workflow:"🧪+Snap+Builds")[![Periodic Builds and Scans](https://github.com/kz6fittycent/mc-server-installer/actions/workflows/periodic_builds.yml/badge.svg)](https://github.com/kz6fittycent/mc-server-installer/actions/workflows/periodic_builds.yml)

#### If you like what I'm doing, please consider supporting me on Patreon!
[![Patreon](https://img.shields.io/badge/Patreon-F96854?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/kz6fittycent)  

# MC-Server-Installer
A Minecraft server installer and configuration tool

    A Minecraft Server installer and configuration snap that downloads the latest .jar file 
    and allows you to start your server with the amount of RAM you choose. 
    
    Admins may now run custom MAX RAM settings! Minimum RAM requirements are 1024M, so please
    keep this in mind. Additionally, -Xmn values have been reduced to 128M to keep with current
    guidance. See: https://minecraft.gamepedia.com/Server/Requirements 
    
    You can also backup your entire server with option 10 in the menu. They are pushed to
    /home/user/ so that uninstalling the snap won't affect your backups. 

## MC-SERVER-INSTALLER is not an officially supported or licensed application of Mojang.

    Select option #1 and the latest server.jar will be downloaded. Then, select option 2,
    and MC-SERVER-INSTALLER will perform a first run and agree to the EULA.

### NO. THIS WON'T BE CHANGED! BECAUSE LEGAL STUFF...

    After selecting option #2, you can proceed with choosing any of the other options or
    setting up your server's configuration, which is located in:

 ```
 ~/snap/mc-server-installer/current
 ```
    To update, just run option 1 again. No need to agree to the EULA. 


    This snap package was built from scratch with an MIT License, by kz6fittycent:
 
    https://github.com/kz6fittycent/mc-server-installer

### TUI USAGE:

    The application will start the server running in the background. 
    You can check your logs via server.log. You can go ahead and safely quit the TUI, and 
    it won't interrupt the server running. 
    
    You can either stop the server using the typical commands in the terminal 
    (e.g. searching for the pids) or you can return to the TUI, and scroll to "Option 13" 
    and hit enter. The TUI will stop the server running.

------------------------------------------------------------------

# To install:
`sudo snap install mc-server-installer`

# Connect the interface:
`sudo snap connect mc-server-installer:process-control`

-------------------------------------------------------------------
