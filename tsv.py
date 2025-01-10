import requests
import os
import re
import json
from colorama import init, Fore
import base64

init(autoreset=True)
file_path = 'keys.tsv'
list_path = "list.txt"
settings_file = "settings.json"
_u1 = base64.b64decode('aHR0cHM6Ly9yYXcuZ2l0aHVidXNlcmNvbnRlbnQuY29tL3dhZHVkaTgyL2FoL21haW4vaW5mbzEudHh0').decode()
_u2 = base64.b64decode('aHR0cHM6Ly9yYXcuZ2l0aHVidXNlcmNvbnRlbnQuY29tL3dhZHVkaTgyL2FoL21haW4vMTI4MTAyOTMudHh0').decode()

def read_settings(settings_file):
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as file:
            return json.load(file)
    else:
        return {}

def read_local_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return [line.strip() for line in file.readlines()]
    else:
        return []

def update_keys():
    settings = read_settings(settings_file)
    if settings.get("UpdateKeys", "True") == "False":
        print("Auto-update Keys is disabled.")
        return
    
    print("Checking for new keys...", end='', flush=True)
    local_data = read_local_file(file_path)
    response = requests.get(_u2)
    response.raise_for_status()
    remote_data = [line.strip() for line in response.text.splitlines()]
    
    if local_data != remote_data:
        num_new_lines = len(remote_data) - len(local_data)
        with open(file_path, 'w') as file:
            file.write('\n'.join(remote_data) + '\n')
        print("\r" + " " * len("Checking for new keys...") + "\r", end="", flush=True)
        print(Fore.GREEN + f"Keys updated! +{num_new_lines} added")
    else:
        print("\r" + " " * len("Checking for new keys...") + "\r", end="", flush=True)

def normalize_text(text):
    text = re.sub(r'[^\x20-\x7E]', '', text)
    return text.strip()

def check_dlc_list(show_new=False, force_update_list=False):
    settings = read_settings(settings_file)
    if not force_update_list and settings.get("UpdateKeys", "True") == "False":
        return [], False
        
    print("Checking for new dlc list...", end='', flush=True)
    local_data = read_local_file(list_path)
    response = requests.get(_u1)
    response.raise_for_status()
    
    local_data = [normalize_text(line) for line in local_data]
    remote_data = [normalize_text(line) for line in response.content.decode('utf-8', errors='ignore').splitlines()]
    new_lines = [line for line in remote_data if line not in local_data]
    num_new_lines = len(new_lines)
    
    if num_new_lines > 0:
        with open(list_path, 'w', encoding='utf-8') as file:
            file.write('\n'.join(remote_data) + '\n')
        print("\r" + " " * len("Checking for new dlc list...") + "\r", end="", flush=True)
        print(Fore.GREEN + f"List updated! +{num_new_lines} added")
        print("(type --new to see the new items)")
        
        if show_new:
            print("Added items in keys:")
            print()
            for line in new_lines:
                stripped_line = re.sub(r'\s*[\da-fA-F-]{36}$', '', line).strip()
                print(stripped_line)
            print()
    else:
        print("\r" + " " * len("Checking for new dlc list...") + "\r", end="", flush=True)
    
    return new_lines, num_new_lines > 0
global_new_lines = []

def force_update_keys():
    local_data = read_local_file(file_path)
    response = requests.get(_u2)
    response.raise_for_status()
    remote_data = [line.strip() for line in response.text.splitlines()]
    
    if local_data != remote_data:
        num_new_lines = len(remote_data) - len(local_data)
        with open(file_path, 'w') as file:
            file.write('\n'.join(remote_data) + '\n')
        print(Fore.GREEN + f"Keys updated! +{num_new_lines} added")
    else:
        print(Fore.GREEN + "Keys are already up to date!")
