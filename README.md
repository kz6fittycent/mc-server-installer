[![mc-server-installer](https://snapcraft.io//mc-server-installer/badge.svg)](https://snapcraft.io/mc-server-installer)

# SPECIAL NOTE ABOUT LOG4J:
`mc-server-installer` can download the latest patch `1.18.1` by choosing OPTION #1 from the main menu. 
Go to this link to learn more: https://www.minecraft.net/en-us/article/important-message--security-vulnerability-java-edition?ref=launcher

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
 
------------------------------------------------------------------

# To install:
`sudo snap install mc-server-installer`

-------------------------------------------------------------------
