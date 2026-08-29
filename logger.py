# ============================================================
# logger.py
# ASHRAM FILE MIGRATOR — STEP 21
# ============================================================
#
# WHAT:
#     Creates and writes a permanent log file for every
#     migration run.
#
# WHY:
#     The terminal output disappears when the window closes.
#     The CSV report shows results but not the full history.
#     A log file is permanent — it can be opened any time
#     to see exactly what happened during a migration.
#
# WHY separate from reporter.py?
#     reporter.py creates structured CSV files (data).
#     logger.py creates human-readable text logs (history).
#     They serve different purposes.
#
# HOW:
#     Every migration creates one log file named with the
#     timestamp. The logger writes entries throughout the
#     migration — start, each file, errors, completion.
#
# ============================================================

import os
from datetime import datetime


# ============================================================
# MIGRATION LOGGER CLASS
# ============================================================

class MigrationLogger:
    """
    Writes a human-readable log file for one migration run.

    Usage:
        logger = MigrationLogger(logs_folder)
        logger.start("COPY", sources, destination)
        logger.file_copied("Photos/baba.jpg")
        logger.file_verified("Photos/baba.jpg", "VERIFIED")
        logger.file_error("Photos/maa.jpg", "Permission denied")
        logger.complete(copied=57, verified=57, failed=0)
    """

    def cloud_auth_failed(self, service, error):
        self._write(
        "ERROR",
        f"[CLOUD AUTH] {service} → AUTHENTICATION FAILED — {error}"
    )

    def __init__(self, logs_folder="logs"):
        """
        Create a new log file for this migration run.

        WHY timestamp in filename?
            Every migration gets a unique log file.
            Old logs are never overwritten.
            The Ashram can keep a full history of all migrations.
        """

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

        self.start_time = datetime.now()
        self.end_time = None
        self._closed = False

        self.log_path = None
        self._file = None

        try:
            os.makedirs(
                logs_folder,
                exist_ok=True
            )

            self.log_path = os.path.join(
                logs_folder,
                f"migration_{timestamp}.log"
            )

            self._file = open(
                self.log_path,
                "w",
                encoding="utf-8"
            )

        except Exception:
            # Logging failure must NEVER crash the migration.
            # The migration may continue without a permanent log.
            self.log_path = None
            self._file = None

        self._write_header()

    def info(self, message):
        """
        Write a general informational message.
        """

        self._write(
            message,
            "INFO"
        )

    # --------------------------------------------------------
    # INTERNAL — write the log file header
    # --------------------------------------------------------

    def _write_header(self):
        """Write basic application information to the log."""

        self._write(
        "Ashram File Migrator",
        "SYSTEM"
        )

        self._write(
        "Narayanashrama Tapovanam",
        "SYSTEM"
        )

    # --------------------------------------------------------
    # INTERNAL — timestamp
    # --------------------------------------------------------

    def _timestamp(self):
        """Return the standard timestamp used by every log entry."""

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --------------------------------------------------------
    # INTERNAL — write one line to the log
    # --------------------------------------------------------

    def _write(self, message, level="INFO"):
        """
        Write one line to the log file.

        Format:
            [2026-08-18 16:31:26] [LEVEL] message
        """

        if (
            self._closed
            or self._file is None
            or self._file.closed
        ):
            return

        timestamp = self._timestamp()

        line = f"[{timestamp}] [{level}] {message}"
            

        self._file.write(line + "\n")

        # Flush immediately so the log is always up to date
        # WHY flush?
        #     If the program crashes, unflushed lines are lost.
        #     Flushing after every line means the log is always
        #     complete up to the last action.

        self._file.flush()

    # --------------------------------------------------------
    # PUBLIC — log migration start
    # --------------------------------------------------------

    def start(self, operation, source_roots, destination, total_files):
        """Log the start and basic details of a migration."""

        self._write("Migration started", "START")

        self._write(
            f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "INFO"
        )

        self._write(
            f"Operation: {operation}",
            "INFO"
        )

        self._write(
            f"Total files: {total_files}",
            "INFO"
        )

        for number, path in enumerate(source_roots, start=1):
            self._write(
                f"Source {number}: {path}",
                "INFO"
            )

        self._write(
            f"Destination: {destination}",
            "INFO"
        )

    # --------------------------------------------------------
    # PUBLIC — log path validation result
    # --------------------------------------------------------

    def paths_checked(self, ok):
        """Log the result of path validation."""

        if ok:
            self._write(
                "Path validation PASSED",
                "CHECK"
            )
        else:
            self._write(
                "Path validation FAILED — migration stopped",
                "ERROR"
            )

        

        # --------------------------------------------------------
    # INTERNAL — human readable size
    # --------------------------------------------------------

    @staticmethod
    def _format_size(size):
        """Convert bytes into a readable size."""

        if size is None:
            return "Unknown"

        size = float(size)

        for unit in ["bytes", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"

            size /= 1024

        return f"{size:.1f} PB"

    # --------------------------------------------------------
    # PUBLIC — log destination disk-space check
    # --------------------------------------------------------

    def disk_space_checked(
        self,
        required_bytes,
        available_bytes,
        required_with_margin,
        ok
    ):
        """Log the destination free-space safety check."""

        self._write(
            f"Required file space: "
            f"{self._format_size(required_bytes)}",
            "INFO"
        )

        self._write(
            f"Required with safety margin: "
            f"{self._format_size(required_with_margin)}",
            "INFO"
        )

        self._write(
            f"Destination available space: "
            f"{self._format_size(available_bytes)}",
            "INFO"
        )

        if ok:
            self._write(
                "Disk space check PASSED",
                "CHECK"
            )
        else:
            self._write(
                "Disk space check FAILED — insufficient space",
                "ERROR"
            )


    # --------------------------------------------------------
    # PUBLIC — log inventory creation
    # --------------------------------------------------------

    def inventory_created(self, inventory_path, file_count):
        """Log that the inventory CSV was created."""

        self._write(f"Inventory created: {inventory_path}", "SCAN")
        self._write(f"Files scanned: {file_count}", "SCAN")
        self._write("")

    def inventory_report(self, report_path):
        """Log the inventory CSV report path."""

        self._write(
            f"Inventory CSV: {report_path}",
            "REPORT"
        )

    def verification_report(self, report_path):
        """Log the verification CSV report path."""

        self._write(
            f"Verification CSV: {report_path}",
            "REPORT"
        )
    

    # --------------------------------------------------------
    # PUBLIC — log a single file copy result
    # --------------------------------------------------------

    def file_copied(self, relative_path):
        """Log a successful file copy."""

        self._write(
            f"{relative_path} → OK",
            "COPY"
        )

    def file_copy_failed(
        self,
        relative_path,
        error,
        category="COPY FAILED"
    ):
        """
        Log a failed copy with a clear failure category.
        

        Examples:
            PERMISSION DENIED
            NETWORK INTERRUPTION
            PATH TOO LONG
            COPY FAILED
        """

        self._write(
            f"[COPY] {relative_path} → {category} — {error}",
            "ERROR"
        )    

    # --------------------------------------------------------
    # PUBLIC — log a single file verification result
    # --------------------------------------------------------

    def file_verified(self, relative_path, status, error=None):
        """
        Log the verification result for one file.

        Supported status values:
            VERIFIED
            HASH_MISMATCH
            COPY_FAILED
            ERROR
        """

        if status == "VERIFIED":

            self._write(
                f"{relative_path} → VERIFIED",
                "VERIFY"
            )

        elif status == "HASH_MISMATCH":

            self._write(
                f"[VERIFY] {relative_path} → HASH MISMATCH",
                "ERROR"
            )

        elif status == "COPY_FAILED":

            self._write(
                f"[VERIFY] {relative_path} → NOT VERIFIED — COPY FAILED",
                "ERROR"
            )

        elif status == "ERROR":

            self._write(
                f"[VERIFY] {relative_path} → ERROR — {error}",
                "ERROR"
            )

        else:

            self._write(
                f"[VERIFY] {relative_path} → FAILED — {status}",
                "ERROR"
            )

    # --------------------------------------------------------
    # PUBLIC — log a general error
    # --------------------------------------------------------

    def error(self, message):
        """Log any error message."""

        self._write(message, "ERROR")

    # --------------------------------------------------------
    # PUBLIC — log a warning
    # --------------------------------------------------------

    def warning(self, message):
        """Log a warning message."""

        self._write(message, "WARN")

    # --------------------------------------------------------
    # PUBLIC — log deletion result
    # --------------------------------------------------------

    def file_deleted(self, relative_path):
        """Log a successful source file deletion."""

        self._write(f"{relative_path} → DELETED", "DELETE")

    def file_delete_failed(self, relative_path, error):
        """Log a failed source file deletion."""

        self._write(
            f"[DELETE]  {relative_path} → FAILED — {error}",
            "ERROR"
        )

    # --------------------------------------------------------
    # PUBLIC — log migration completion
    # --------------------------------------------------------

    def complete(
        self,
        operation,
        total,
        copied,
        verified,
        failed,
        deleted=0,
        success=True
    ):
        """Write the final professional migration summary."""

        end_time = datetime.now()

        duration = end_time - self.start_time
        total_seconds = int(duration.total_seconds())

        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        # ----------------------------------------------------
        # FINAL COUNTS
        # ----------------------------------------------------

        self._write(
            f"Operation: {operation}",
            "DONE"
        )

        self._write(
            f"Total files: {total}",
            "DONE"
        )

        self._write(
            f"Copied: {copied}",
            "DONE"
        )

        self._write(
            f"Verified: {verified}",
            "DONE"
        )

        self._write(
            f"Failed: {failed}",
            "DONE"
        )

        if operation == "MOVE":
            self._write(
                f"Deleted: {deleted}",
                "DONE"
            )

        # ----------------------------------------------------
        # TIME INFORMATION
        # ----------------------------------------------------

        self._write(
            f"Duration: {hours:02d}:{minutes:02d}:{seconds:02d}",
            "DONE"
        )

        self._write(
            f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "DONE"
        )

        # ----------------------------------------------------
        # FINAL RESULT
        # ----------------------------------------------------

        self._write(
            f"Result: {'SUCCESS' if success else 'FAILED'}",
            "DONE"
        )

        self.end_time = end_time
        self.close()

    # --------------------------------------------------------
    # PUBLIC — get the log file path
    # --------------------------------------------------------

    def get_log_path(self):
            """Return the full path to this log file."""

            return self.log_path

    # --------------------------------------------------------
    # PUBLIC — close log if not already closed
    # --------------------------------------------------------

    def close(self):
        """
        Safely close the log file.

        Calling close() more than once is safe.
        """

        if self._closed:
            return

        try:
            if (
                self._file is not None
                and not self._file.closed
            ):

                timestamp = self._timestamp()

                self._file.write(
                    f"[{timestamp}] [END] Log closed.\n"
                )

                self._file.flush()
                self._file.close()

        except Exception:
            pass

        finally:
            self._closed = True