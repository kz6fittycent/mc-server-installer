#!/usr/bin/env python3

import os.path
from urllib.request import urlretrieve 
import subprocess
import os
import re


def main():
    
    urlretrieve("https://launcher.mojang.com/v1/objects/f1a0073671057f01aa843443fef34330281333ce/server.jar", "server.jar")
    subprocess.call(['java','-Xmx4096M', '-Xms1024M','-jar','server.jar','nogui'])
    
main()
