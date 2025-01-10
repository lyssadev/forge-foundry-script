import os
import struct
from Crypto.Cipher import AES
import uuid
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from colorama import Fore, Style

def is_running_in_termux():
    #Check if it's running on Termux
    return 'TERMUX_VERSION' in os.environ

def is_running_in_pydroid():
    #Check if it's running on Pydroid
    return 'PYDROID_RPC' in os.environ

def aes256_cfb_decrypt(key, iv, data):
  decryptor = AES.new(key, AES.MODE_CFB, iv)
  decrypted_data = decryptor.decrypt(data)
  return decrypted_data

def read_and_decrypt(file_path, skin_key=None, keys_file=None):
    with open(file_path, 'rb') as file:
        header = file.read(17)  # Read the header
        _, magic, _, uuid_length = struct.unpack('<IIQb', header)
        uuid = file.read(uuid_length).decode('utf-8')  # Read the UUID

        if magic != 0x9BCFB9FC:  # Check for the expected magic number
            raise ValueError("Not a valid contents.json file.")

        if skin_key:
            key = skin_key
        else:
            key = get_key_from_tsv(keys_file, uuid)
            if not key:
                raise ValueError("Key not found for the DLC")

        file.seek(0x100)  # Skip header
        encrypted_data = file.read()  # Read the encrypted data
        iv = key[:16]  # Use the first 16 bytes of the key as IV

        decrypted_data = aes256_cfb_decrypt(key, iv, encrypted_data)
        return decrypted_data, uuid

def contents_json_skin(file_path, skin_key):
    return read_and_decrypt(file_path, skin_key=skin_key)

def world_or_contents_json_decrypt(file_path, keys_file):
    return read_and_decrypt(file_path, keys_file=keys_file)

def get_key_from_tsv(keys_file, uuid):
  with open(keys_file, 'r') as f:
    for line in f:
      fields = line.strip().split('\t')
      if len(fields) >= 4 and fields[1] == uuid:
        return fields[3].encode('utf-8')  # Convert the key to bytes
  return None

def decrypt_custom_file(file_path, key):
  with open(file_path, 'rb') as file:
    encrypted_data = file.read()
    iv = key[:16]  # Use the first 16 bytes of the key as IV
    decrypted_data = aes256_cfb_decrypt(key, iv, encrypted_data)
    return decrypted_data

def find_files(directory, file_name=None):
  for root, _, filenames in os.walk(directory):
    for filename in filenames:
      if file_name is None or filename == file_name:
        yield os.path.join(root, filename)

