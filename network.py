# ============================================================
# network.py
# ASHRAM FILE MIGRATOR — STEP 12
# ============================================================
#
# WHAT:
#     Checks all paths before migration starts.
#     Works for local paths AND network paths.
#
# WHY a separate file?
#     main.py controls the flow.
#     network.py handles all path checking logic.
#     Keeping them separate makes each file easier to read.
#
# ============================================================


import os
import shutil



# ============================================================
# HELPER — is this a network path?
# ============================================================
#
# WHY:
#     Network paths on Windows start with \\
#     Example: \\192.168.1.10\AshramData
#              \\NAS\Backup
#
#     We need to know this so we can warn the user
#     that network connections can drop during migration.
#
# ============================================================


def is_network_path(path):
    """
    Returns True if path is a network/UNC path.
    Example: \\\\SERVER\\share returns True
             C:\\AshramData  returns False
    """


    # os.path.normpath converts / to \ on Windows
    normalised = os.path.normpath(path)


    # All network paths on Windows start with \\
    return normalised.startswith("\\\\")



# ============================================================
# HELPER — human readable file size
# ============================================================
#
# WHY:
#     "157286400 bytes" is hard to read.
#     "150.0 MB" is clear and useful.
#
# ============================================================


def format_size(bytes_value):
    """
    Convert a number of bytes into a readable string.
    Examples:
        1024       → "1.0 KB"
        1048576    → "1.0 MB"
        1073741824 → "1.0 GB"
    """


    if bytes_value is None:
        return "unknown"


    for unit in ["bytes", "KB", "MB", "GB", "TB"]:


        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"


        bytes_value /= 1024


    return f"{bytes_value:.1f} PB"



# ============================================================
# HELPER — total size of all files to be migrated
# ============================================================
#
# WHY:
#     We need to know how much space the files need
#     at the destination BEFORE we start copying.
#     If there is not enough space, we stop immediately.
#
# ============================================================


def get_total_size(file_list):
    """
    Add up the size of every file in the list.
    Returns total in bytes.
    """


    total = 0


    for file_path in file_list:


        try:
            total += os.path.getsize(file_path)


        except Exception:
            # If we cannot read the size, skip it.
            # The copy step will catch this file later.
            pass


    return total



# ============================================================
# MAIN FUNCTION — validate_paths()
# ============================================================
#
# WHAT:
#     This is the only function main.py calls.
#     It runs all checks and prints results clearly.
#
# PARAMETERS:
#     source_roots  — list of folders/files user selected
#     destination   — destination folder path
#     source_files  — flat list of every file to migrate
#                     (used to calculate required space)
#
# RETURNS:
#     True  — everything ok, safe to start migration
#     False — something is wrong, stop migration
#
# ============================================================


