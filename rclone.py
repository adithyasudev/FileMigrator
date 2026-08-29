# ============================================================
# rclone.py
# ASHRAM FILE MIGRATOR — STEP 14
# ============================================================
#
# WHAT:
#     This module lets our program talk to Rclone.
#     Rclone handles all cloud storage operations.
#
# WHY Rclone instead of writing cloud code ourselves?
#     Each cloud has a completely different API.
#     Google Drive API is different from OneDrive API
#     which is different from Amazon S3 API.
#     Writing all of them would take months.
#
#     Rclone already supports 50+ clouds.
#     We just run rclone commands from Python.
#     One file — works with every cloud the Ashram uses.
#
# HOW:
#     Python has a built-in module called subprocess.
#     subprocess lets Python run any terminal command
#     and capture the output.
#
#     So when we call list_files("test-google-drive"),
#     Python runs:  rclone lsjson test-google-drive:
#     and gives us the result as a Python list.
#
# ============================================================

from app_paths import get_rclone_executable
import subprocess
import json
import os
# Prevent rclone.exe from opening a visible console window
# when called by the packaged Windows GUI.
RCLONE_CREATION_FLAGS = (
    subprocess.CREATE_NO_WINDOW
    if os.name == "nt"
    else 0
)



# ============================================================
# HELPER — run any rclone command
# ============================================================
#
# WHY a helper function?
#     Every rclone operation needs the same three steps:
#       1. Build and run the command
#       2. Check if it succeeded or failed
#       3. Return the output or error
#
#     One helper means we write this logic once
#     and every other function uses it.
#
# ============================================================

def _is_authentication_error(error_text):
    """
    Return True when an Rclone error looks like a
    cloud authentication / authorization problem.
    """

    text = str(error_text).lower()

    auth_signals = [
        "invalid_grant",
        "invalid credentials",
        "authentication failed",
        "unauthorized",
        "access denied",
        "access_denied",
        "token expired",
        "expired token",
        "oauth",
        "failed to refresh token",
    ]

    return any(signal in text for signal in auth_signals)

    


def _run_rclone(args, capture_output=True):
    """
    Run an rclone command.


    args           — list of arguments
                     e.g. ['ls', 'test-google-drive:']
    capture_output — retained for compatibility with existing callers.
                     rclone output is always captured so the
                     Windows GUI never writes progress to a terminal.
                     (use False for copy/progress display)


    Returns:
        (True,  output_text)   if command succeeded
        (False, error_text)    if command failed
    """


    # We build the full command as a list.
    # WHY a list, not a string?
    #     subprocess handles lists more reliably.
    #     Paths with spaces work correctly in lists.
    #     Example: ["rclone", "ls", "gdrive:My Folder"]
    #     works even though "My Folder" has a space.

    command = [get_rclone_executable()] + args
    
    
    try:


        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=RCLONE_CREATION_FLAGS
        )

        if result.returncode == 0:


            # Command succeeded
            output = result.stdout or result.stderr or ""
            return True, output


        else:

            error = result.stderr or result.stdout or ""

            if _is_authentication_error(error):

                return False, (
                    "CLOUD AUTHENTICATION FAILED.\n\n"
                    "The cloud login/token may have expired.\n"
                    "Migration has been stopped safely.\n\n"
                    "Reconnect the cloud remote using:\n"
                    "rclone config reconnect <remote>:\n\n"
                    f"Rclone details:\n{error}"
                )

            return False, f"Rclone error:\n{error}"


    except FileNotFoundError:


        # This happens if rclone is not installed
        return False, (
            "ERROR: rclone not found.\n"
            "Make sure rclone is installed.\n"
            "Download from: https://rclone.org/downloads/"
        )


    except Exception as error:


        return False, f"Unexpected error running rclone: {error}"



def _run_rclone_with_progress(
    args,
    progress_callback=None,
    stop_callback=None
):
    """
    Run a long rclone operation without writing anything
    directly to the terminal.

    rclone output is captured line-by-line and optionally
    forwarded to the GUI through progress_callback.

    Returns:
        (True, output_text)   on success
        (False, error_text)   on failure
    """

    command = [get_rclone_executable()] + args

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=RCLONE_CREATION_FLAGS
        )

        output_lines = []

        if process.stdout is not None:
            for line in process.stdout:

                # ------------------------------------------------
                # GRACEFUL APPLICATION-CLOSE CANCELLATION
                # ------------------------------------------------

                if (
                    stop_callback is not None
                    and stop_callback()
                ):
                    process.terminate()

                    try:
                        process.wait(timeout=5)
                    except Exception:
                        process.kill()

                    return False, (
                        "Cloud migration interrupted by user. "
                        "Progress was preserved for resume."
                    )

                line = line.strip()

                if not line:
                    continue

                output_lines.append(line)

                if progress_callback is not None:
                    progress_callback(line)
        return_code = process.wait()

        output = "\n".join(output_lines)

        if return_code == 0:
            return True, output

        if _is_authentication_error(output):
            return False, (
                "CLOUD AUTHENTICATION FAILED.\n\n"
                "The cloud login/token may have expired.\n"
                "Migration has been stopped safely.\n\n"
                "Reconnect the cloud remote using:\n"
                "rclone config reconnect <remote>:\n\n"
                f"Rclone details:\n{output}"
            )

        return False, f"Rclone error:\n{output}"

    except FileNotFoundError:
        return False, (
            "ERROR: rclone not found.\n"
            "Make sure rclone is available to the application."
        )

    except Exception as error:
        return False, (
            f"Unexpected error running rclone: {error}"
        )



