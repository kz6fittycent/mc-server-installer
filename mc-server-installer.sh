#!/bin/sh

# ARCH VARIABLES

if [ "$SNAP_ARCH" = "amd64" ]; then
  ARCH="x86_64-linux-gnu"
elif [ "$SNAP_ARCH" = "armhf" ]; then
  ARCH="arm-linux-gnueabihf"
else
  ARCH="$SNAP_ARCH-linux-gnu"
fi

# DEFINE LATEST JAR
LATEST=`curl -fsSL 'https://launchermeta.mojang.com/mc/game/version_manifest.json' |jq -r '.latest.release'`

# DEFINE URL
MANIFEST_URL=`curl -fsSL 'https://launchermeta.mojang.com/mc/game/version_manifest.json' |jq -r '.versions[] |select(.id=="'"$LATEST"'") |.url'`

# URL CONT'D
JAR_URL=`curl -fsSL "$MANIFEST_URL" |jq -r '.downloads.server.url'`



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

options=(
    "Download latest server.jar"
    "Agree to the EULA"
    "Run MC server with max 2GB of RAM"
    "Run MC server with max 4GB of RAM"
    "Run MC server with max 6GB of RAM"
    "Run MC server with max 8GB of RAM"
    "Run MC server with max 16GB of RAM"
    "Quit"
)

PS3="Enter a number (1-${#options[@]}): "

select option in "${#options[@]}"; do

    case "$REPLY" in
        1) curl -so server.jar $JAR_URL;;
        2) sed -ie s/false/true/g eula.txt;;
        3) java -Xmx2048M -Xmx1024M -jar server.jar nogui;;
        4) java -Xmx4096M -Xms1024M -jar server.jar nogui;;
        5) java -Xmx6144M -Xms1024M -jar server.jar nogui;;
        6) java -Xmx9192M -Xms1024M -jar server.jar nogui;;
        7) java -Xmx16384 -Xms1024M -jar server.jar nogui;;
        8) break;;
    esac
done
