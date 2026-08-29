# ============================================================
# reporter.py — STEP 18
# ============================================================
import os
import csv
from datetime import datetime
from hasher import calculate_hashes

def create_inventory_report(files, output_file):
    fieldnames = [
        "File Name", "Full Source Path", "File Size (Bytes)",
        "MD5", "SHA-1", "SHA-256", "Scan Time", "Status"
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for number, file_path in enumerate(files, start=1):
            print(f"  Scanning [{number}/{len(files)}]: {file_path}")
            try:
                hashes    = calculate_hashes(file_path)
                scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow({
                    "File Name":         os.path.basename(file_path),
                    "Full Source Path":  file_path,
                    "File Size (Bytes)": os.path.getsize(file_path),
                    "MD5":               hashes["md5"],
                    "SHA-1":             hashes["sha1"],
                    "SHA-256":           hashes["sha256"],
                    "Scan Time":         scan_time,
                    "Status":            "OK"
                })
            except Exception as error:
                writer.writerow({
                    "File Name":         os.path.basename(file_path),
                    "Full Source Path":  file_path,
                    "File Size (Bytes)": "",
                    "MD5":  "", "SHA-1": "", "SHA-256": "",
                    "Scan Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Status": f"ERROR: {error}"
                })
                print(f"    ERROR: {error}")

def create_verification_report(verification_results, deletion_results, report_path):
    fieldnames = [
        "Source Path", "Destination Path",
        "Source Size (Bytes)", "Destination Size (Bytes)",
        "Source MD5", "Destination MD5",
        "Source SHA-1", "Destination SHA-1",
        "Source SHA-256", "Destination SHA-256",
        "Verification Status", "Deletion Status"
    ]

    with open(report_path, "w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=fieldnames)
        writer.writeheader()

        for result in verification_results:
            deletion_status = "NOT DELETED"
            for deletion in deletion_results:
                if deletion["source_path"] == result["source_path"]:
                    deletion_status = deletion["status"]
                    break

            writer.writerow({
                "Source Path":              result.get("source_path", ""),
                "Destination Path":         result.get("destination_path", ""),
                "Source Size (Bytes)":      result.get("source_size", ""),
                "Destination Size (Bytes)": result.get("destination_size", ""),
                "Source MD5":               result.get("source_md5", ""),
                "Destination MD5":          result.get("destination_md5", ""),
                "Source SHA-1":             result.get("source_sha1", ""),
                "Destination SHA-1":        result.get("destination_sha1", ""),
                "Source SHA-256":           result.get("source_sha256", ""),
                "Destination SHA-256":      result.get("destination_sha256", ""),
                "Verification Status":      result.get("status", ""),
                "Deletion Status":          deletion_status
            })

    return report_path

def _simple_failure_reason(raw_reason):
    """
    Convert technical status/error text into wording
    suitable for a nontechnical user.
    """

    text = str(raw_reason or "").strip()
    upper_text = text.upper()

    if "HASH MISMATCH" in upper_text:
        return "The copied file did not match the original file."

    if (
        "PERMISSION" in upper_text
        or "ACCESS IS DENIED" in upper_text
        or "WINERROR 5" in upper_text
    ):
        return "Windows permission was denied for this file."

    if (
        "BEING USED BY ANOTHER PROCESS" in upper_text
        or "WINERROR 32" in upper_text
    ):
        return "The file was open or being used by another program."

    if (
        "NETWORK" in upper_text
        or "CONNECTION" in upper_text
        or "UNREACHABLE" in upper_text
    ):
        return "The network connection was interrupted."

    if (
        "NOT FOUND" in upper_text
        or "MISSING" in upper_text
        or "NO SUCH FILE" in upper_text
    ):
        return "The file or destination could not be found."

    if (
        "COPY FAILED" in upper_text
        or "COPY_FAILED" in upper_text
    ):
        return "The file could not be copied."

    if (
        "DELETE" in upper_text
        or "DELETION" in upper_text
    ):
        return "The source file could not be removed after verification."

    return "The file could not be completed successfully."


def create_user_report(
    report_path,
    operation,
    migration_type,
    total_files,
    successful_files,
    failed_files,
    failed_items=None
):
    """
    Create a simple CSV report for nontechnical users.

    The first row is the migration summary.
    Additional rows are included only for failed files.
    """

    fieldnames = [
        "Record Type",
        "Migration Date/Time",
        "Operation",
        "Migration Type",
        "Overall Result",
        "Total Files",
        "Successful",
        "Failed",
        "Failed File Name",
        "Simple Failure Reason"
    ]

    failed_items = failed_items or []

    overall_result = (
        "SUCCESS"
        if int(failed_files) == 0
        else "FAILED"
    )

    report_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with open(
        report_path,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as report_file:

        writer = csv.DictWriter(
            report_file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerow({
            "Record Type": "MIGRATION SUMMARY",
            "Migration Date/Time": report_time,
            "Operation": operation,
            "Migration Type": migration_type,
            "Overall Result": overall_result,
            "Total Files": int(total_files),
            "Successful": int(successful_files),
            "Failed": int(failed_files),
            "Failed File Name": "",
            "Simple Failure Reason": ""
        })

        for failed_item in failed_items:
            source_path = failed_item.get(
                "source_path",
                ""
            )

            file_name = (
                failed_item.get("file_name")
                or os.path.basename(source_path)
                or source_path
                or "Unknown file"
            )

            raw_reason = (
                failed_item.get("reason")
                or failed_item.get("status")
                or ""
            )

            writer.writerow({
                "Record Type": "FAILED FILE",
                "Migration Date/Time": "",
                "Operation": "",
                "Migration Type": "",
                "Overall Result": "",
                "Total Files": "",
                "Successful": "",
                "Failed": "",
                "Failed File Name": file_name,
                "Simple Failure Reason": (
                    _simple_failure_reason(
                        raw_reason
                    )
                )
            })

    return report_path