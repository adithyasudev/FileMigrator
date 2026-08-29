# ============================================================
# selector.py
# ASHRAM FILE MIGRATOR — STEP 10
# ============================================================
#
# WHAT:
#     This module handles all user input for SELECTING
#     what files and folders are to be migrated.
#
# WHY:
#     Previously main.py only accepted one folder path typed
#     manually.
#
#     The Ashram requirement says:
#     "copy a file, folder, a list of folders"
#
#     So we need to support:
#
#     1. A single file       (e.g.  C:\AshramData\baba.jpg)
#     2. A single folder     (e.g.  C:\AshramData\Photos)
#     3. Multiple folders    (e.g.  Photos + Documents + Videos)
#
#     AND the user should be able to:
#     A. Type the path manually in the terminal
#     B. Use a Browse window (tkinter file/folder dialog)
#
# HOW IT WORKS:
#     This file exports one main function:
#
#         get_sources()
#
#     It returns a flat list of every file path that
#     should be migrated.
#
#     main.py calls get_sources() and receives the list.
#     main.py does not need to know HOW the selection happened.
#
# ============================================================



import os
import tkinter
import tkinter.filedialog




# ============================================================
# INTERNAL HELPER — find every file inside a folder
# ============================================================
#
# WHY:
#     When the user selects a folder, we need to expand it
#     into a flat list of all files inside it (recursively).
#
#     This is the same logic that was in main.py previously.
#
# ============================================================



def _find_files_in_folder(folder_path):
    """
    Walk a folder recursively and return a list of all
    file paths found inside it.
    """


    files = []


    for root, directories, filenames in os.walk(folder_path):


        for filename in filenames:


            full_path = os.path.join(root, filename)


            files.append(full_path)
    return files




# ============================================================
# INTERNAL HELPER — expand sources into a flat file list
# ============================================================
#
# WHY:
#     The user might give us a mix of files and folders.
#     We need to convert everything into individual file paths.
#
#     If the source is a FILE:   add it directly.
#     If the source is a FOLDER: expand it recursively.
#
# ============================================================



def _expand_sources(source_paths):
    """
    Accept a list of file and/or folder paths.

    Return a flat list of unique individual file paths.

    If the same file is included more than once — for example,
    selected individually and also contained inside a selected
    folder — it is included only once.
    """

    all_files = []

    # Used only for fast duplicate checking.
    # normcase() makes Windows path comparison case-insensitive.
    seen_files = set()

    for path in source_paths:

        if os.path.isfile(path):

            normalized_file = os.path.normcase(
                os.path.abspath(path)
            )

            if normalized_file not in seen_files:
                seen_files.add(normalized_file)
                all_files.append(path)

        elif os.path.isdir(path):

            files_in_folder = _find_files_in_folder(path)

            for file_path in files_in_folder:

                normalized_file = os.path.normcase(
                    os.path.abspath(file_path)
                )

                if normalized_file not in seen_files:
                    seen_files.add(normalized_file)
                    all_files.append(file_path)

        else:

            # Keep the existing terminal-mode warning behavior.
            print()
            print(f"  ✗ PATH NOT FOUND: {path}")
            print("    This folder or file does not exist.")
            print("    Check the spelling and try again.")
            print()

    return all_files




# ============================================================
# BROWSE — open a tkinter dialog window
# ============================================================
#
# WHY:
#     Some users prefer clicking to find files/folders
#     rather than typing long paths.
#
#     tkinter is built into Python — no installation needed.
#
# ============================================================



