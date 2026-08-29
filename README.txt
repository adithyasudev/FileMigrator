NARAYANASHRAM FILE MIGRATOR
Version 1.0.0

Narayanashrama Tapovanam
Safe - Verified - Reliable


1. ABOUT

Narayanashram File Migrator is a Windows application for transferring
files between local folders and supported cloud locations.

It supports:

- Local COPY and MOVE
- Cloud upload and download
- Cloud-to-cloud transfer
- MD5, SHA-1, and SHA-256 verification
- Safe source deletion after verification
- Interrupted-migration recovery
- CSV reports and permanent logs


2. INSTALLATION

1. Copy the complete AshramFileMigrator folder to a writable location
   such as the Desktop or Documents folder.

2. Keep these items together:

   AshramFileMigrator.exe
   _internal
   logs
   reports
   README.txt

3. Do not distribute or move only the EXE. The _internal folder is
   required.

4. Open AshramFileMigrator.exe.

5. If Windows SmartScreen appears, select:

   More info > Run anyway

Python, VS Code, PyInstaller, and a separate rclone installation are
not required. The required rclone executable is included inside:

_internal\rclone.exe


SYSTEM REQUIREMENTS

- 64-bit Windows 10 or Windows 11
- Read access to source locations
- Write access to destination locations
- Sufficient destination space
- Internet connection for cloud transfers


3. COPY AND MOVE

COPY keeps the original source files.

MOVE removes source files only according to successful verification.
Use COPY whenever the original files should remain available.


HOW TO START

1. Open AshramFileMigrator.exe.

2. Select COPY or MOVE.

3. Under SOURCE, select:

   Browse Files
       Select one or more individual files.

   Browse Folder
       Select a complete local folder.

   Cloud
       Select a configured cloud location.

4. Under DESTINATION, select:

   Browse Folder
       Select a local destination.

   Cloud
       Select a configured cloud destination.

5. Confirm the source, destination, operation, and file count.

6. Click START MIGRATION.

7. Review the confirmation window and click Yes.

8. Keep the application open until transfer and verification finish.


SUCCESS

A successful operation displays:

COPY COMPLETE

or:

MOVE COMPLETE

Confirm:

- Progress is 100%
- Failed count is 0
- Destination files exist
- Reports and logs were created

For MOVE, confirm the source-deletion status in the Technical Report.


4. FIRST-TIME GOOGLE DRIVE CONFIGURATION

Rclone is already included. It does not need to be installed
separately.

Each Windows user must authorize their own Google Drive account once.
Never distribute another user's rclone configuration.


STEP-BY-STEP CONFIGURATION

1. Open the delivered AshramFileMigrator folder.

2. Click the File Explorer address bar.

3. Type:

   powershell

4. Press Enter.

5. Run:

   .\_internal\rclone.exe config

6. At the configuration menu, enter:

   n

   In this menu, n means New remote.

7. Enter a remote name, for example:

   ashram-google-drive

   Do not include a colon in the name.

8. Find Google Drive in the storage-provider list.

9. Enter the number displayed beside Google Drive.

   The number may change between rclone versions. If the prompt
   accepts provider names, enter:

   drive

10. At Google Application Client ID:

    client_id>

    Press Enter to leave it blank.

11. At Google Application Client Secret:

    client_secret>

    Press Enter to leave it blank.

12. For access scope, select:

    Full access to all files

    This is normally option 1. Full access is required for upload,
    download, cloud copy, and MOVE operations.

13. At root_folder_id, press Enter to leave it blank.

14. At service_account_file, press Enter to leave it blank.

15. When asked:

    Edit advanced config?

    Enter:

    n

16. When asked:

    Use web browser to automatically authenticate rclone?

    Enter:

    y

17. The browser opens. Sign in using the Google account that will
    be used with Ashram File Migrator.

18. Review the permission request and select Allow or Continue.

19. Return to PowerShell after authorization succeeds.

20. When asked:

    Configure this as a Shared Drive?

    For a normal My Drive account, enter:

    n

    For an organizational Google Shared Drive, enter:

    y

    Then select the required Shared Drive.

21. Review the completed configuration.

22. When asked whether to keep the remote, enter:

    y