def decrypt_files_for_contents_json(contents_json_file, key, first_uuid):
    try:
        with open(contents_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except UnicodeDecodeError:
        print(Fore.RED + "error: Decryption failed, incorrect key" + Style.RESET_ALL)
        raise
    
    content_array = data.get("content", [])
    total_files = len(content_array)
    files_processed = 0
    with ThreadPoolExecutor() as executor:
        futures = []
        for entry in content_array:
            if "key" in entry and "path" in entry:
                key = entry["key"]
                path = entry["path"]
                target_file_path = os.path.join(os.path.dirname(contents_json_file), path)
                future = executor.submit(decrypt_and_write_file, target_file_path, key, first_uuid)
                futures.append(future)
        for future in futures:
            future.result()  # Wait for each thread to finish
            files_processed += 1
            progress = (files_processed / total_files) * 100
            print(f"Decrypting packs {progress:.2f}% completed", end='\r')
    # Print final completion message after loop ends
    print("\x1b[K", end='')
    print("Packs decrypted.")

def log_error(first_uuid, e):
    error_log_file = 'error_log.txt'
    error_message = f"uuid: {first_uuid} - Error: {str(e)} (please report it)"
    print(error_message)
    with open(error_log_file, 'a') as error_file:
        error_file.write(error_message + '\n')

def decrypt_and_write_file(target_file_path, key, first_uuid):
    try:
        decrypted_data = decrypt_custom_file(target_file_path, key.encode('utf-8'))
        with open(target_file_path, 'wb') as target_file:
            target_file.write(decrypted_data)
    except Exception as e:
        log_error(first_uuid, e)

def decrypt_files(root_directory, keys_file, first_uuid):
    contents_json_files = list(find_files(root_directory, "contents.json"))
    total_files = len(contents_json_files)
    files_processed = 0
    
    for contents_json_file in contents_json_files:
        decrypted_data, _ = world_or_contents_json_decrypt(contents_json_file, keys_file)
        with open(contents_json_file, 'wb') as f:
            f.write(decrypted_data)
        
        relative_path = os.path.relpath(contents_json_file, root_directory)
        print("Decrypted:", relative_path)
        decrypt_files_for_contents_json(contents_json_file, keys_file, first_uuid)

    db_folder_path = os.path.join(root_directory, "db")
    db_files = list(find_files(db_folder_path))
    total_files += len(db_files)
    
    for i, db_file in enumerate(db_files, start=1):
        # Check if the file is empty
        if os.path.getsize(db_file) == 0:
            continue

        if "lost" in os.path.dirname(db_file):
            continue

        decrypted_data, _ = world_or_contents_json_decrypt(db_file, keys_file)
        with open(db_file, 'wb') as f:
            f.write(decrypted_data)
        
        files_processed += 1
        progress = (files_processed / total_files) * 100
        print(f"\rDecrypted db file {progress:.2f}%", end='\r')
    # Clear the current line
    print("\x1b[K", end='')
    if files_processed > 0:
        print("Files on db decrypted.")


def modify_file(file_path):
    with open(file_path, "r+b") as f:
        file_data = f.read()
        search_bytes = b"prid"
        replacement_bytes = b"pria"
        offset = file_data.find(search_bytes)
        while offset != -1:
            file_data = file_data[:offset] + replacement_bytes + file_data[offset + len(search_bytes):]
            offset = file_data.find(search_bytes, offset + len(replacement_bytes))
        f.seek(0)
        f.write(file_data)
        f.truncate()

def modify_level_dat(root_directory):
    level_dat_file = os.path.join(root_directory, "level.dat")
    if os.path.exists(level_dat_file):
        modify_file(level_dat_file)
    else:
        return False
    return True

def get_folder_type(folder_path, dlc_pack_name):
    manifest_path = os.path.join(folder_path, "manifest.json")
    with open(manifest_path, 'r') as manifest_file:
        manifest_data = json.load(manifest_file)
        if "modules" in manifest_data:
            for module in manifest_data["modules"]:
                if "type" in module:
                    module_type = module["type"]
                    if module_type == "resources":
                        return f"{dlc_pack_name} RP"
                    elif module_type == "data":
                        return f"{dlc_pack_name} BP"
    return "Unknown"


def detect_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
        try:
            raw_data.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            return 'latin1'

def remove_forbidden_chars(name):
    # Define a list of characters to remove
    forbidden_chars = [':', '?', '/', '<', '>', '\\', '|', '*']

    # Remove forbidden characters
    for char in forbidden_chars:
        name = name.replace(char, '')

    return name

def get_dlc_pack_name(extracted_folder_path):
    lang_file_path = os.path.join(extracted_folder_path, "texts", "en_US.lang")

    encoding = detect_encoding(lang_file_path)
    
    with open(lang_file_path, 'r+', encoding=encoding) as file:
        lines = file.readlines()
        file.seek(0)
        for line in lines:
            if line.startswith("pack.name="):
                line = line.replace('&', '')
            file.write(line)
        file.truncate()
    
    # Process the modified content
    with open(lang_file_path, 'rb') as lang_file:
        # Check for BOM and skip it if present
        bom = lang_file.read(3)
        if bom != b'\xef\xbb\xbf':
            lang_file.seek(0)
        
        for line in lang_file:
            try:
                decoded_line = line.decode('utf-8')
            except UnicodeDecodeError:
                decoded_line = line.decode('utf-8', errors='ignore')  # Skip problematic characters
            
            # Split the line at the first occurrence of '#'
            parts = decoded_line.split('#', 1)
            if len(parts) > 1:
                decoded_line = parts[0].strip()  # Take only the part before '#'
            
            if decoded_line.startswith("pack.name="):
                dlc_pack_name = decoded_line[len("pack.name="):].strip()
                # Replace tabs with spaces in the pack name
                dlc_pack_name = dlc_pack_name.replace('\t', ' ')
                # Remove forbidden characters from the pack name
                dlc_pack_name = remove_forbidden_chars(dlc_pack_name)
                return dlc_pack_name

    print("Error: pack name not found in en_US.lang")
    return None


def compress_files_zip(source_folders, dlc_pack_name, output_folder, is_addon=False):
    print("Compressing files... ")

    # Handle addon case
    if is_addon:
        base_name = os.path.join(output_folder, f"{dlc_pack_name} (addon)")
        extension = ".mcaddon"
        zip_filename = f"{base_name}{extension}"
    else:
        # Determine if it's a world template or resource pack
        source_folder = source_folders if isinstance(source_folders, str) else source_folders[0]
        if os.path.exists(os.path.join(source_folder, "level.dat")):
            base_name = os.path.join(output_folder, f"{dlc_pack_name} (world_template)")
            extension = ".mctemplate"
        else:
            base_name = os.path.join(output_folder, f"{dlc_pack_name} (resources)")
            extension = ".mcpack"
        zip_filename = f"{base_name}{extension}"

    # Handle file naming for duplicates
    i = 1
    while os.path.exists(zip_filename):
        i += 1
        zip_filename = f"{base_name}_{i}{extension}"

    # Create the zip file
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        if is_addon:
            # Handle addon compression
            for folder in source_folders:
                folder_type = get_folder_type(folder, dlc_pack_name)
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        if file not in ["signatures.json", "contents.json"]:
                            filepath = os.path.join(root, file)
                            arcname = os.path.relpath(filepath, folder)
                            arcname = os.path.join(folder_type, arcname)
                            zipf.write(filepath, arcname)
        else:
            # Handle single folder compression
            source_folder = source_folders if isinstance(source_folders, str) else source_folders[0]
            for root, dirs, files in os.walk(source_folder):
                for file in files:
                    if file not in ["signatures.json", "contents.json"]:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.relpath(file_path, source_folder))

    print("Compressed files into: " + Fore.YELLOW + f"{os.path.basename(zip_filename)}" + Style.RESET_ALL)
    return zip_filename

