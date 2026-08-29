# comparator.py
# ASHRAM FILE MIGRATOR — STEP 15
# ============================================================
#
# WHAT:
#     Compare two cloud storage locations and check
#     whether they are identical.
#
# WHY:
#     Requirement 5 says:
#     "compare two cloud storages for confirmation
#      of their identicalness"
#
#     After migrating files from one cloud to another,
#     we need PROOF that both clouds have the same files
#     with the same content before deleting the source.
#
#     This is the verification step for cloud migrations.
#
# HOW:
#     1. Get MD5 hash of every file in Cloud A
#     2. Get MD5 hash of every file in Cloud B
#     3. Compare the two lists
#     4. Report: identical / different / missing files
#     5. Save a CSV report
#
# WHY MD5 for cloud comparison?
#     Google Drive and most clouds store MD5 hashes
#     for every file automatically.
#     We can get these hashes WITHOUT downloading files.
#     This makes comparison fast even for 10,000 files.
#
# ============================================================


import os
import csv
from datetime import datetime
from rclone import get_cloud_hashes, check_remote



# ============================================================
# COMPARE TWO CLOUD LOCATIONS
# ============================================================
#
# WHAT:
#     Get hashes from both clouds and compare them.
#
# RETURNS a dictionary with four categories:
#
#     identical — same file, same hash in both clouds
#     different — same file name, different hash (corrupted?)
#     only_in_a — file exists in A but missing from B
#     only_in_b — file exists in B but not in A
#
# ============================================================


def compare_clouds(
    remote_a, path_a,
    remote_b, path_b
):
    """
    Compare files between two cloud locations.


    remote_a — first rclone remote  e.g. 'test-google-drive'
    path_a   — folder path on A     e.g. 'videos'
    remote_b — second rclone remote e.g. 'onedrive'
    path_b   — folder path on B     e.g. 'AshramBackup/videos'


    Returns:
        (True,  results_dictionary)
        (False, error_message)
    """


    print()
    print("==========================================")
    print("CLOUD-TO-CLOUD COMPARISON")
    print("==========================================")
    print()
    print(f"  Cloud A: {remote_a}:{path_a}")
    print(f"  Cloud B: {remote_b}:{path_b}")
    print()


    # ----------------------------------------------------------
    # Step 1 — Check both remotes are reachable
    #
    # WHY check before getting hashes?
    #     If a remote is unreachable, we get a confusing
    #     error message. Better to check clearly first.
    # ----------------------------------------------------------


    print("  Checking Cloud A...")
    ok_a, msg_a = check_remote(remote_a)


    if not ok_a:
        return False, f"Cloud A not reachable: {msg_a}"


    print(f"    ✓ {msg_a}")


    print("  Checking Cloud B...")
    ok_b, msg_b = check_remote(remote_b)


    if not ok_b:
        return False, f"Cloud B not reachable: {msg_b}"


    print(f"    ✓ {msg_b}")
    print()


    # ----------------------------------------------------------
    # Step 2 — Get MD5 hashes from Cloud A
    #
    # WHY hashes?
    #     Hash comparison proves files are byte-for-byte
    #     identical without downloading them.
    # ----------------------------------------------------------


    print("  Getting file hashes from Cloud A...")


    ok, hashes_a = get_cloud_hashes(remote_a, path_a)


    if not ok:
        return False, f"Could not get hashes from Cloud A: {hashes_a}"


    print(f"    ✓ Found {len(hashes_a)} files in Cloud A")


    # ----------------------------------------------------------
    # Step 3 — Get MD5 hashes from Cloud B
    # ----------------------------------------------------------


    print("  Getting file hashes from Cloud B...")


    ok, hashes_b = get_cloud_hashes(remote_b, path_b)


    if not ok:
        return False, f"Could not get hashes from Cloud B: {hashes_b}"


    print(f"    ✓ Found {len(hashes_b)} files in Cloud B")
    print()


    # ----------------------------------------------------------
    # Step 4 — Compare the two hash dictionaries
    #
    # WHY use sets?
    #     Sets make it very easy to find:
    #       - files in A but not B  (set difference A - B)
    #       - files in B but not A  (set difference B - A)
    #       - files in both         (set intersection)
    # ----------------------------------------------------------


    files_in_a = set(hashes_a.keys())
    files_in_b = set(hashes_b.keys())


    # Files that exist in both clouds
    in_both = files_in_a & files_in_b


    # Files only in A (missing from B)
    only_in_a = files_in_a - files_in_b


    # Files only in B (missing from A)
    only_in_b = files_in_b - files_in_a


    # Compare hashes for files that exist in both
    identical  = []
    different  = []


    for filename in sorted(in_both):


        hash_a = hashes_a[filename]
        hash_b = hashes_b[filename]


        if hash_a == hash_b:


            # Same hash = identical file
            identical.append({
                "file":   filename,
                "hash_a": hash_a,
                "hash_b": hash_b
            })


        else:


            # Different hash = file was corrupted or changed
            different.append({
                "file":   filename,
                "hash_a": hash_a,
                "hash_b": hash_b
            })


    # Build results
    results = {
        "remote_a":    remote_a,
        "path_a":      path_a,
        "remote_b":    remote_b,
        "path_b":      path_b,
        "identical":   identical,
        "different":   different,
        "only_in_a":   sorted(only_in_a),
        "only_in_b":   sorted(only_in_b),
        "total_a":     len(files_in_a),
        "total_b":     len(files_in_b),
    }


    return True, results



