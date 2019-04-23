#!/usr/bin/env python3

import os.path
from urllib.request import urlretrieve 
import subprocess
import os
import re


def main():
    urlretrieve("https://launcher.mojang.com/v1/objects/3737db93722a9e39eeada7c27e7aca28b144ffa7/server.jar", "server.jar")   
main()
