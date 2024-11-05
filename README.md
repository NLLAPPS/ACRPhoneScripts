# ACR Recordings Recovery Tool:
Author: Przemysław Hołubowski (przemhb@wp.pl).

Licence: GNU GPL.

Simple program to bring back selected recordings from cloud backups back to the ACR Phone to make them playable.
Founds recordings which are starred or have notes and copies them from clouds to a local folder.
Supported cloud services: Nextcloud (directly), Google Drive (via local virtual disk - use Google Drive app).

USAGE:
1. Configure paths and credentials. 
2. Copy: recording.db, recording.db-shm, recording.db-wal from: /system/data/data/com.nll.cb/databases to the folder where this file is. Root needed.
3. Run this program.
4. Copy updated recording.db back to the original location and delete recording.db-shm, recording.db-wal present there.
5. Copy recovered files from the local folder to the ACR Phone's recordings folder on your phone.
