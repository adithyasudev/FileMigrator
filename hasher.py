# ============================================================
# hasher.py — STEP 18
# ============================================================
import hashlib

def calculate_hashes(file_path):
    md5    = hashlib.md5()
    sha1   = hashlib.sha1()
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)

    return {
        "md5":    md5.hexdigest(),
        "sha1":   sha1.hexdigest(),
        "sha256": sha256.hexdigest()
    }