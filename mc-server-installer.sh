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
echo ""
echo "Welcome to MC-SERVER-INSTALLER"
echo ""
echo "MIT LICENSE"
echo ""
sleep 2s

# java paths
export JAVA_HOME=$SNAP/usr/lib/jvm/java-1.8.0-openjdk-$SNAP_ARCH
export PATH=$JAVA_HOME/bin:$JAVA_HOME/jre/bin:$PATH

# Rock n' Roll

cd $SNAP_USER_DATA

# Get the server jar

echo "Getting latest server.jar..."

sleep 1s 

rm server.jar

wget https://launcher.mojang.com/v1/objects/f1a0073671057f01aa843443fef34330281333ce/server.jar 

# Run the server

#echo "Running the server..."

sleep 2s 

#DIALOG

options=(
    "Run MC server with max 2GB of RAM"
    "Run MC server with max 4GB of RAM"
    "Run MC server with max 6GB of RAM"
    "Run MC server with max 8GB of RAM"
    "Quit"
)

PS3="Enter a number (1-5): "

select option in "${#options[@]}"; do
    case "$REPLY" in
        1) java -Xmx2048M -Xmx1024M -jar server.jar nogui;;
        2) java -Xmx4096M -Xms1024M -jar server.jar nogui;;
        3) java -Xmx6144M -Xms1024M -jar server.jar nogui;;
        4) java -Xmx9192M -Xms1024M -jar server.jar nogui;;
        5) break;;
    esac
done
