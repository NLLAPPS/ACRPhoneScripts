# ACR Recordings Recovery Tool v0.01
#
# Author: Przemysław Hołubowski (przemhb@wp.pl).
# Licence: GNU GPL.
#
# Simple program to bring back selected recordings from cloud backups back to the ACR Phone to make them playable.
# Founds recordings which are starred or have notes and copies them from clouds to a local folder.
# Supported cloud services: Nextcloud (directly), Google Drive (via local virtual disk - use Google Drive app).
# 
# USAGE:
# 1. Configure paths and credentials. 
# 2. Copy: recording.db, recording.db-shm, recording.db-wal from: /system/data/data/com.nll.cb/databases to the folder where this file is. Root needed.
# 3. Run this program.
# 4. Copy updated recording.db back to the original location and delete recording.db-shm, recording.db-wal present there.
# 5. Copy recovered files from the local folder to the ACR Phone's recordings folder on your phone.
#
# NOTE: The program is a piece of a dirty code. It worked just fine for me, but there is no guarantee it will work for you.
#
import sqlite3
import os
import re
from datetime import datetime
import urllib.parse
from requests.auth import HTTPBasicAuth
import logging
from owncloud import Client
import shutil
# import json

# Paths and credentials
DB_PATH = 'recording.db'
CLD_PATH = 'Backup/ACRPhone/LM-V600/'   # Main ACR Phone backup folder on the Nextcloud
GDRV_PATH = 'd:/Mój dysk/ACR Recordings/'   # Path to ACR Phone backup folder on Google Drive (local; use Google Drive app)
DST_PATH = './recovered/'   # Path were to put restored recordings
NEXTCLOUD_URL = 'https://example.com/nextcloud' # URL of your Nextcloud
USERNAME = 'your_Nextcloud_login'
PASSWORD = 'your_Nextcloud_password'
BASE_URI = "content://com.android.externalstorage.documents/tree/D7AF-3330%3AACRPhoneCalls/document/D7AF-3330%3AACRPhoneCalls%2FACRPhone" # Folder, where ACR Phone stores recordings. Use SQLite Explorer to get it right.

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Step 1: Generate list of recordings which are starred, have notes etc. Those will be processed.
def get_starred_files(db_path):
    """
    Retrieves starred recordings from the SQLite database and generates their URI paths.

    Args:
        db_path (str): The path to the SQLite database.

    Returns:
        list: A list of encoded URI paths for starred recordings.
    """
    starred_filenames = []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Issue DB query
        cursor.execute("SELECT id, recordingDate, phoneNumber, callDirection, fileUri, cachedContactName FROM recordings WHERE isStarred = 1 or note != ''")
        starred_records = cursor.fetchall()

        # Close DB connection
        conn.close()

        # Process results
        for (id, recordingDate, phoneNumber, callDirection, fileUri, cachedContactName) in starred_records:
            # Convert timestamp to date
            date_obj = datetime.fromtimestamp(recordingDate / 1000)
            year, month, day = date_obj.strftime("%Y"), date_obj.strftime("%m"), date_obj.strftime("%d")

            # Prepare output filename
            filename = f"{phoneNumber}-{callDirection}-{recordingDate}.{fileUri[-3:]}"
            # Construct the dynamic part of the URI with selective encoding
            dynamic_path = f"%2F{year}%2F{month}%2F{day}%2F{urllib.parse.quote(phoneNumber)}%2F{urllib.parse.quote(filename)}"

            # Combine base URI with the encoded dynamic path
            uri_path = f"{BASE_URI}{dynamic_path}"
            starred_filenames.append((id, uri_path, recordingDate, phoneNumber, cachedContactName))
        
        logging.info(f"Found {len(starred_filenames)} recordings to process.")
    
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    except Exception as e:
        logging.error(f"Error: {e}")

    return starred_filenames