def _browse_for_sources():
    """
    Open a tkinter dialog and let the user choose files
    and/or folders using Browse windows.



    Returns a list of selected paths (files and/or folders).
    """



    # --------------------------------------------------------
    # We must create and immediately hide a root tkinter window.
    #
    # WHY:
    #     tkinter requires a root window to exist before
    #     any dialog can be opened.
    #     We don't want a blank window appearing on screen,
    #     so we hide it immediately with withdraw().
    # --------------------------------------------------------



    root = tkinter.Tk()
    root.withdraw()



    # --------------------------------------------------------
    # Bring the dialog to the front on Windows.
    #
    # WHY:
    #     Without this, the dialog can appear behind other
    #     windows and confuse the user.
    # --------------------------------------------------------



    root.attributes("-topmost", True)



    selected_paths = []



    print()
    print("  Browse mode — a dialog window will open.")
    print("  You can add files and folders one at a time.")
    print("  Type 'done' when finished adding sources.")
    print()



    while True:



        print("  What do you want to add next?")
        print()
        print("  1. Browse for a FILE")
        print("  2. Browse for a FOLDER")
        print("  3. Done — start migration")
        print()



        browse_choice = input("  Enter choice (1, 2, or 3): ").strip()



        if browse_choice == "1":



            # Open a file picker dialog.



            file_path = tkinter.filedialog.askopenfilename(
                title="Select a file to migrate",
                parent=root
            )



            if file_path:



                # tkinter returns forward slashes on Windows.
                # Convert to the OS native path format.



                file_path = os.path.normpath(file_path)



                selected_paths.append(file_path)



                print(f"  Added file: {file_path}")



            else:



                print("  No file selected.")



        elif browse_choice == "2":



            # Open a folder picker dialog.



            folder_path = tkinter.filedialog.askdirectory(
                title="Select a folder to migrate",
                parent=root
            )



            if folder_path:



                folder_path = os.path.normpath(folder_path)



                selected_paths.append(folder_path)



                print(f"  Added folder: {folder_path}")



            else:



                print("  No folder selected.")



        elif browse_choice == "3":



            # User is done selecting.



            break



        else:



            print("  Invalid choice. Please enter 1, 2, or 3.")



        print()



    # Destroy the hidden root window now that we are done.



    root.destroy()



    return selected_paths




# ============================================================
# MANUAL — let the user type paths one by one
# ============================================================
#
# WHY:
#     Some users prefer typing — especially over remote
#     desktop or terminal-only environments where a Browse
#     window may not work properly.
#
# ============================================================



def _type_sources_manually():
    """
    Let the user type file and folder paths one by one.
    Returns a list of entered paths.
    """



    entered_paths = []



    print()
    print("  Manual mode.")
    print("  Type one file or folder path per line.")
    print("  Press ENTER with nothing typed when done.")
    print()



    while True:



        path = input("  Path (or ENTER to finish): ").strip().strip('"')



        if path == "":



            # Empty input — the user is finished.



            break



        entered_paths.append(path)



        print(f"  Added: {path}")
        print()



    return entered_paths




# ============================================================
# get_destination() — ask for the destination
# ============================================================
#
# WHY:
#     We also need to ask where files should be copied TO.
#     This function handles both typed input and Browse.
#
# ============================================================



def get_destination(input_method):
    """
    Ask the user for the destination folder.



    input_method: "type" or "browse"



    Returns the destination folder path as a string.
    """



    print()
    print("==========================================")
    print("SELECT DESTINATION FOLDER")
    print("==========================================")
    print()



    if input_method == "browse":



        print("  Next: select your DESTINATION folder.")
        print("  This is WHERE the files will be copied TO.")
        print()
        print("  Press ENTER when ready — a Browse window will open.")
        input("  >>> ")



        while True:




            # --------------------------------------------------------
            # WHY a while loop here?
            #     If the user accidentally closes the Browse window,
            #     we ask again instead of crashing or exiting.
            #     They get unlimited chances to select a destination.
            # --------------------------------------------------------



            



            root = tkinter.Tk()
            root.withdraw()



            # Bring dialog to front on Windows
            root.attributes("-topmost", True)



            folder_path = tkinter.filedialog.askdirectory(
                title="Select destination folder",
                parent=root
            )



            root.destroy()



            if folder_path:
                # tkinter returns forward slashes — convert to Windows path



                folder_path = os.path.normpath(folder_path)
                print()



                print(f"  Destination: {folder_path}")



                return folder_path



            else:



                # --------------------------------------------------------
                # User cancelled or closed the window.
                # WHY ask again instead of exiting?
                #     It is very easy to accidentally close a Browse
                #     window. Exiting the whole program would be
                #     very frustrating for the Ashram user.
                # --------------------------------------------------------



                print()
                print("  No folder selected. Did you close the window?")
                print()
                print("  What do you want to do?")
                print()
                print("  1. Try again — open Browse window again")
                print("  2. Type the path manually instead")
                print("  3. Cancel — exit the program")
                print()





                retry = input("  Enter choice (1, 2, or 3): ").strip()
                if retry == "1":
                    print()
                    print("  Opening Browse window again...")
                    print()
                    continue   # loop again — open Browse window



                elif retry == "2":



                    # Fall through to manual typing below
                    break



                else:



                    print()
                    print("  Migration cancelled.")
                    return None




        # If we reach here, user chose to type manually.
        
    # Manual typing (either chosen originally or as fallback)
    print("  Type the full destination folder path.")
    print("  Example:  D:\\AshramBackup")
    print()



    while True:



        path = input("  Destination path: ").strip().strip('"')



        if path:
            return path



        else:
            print("  Path cannot be empty. Please try again.")
            print()




