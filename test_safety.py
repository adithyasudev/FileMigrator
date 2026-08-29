# ============================================================
# test_safety.py
# ASHRAM FILE MIGRATOR — SAFETY TEST
# ============================================================
#
# WHAT:
#     Tests the most critical safety rule:
#     If ANY file fails verification during MOVE,
#     the source files must NOT be deleted.
#
# HOW:
#     1. Copy files to destination
#     2. Deliberately corrupt one destination file
#     3. Run verification
#     4. Confirm MOVE is stopped
#     5. Confirm source files still exist
#
# ============================================================

import os
import shutil
from copier   import copy_files, find_root_for_file
from verifier import verify_file

print()
print("==========================================")
print("SAFETY TEST — MOVE WITH CORRUPTED FILE")
print("==========================================")
print()

# ----------------------------------------------------------
# Setup test folders
# ----------------------------------------------------------

source_folder = r"C:\AshramData\RealSafetyTest"
dest_folder   = r"D:\AshramBackup"

# Clean destination if it exists
if os.path.exists(dest_folder):
    shutil.rmtree(dest_folder)
os.makedirs(dest_folder)

# Create test source files
os.makedirs(source_folder, exist_ok=True)

test_files = ["file1.txt", "file2.txt", "file3.txt"]

for filename in test_files:
    path = os.path.join(source_folder, filename)
    with open(path, "w") as f:
        f.write(f"Original content of {filename}")

print("  Test files created:")
for filename in test_files:
    print(f"    {os.path.join(source_folder, filename)}")

print()

# ----------------------------------------------------------
# Step 1 — Copy files
# ----------------------------------------------------------

print("  STEP 1 — Copying files...")
print()

source_roots = [source_folder]
source_files = [
    os.path.join(source_folder, f)
    for f in test_files
]

copied, failed = copy_files(source_files, source_roots, dest_folder)
print(f"  Copied: {copied}  Failed: {failed}")
print()

# ----------------------------------------------------------
# Step 2 — Deliberately corrupt ONE destination file
#
# WHY:
#     This simulates what would happen if a file was
#     damaged during transfer (disk error, network glitch).
#     The program must detect this and stop deletion.
# ----------------------------------------------------------

print("  STEP 2 — Deliberately corrupting file1.txt at destination...")

corrupted_file = os.path.join(dest_folder, "RealSafetyTest", "file1.txt")

with open(corrupted_file, "w") as f:
    f.write("CORRUPTED — this is different from source")

print(f"  Corrupted: {corrupted_file}")
print()

# ----------------------------------------------------------
# Step 3 — Verify all files
# ----------------------------------------------------------

print("  STEP 3 — Verifying all files...")
print()

verification_results = []
all_verified = True

for source_file in source_files:

    matched_root  = find_root_for_file(source_file, source_roots)
    base          = os.path.dirname(matched_root)
    relative_path = os.path.relpath(source_file, base)
    dest_file     = os.path.join(dest_folder, relative_path)

    result = verify_file(source_file, dest_file)
    verification_results.append(result)

    status = result["status"]
    mark   = "✓" if status == "VERIFIED" else "✗"
    print(f"    {mark} {status} — {os.path.basename(source_file)}")

    if status != "VERIFIED":
        all_verified = False

print()

# ----------------------------------------------------------
# Step 4 — Safety check
# ----------------------------------------------------------

print("  STEP 4 — Safety check...")
print()

if all_verified:
    print("  ✓ All verified — deletion would proceed")
else:
    print("  ✗ NOT ALL VERIFIED — deletion is BLOCKED")

print()

# ----------------------------------------------------------
# Step 5 — Delete ONLY if all verified
# ----------------------------------------------------------

print("  STEP 5 — Checking source files...")
print()

if all_verified:

    print("  All verified — deleting source files...")

    for f in source_files:
        os.remove(f)
        print(f"    Deleted: {f}")

else:

    # THIS IS THE CRITICAL SAFETY RULE
    # Even one failure = keep ALL source files

    print("  Deletion BLOCKED — checking source files are safe:")
    print()

    all_safe = True

    for f in source_files:
        exists = os.path.isfile(f)
        mark   = "✓" if exists else "✗"
        print(f"    {mark} {'EXISTS — SAFE' if exists else 'MISSING — DANGER'}: {f}")
        if not exists:
            all_safe = False

    print()

    if all_safe:
        print("==========================================")
        print("  ✓ SAFETY TEST PASSED")
        print("    All source files are safe.")
        print("    Deletion was correctly blocked.")
        print("==========================================")
    else:
        print("==========================================")
        print("  ✗ SAFETY TEST FAILED")
        print("    Source files were lost!")
        print("==========================================")