def decrypt_files_for_contents_json_skin(contents_json_file):
  with open(contents_json_file, 'r', encoding='utf-8') as f:
    data = json.load(f)
    content_array = data.get("content", [])
    for entry in content_array:
      if "key" in entry and "path" in entry:
        key = entry["key"]
        path = entry["path"]
        target_file_path = os.path.join(os.path.dirname(contents_json_file), path)
        decrypted_data = decrypt_custom_file(target_file_path, key.encode('utf-8'))
        with open(target_file_path, 'wb') as target_file:
          target_file.write(decrypted_data)
    print("Files decrypted")

def decrypt_files_skins(root_directory, skin_key):
    # Decrypt contents.json files first
    contents_json_files = find_files(root_directory, "contents.json")
    for contents_json_file in contents_json_files:
        decrypted_data, _ = contents_json_skin(contents_json_file, skin_key)
        with open(contents_json_file, 'wb') as f:
            f.write(decrypted_data)
        decrypt_files_for_contents_json_skin(contents_json_file)

def modify_skin_json(root_directory):
    for dirpath, _, filenames in os.walk(root_directory):
        for filename in filenames:
            if filename == "skins.json":
                sk_json_file = os.path.join(dirpath, filename)
                with open(sk_json_file, "r+") as f:
                    file_data = f.read()
                    modified_data = file_data.replace("paid", "free")
                    f.seek(0)
                    f.write(modified_data)
                    f.truncate()

def get_skin_pack_name(extracted_folder_path):
    lang_file_path = os.path.join(extracted_folder_path, "texts", "en_US.lang")

    encoding = detect_encoding(lang_file_path)
    
    # Read, modify, and write the file content
    with open(lang_file_path, 'r+', encoding=encoding) as file:
        content = file.read()
        modified_content = content.replace('&', '')
        file.seek(0)
        file.write(modified_content)
        file.truncate()

    # Process the modified content
    with open(lang_file_path, 'rb') as lang_file:
        # Check for BOM and skip it if present
        bom = lang_file.read(3)
        if bom != b'\xef\xbb\xbf':
            lang_file.seek(0)

        first_line = None
        persona_present = False

        for line in lang_file:
            if b'skinpack' in line or b'persona' in line:
                first_line = line
                persona_present = b'persona' in line
                break

        try:
            decoded_line = first_line.decode('utf-8')
        except UnicodeDecodeError:
            decoded_line = first_line.decode('utf-8', errors='ignore')  # Skip problematic characters

        skin_pack_name = decoded_line.split('=')[-1].strip().replace('\t', ' ')

        if persona_present and not skin_pack_name:
            name_parts = decoded_line.split('.')
            if len(name_parts) > 1:
                skin_pack_name = name_parts[1]

        # Remove forbidden characters from the pack name
        skin_pack_name = remove_forbidden_chars(skin_pack_name)

    return skin_pack_name, persona_present

