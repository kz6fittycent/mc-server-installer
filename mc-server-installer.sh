#!/bin/sh

# VARIABLES

if [ "$SNAP_ARCH" = "amd64" ]; then
  ARCH="x86_64-linux-gnu"
elif [ "$SNAP_ARCH" = "armhf" ]; then
  ARCH="arm-linux-gnueabihf"
else
  ARCH="$SNAP_ARCH-linux-gnu"
fi


# START THE INSTALLER
echo "-------------------------------"
echo "Welcome to MC-SERVER-INSTALLER"
echo ""
echo "MIT LICENSE"
echo "-------------------------------"
sleep 2s


echo "             MENU"
echo ""
echo "1) Download latest server.jar"
echo "2) Agree to the EULA"
echo "3) Run MC server with max 2GB of RAM"
echo "4) Run MC server with max 4GB of RAM"
echo "5) Run MC server with max 6GB of RAM"
echo "6) Run MC server with max 8GB of RAM"
echo "7) Run MC server with max 16GB of RAM"
echo "8) Quit"
echo ""

# java paths
export JAVA_HOME=$SNAP/usr/lib/jvm/java-1.8.0-openjdk-$SNAP_ARCH
export PATH=$JAVA_HOME/bin:$JAVA_HOME/jre/bin:$PATH

# Rock n' Roll

cd $SNAP_USER_DATA

#options=(
#    "Download latest server.jar"
#    "Agree to the EULA"
#    "Run MC server with max 2GB of RAM"
#    "Run MC server with max 4GB of RAM"
#    "Run MC server with max 6GB of RAM"
#    "Run MC server with max 8GB of RAM"
#    "Run MC server with max 16GB of RAM"
#    "Quit"
#)

PS3="Enter a number (1-${#options[@]}): "

select option in "${#options[@]}"; do

    case "$REPLY" in
        1) rm server.jar && wget https://launcher.mojang.com/v1/objects/ed76d597a44c5266be2a7fcd77a8270f1f0bc118/server.jar;;
        2) sed -ie s/false/true/g eula.txt;;
        3) java -Xmx2048M -Xmx1024M -jar server.jar nogui;;
        4) java -Xmx4096M -Xms1024M -jar server.jar nogui;;
        5) java -Xmx6144M -Xms1024M -jar server.jar nogui;;
        6) java -Xmx9192M -Xms1024M -jar server.jar nogui;;
        7) java -Xmx16384 -Xms1024M -jar server.jar nogui;;
        8) break;;
    esac
done
