# ============================================================
# copier.py — STEP 18
# ============================================================
import os
import shutil

def find_root_for_file(file_path, source_roots):
    for root in source_roots:
        if os.path.isfile(root):
            if file_path == root:
                return root
        elif file_path.startswith(root):
            return root
    return None

def copy_files(files, source_roots, destination_root):
    copied_count = 0
    failed_count = 0

    for number, source_file in enumerate(files, start=1):
        try:
            matched_root = find_root_for_file(source_file, source_roots)
            if matched_root is None:
                matched_root = os.path.dirname(source_file)

            base             = os.path.dirname(matched_root)
            relative_path    = os.path.relpath(source_file, base)
            destination_file = os.path.join(destination_root, relative_path)

            os.makedirs(os.path.dirname(destination_file), exist_ok=True)

            print(f"  [{number}/{len(files)}] Copying: {source_file}")
            shutil.copy2(source_file, destination_file)
            copied_count += 1

        except Exception as error:
            failed_count += 1
            print(f"  ERROR copying {source_file}: {error}")

    print()
    print(f"  Copy completed. Successful: {copied_count}, Failed: {failed_count}")
    return copied_count, failed_count