def compress_skinpack(source_folder, skin_pack_name, persona_present, output_folder):
    if persona_present:
        zip_filename = f"{skin_pack_name} (persona).zip"
    else:
        zip_filename = f"{skin_pack_name} (skin_pack).mcpack"    
    zip_file_path = os.path.join(output_folder, zip_filename)    
    if os.path.exists(zip_file_path):
        base_filename, ext = os.path.splitext(zip_filename)
        count = 1
        while True:
            new_filename = f"{base_filename}_{count}{ext}"
            new_file_path = os.path.join(output_folder, new_filename)
            if not os.path.exists(new_file_path):
                break
            count += 1
        zip_filename = new_filename
        zip_file_path = os.path.join(output_folder, zip_filename)    
    with zipfile.ZipFile(zip_file_path, 'w') as zipf:
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, source_folder))
    print("Compressed files into:", Fore.YELLOW + zip_filename + Style.RESET_ALL)

def replace_uuids_in_manifest(manifest_path):
    with open(manifest_path, "r+") as f:
        manifest_data = json.load(f)

        # Replace the UUIDs with new ones
        manifest_data["header"]["uuid"] = str(uuid.uuid4())
        
        for module in manifest_data.get("modules", []):
            module["uuid"] = str(uuid.uuid4())

        f.seek(0)
        json.dump(manifest_data, f, separators=(',', ':'))
        f.truncate()

def skin_main(pack_folder, output_folder=None):
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
        except OSError as e:
            print(f"Error creating directory '{output_folder}': {e}")
            return
    
    if os.path.isdir(pack_folder):
        # Look for contents.json in the extracted folder
        contents_json_files = find_files(pack_folder, "contents.json")
        if contents_json_files:
            skin_key = b's5s5ejuDru4uchuF2drUFuthaspAbepE'  # Key for decryption
            # Decrypt files in the extracted folder
            decrypt_files_skins(pack_folder, skin_key)
            # Modify skins.json
            modify_skin_json(pack_folder)
            manifest_file = os.path.join(pack_folder, "manifest.json")
            replace_uuids_in_manifest(manifest_file)
            # Get skin pack name from en_US.lang file
            skin_pack_name, persona_present = get_skin_pack_name(pack_folder)
            # Compress the decrypted files into a new zip file with the skin pack name
            compress_skinpack(pack_folder, skin_pack_name, persona_present, output_folder)
        else:
            print("contents.json file not found in the extracted folder:", pack_folder)
    else:
        print("Invalid pack folder path:", pack_folder)

def main(extracted_folders, keys_file, output_folder, is_addon=False):
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
        except OSError as e:
            print(f"Error creating directory '{output_folder}': {e}")
            return
            
    if not isinstance(extracted_folders, list):
        extracted_folders = [extracted_folders]

    folders_to_compress = []
    for extracted_folder in extracted_folders:
        manifest_path = os.path.join(extracted_folder, "manifest.json")
        pack_folder = extracted_folder

        with open(manifest_path, 'r') as manifest_file:
            manifest_data = json.load(manifest_file)
            first_uuid = manifest_data.get("header", {}).get("uuid")

        if first_uuid:
            # Decrypt files using the key corresponding to the first UUID in manifest.json
            key = get_key_from_tsv(keys_file, first_uuid)
            if key:
                decrypt_files(pack_folder, keys_file, first_uuid)
                modify_level_dat(pack_folder)
                dlc_pack_name = get_dlc_pack_name(pack_folder)
                
                folders_to_compress.append(pack_folder)
            else:
                print(Fore.RED + "Key not found for the DLC" + Style.RESET_ALL)
        else:
            print("UUID not found in manifest.json")
    
    if folders_to_compress:
        if is_addon:
            compress_files_zip(folders_to_compress, dlc_pack_name, output_folder, is_addon=True)
        else:
            for folder in folders_to_compress:
                compress_files_zip(folder, dlc_pack_name, output_folder, is_addon=False)
    else:
        print("No folders found to compress.")

    return False