# ============================================================
# LIST REMOTES
# ============================================================
#
# WHAT:
#     Return all cloud remotes the user has configured.
#
# WHY:
#     The user needs to see which clouds are available
#     so they can choose where to copy files to/from.
#
# Example output:
#     ['test-google-drive', 'onedrive', 's3-backup']
#
# ============================================================


def list_remotes():
    """
    Return a list of all configured rclone remotes.


    Returns:
        (True,  ['remote1', 'remote2'])
        (False, 'error message')
    """


    ok, output = _run_rclone(["listremotes"])


    if not ok:
        return False, output


    # Each line looks like: "test-google-drive:\n"
    # We remove the colon and whitespace.


    remotes = []


    for line in output.strip().splitlines():


        remote = line.strip().rstrip(":")


        if remote:
            remotes.append(remote)


    return True, remotes



# ============================================================
# CHECK REMOTE — is this cloud reachable?
# ============================================================
#
# WHY:
#     Before starting a migration, we verify the cloud
#     remote is reachable. If authentication has expired
#     or the network is down, we catch it here — before
#     touching any files.
#
# ============================================================


def check_remote(remote):
    """
    Check if a remote is configured and reachable.


    Returns:
        (True,  'OK message')
        (False, 'error message')
    """


    ok, output = _run_rclone([
        "lsd",
        f"{remote}:",
        "--max-depth", "1"
    ])


    if ok:
        return True, f"Remote '{remote}' is reachable."

    else:

        if "CLOUD AUTHENTICATION FAILED" in output:
            return False, output

        return False, (
            f"Remote '{remote}' is NOT reachable.\n"
            f"Possible reasons:\n"
            f"  - Remote not configured (run: rclone config)\n"
            f"  - Authentication expired (run: rclone config reconnect {remote}:)\n"
            f"  - No internet connection\n\n"
            f"Rclone details:\n{output}"
        )



# ============================================================
# LIST FILES — see what is in a cloud location
# ============================================================
#
# WHAT:
#     List all files inside a cloud folder.
#     Returns file names, sizes, and paths.
#
# WHY lsjson?
#     rclone lsjson returns JSON format.
#     JSON is easy to read in Python.
#     It includes size, name, path, and hash info.
#
# ============================================================


def list_files(remote, path=""):
    """
    List all files in a cloud location.

    remote — rclone remote name e.g. 'test-google-drive'
    path   — subfolder e.g. 'videos'
             leave empty for root of remote

    Returns:
        (True,  [list of file info dictionaries])
        (False, 'error message')
    """

    # Build the remote:path string
    if path:
        remote_path = f"{remote}:{path}"
    else:
        remote_path = f"{remote}:"

    ok, output = _run_rclone([
        "lsjson",
        remote_path
    ])

    if not ok:
        return False, output

    # --------------------------------------------------------
    # WHY check for empty output?
    #     If the folder is empty, rclone returns nothing
    #     or an empty string. json.loads("") would crash.
    #     We return an empty list instead.
    # --------------------------------------------------------

    if not output or not output.strip():
        return True, []

    try:
        files = json.loads(output)
        return True, files

    except json.JSONDecodeError as error:
        return False, f"Could not read rclone output: {error}"

# ============================================================
# GET CLOUD FILE HASHES — for verification
# ============================================================
#
# WHY:
#     After copying files to cloud, we need to verify
#     they arrived intact — just like local verification.
#
#     Google Drive stores MD5 hashes for every file.
#     We can get these WITHOUT downloading the file.
#     This makes cloud verification fast.
#
# HOW:
#     rclone hashsum md5 fetches MD5 hashes from cloud.
#     Returns one hash per file.
#
# ============================================================


def get_cloud_hashes(remote, path=""):
    """
    Get MD5 hashes of all files in a cloud location.


    Returns a dictionary mapping file path to MD5 hash:
    {
        "videos/baba.mp4": "abc123...",
        "videos/maa.mp4":  "def456...",
    }


    Returns:
        (True,  {path: hash, ...})
        (False, 'error message')
    """


    if path:
        remote_path = f"{remote}:{path}"
    else:
        remote_path = f"{remote}:"


    ok, output = _run_rclone([
        "hashsum",
        "md5",
        remote_path
    ])


    if not ok:
        return False, output


    # Each output line looks like:
    # "abc123def456...  videos/baba.mp4"
    # We split into hash and filename.


    hashes = {}


    for line in output.strip().splitlines():


        # Split on whitespace, maximum 2 parts
        parts = line.split(None, 1)


        if len(parts) == 2:
            hash_value = parts[0]
            file_path  = parts[1].strip()
            hashes[file_path] = hash_value


    return True, hashes