# Step 2: Recurent filneme fetch from the Nextcloud, depth=4 (year -> month -> day -> phone_number)
def get_nextcloud_files(cld_path, depth=4):
    """
    Retrieves files from Nextcloud at the specified depth.

    Args:
        cld_path (str): The path to start searching for files on Nextcloud.
        depth (int): The maximum depth to search for files.

    Returns:
        list: A list of tuples containing filenames and their respective paths.
    """
    cld_filenames = []

    # Initialize the Nextcloud client
    nc = Client(NEXTCLOUD_URL)
    nc.login(USERNAME, PASSWORD)

    def list_files_recursive(path, level):
        if level > depth:
            return
        
        try:
            # List files in the current directory
            items = nc.list(path)
            for item in items:
                filename = item.name
                item_path = item.path
            
                if filename.endswith(".m4a"):
                    cld_filenames.append((filename, item_path))
                else:
                    # Recursive call for directories
                    list_files_recursive(item_path, level + 1)
        
        except Exception as e:
            logging.error(f"Error while fetchin files from {path}: {e}")

    list_files_recursive(cld_path, 1)
    logging.info(f"Found {len(cld_filenames)} files in the Nextcloud.")
    
    return cld_filenames

# Step 3: File matching and copying to destination folder
def copy_starred_files_to_local(starred_filenames, cld_files, dst_path):
    copiedFilesCount = 0
    copiedFilesIDs = []

    # Initialize the Nextcloud client
    nc = Client(NEXTCLOUD_URL)
    nc.login(USERNAME, PASSWORD)  # Logging in instead of setting credentials

    for id, starred_uri, _, _, _ in starred_filenames:
        # Parsing details from URI
        decoded_uri = urllib.parse.unquote(starred_uri)
        parts = decoded_uri.split("/")
        phone_number = parts[-2]
        file_info = parts[-1].removesuffix(".m4a").removesuffix(".mp3")
        _, call_direction, recording_timestamp = file_info.split("-")

        # Timestamp to date conversion
        date_obj = datetime.fromtimestamp(int(float(recording_timestamp)) / 1000)
        date_str = date_obj.strftime("%Y-%m-%d %H-%M-%S")

        # Pattern to match file in the cloud
        # Polish words needs to be replaced with the language at the time of the upload matching the naming convention used by the ACR Phone.
        pattern = rf"\({re.escape(phone_number)}\) \[{date_str}\] \[Połączenia {'wychodzące' if call_direction == '1' else 'przychodzące'}\]\.m4a"

        # Searching through the cloud files
        matched_file = next((file_path for filename, file_path in cld_files if re.search(pattern, filename)), None)
        if matched_file:
            # Destination path on a local system
            local_file_path = os.path.join(dst_path, date_obj.strftime("%Y/%m/%d"), phone_number)
            os.makedirs(local_file_path, exist_ok=True)
            dest_file_path = os.path.join(local_file_path, f"{phone_number}-{call_direction}-{recording_timestamp}.m4a")

            # Downloading the matched file to destination path and renaming it according to ACR filename format
            try:
                nc.get_file(matched_file, dest_file_path)
                copiedFilesCount += 1
                copiedFilesIDs.append(id)
            except Exception as e:
                logging.info(f"Unable to fetch file: {matched_file}. Error: {e}")
    return copiedFilesIDs

