#!/usr/bin/env python3
#THIS SCRIPT DOWNLOADS AND STARTS MINECRAFT SERVER
#THIS IS INTENDED TO BE USED AS A SNAP BUT CAN BE MODIFIED TO RUN AS A SIMPLE SCRIPT


import os.path
from urllib.request import urlretrieve 
import subprocess
import os
import re

# Set path
#os.environ['JAVA_HOME'] = '$SNAP/usr/lib/jvm/java-1.8.0-openjdk-amd64'

# MAIN
def main():
    
    urlretrieve("https://launcher.mojang.com/v1/objects/f1a0073671057f01aa843443fef34330281333ce/server.jar", "server.jar")
    subprocess.call(['/usr/lib/jvm/java-1.8.0-openjdk-amd64','-Xmx4096M', '-Xms1024M','-jar','server.jar','nogui'])
    
main()
