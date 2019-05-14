#!/bin/bash

# 6GB SCRIPT FOR MINECRAFT SERVER 

# Variables

if [ "$SNAP_ARCH" = "amd64" ]; then
  ARCH="x86_64-linux-gnu"
elif [ "$SNAP_ARCH" = "armhf" ]; then
  ARCH="arm-linux-gnueabihf"
else
  ARCH="$SNAP_ARCH-linux-gnu"
fi

# java paths
export JAVA_HOME=$SNAP/usr/lib/jvm/java-1.8.0-openjdk-$SNAP_ARCH
export PATH=$JAVA_HOME/bin:$JAVA_HOME/jre/bin:$PATH

# Rock n' Roll

cd $SNAP_USER_DATA

# Get the server jar

echo "Getting latest server.jar..."

sleep 1s 

rm server.jar

wget https://launcher.mojang.com/v1/objects/ed76d597a44c5266be2a7fcd77a8270f1f0bc118/server.jar

# Run the server

echo "Running the server..."

sleep 2s 

java -Xmx6144M -Xms1024M -jar server.jar nogui

# Agree to the EULA

echo "Please mark the EULA to eula=true located in ~/snap/mc-installer/current/eula.txt"