# ============================================================
# COPY LOCAL → CLOUD
# ============================================================
#
# WHAT:
#     Upload local files to a cloud remote.
#
# WHY rclone copy not rclone move?
#     Same reason as local migration — we COPY first,
#     VERIFY, then delete source only if all verified.
#     Never move directly — too risky.
#
# ============================================================


def copy_to_cloud(
    local_path,
    remote,
    remote_path="",
    progress_callback=None,
    stop_callback=None,
    files_from=None
):
    """
    Copy a local file or folder to cloud.

    progress_callback:
        Optional function used by the GUI to receive
        live rclone progress lines.
    """

    if remote_path:
        destination = f"{remote}:{remote_path}"
    else:
        destination = f"{remote}:"

    args = [
        "copy",
        local_path,
        destination,
        "--progress",
        "--stats",
        "1s"
    ]

    if files_from:
        for relative_path in files_from:
            args.extend([
                "--include",
                relative_path
            ])

    ok, output = _run_rclone_with_progress(
        args,
        progress_callback=progress_callback,
        stop_callback=stop_callback
    )

    if ok:
        return True, (
            f"Upload complete: "
            f"{local_path} → {destination}"
        )

    return False, output



# ============================================================
# COPY CLOUD → LOCAL
# ============================================================
#
# WHAT:
#     Download files from cloud to local storage.
#
# WHY:
#     When cloud is the SOURCE of a migration.
#     Download first, verify, then delete cloud source.
#
# ============================================================


def copy_from_cloud(
    remote,
    remote_path,
    local_path,
    progress_callback=None,
    stop_callback=None,
    files_from=None
):
    
    """
    Download files from cloud to a local folder.

    progress_callback:
        Optional function used by the GUI to receive
        live rclone progress lines.
    """

    if remote_path:
        source = f"{remote}:{remote_path}"
    else:
        source = f"{remote}:"

    os.makedirs(
        local_path,
        exist_ok=True
    )
    args = [
        "copy",
        source,
        local_path,
        "--progress",
        "--stats",
        "1s"
    ]

    if files_from:
        for relative_path in files_from:
            args.extend([
                "--include",
                relative_path
            ])


    ok, output = _run_rclone_with_progress(
        args,
        progress_callback=progress_callback,
        stop_callback=stop_callback
    )

    if ok:
        return True, (
            f"Download complete: "
            f"{source} → {local_path}"
        )

    return False, output



# ============================================================
# COPY CLOUD → CLOUD
# ============================================================
#
# WHAT:
#     Copy directly between two cloud locations.
#
# WHY:
#     Most efficient way to migrate between clouds.
#     Files go directly cloud to cloud.
#     No downloading to your computer needed.
#
# Example:
#     Google Drive → OneDrive
#     S3 Bucket A  → S3 Bucket B
#
# ============================================================


def copy_cloud_to_cloud(
    source_remote,
    source_path,
    dest_remote,
    dest_path,
    progress_callback=None,
    stop_callback=None
):
    """
    Copy files directly from one cloud location
    to another.
    """

    source = (
        f"{source_remote}:{source_path}"
        if source_path
        else f"{source_remote}:"
    )

    destination = (
        f"{dest_remote}:{dest_path}"
        if dest_path
        else f"{dest_remote}:"
    )

    ok, output = _run_rclone_with_progress(
        [
            "copy",
            source,
            destination,
            "--progress",
            "--stats",
            "1s"
        ],
        progress_callback=progress_callback,
        stop_callback=stop_callback
    )

    if ok:
        return True, (
            f"Cloud copy complete: "
            f"{source} → {destination}"
        )

    return False, output

def delete_cloud_file(
    remote,
    relative_path,
    progress_callback=None,
    stop_callback=None
):
    """
    Delete exactly one file from a cloud remote.

    This is used only AFTER verification succeeds.

    Returns:
        (True, success_message)
        (False, error_message)
    """

    cloud_file = (
        f"{remote}:{relative_path}"
    )

    ok, output = _run_rclone_with_progress(
        [
            "deletefile",
            cloud_file
        ],
        progress_callback=progress_callback,
        stop_callback=stop_callback
    )

    if ok:
        return True, (
            f"Deleted cloud source file: {cloud_file}"
        )

    return False, output



# ============================================================
# SHOW REMOTES — print configured remotes for user
# ============================================================


def show_remotes():
    """
    Print all configured remotes to the terminal.
    """


    ok, remotes = list_remotes()


    if not ok:
        print(f"  Error: {remotes}")
        return


    if not remotes:
        print("  No cloud remotes configured.")
        print("  Run: rclone config")
        return


    print("  Configured cloud remotes:")
    print()


    for i, remote in enumerate(remotes, start=1):
        print(f"    {i}. {remote}")


    print()