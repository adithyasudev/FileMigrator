# ============================================================
# cloudhash.py
# ASHRAM FILE MIGRATOR — STEP 17
# ============================================================
#
# WHAT:
#     Get and display MD5 hashes of files stored in
#     Google Drive or any cloud storage.
#
# WHY:
#     Requirement 7 mentions:
#     "CloudHASH / Chrome extension MD5 checker
#      for Google Drive"
#
#     CloudHASH is a Chrome extension that shows MD5
#     hashes of Google Drive files one at a time.
#     It is manual, slow, and browser-only.
#
#     Our program replaces CloudHASH completely:
#       - Gets MD5 of ALL files automatically
#       - Works for any cloud, not just Google Drive
#       - Saves results to CSV report
#       - Can compare local MD5 vs cloud MD5
#
# HOW:
#     Google Drive stores MD5 hashes for every file.
#     Rclone can fetch these hashes WITHOUT downloading.
#     We get them, display them, and save to CSV.
#
# ============================================================

import os
import csv
from datetime import datetime
from rclone import get_cloud_hashes, list_files, check_remote


# ============================================================
# FORMAT SIZE — human readable
# ============================================================

def format_size(bytes_value):
    """Convert bytes to readable string."""

    if bytes_value is None:
        return "unknown"

    for unit in ["bytes", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024

    return f"{bytes_value:.1f} PB"


# ============================================================
# GET CLOUD FILE INFO — hashes + sizes combined
# ============================================================
#
# WHY combine hashes and file info?
#     get_cloud_hashes() gives us MD5 values.
#     list_files() gives us sizes and full details.
#     Combining both gives us a complete picture
#     of every file in the cloud.
#
# ============================================================

def get_cloud_file_info(remote, path=""):
    """
    Get MD5 hash and size for every file in a cloud location.

    Returns a list of dictionaries:
    [
        {
            "path":  "videos/baba.mp4",
            "name":  "baba.mp4",
            "size":  4767552,
            "md5":   "ea088a76..."
        },
        ...
    ]

    Returns:
        (True,  [file_info_list])
        (False, error_message)
    """

    # --------------------------------------------------------
    # Get MD5 hashes
    # --------------------------------------------------------

    ok, hashes = get_cloud_hashes(remote, path)

    if not ok:
        return False, f"Could not get hashes: {hashes}"

    # --------------------------------------------------------
    # Get file details (size, name, path)
    # --------------------------------------------------------

    ok, file_list = list_files(remote, path)

    if not ok:
        return False, f"Could not list files: {file_list}"

    # --------------------------------------------------------
    # Combine hashes with file details
    #
    # WHY build a lookup dictionary?
    #     list_files returns a list — slow to search.
    #     A dictionary lets us find files by path instantly.
    # --------------------------------------------------------

    # Build lookup: path → file details
    file_details = {}

    for f in file_list:

        if not f.get("IsDir", False):

            # Normalise path separators
            file_path = f["Path"].replace("\\", "/")
            file_details[file_path] = f

    # --------------------------------------------------------
    # Build combined result list
    # --------------------------------------------------------

    combined = []

    for file_path, md5 in hashes.items():

        # Normalise path
        normalised = file_path.replace("\\", "/")

        # Get file details if available
        details = file_details.get(normalised, {})

        combined.append({
            "path": normalised,
            "name": os.path.basename(normalised),
            "size": details.get("Size", None),
            "md5":  md5
        })

    # Sort by path for consistent display
    combined.sort(key=lambda x: x["path"])

    return True, combined


# ============================================================
# DISPLAY CLOUD HASHES — print to terminal
# ============================================================
#
# WHY display clearly?
#     The Ashram user needs to read these values.
#     A clear table format is much easier than
#     raw rclone output.
#
# ============================================================

def display_cloud_hashes(remote, path, file_info_list):
    """
    Print cloud file hashes to the terminal in a
    clear, readable format.
    """

    print()
    print("==========================================")
    print("CLOUD FILE HASHES")
    print("==========================================")
    print()
    print(f"  Remote: {remote}:{path if path else '(root)'}")
    print(f"  Files:  {len(file_info_list)}")
    print()
    print(f"  {'MD5 Hash':<35} {'Size':<12} File")
    print(f"  {'-'*35} {'-'*12} {'-'*40}")

    for f in file_info_list:

        size_str = format_size(f["size"]) if f["size"] else "unknown"
        md5_short = f["md5"][:32] if f["md5"] else "unavailable"

        print(f"  {md5_short:<35} {size_str:<12} {f['path']}")

    print()


# ============================================================
# COMPARE LOCAL FILE VS CLOUD FILE
# ============================================================
#
# WHY:
#     After uploading a file to cloud, we want to confirm
#     the cloud copy has the same MD5 as the local file.
#     This is the ultimate verification step.
#
# HOW:
#     1. Calculate MD5 of the local file
#     2. Get MD5 of the cloud file from Google Drive
#     3. Compare — must be identical
#
# ============================================================

def compare_local_vs_cloud(local_file_path, remote, cloud_file_path):
    """
    Compare MD5 of a local file with its cloud copy.

    local_file_path  — full local path e.g. C:\\AshramData\\baba.jpg
    remote           — rclone remote name
    cloud_file_path  — path on cloud e.g. Photos/baba.jpg

    Returns:
        (True,  result_dictionary)
        (False, error_message)
    """

    import hashlib

    # --------------------------------------------------------
    # Calculate local MD5
    # --------------------------------------------------------

    print(f"  Calculating local MD5:  {local_file_path}")

    try:

        md5 = hashlib.md5()

        with open(local_file_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                md5.update(chunk)

        local_md5 = md5.hexdigest()
        print(f"    Local MD5:  {local_md5}")

    except Exception as error:
        return False, f"Could not read local file: {error}"

    # --------------------------------------------------------
    # Get cloud MD5
    # --------------------------------------------------------

    print(f"  Getting cloud MD5:  {remote}:{cloud_file_path}")

    # Extract folder path from the cloud file path
    cloud_folder = os.path.dirname(cloud_file_path)
    cloud_name   = os.path.basename(cloud_file_path)

    ok, hashes = get_cloud_hashes(remote, cloud_folder)

    if not ok:
        return False, f"Could not get cloud hashes: {hashes}"

    # Find the specific file in the hashes
    cloud_md5 = None

    for file_path, hash_value in hashes.items():

        if os.path.basename(file_path) == cloud_name:
            cloud_md5 = hash_value
            break

    if not cloud_md5:
        return False, f"File not found in cloud: {cloud_file_path}"

    print(f"    Cloud MD5:  {cloud_md5}")

    # --------------------------------------------------------
    # Compare
    # --------------------------------------------------------

    match = (local_md5 == cloud_md5)

    result = {
        "local_path":  local_file_path,
        "cloud_path":  f"{remote}:{cloud_file_path}",
        "local_md5":   local_md5,
        "cloud_md5":   cloud_md5,
        "status":      "IDENTICAL" if match else "DIFFERENT"
    }

    return True, result


# ============================================================
# SAVE CLOUD HASH REPORT TO CSV
# ============================================================
#
# WHY save to CSV?
#     Permanent record of what was in the cloud.
#     Opens in Excel.
#     Can be used to verify cloud contents later.
#
# ============================================================

def save_cloud_hash_report(remote, path, file_info_list, reports_folder):
    """
    Save cloud file hashes to a CSV report.
    Returns the path to the saved file.
    """

    os.makedirs(reports_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_path = os.path.join(
        reports_folder,
        f"cloud_hashes_{timestamp}.csv"
    )

    fieldnames = [
        "File Path",
        "File Name",
        "Size",
        "MD5 Hash",
        "Cloud Remote",
        "Cloud Path",
        "Scan Time"
    ]

    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(
        report_path, "w", newline="", encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for file_info in file_info_list:

            writer.writerow({
                "File Path":    file_info["path"],
                "File Name":    file_info["name"],
                "Size":         file_info["size"] or "",
                "MD5 Hash":     file_info["md5"],
                "Cloud Remote": remote,
                "Cloud Path":   path or "(root)",
                "Scan Time":    scan_time
            })

    return report_path


# ============================================================
# MAIN FUNCTION — run_cloud_hash_check()
# ============================================================
#
# WHAT:
#     Complete CloudHASH replacement.
#     Lists all files in a cloud location with their
#     MD5 hashes, displays them, and saves to CSV.
#
# ============================================================

def run_cloud_hash_check(remote, path="", reports_folder="reports"):
    """
    Get MD5 hashes for all files in a cloud location.
    Display results and save to CSV report.

    remote         — rclone remote name
    path           — cloud folder path (empty = root)
    reports_folder — where to save CSV report

    Returns:
        True  — completed successfully
        False — error occurred
    """

    print()
    print("==========================================")
    print("CLOUD HASH CHECKING...")
    print("==========================================")
    print()
    print(f"  Checking: {remote}:{path if path else '(root)'}")
    print()

    # Check remote is reachable
    ok, msg = check_remote(remote)

    if not ok:
        print(f"  ✗ Remote not reachable: {msg}")
        return False

    print(f"  ✓ {msg}")
    print()

    # Get file info
    print("  Getting file hashes from cloud...")
    print()

    ok, file_info_list = get_cloud_file_info(remote, path)

    if not ok:
        print(f"  ✗ Error: {file_info_list}")
        return False

    if not file_info_list:
        print("  No files found at this location.")
        return True

    # Display results
    display_cloud_hashes(remote, path, file_info_list)

    # Save report
    report_path = save_cloud_hash_report(
        remote, path, file_info_list, reports_folder
    )

    print(f"  Report saved: {report_path}")
    print()

    return True