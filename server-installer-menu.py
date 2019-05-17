#!/usr/bin/env python3

import subprocess
import time
import os
import sys

export SNAP
os.environ.get("SNAP")

print()
def print_menu():       
    print (20 * "-" , "MC-SERVER-INSTALLER MENU" , 20 * "-")
    print ()
    print ("Choose the amount of RAM you need: ")
    print ()
    print ("1. 2GB Max allotment")
    print ("2. 4GB Max allotment")
    print ("3. 6GB Max allotment")
    print ("4. 8GB Max allotment")
    print ("5. 12GB Max allotment")
    print ("6. 16GB Max allotment")
    print ("7. 24GB Max allotment")
    print ("8. Exit")
    print ()
    print (67 * "-")
    print ()
  
loop=True      
  
while loop:          
    print_menu()    
    choice = str(input("Enter your choice: "))
    
    choice = int(choice)
    
    if choice == 1:     
        print ("Starting server with 2GB max...")
        subprocess.call(['sh','SNAP/2.sh'])
    elif choice == 2:
        print ("Starting server with 4GB max...")
        subprocess.call(['sh','SNAP/4.sh'])
    elif choice == 3:
        print ("Starting server with 6GB max...")
        subprocess.call(['sh','SNAP/6.sh'])
    elif choice == 4:
        print ("Starting server with 8GB max...")
        subprocess.call(['sh','SNAP/8.sh'])
    elif choice == 5:
        print ("Starting server with 12GB max...")
        subprocess.call(['sh','SNAP/12.sh'])
    elif choice == 6:
        print ("Starting server with 16GB max...")
        subprocess.call(['sh','SNAP/16.sh'])
    elif choice == 7:
        print ("Starting server with 24GB max...")
        subprocess.call(['sh','SNAP/24.sh'])
    elif choice == 8:
        print ("Exiting. Goodbye!")
        
        loop=False 
        
    else:
        
        print("Invalid choice, please choose a menu item.")
