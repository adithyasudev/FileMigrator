# ============================================================
# cloud_migration.py
# ASHRAM FILE MIGRATOR 
# ============================================================
#
# WHAT:
#     Full cloud migration workflow.
#     Copy from one cloud location to another,
#     verify everything matches, then optionally
#     delete the source.
#
# WHY:
#     Requirement 6 says:
#     "used for moving cloud storage"
#
#     This is the complete safe MOVE for cloud storage.
#     Same safety rules as local MOVE:
#       - Copy first
#       - Verify ALL files
#       - Delete source ONLY if ALL verified
#       - If even one file fails — keep source safe
#
# ============================================================

import os
from datetime import datetime
from rclone import (
    check_remote,
    copy_cloud_to_cloud,
    copy_to_cloud,
    copy_from_cloud,
    get_cloud_hashes,
    list_files
)
from comparator import (
    compare_clouds,
    print_comparison_results,
    save_comparison_report
)


# ============================================================
# HELPER — format bytes into readable size
# ============================================================

def format_size(bytes_value):
    """Convert bytes to human readable string."""

    if bytes_value is None:
        return "unknown"

    for unit in ["bytes", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024

    return f"{bytes_value:.1f} PB"


# ============================================================
# SHOW MIGRATION PLAN
# ============================================================
#
# WHY show plan before starting?
#     Cloud migration can affect thousands of files.
#     User must see exactly what will happen before
#     anything is touched.
#
# ============================================================

def show_migration_plan(
    source_remote, source_path,
    dest_remote,   dest_path,
    operation
):
    """Print the migration plan clearly."""

    print()
    print("==========================================")
    print("CLOUD MIGRATION PLAN")
    print("==========================================")
    print()
    print(f"  Operation:   {operation}")
    print()
    print(f"  SOURCE:      {source_remote}:{source_path}")
    print(f"  DESTINATION: {dest_remote}:{dest_path}")
    print()

    if operation == "MOVE":
        print("  WARNING: Source files will be DELETED")
        print("  after ALL files are verified identical.")
        print("  If any file fails — source is kept safe.")
    else:
        print("  Source files will be KEPT (COPY operation).")

    print()


# ============================================================
# DELETE FILES FROM CLOUD SOURCE
# ============================================================
#
# WHY a separate function?
#     Deletion is the most dangerous operation.
#     Keeping it separate makes it very clear
#     when and why deletion happens.
#
# WHY only called after verification?
#     Same rule as local MOVE:
#     NEVER delete source until ALL files verified.
#
# ============================================================

def delete_cloud_source(remote, path):
    """
    Delete all files from a cloud source location.
    Only called after successful verification.

    Returns:
        (True,  'success message')
        (False, 'error message')
    """

    import subprocess

    source = f"{remote}:{path}"

    print()
    print(f"  Deleting source: {source}")

    # WHY rclone delete not rclone move?
    #     We already copied and verified.
    #     Now we just remove the source files.
    #     rclone delete removes all files in a path.

    result = subprocess.run(
        ["rclone", "delete", source],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return True, f"Source deleted: {source}"
    else:
        return False, f"Delete failed: {result.stderr}"


# ============================================================
# MAIN FUNCTION — run_cloud_migration()
# ============================================================
#
# WHAT:
#     Complete cloud migration in one function call.
#
# FLOW:
#     1. Check both remotes reachable
#     2. Show migration plan
#     3. User confirms
#     4. Copy source → destination
#     5. Compare hashes
#     6. All identical? → offer to delete source
#     7. Save report
#
# ============================================================

def run_cloud_migration(
    source_remote, source_path,
    dest_remote,   dest_path,
    operation="COPY",
    reports_folder="reports"
):
    """
    Run a complete cloud migration.

    source_remote — rclone remote for source
    source_path   — folder path on source cloud
    dest_remote   — rclone remote for destination
    dest_path     — folder path on destination cloud
    operation     — "COPY" or "MOVE"
    reports_folder— where to save the CSV report

    Returns:
        True  — migration successful
        False — migration failed
    """

    print()
    print("==========================================")
    print("CLOUD MIGRATION — PROCESSED....!")
    print("==========================================")

    # ----------------------------------------------------------
    # Step 1 — Check both remotes are reachable
    # ----------------------------------------------------------

    print()
    print("  Checking remotes...")
    print()

    ok, msg = check_remote(source_remote)
    if not ok:
        print(f"  ✗ Source remote not reachable: {msg}")
        return False
    print(f"  ✓ Source:      {source_remote} — reachable")

    ok, msg = check_remote(dest_remote)
    if not ok:
        print(f"  ✗ Destination remote not reachable: {msg}")
        return False
    print(f"  ✓ Destination: {dest_remote} — reachable")

    # ----------------------------------------------------------
    # Step 2 — Show migration plan and get confirmation
    # ----------------------------------------------------------

    show_migration_plan(
        source_remote, source_path,
        dest_remote,   dest_path,
        operation
    )

    confirm = input(
        "  Type YES to start migration, anything else to cancel: "
    ).strip().lower()

    if confirm not in ("yes", "y"):
        print()
        print("  Migration cancelled. Nothing was changed.")
        return False

    # ----------------------------------------------------------
    # Step 3 — Copy source to destination
    #
    # WHY copy_cloud_to_cloud?
    #     Files go directly cloud to cloud.
    #     No downloading to your computer.
    #     Faster and uses less internet bandwidth.
    # ----------------------------------------------------------

    print()
    print("==========================================")
    print("COPYING FILES...")
    print("==========================================")
    print()

    ok, msg = copy_cloud_to_cloud(
        source_remote, source_path,
        dest_remote,   dest_path
    )

    if not ok:
        print(f"  ✗ Copy failed: {msg}")
        print("  Source files have NOT been deleted.")
        return False

    print()
    print(f"  ✓ {msg}")

    # ----------------------------------------------------------
    # Step 4 — Compare hashes to verify copy
    #
    # WHY compare after copying?
    #     rclone copy does not automatically verify.
    #     We must confirm every file arrived intact.
    #     Same principle as local verification.
    # ----------------------------------------------------------

    print()
    print("==========================================")
    print("VERIFYING — COMPARING HASHES...")
    print("==========================================")
    print()

    ok, results = compare_clouds(
        source_remote, source_path,
        dest_remote,   dest_path
    )

    if not ok:
        print(f"  ✗ Verification failed: {results}")
        print("  Source files have NOT been deleted.")
        return False

    # Print comparison results
    print_comparison_results(results)

    # ----------------------------------------------------------
    # Step 5 — Check if ALL files are identical
    # ----------------------------------------------------------

    all_identical = (
        len(results["different"]) == 0
        and len(results["only_in_a"]) == 0
        and len(results["only_in_b"]) == 0
    )

    # ----------------------------------------------------------
    # Step 6 — Delete source ONLY if MOVE + ALL identical
    #
    # WHY this strict condition?
    #     If even ONE file is different or missing,
    #     the source must be kept.
    #     The Ashram cannot lose a single file.
    # ----------------------------------------------------------

    deleted = False

    if operation == "MOVE" and all_identical:

        print()
        print("==========================================")
        print("ALL FILES VERIFIED IDENTICAL")
        print("==========================================")
        print()
        print("  All files copied and verified successfully.")
        print()
        print("  Ready to delete source files.")
        print(f"  Source: {source_remote}:{source_path}")
        print()

        # Ask one final confirmation before deleting
        # WHY ask again?
        #     Deletion is permanent.
        #     Double confirmation protects against accidents.

        final_confirm = input(
            "  Type DELETE to remove source files, "
            "anything else to keep them: "
        ).strip().upper()

        if final_confirm == "DELETE":

            ok, msg = delete_cloud_source(source_remote, source_path)

            if ok:
                print(f"  ✓ {msg}")
                deleted = True
            else:
                print(f"  ✗ {msg}")
                print("  Source files may still exist.")

        else:

            print()
            print("  Source files kept — deletion cancelled.")

    elif operation == "MOVE" and not all_identical:

        print()
        print("==========================================")
        print("  ✗ VERIFICATION FAILED")
        print("  Source files NOT deleted for safety.")
        print("==========================================")

    # ----------------------------------------------------------
    # Step 7 — Save comparison report to CSV
    # ----------------------------------------------------------

    report_path = save_comparison_report(results, reports_folder)

    print()
    print("==========================================")
    print("MIGRATION COMPLETE")
    print("==========================================")
    print()
    print(f"  Operation:   {operation}")
    print(f"  Source:      {source_remote}:{source_path}")
    print(f"  Destination: {dest_remote}:{dest_path}")
    print()
    print(f"  Files in source:      {results['total_a']}")
    print(f"  Files in destination: {results['total_b']}")
    print(f"  Identical:            {len(results['identical'])}")
    print(f"  Different:            {len(results['different'])}")
    print(f"  Source deleted:       {'YES' if deleted else 'NO'}")
    print()
    print(f"  Report saved: {report_path}")
    print()

    return all_identical