23. At the main configuration menu, enter:

    q

24. Confirm that the remote was saved:

    .\_internal\rclone.exe listremotes

25. Expected output:

    ashram-google-drive:

26. Test the connection:

    .\_internal\rclone.exe lsd "ashram-google-drive:"

27. If Google Drive folders are displayed, close and reopen
    Ashram File Migrator.

28. Click Cloud and select:

    ashram-google-drive


CONFIGURATION LOCATION

The private configuration is stored for the current Windows user at:

%APPDATA%\rclone\rclone.conf


RECONNECTING GOOGLE DRIVE

If authorization expires, run:

.\_internal\rclone.exe config reconnect ashram-google-drive:


CLOUD SECURITY

- Never include rclone.conf in the delivery package.
- Never share rclone.conf, tokens, or authorization screenshots.
- Confirm that the correct Google account is selected.
- Configure the remote while signed in as the Windows user who will
  operate the application.


5. CLOUD MIGRATION

Cloud access must be configured before clicking Cloud.


LOCAL TO CLOUD

1. Select COPY or MOVE.
2. Select a local source.
3. Click Cloud under DESTINATION.
4. Select the remote and cloud folder.
5. Click START MIGRATION and confirm.


CLOUD TO LOCAL

1. Select COPY or MOVE.
2. Click Cloud under SOURCE.
3. Select the remote cloud file or folder.
4. Select a local destination folder.
5. Click START MIGRATION and confirm.


CLOUD TO CLOUD

1. Select COPY or MOVE.
2. Select the cloud source.
3. Select the cloud destination.
4. Confirm that source and destination are different.
5. Click START MIGRATION and confirm.


CLOUD SAFETY

- Keep the internet connected.
- Do not close the application during transfer.
- COPY keeps the original source.
- Review reports after every cloud MOVE.
- Cloud speed depends on the connection and provider limits.


6. RESUMING AN INTERRUPTED MIGRATION

If an incomplete migration is detected when the application opens:

1. Review the operation, destination, and verified-file count.

2. Click Yes to resume.

3. Confirm the already-verified and remaining-file counts.

4. Click START MIGRATION.

5. Previously verified files are skipped.

6. Remaining files are transferred and verified.

Do not rename, modify, or remove source files before resuming. Do not
change the saved destination or manually edit recovery files.


7. REPORTS AND LOGS

The application stores permanent records inside:

reports
logs


USER REPORT

Provides a simple summary:

- Operation
- Migration type
- Overall result
- Total files
- Successful files
- Failed files
- Simple failure reason


TECHNICAL REPORT

Provides detailed information:

- Source and destination paths
- Source and destination sizes
- MD5
- SHA-1
- SHA-256
- Verification status
- Deletion status

Use the User Report, Technical Report, and Reports Folder buttons to
save or review migration results.


8. ERRORS AND RECOVERY

INSUFFICIENT SPACE

Free destination space or select another destination.


SOURCE OR DESTINATION NOT FOUND

Reconnect the drive or network location, confirm the path, and check
access permissions.


VERIFICATION FAILED

Do not delete the source. Open the reports, identify the failed file,
correct the destination problem, and repeat the affected transfer.


MIGRATION INTERRUPTED

Reopen the application, accept the resume prompt, complete the
migration, and review the final report.


CLOUD CONNECTION FAILED

Confirm:

- Internet connection is working
- Cloud configuration was completed
- The correct remote was selected
- Authorization is still valid
- The cloud path exists

Test the remote with:

.\_internal\rclone.exe lsd "ashram-google-drive:"


APPLICATION ALREADY RUNNING

Only one application window is allowed. Use the window that is already
open.


9. SAFETY

The application follows this process:

Source > Transfer > Destination > Verification > Report
> Optional source deletion


IMPORTANT RULES

- Verify the source, destination, and operation before starting.
- COPY keeps the source.
- MOVE may permanently remove verified source files.
- Wait for verification; visible destination files alone do not prove
  success.
- Confirm that the failed count is zero.
- Review reports after important migrations.
- Never disconnect storage or turn off the computer while deletion is
  running.
- Keep reports and logs until the destination has been reviewed.