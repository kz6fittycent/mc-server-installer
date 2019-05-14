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

wget https://launcher.mojang.com/v1/objects/ed76d597a44c5266be2a7fcd77a8270f1f0bc118/server.jar

sleep 2s 

# Simple menu

# MENU VARIABLES

CHOICE1=$(java -Xmx2048M -Xms1024M -jar server.jar nogui)
CHOICE2=$(java -Xmx4096M -Xms1024M -jar server.jar nogui)
CHOICE3=$(java -Xmx6144M -Xms1024M -jar server.jar nogui)
CHOICE4=$(java -Xmx9192M -Xms1024M -jar server.jar nogui)

while true; do

#DIALOG

echo "\nHow much RAM do you want to allot?\n\n1. 2GB max\n2. 4GB max\n3. 6GB max\n4. 8GB max\n5. Exit\nEnter Selection: "

    read answer
        case $answer in

        1)    echo Starting server with 2GB max RAM allotted...
              sleep 1
              $CHOICE1
              clear
              continue;;
        2)    echo Starting server with 4GB max RAM allotted...
              sleep 1
              $CHOICE2
              clear
              continue;;
        3)    echo Starting server with 6GB max RAM allotted...
              sleep 1
              $CHOICE3
              clear
              continue;;
        4)    echo Starting server with 8GB max RAM allotted...
              sleep 1
              $CHOICE4
              clear
              continue;;
        5)    echo Exiting...
              sleep 1              
              # Agree to the EULA
              echo "Please mark the EULA to eula=true located in ~/snap/mc-installer/current/eula.txt"
              clear
              break;;
        *)    echo Please choose an option between 1-5
              sleep 1
              clear
              continue;;
    esac
done