# Step 4: Updating database - setting fileUri for copied files
def update_db_with_copied_files_filenames(copied_files_ids, starred_filenames, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Creating map id -> filename for quicker matching
    id_to_filename_map = {file_id: filename for file_id, filename, _, _, _ in starred_filenames}

    # Updating fileUri based on copied_files_ids
    for file_id in copied_files_ids:
        if file_id in id_to_filename_map:
            new_file_uri = id_to_filename_map[file_id]
            cursor.execute("UPDATE recordings SET fileUri = ? WHERE id = ?", (new_file_uri, file_id))
    
    conn.commit()
    conn.close()
    logging.info("Database was updated for the copied files.")

# Step 2b - fetching filenames from the local disk (Google Drive)
def get_local_gdrive_files(directory):
    """
    Analyzes file names in the specified directory and extracts metadata.

    Args:
        directory (str): The path to the directory containing the audio files.

    Returns:
        list: A list of dictionaries with extracted metadata.
    """
    file_data = []
    # Pattern for matching files
    pattern = r"^(?:(?P<contact>(?:Nieznany|[^_]+(?:_{1,2}[^_]+)*)_)?(?P<phoneNumber>\+?\d+(?:,\d+){0,1}(?:,\d+)?)?)_(?P<year>\d{4})_(?P<month>\d{2})_(?P<day>\d{2})_(?P<hour>\d{2})_(?P<minute>\d{2})_(?P<second>\d{2})_(?:\[(?P<callDirection>\d)\])?\.(mp3|m4a)$"

    for filename in os.listdir(directory):
        match = re.match(pattern, filename)
        if match:
            data = match.groupdict()
            recordingDate = int(datetime(
                int(data['year']), int(data['month']), int(data['day']),
                int(data['hour']), int(data['minute']), int(data['second'])
            ).timestamp() * 1000)  # Convert to milliseconds if needed

            file_data.append({
                'contact': data['contact'],
                'phoneNumber': data['phoneNumber'],
                'recordingDate': recordingDate,
                'callDirection': data['callDirection'],
                'filePath': os.path.join(directory, filename)
            })
        else:
            logging.info(f"WARNING: no match found for the file: {filename}!")

    if len(os.listdir(directory)) != len(file_data):
        logging.info(f"WARNING: no match found for {len(os.listdir(directory))-len(file_data)} files!")

    # Saving file_data for debugging purpose
    # with open("file_data_debug.json", "w", encoding="utf-8") as debug_file:
    #     json.dump(file_data, debug_file, ensure_ascii=False, indent=4)

    return file_data

# Step 3b - Copying matching recordings to destination path
def copy_starred_files_from_gdrive_to_local(starred_filenames, gdrive_files, dst_path):
    copied_files_count = 0
    copied_files_ids = []

    for id, starred_uri, _, _, _ in starred_filenames:
        # Get details from URI
        decoded_uri = urllib.parse.unquote(starred_uri)
        parts = decoded_uri.split("/")
        phone_number = parts[-2]
        file_info = parts[-1].removesuffix(".m4a").removesuffix(".mp3")
        _, call_direction, recording_timestamp = file_info.split("-")

        # Timestamp to date conversion
        date_obj = datetime.fromtimestamp(int(float(recording_timestamp)) / 1000)

        # Searching through files on the local Google Drive backup
        match = next(
            (file for file in gdrive_files if 
             file['phoneNumber'] == phone_number and 
             file['recordingDate'] == int(recording_timestamp) and 
             file['callDirection'] == call_direction), None
        )
        
        if match:
            # Destination path on the local system
            local_file_path = os.path.join(dst_path, date_obj.strftime("%Y/%m/%d"), phone_number)
            os.makedirs(local_file_path, exist_ok=True)
            file_extension = os.path.splitext(match['filePath'])[-1]
            dest_file_path = os.path.join(local_file_path, f"{phone_number}-{call_direction}-{recording_timestamp}{file_extension}")

            # Copying matching recording file
            try:
                shutil.copy(match['filePath'], dest_file_path)
                copied_files_count += 1
                copied_files_ids.append(id)
            except Exception as e:
                logging.error(f"Failed to fetch file: {match['filePath']}. Error: {e}")

    return copied_files_ids

def display_status(starred_files, copiedFilesIDs):
    print(f"\nCOPIED RECORDINGS:")
    cnt = 1
    for id, _, recordingDate, phoneNumber, cachedContactName in starred_files:
        if id in copiedFilesIDs:
            date = datetime.fromtimestamp(int(float(recordingDate)) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{cnt}. {date} ({recordingDate}) tel.: {phoneNumber} name: {cachedContactName}")
            cnt += 1
    print(f"\nMISSING RECORDINGS:")
    cnt = 1
    for id, _, recordingDate, phoneNumber, cachedContactName in starred_files:
        if id not in copiedFilesIDs:
            date = datetime.fromtimestamp(int(float(recordingDate)) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{cnt}. {date} ({recordingDate}) tel.: {phoneNumber} name: {cachedContactName}")
            cnt += 1


starred_filenames = get_starred_files(DB_PATH)
# Process archive from Nextcloud
cld_filenames = get_nextcloud_files(CLD_PATH)
copiedFilesIDs = copy_starred_files_to_local(starred_filenames, cld_filenames, DST_PATH)
# Process archive from Google Drive (local folder)
gdrive_files = get_local_gdrive_files(GDRV_PATH)
copiedFilesIDs.extend(copy_starred_files_from_gdrive_to_local(starred_filenames, gdrive_files, DST_PATH))
update_db_with_copied_files_filenames(copiedFilesIDs,starred_filenames,DB_PATH)
display_status(starred_filenames,copiedFilesIDs)
