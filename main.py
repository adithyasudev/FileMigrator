import os
from datetime import datetime

from hasher   import calculate_hashes
from scanner  import find_files
from copier   import copy_files, find_root_for_file
from verifier import verify_file
from reporter import create_inventory_report, create_verification_report
from selector import get_sources, get_destination
from network  import validate_paths




# ============================================================
# MAIN PROGRAM
# ============================================================


def main():


    print()
    print("==========================================")
    print("   ASHRAM FILE MIGRATOR")
    print("==========================================")


    # ----------------------------------------------------------
    # STEP 9A — Ask COPY or MOVE
    # ----------------------------------------------------------


    while True:


        print()
        print("Choose operation:")
        print()
        print("  1. COPY  (original files are kept)")
        print("  2. MOVE  (original files deleted ONLY after")
        print("            all files are verified)")
        print()


        operation_choice = input(
            "  Enter your choice (1 or 2): "
        ).strip()


        if operation_choice == "1":
            operation = "COPY"
            break


        elif operation_choice == "2":
            operation = "MOVE"
            break


        else:
            print()
            print("  Invalid choice. Please enter 1 or 2.")


    print()
    print(f"  Operation selected: {operation}")


    # ----------------------------------------------------------
    # STEP 10 — Get source files using selector
    #
    # WHY:
    #     Previously this was just:
    #         folder_path = input("Enter folder path: ")
    #
    #     Now selector.py handles all selection complexity:
    #     - single file, folder, or multiple folders
    #     - typed manually OR chosen with Browse window
    #
    # get_sources() returns:
    #     source_files  — flat list of every file to migrate
    #     source_roots  — the original selected paths
    #                     (needed for relative path calculation)
    #     input_method  — "type" or "browse"
    # ----------------------------------------------------------


    source_files, source_roots, input_method = get_sources()


    if not source_files:


        print()
        print("  No files to migrate.")
        print("  Possible reasons:")
        print("    - The path you entered does not exist")
        print("    - The folder you selected is empty")
        print("    - The path was skipped due to an error above")
        print()
        print("  Please run  again with a correct path.")
        return


    # ----------------------------------------------------------
    # STEP 10 — Get destination using selector
    # ----------------------------------------------------------


    destination_path = get_destination(input_method)


    if not destination_path:


        print()
        print("  No destination selected. Exiting.")
        return


    # ----------------------------------------------------------
    # Show the migration plan to the user before starting
    #
    # WHY:
    #     This gives the user a chance to confirm before
    #     any files are copied or deleted.
    # ----------------------------------------------------------


    print()
    print("==========================================")
    print("MIGRATION PLAN")
    print("==========================================")
    print()
    print(f"  Operation:   {operation}")
    print(f"  Files found: {len(source_files)}")
    print(f"  Destination: {destination_path}")
    print()
    print("  Sources selected:")


    for root in source_roots:
        kind = "[FILE]  " if os.path.isfile(root) else "[FOLDER]"
        print(f"    {kind} {root}")


    print()


    confirm = input(
        "  Confirm — start migration? (yes / no): "
    ).strip().lower()


    if confirm not in ("yes", "y"):


        print()
        print("  Migration cancelled.")
        return
    # ----------------------------------------------------------
    # STEP 12 — Validate all paths before starting
    #
    # WHY here — after confirm but before any file operation?
    #     User has confirmed the plan.
    #     Now we check paths are reachable.
    #     If network is down we stop immediately with a
    #     clear message — before touching any files.
    # ----------------------------------------------------------


    paths_ok = validate_paths(source_roots, destination_path, source_files)


    if not paths_ok:
        print("  Migration stopped. Fix the path issues and try again.")
        return





    # ----------------------------------------------------------
    # Create the reports folder
    # ----------------------------------------------------------


    reports_folder = os.path.join(os.getcwd(), "reports")
    os.makedirs(reports_folder, exist_ok=True)


    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


    # ----------------------------------------------------------
    # STEP 4 — Create inventory report (source hashes)
    # ----------------------------------------------------------


    inventory_file = os.path.join(
        reports_folder,
        f"inventory_{timestamp}.csv"
    )


    print()
    print("==========================================")
    print("SCANNING & CREATING INVENTORY...")
    print("==========================================")
    print()


    create_inventory_report(source_files, inventory_file)


    print()
    print(f"  Inventory saved: {inventory_file}")


    # ----------------------------------------------------------
    # STEP 5 / 9B — Copy files
    # ----------------------------------------------------------


    print()
    print("==========================================")


    if operation == "COPY":
        print("COPYING FILES...")
    else:
        print("COPYING FILES (MOVE — delete only after verify)...")


    print("==========================================")
    print()


    copied_count, failed_count = copy_files(
        source_files,
        source_roots,
        destination_path
    )


    # ----------------------------------------------------------
    # STEP 6 / 9C — Verify all copied files
    # ----------------------------------------------------------


    print()
    print("==========================================")
    print("VERIFYING COPIED FILES...")
    print("==========================================")
    print()


    verification_results = []


    for number, source_file in enumerate(source_files, start=1):


        # -------------------------------------------------------
        # Reconstruct the destination path using the same logic
        # as copy_files() so we verify the correct file.
        # -------------------------------------------------------


        matched_root = find_root_for_file(source_file, source_roots)


        if matched_root is None:
            matched_root = os.path.dirname(source_file)


        # Use parent of matched_root to preserve folder names.
        base = os.path.dirname(matched_root)
        relative_path = os.path.relpath(source_file, base)


        destination_file = os.path.join(
            destination_path,
            relative_path
        )


        print(
            f"  [{number}/{len(source_files)}] "
            f"Verifying: {source_file}"
        )


        try:


            result = verify_file(source_file, destination_file)
            verification_results.append(result)


            if result["status"] == "VERIFIED":
                print("    ✓ VERIFIED")
            else:
                print("    ✗ FAILED")
                if "reason" in result:
                    print(f"    Reason: {result['reason']}")


        except Exception as error:
            print(f"    ERROR: {error}")


    # ----------------------------------------------------------
    # STEP 9D — Count results
    # ----------------------------------------------------------


    verified_count          = sum(
        1 for r in verification_results if r["status"] == "VERIFIED"
    )
    verification_failed_count = sum(
        1 for r in verification_results if r["status"] != "VERIFIED"
    )


    print()
    print("==========================================")
    print("MIGRATION SUMMARY")
    print("==========================================")
    print()
    print(f"  Files selected:          {len(source_files)}")
    print(f"  Files copied:            {copied_count}")
    print(f"  Files failed (copy):     {failed_count}")
    print(f"  Files verified:          {verified_count}")
    print(f"  Files failed (verify):   {verification_failed_count}")


    # ----------------------------------------------------------
    # STEP 9D — Safety check
    # ----------------------------------------------------------


    print()
    print("==========================================")
    print("VERIFICATION SAFETY CHECK")
    print("==========================================")
    print()


    all_files_verified = (
        copied_count          == len(source_files)
        and failed_count      == 0
        and verified_count    == len(source_files)
        and verification_failed_count == 0
    )


    if all_files_verified:
        print("  ✓ All files copied and verified successfully.")
        print("  Every destination file matches its source.")
    else:
        print("  ✗ Verification FAILED.")
        print("  Not all files passed. Original files will NOT be deleted.")


    # ----------------------------------------------------------
    # STEP 9E — Delete originals ONLY if MOVE + ALL VERIFIED
    # ----------------------------------------------------------


    deleted_count      = 0
    delete_failed_count = 0
    deletion_results   = []


    if operation == "MOVE" and all_files_verified:


        print()
        print("==========================================")
        print("DELETING ORIGINAL FILES (MOVE confirmed)")
        print("==========================================")
        print()


        for number, source_file in enumerate(source_files, start=1):


            try:


                print(
                    f"  [{number}/{len(source_files)}] "
                    f"Deleting: {source_file}"
                )


                os.remove(source_file)


                deleted_count += 1


                deletion_results.append({
                    "source_path": source_file,
                    "status": "DELETED"
                })


            except Exception as error:


                delete_failed_count += 1


                deletion_results.append({
                    "source_path": source_file,
                    "status": f"FAILED: {error}"
                })


                print(f"    ERROR deleting: {error}")


        print()
        print(f"  Deleted successfully: {deleted_count}")
        print(f"  Failed to delete:     {delete_failed_count}")


    else:


        print()


        if operation == "COPY":
            print("  Operation was COPY — originals retained.")
        else:
            print("  MOVE cancelled — originals retained for safety.")


    # ----------------------------------------------------------
    # STEP 7 — Write verification report CSV
    # ----------------------------------------------------------


    report_path = os.path.join(
        reports_folder,
        f"verification_report_{timestamp}.csv"
    )


    create_verification_report(
        verification_results,
        deletion_results,
        report_path
    )


    print()
    print("==========================================")
    print("REPORTS CREATED")
    print("==========================================")
    print()
    print(f"  Inventory:            {inventory_file}")
    print(f"  Verification report:  {report_path}")

    # ----------------------------------------------------------
    # Show disk space remaining after migration
    #
    # WHY:
    #     After copying large files the user needs to know
    #     how much space is left at the destination.
    #     This helps them plan future migrations.
    # ----------------------------------------------------------

    print()
    print("==========================================")
    print("DISK SPACE AFTER MIGRATION")
    print("==========================================")
    print()

    try:
        import shutil
        dest_usage  = shutil.disk_usage(destination_path)
        source_usage = shutil.disk_usage(os.path.dirname(
            source_roots[0]
        ))

        def fmt(b):
            for unit in ["bytes","KB","MB","GB","TB"]:
                if b < 1024:
                    return f"{b:.1f} {unit}"
                b /= 1024

        print(f"  Destination drive:")
        print(f"    Total:     {fmt(dest_usage.total)}")
        print(f"    Used:      {fmt(dest_usage.used)}")
        print(f"    Free:      {fmt(dest_usage.free)}")
        print()
        print(f"  Source drive:")
        print(f"    Total:     {fmt(source_usage.total)}")
        print(f"    Used:      {fmt(source_usage.used)}")
        print(f"    Free:      {fmt(source_usage.free)}")

    except Exception as error:
        print(f"  Could not read disk space: {error}")

    print()
    print("==========================================")
    print("  MIGRATION COMPLETE")
    print("==========================================")
    print()



# ============================================================
# Entry point
# ============================================================


if __name__ == "__main__":


    main() 