def validate_paths(source_roots, destination, source_files):


    print()
    print("==========================================")
    print("CHECKING PATHS BEFORE MIGRATION")
    print("==========================================")
    print()


    # We collect all problems and show them together
    # WHY: better to show ALL problems at once than
    # stop at the first one and make the user run again
    # and again to find each problem one by one.


    all_ok = True


    # ----------------------------------------------------------
    # CHECK 1 — Does each source path exist and can we read it?
    # ----------------------------------------------------------


    print("  SOURCE PATHS:")
    print()


    for path in source_roots:


        # Tell user what type of path this is
        if is_network_path(path):
            label = "[NETWORK]"
        else:
            label = "[LOCAL]  "


        print(f"  {label} {path}")


        # Does it exist?
        if not os.path.exists(path):
            print(f"    ✗ NOT FOUND")
            print(f"      This path does not exist.")
            print(f"      Check the spelling and try again.")
            all_ok = False
            print()
            continue  # no point checking further for this path


        print(f"    ✓ Exists")


        # Can we read it?
        # WHY: a folder can exist but still be locked
        # by Windows security or another program.
        try:


            if os.path.isdir(path):
                os.listdir(path)  # try to list the folder
                print(f"    ✓ Readable")


            elif os.path.isfile(path):
                with open(path, "rb") as f:
                    f.read(1)    # try to read one byte
                print(f"    ✓ Readable")


        except PermissionError:
            print(f"    ✗ PERMISSION DENIED")
            print(f"      Windows is blocking access to this path.")
            print(f"      Try right-clicking the terminal and")
            print(f"      choosing 'Run as administrator'.")
            all_ok = False


        except Exception as error:
            print(f"    ✗ ERROR: {error}")
            all_ok = False


        print()


    # ----------------------------------------------------------
    # CHECK 2 — Does destination exist and can we write to it?
    # ----------------------------------------------------------


    print("  DESTINATION:")
    print()


    if is_network_path(destination):
        label = "[NETWORK]"
    else:
        label = "[LOCAL]  "


    print(f"  {label} {destination}")


    if not os.path.exists(destination):
        print(f"    ✗ NOT FOUND")
        print(f"      This destination folder does not exist.")
        print(f"      Create it first, then run the program again.")
        print(f"      Command to create it:")
        print(f"      mkdir \"{destination}\"")
        all_ok = False


    else:


        print(f"    ✓ Exists")


        # Test write permission by creating a tiny temp file
        # WHY a real file test instead of os.access()?
        #     os.access() is not always accurate on Windows.
        #     Actually writing a file is the only reliable test.


        test_path = os.path.join(destination, "_write_test.tmp")


        try:


            with open(test_path, "w") as f:
                f.write("test")


            os.remove(test_path)  # clean up immediately


            print(f"    ✓ Writable")


        except PermissionError:
            print(f"    ✗ PERMISSION DENIED")
            print(f"      Cannot write to this destination.")
            print(f"      Try running as administrator.")
            all_ok = False


        except Exception as error:
            print(f"    ✗ ERROR: {error}")
            all_ok = False


    print()


    # ----------------------------------------------------------
    # CHECK 3 — Is there enough free space at destination?
    #
    # WHY check space before copying?
    #     If the disk fills up halfway through, some files
    #     will be copied and some will not.
    #     The migration will be incomplete and confusing.
    #     Better to stop before starting.
    #
    # We add a 10% safety buffer on top of required space.
    # WHY 10%?
    #     Reports, logs, and temp files take some space.
    #     Also good practice never to fill a disk completely.
    # ----------------------------------------------------------


    print("  DISK SPACE:")
    print()


    total_needed  = get_total_size(source_files)
    needed_plus_buffer = int(total_needed * 1.1)  # add 10%


    try:
        free = shutil.disk_usage(destination).free
    except Exception:
        free = None


    print(f"    Space needed (files):     {format_size(total_needed)}")
    print(f"    Space needed (+ 10% buf): {format_size(needed_plus_buffer)}")
    print(f"    Free space at destination:{format_size(free)}")
    print()


    if free is None:
        print(f"    ? Cannot check free space — continuing anyway.")
        print(f"      Watch for 'disk full' errors during copy.")


    elif free >= needed_plus_buffer:
        print(f"    ✓ Enough free space")


    else:
        print(f"    ✗ NOT ENOUGH SPACE")
        print(f"      Need:      {format_size(needed_plus_buffer)}")
        print(f"      Available: {format_size(free)}")
        print(f"      Free up space on the destination drive first.")
        all_ok = False


    print()


    # ----------------------------------------------------------
    # Network warning
    #
    # WHY warn even when everything passes?
    #     A network path that is reachable NOW can drop
    #     during migration. The user should know this.
    # ----------------------------------------------------------


    any_network = (
        any(is_network_path(p) for p in source_roots)
        or is_network_path(destination)
    )


    if any_network:
        print("  WARNING — NETWORK PATH DETECTED:")
        print("    Network connections can drop during migration.")
        print("    If disconnected, the copy stops safely.")
        print("    Original files are never deleted until")
        print("    ALL files are verified.")
        print("    Make sure your network is stable before starting.")
        print()


    # ----------------------------------------------------------
    # Final verdict
    # ----------------------------------------------------------


    print("==========================================")


    if all_ok:
        print("  ✓ All checks passed. Ready to migrate.")
    else:
        print("  ✗ Problems found. Fix them and run again.")


    print("==========================================")
    print()


    return all_ok