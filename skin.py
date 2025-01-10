import os
import struct
from Crypto.Cipher import AES
import uuid
import json
import zipfile
from colorama import Fore, Style


def aes256_cfb_decrypt(key, iv, data):
  decryptor = AES.new(key, AES.MODE_CFB, iv)
  decrypted_data = decryptor.decrypt(data)
  return decrypted_data

def world_or_contents_json_decrypt(file_path, key):
    with open(file_path, 'rb') as file:
        header = file.read(17)  # Read the header

        # Read and unpack the header values
        _, magic, _, uuid_length = struct.unpack('<IIQb', header)
        uuid = file.read(uuid_length).decode('utf-8')  # Read the UUID

        if magic == 0x9BCFB9FC:  # Check for the expected magic number

            file.seek(0x100)  # Skip header
            encrypted_data = file.read()  # Read the encrypted data

            iv = key[:16]  # Use the first 16 bytes of the key as IV

            decrypted_data = aes256_cfb_decrypt(key, iv, encrypted_data)
            return decrypted_data, uuid
        else:
            raise ValueError("Not a valid contents.json")

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

def decrypt_files_for_contents_json(contents_json_file, key):
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

def decrypt_files(root_directory, key):
    # Decrypt contents.json files first
    contents_json_files = find_files(root_directory, "contents.json")
    for contents_json_file in contents_json_files:
        decrypted_data, _ = world_or_contents_json_decrypt(contents_json_file, key)
        with open(contents_json_file, 'wb') as f:
            f.write(decrypted_data)
        decrypt_files_for_contents_json(contents_json_file, key)

def modify_sk_json(root_directory):
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


def remove_forbidden_chars(name):
    # Define a list of characters to remove
    forbidden_chars = ['#', ':', '?', '/', '<', '>', '\\']

    # Remove forbidden characters
    for char in forbidden_chars:
        name = name.replace(char, '')

    return name

def detect_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
        try:
            raw_data.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            return 'latin1'

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

def compress_to_zip(source_folder, skin_pack_name, persona_present, output_folder):
    if persona_present:  # Check if 'persona' was detected
        zip_filename = f"{skin_pack_name} (persona).zip"
    else:
        zip_filename = f"{skin_pack_name} (skin_pack).mcpack"
    
    zip_file_path = os.path.join(output_folder, zip_filename)
    
    # Check if the file already exists
    if os.path.exists(zip_file_path):
        # Extract the base filename without the count and extension
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

def main(pack_folder, output_folder):
    if os.path.isdir(pack_folder):
        # Look for contents.json in the extracted folder
        contents_json_files = find_files(pack_folder, "contents.json")
        if contents_json_files:
            key = b's5s5ejuDru4uchuF2drUFuthaspAbepE'  # Key for decryption
            # Decrypt files in the extracted folder
            decrypt_files(pack_folder, key)
            # Modify skins.json
            modify_sk_json(pack_folder)
            manifest_file = os.path.join(pack_folder, "manifest.json")
            replace_uuids_in_manifest(manifest_file)
            # Get skin pack name from en_US.lang file
            skin_pack_name, persona_present = get_skin_pack_name(pack_folder)
            # Compress the decrypted files into a new zip file with the skin pack name
            compress_to_zip(pack_folder, skin_pack_name, persona_present, output_folder)
        else:
            print("contents.json file not found in the extracted folder:", pack_folder)
    else:
        print("Invalid pack folder path:", pack_folder)

if __name__ == "__main__":
    main()