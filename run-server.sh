#!/bin/sh

if [ "$SNAP_ARCH" = "amd64" ]; then
  ARCH="x86_64-linux-gnu"
elif [ "$SNAP_ARCH" = "armhf" ]; then
  ARCH="arm-linux-gnueabihf"
else
  ARCH="$SNAP_ARCH-linux-gnu"
fi

#start screen
screen -dm sleep 10

# download jar file
python3 download-server.py

# java
export JAVA_HOME=$SNAP/usr/lib/jvm/java-1.8.0-openjdk-$SNAP_ARCH
export PATH=$JAVA_HOME/bin:$JAVA_HOME/jre/bin:$PATH

# run
cd $SNAP_USER_DATA

$JAVA_HOME/jre/bin/java -Xmx4096M -Xms1024M -jar $SNAP/server.jar