# ============================================================
# PRINT COMPARISON RESULTS
# ============================================================
#
# WHAT:
#     Show the comparison results clearly in the terminal.
#
# WHY a separate function?
#     Keeps the compare logic separate from display logic.
#     Makes it easy to show results whether called from
#     main.py or from a future GUI.
#
# ============================================================


def print_comparison_results(results):
    """
    Print comparison results to the terminal in a
    clear, readable format.
    """


    print("==========================================")
    print("COMPARISON RESULTS")
    print("==========================================")
    print()
    print(f"  Cloud A: {results['remote_a']}:{results['path_a']}")
    print(f"  Cloud B: {results['remote_b']}:{results['path_b']}")
    print()
    print(f"  Files in Cloud A:   {results['total_a']}")
    print(f"  Files in Cloud B:   {results['total_b']}")
    print()


    identical = results["identical"]
    different = results["different"]
    only_in_a = results["only_in_a"]
    only_in_b = results["only_in_b"]


    print(f"  ✓ Identical:        {len(identical)}")
    print(f"  ✗ Different:        {len(different)}")
    print(f"  ✗ Missing in B:     {len(only_in_a)}")
    print(f"  ✗ Missing in A:     {len(only_in_b)}")
    print()


    # ----------------------------------------------------------
    # Show verdict
    # ----------------------------------------------------------


    if (
        len(different) == 0
        and len(only_in_a) == 0
        and len(only_in_b) == 0
    ):


        print("==========================================")
        print("  ✓ CLOUDS ARE IDENTICAL")
        print("    Every file matches. Safe to proceed.")
        print("==========================================")


    else:


        print("==========================================")
        print("  ✗ CLOUDS ARE NOT IDENTICAL")
        print("    Differences found. See details below.")
        print("==========================================")


        # Show different files
        if different:
            print()
            print("  FILES WITH DIFFERENT CONTENT:")
            for item in different:
                print(f"    ✗ {item['file']}")
                print(f"      Hash A: {item['hash_a']}")
                print(f"      Hash B: {item['hash_b']}")


        # Show missing in B
        if only_in_a:
            print()
            print("  FILES MISSING FROM CLOUD B:")
            for f in only_in_a:
                print(f"    ✗ {f}")


        # Show missing in A
        if only_in_b:
            print()
            print("  FILES MISSING FROM CLOUD A:")
            for f in only_in_b:
                print(f"    ✗ {f}")


    print()



