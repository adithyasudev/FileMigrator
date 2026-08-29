# ============================================================
# verifier.py — STEP 18
# ============================================================
import os
from hasher import calculate_hashes

def verify_file(source_file, destination_file):
    if not os.path.isfile(destination_file):
        return {
            "status":             "FAILED",
            "reason":             "Destination file does not exist.",
            "source_path":        source_file,
            "destination_path":   destination_file,
            "source_size":        "",
            "destination_size":   "",
            "source_md5":         "",
            "destination_md5":    "",
            "source_sha1":        "",
            "destination_sha1":   "",
            "source_sha256":      "",
            "destination_sha256": ""
        }

    source_size      = os.path.getsize(source_file)
    destination_size = os.path.getsize(destination_file)

    source_hashes      = calculate_hashes(source_file)
    destination_hashes = calculate_hashes(destination_file)

    hashes_match = (
        source_hashes["md5"]    == destination_hashes["md5"]
        and
        source_hashes["sha1"]   == destination_hashes["sha1"]
        and
        source_hashes["sha256"] == destination_hashes["sha256"]
    )

    sizes_match = (source_size == destination_size)
    status      = "VERIFIED" if (hashes_match and sizes_match) else "FAILED"

    return {
        "source_path":        source_file,
        "destination_path":   destination_file,
        "source_size":        source_size,
        "destination_size":   destination_size,
        "source_md5":         source_hashes["md5"],
        "destination_md5":    destination_hashes["md5"],
        "source_sha1":        source_hashes["sha1"],
        "destination_sha1":   destination_hashes["sha1"],
        "source_sha256":      source_hashes["sha256"],
        "destination_sha256": destination_hashes["sha256"],
        "status":             status
    }