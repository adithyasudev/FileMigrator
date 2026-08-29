# ============================================================
# scanner.py — STEP 18
# ============================================================
import os

def find_files(folder_path):
    files = []
    for root, directories, filenames in os.walk(folder_path):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            files.append(full_path)
    return files