# ============================================================
# SAVE COMPARISON REPORT TO CSV
# ============================================================
#
# WHY save to CSV?
#     The Ashram needs a permanent written record.
#     CSV opens directly in Microsoft Excel.
#     It proves which files matched and which did not.
#
# ============================================================


def save_comparison_report(results, reports_folder):
    """
    Save the comparison results to a CSV file.


    Returns the path to the saved report.
    """


    os.makedirs(reports_folder, exist_ok=True)


    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


    report_path = os.path.join(
        reports_folder,
        f"cloud_comparison_{timestamp}.csv"
    )


    fieldnames = [
        "File",
        "Status",
        "Hash Cloud A",
        "Hash Cloud B",
        "Cloud A",
        "Cloud B"
    ]


    with open(
        report_path, "w", newline="", encoding="utf-8"
    ) as f:


        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()


        # Write identical files
        for item in results["identical"]:
            writer.writerow({
                "File":        item["file"],
                "Status":      "IDENTICAL",
                "Hash Cloud A": item["hash_a"],
                "Hash Cloud B": item["hash_b"],
                "Cloud A":     f"{results['remote_a']}:{results['path_a']}",
                "Cloud B":     f"{results['remote_b']}:{results['path_b']}"
            })


        # Write different files
        for item in results["different"]:
            writer.writerow({
                "File":        item["file"],
                "Status":      "DIFFERENT",
                "Hash Cloud A": item["hash_a"],
                "Hash Cloud B": item["hash_b"],
                "Cloud A":     f"{results['remote_a']}:{results['path_a']}",
                "Cloud B":     f"{results['remote_b']}:{results['path_b']}"
            })


        # Write files only in A
        for filename in results["only_in_a"]:
            writer.writerow({
                "File":        filename,
                "Status":      "MISSING IN B",
                "Hash Cloud A": results.get("hashes_a", {}).get(filename, ""),
                "Hash Cloud B": "",
                "Cloud A":     f"{results['remote_a']}:{results['path_a']}",
                "Cloud B":     f"{results['remote_b']}:{results['path_b']}"
            })


        # Write files only in B
        for filename in results["only_in_b"]:
            writer.writerow({
                "File":        filename,
                "Status":      "MISSING IN A",
                "Hash Cloud A": "",
                "Hash Cloud B": results.get("hashes_b", {}).get(filename, ""),
                "Cloud A":     f"{results['remote_a']}:{results['path_a']}",
                "Cloud B":     f"{results['remote_b']}:{results['path_b']}"
            })


    return report_path



# ============================================================
# MAIN COMPARISON FUNCTION — called from main.py
# ============================================================
#
# WHAT:
#     This is the single function main.py calls
#     to run a complete cloud comparison.
#
# It:
#     1. Compares the two clouds
#     2. Prints results to terminal
#     3. Saves CSV report
#     4. Returns True if identical, False if different
#
# ============================================================


def run_cloud_comparison(
    remote_a, path_a,
    remote_b, path_b,
    reports_folder="reports"
):
    """
    Run a full cloud-to-cloud comparison.


    Returns:
        True  — clouds are identical
        False — clouds differ or error occurred
    """


    # Compare
    ok, results = compare_clouds(
        remote_a, path_a,
        remote_b, path_b
    )


    if not ok:
        print(f"  ✗ Comparison failed: {results}")
        return False


    # Print results
    print_comparison_results(results)


    # Save report
    report_path = save_comparison_report(results, reports_folder)


    print(f"  Comparison report saved:")
    print(f"  {report_path}")
    print()


    # Return True only if perfectly identical
    identical = (
        len(results["different"]) == 0
        and len(results["only_in_a"]) == 0
        and len(results["only_in_b"]) == 0
    )