# ============================================================
# get_sources() — THE MAIN PUBLIC FUNCTION
# ============================================================
#
# WHAT:
#     This is the only function that main.py needs to call.
#
# WHY:
#     It hides all the complexity of selection mode,
#     browse dialogs, manual typing, and path expansion.
#
#     main.py just calls:
#
#         source_files, source_roots, input_method = get_sources()
#
#     And receives:
#         source_files  — flat list of every file to migrate
#         source_roots  — list of the original selected paths
#                         (used later for relative path calculation)
#         input_method  — "type" or "browse" (for destination)
#
# ============================================================



def get_sources():
    """
    Ask the user HOW they want to select files/folders,
    then collect the selection, and return a flat list
    of all file paths to migrate.



    Returns:
        source_files  (list of file path strings)
        source_roots  (list of selected root paths)
        input_method  ("type" or "browse")
    """



    print()
    print("==========================================")
    print("SELECT SOURCE FILES / FOLDERS")
    print("==========================================")
    print()
    print("How do you want to select what to migrate?")
    print()
    print("  1. Type path(s) manually")
    print("  2. Browse using a window (click to select)")
    print()



    while True:



        method_choice = input("  Enter choice (1 or 2): ").strip()



        if method_choice == "1":



            input_method = "type"
            break



        elif method_choice == "2":



            input_method = "browse"
            break



        else:



            print("  Invalid choice. Please enter 1 or 2.")



    # --------------------------------------------------------
    # Collect the raw paths from the user.
    # --------------------------------------------------------



    if input_method == "type":



        raw_paths = _type_sources_manually()



    else:



        raw_paths = _browse_for_sources()



    # --------------------------------------------------------
    # Validate that at least one path was selected.
    # --------------------------------------------------------



    if not raw_paths:



        print()
        print("  No sources selected. Exiting.")



        return [], [], input_method



    # --------------------------------------------------------
    # Show the user what they selected.
    # --------------------------------------------------------



    print()
    print("  Sources selected:")



    for path in raw_paths:



        if os.path.isfile(path):



            print(f"    [FILE]   {path}")



        elif os.path.isdir(path):


          print(f"    [FOLDER] {path}")



        else:



            print(f"    [NOT FOUND] {path}")



    # --------------------------------------------------------
    # Expand folders into individual file paths.
    #
    # WHY:
    #     The rest of the program (copy, verify, report)
    #     works with individual files — not folder paths.
    # --------------------------------------------------------



    print()
    print("  Expanding folders into file lists...")



    source_files = _expand_sources(raw_paths)



    print(f"  Total files to migrate: {len(source_files)}")



    # --------------------------------------------------------
    # Return both the file list AND the original root paths.
    #
    # WHY we return source_roots:
    #     When copying, we need to know the "root" of each
    #     selected path so we can calculate relative paths
    #     and preserve the folder structure at the destination.
    #
    #     For example:
    #         selected: C:\AshramData\Photos
    #         file:     C:\AshramData\Photos\baba.jpg
    #         relative: Photos\baba.jpg
    #         dest:     D:\AshramBackup\Photos\baba.jpg
    #
    # --------------------------------------------------------



    return source_files, raw_paths, input_method