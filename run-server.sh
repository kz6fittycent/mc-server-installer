#!/bin/bash

# SCRIPT FOR MINECRAFT SERVER 

# Variables

if [ "$SNAP_ARCH" = "amd64" ]; then
  ARCH="x86_64-linux-gnu"
elif [ "$SNAP_ARCH" = "i386" ]; then
  ARCH="arm-linux-gnueabihf"
else
  ARCH="$SNAP_ARCH-linux-gnu"
fi

echo "Welcome to MC-SERVER-INSTALLER"

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

echo "Running the server..."

sleep 2s 

java -Xmx4096M -Xms1024M -jar server.jar nogui

# Agree to the EULA

echo "#eula=false" >> eula.txt
echo "eula=true" >> eula.txt

echo "By changing the setting to TRUE you are indicating your agreement to our EULA (https://account.mojang.com/documents/minecraft_eula)."

