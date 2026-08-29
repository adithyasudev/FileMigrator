# ============================================================
# resume.py
# ASHRAM FILE MIGRATOR — STEP 22
# ============================================================
#
# Handles resume / recovery state for migrations.
#
# Main state:
#     resume_TIMESTAMP.json
#
# Backup state:
#     resume_TIMESTAMP.json.bak
#
# Efficient verified-file journal:
#     resume_TIMESTAMP.json.verified
#
# ============================================================

import os
import json
import shutil
from datetime import datetime


# ============================================================
# RESUME STATE MANAGER
# ============================================================

class ResumeManager:
    """
    Manages migration state files for resume/recovery.

    The main JSON stores migration information.

    Verified files are recorded efficiently in an
    append-only .verified journal during migration.

    This avoids rewriting a huge JSON file after
    every verified file.
    """

    def __init__(self, logs_folder="logs"):

        self.logs_folder = logs_folder

        self.state_file = None
        self.progress_file = None

        self.state = {}
        self._verified_set = set()
        self._deleted_set = set()

        os.makedirs(
            logs_folder,
            exist_ok=True
        )

    # --------------------------------------------------------
    # START — create a new resume state
    # --------------------------------------------------------

    def start(
        self,
        operation,
        source_roots,
        destination,
        source_files,
        timestamp
    ):
        """
        Start a brand-new migration resume state.
        """

        self.state_file = os.path.join(
            self.logs_folder,
            f"resume_{timestamp}.json"
        )

        # Separate append-only verified-file journal.
        self.progress_file = (
            self.state_file + ".verified"
        )

        # A NEW migration must not inherit an old journal.
        try:

            if os.path.exists(
                self.progress_file
            ):
                os.remove(
                    self.progress_file
                )

        except Exception:
            pass

        self.state = {
            "operation": operation,
            "source_roots": source_roots,
            "destination": destination,
            "timestamp": timestamp,
            "total_files": len(source_files),
            "all_files": source_files,
            "verified_files": [],
            "deleted_files": [],
            "pending_delete": None,
            "status": "IN_PROGRESS",
            "started_at": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        }

        self._verified_set = set()
        self._deleted_set = set()

        self._save()

    # --------------------------------------------------------
    # LOAD EXISTING — resume SAME state file
    # --------------------------------------------------------

    def load_existing(self, state_file):

        """
        Load an interrupted migration and continue
        using the SAME resume file.
        """

        state, verified_set = load_resume_state(
            state_file
        )

        if state is None:
            return False

        self.state_file = state_file

        self.progress_file = (
            state_file + ".verified"
        )

        self.state = state
        self._verified_set = verified_set
        self._deleted_set = set(
            state.get(
                "deleted_files",
                []
            )
        )

        # Migration is active again.
        self.state["status"] = "IN_PROGRESS"

        self.state["resumed_at"] = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        self._save()

        return True

    # --------------------------------------------------------
    # VALIDATE RESUME STATE
    # --------------------------------------------------------

    def validate_resume_context(
        self,
        operation,
        source_roots,
        destination,
        source_files
    ):
        """
        Confirm that the migration being resumed still
        matches the migration stored in the checkpoint.

        Returns:
            (True, "")
            or
            (False, reason)
        """

        if not self.state:

            return (
                False,
                "Resume state is empty or unavailable."
            )

                # ----------------------------------------------------
        # CLOUD -> LOCAL RESUME VALIDATION
        # ----------------------------------------------------

        migration_type = self.state.get(
            "migration_type",
            "LOCAL_TO_LOCAL"
        )

        if migration_type == "CLOUD_TO_LOCAL":

            saved_cloud_source = self.state.get(
                "cloud_source"
            )

            if not saved_cloud_source:
                return (
                    False,
                    "Saved cloud source information is missing."
                )

            saved_remote = str(
                saved_cloud_source.get(
                    "remote",
                    ""
                )
            ).strip()

            saved_cloud_path = str(
                saved_cloud_source.get(
                    "path",
                    ""
                )
            ).replace("\\", "/").strip("/")

            if not saved_remote:
                return (
                    False,
                    "Saved cloud remote is missing."
                )

            saved_source_display = (
                f"{saved_remote}:{saved_cloud_path}"
                if saved_cloud_path
                else f"{saved_remote}:"
            )

            # --------------------------------------------
            # Destination must still exist locally
            # --------------------------------------------

            saved_destination = self.state.get(
                "destination",
                ""
            )

            if not saved_destination:
                return (
                    False,
                    "Saved destination is missing."
                )

            if not os.path.isdir(
                saved_destination
            ):
                return (
                    False,
                    f"Destination no longer exists: "
                    f"{saved_destination}"
                )

            # --------------------------------------------
            # Operation must still match
            # --------------------------------------------

            saved_operation = str(
                self.state.get(
                    "operation",
                    ""
                )
            ).upper()

            current_operation = str(
                operation
            ).upper()

            if saved_operation != current_operation:
                return (
                    False,
                    f"Operation changed from "
                    f"{saved_operation} "
                    f"to {current_operation}."
                )

            # --------------------------------------------
            # Cloud source identity must match
            # --------------------------------------------

            current_source_display = (
                source_roots[0]
                if source_roots
                else ""
            )

            if (
                saved_source_display
                != current_source_display
            ):
                return (
                    False,
                    "Cloud source does not match the "
                    "interrupted migration."
                )

            # --------------------------------------------
            # Destination must match
            # --------------------------------------------

            saved_destination_normalized = (
                os.path.normcase(
                    os.path.abspath(
                        os.path.normpath(
                            saved_destination
                        )
                    )
                )
            )

            current_destination_normalized = (
                os.path.normcase(
                    os.path.abspath(
                        os.path.normpath(
                            destination
                        )
                    )
                )
            )

            if (
                saved_destination_normalized
                != current_destination_normalized
            ):
                return (
                    False,
                    "Destination does not match the "
                    "interrupted migration."
                )

            # --------------------------------------------
            # Cloud file list must match
            # --------------------------------------------

            def normalize_cloud_file(path):
                return str(path).replace(
                    "\\",
                    "/"
                ).strip("/")

            saved_files = self.state.get(
                "all_files",
                []
            )

            saved_file_set = {
                normalize_cloud_file(path)
                for path in saved_files
            }

            current_file_set = {
                normalize_cloud_file(path)
                for path in source_files
            }

            # --------------------------------------------
            # COPY:
            # Cloud file list must still match exactly.
            # --------------------------------------------

            if current_operation == "COPY":

                if saved_file_set != current_file_set:
                    return (
                        False,
                        "Current cloud file list does not match "
                        "the interrupted migration."
                    )

            # --------------------------------------------
            # MOVE:
            # Missing cloud files are allowed ONLY when
            # resume state proves they were already deleted.
            # --------------------------------------------

            elif current_operation == "MOVE":

                deleted_file_set = {
                    normalize_cloud_file(path)
                    for path in self.state.get(
                        "deleted_files",
                        []
                    )
                }

                # Files appearing now that were not part of
                # the original migration are unsafe.
                unexpected_files = (
                    current_file_set
                    - saved_file_set
                )

                if unexpected_files:
                    return (
                        False,
                        "Cloud source contains files that were "
                        "not part of the interrupted MOVE migration."
                    )

                # Original files that no longer exist in cloud.
                missing_files = (
                    saved_file_set
                    - current_file_set
                )

                # A missing source is safe ONLY when we have
                # a successful deletion checkpoint for it.
                unsafe_missing_files = (
                    missing_files
                    - deleted_file_set
                )

                if unsafe_missing_files:
                    return (
                        False,
                        "One or more cloud source files are missing, "
                        "but they were not recorded as safely deleted "
                        "during the interrupted MOVE."
                    )

            return True, ""


        # ----------------------------------------------------
        # 1. SOURCE ROOTS MUST STILL EXIST
        #
        # Only LOCAL sources can be checked with os.path.
        # Cloud paths such as:
        # test-google-drive:Folder
        # are not Windows filesystem paths.
        # ----------------------------------------------------

        saved_roots = self.state.get(
            "source_roots",
            []
        )

        source_is_local = migration_type in (
            "LOCAL_TO_LOCAL",
            "LOCAL_TO_CLOUD"
        )

        if source_is_local:

            for path in saved_roots:

                if not os.path.exists(path):

                    return (
                        False,
                        f"Source no longer exists: {path}"
                    )

        # ----------------------------------------------------
        # 2. DESTINATION MUST STILL EXIST
        #
        # Only LOCAL destinations can be checked with os.path.
        # Cloud destinations are validated by the cloud
        # migration/resume logic instead.
        # ----------------------------------------------------

        saved_destination = self.state.get(
            "destination",
            ""
        )

        if not saved_destination:

            return (
                False,
                "Saved destination is missing."
            )

        destination_is_local = migration_type in (
            "LOCAL_TO_LOCAL",
            "CLOUD_TO_LOCAL"
        )

        if (
            destination_is_local
            and not os.path.exists(
                saved_destination
            )
        ):

            return (
                False,
                f"Destination no longer exists: "
                f"{saved_destination}"
            )

        # ----------------------------------------------------
        # 3. OPERATION MUST MATCH
        # ----------------------------------------------------

        saved_operation = str(
            self.state.get(
                "operation",
                ""
            )
        ).upper()

        current_operation = str(
            operation
        ).upper()

        if (
            saved_operation
            != current_operation
        ):

            return (
                False,
                f"Operation changed from "
                f"{saved_operation} "
                f"to {current_operation}."
            )

        # ----------------------------------------------------
        # PATH NORMALISER
        # ----------------------------------------------------

        def normalize_path(path):

            return os.path.normcase(
                os.path.abspath(
                    os.path.normpath(path)
                )
            )

        # ----------------------------------------------------
        # 4. DESTINATION MUST MATCH
        # ----------------------------------------------------

        if (
            normalize_path(
                saved_destination
            )
            !=
            normalize_path(
                destination
            )
        ):

            return (
                False,
                "Destination does not match the "
                "interrupted migration."
            )

        # ----------------------------------------------------
        # 5. SOURCE ROOTS MUST MATCH
        # ----------------------------------------------------

        saved_root_set = {
            normalize_path(path)
            for path in saved_roots
        }

        current_root_set = {
            normalize_path(path)
            for path in source_roots
        }

        if (
            saved_root_set
            != current_root_set
        ):

            return (
                False,
                "Source selection does not match the "
                "interrupted migration."
            )

        # ----------------------------------------------------
        # 6. FILE LIST MUST MATCH
        # ----------------------------------------------------

                # ----------------------------------------------------
        # 6. FILE LIST MUST MATCH
        # ----------------------------------------------------

        saved_files = self.state.get(
            "all_files",
            []
        )

        saved_file_set = {
            normalize_path(path)
            for path in saved_files
        }

        current_file_set = {
            normalize_path(path)
            for path in source_files
        }

        # ----------------------------------------------------
        # COPY:
        # Every original source file must still exist.
        # ----------------------------------------------------

        if current_operation == "COPY":

            if saved_file_set != current_file_set:

                return (
                    False,
                    "Current file list does not match the "
                    "interrupted migration."
                )

        # ----------------------------------------------------
        # MOVE:
        #
        # Missing source files are allowed ONLY if the
        # resume state proves they were already deleted
        # successfully during this MOVE.
        # ----------------------------------------------------

        elif current_operation == "MOVE":

            deleted_file_set = {
                normalize_path(path)
                for path in self.state.get(
                    "deleted_files",
                    []
                )
            }

            # Every file currently present must belong to
            # the original migration.
            unexpected_files = (
                current_file_set
                - saved_file_set
            )

            if unexpected_files:

                return (
                    False,
                    "Current source contains files that were "
                    "not part of the interrupted MOVE migration."
                )

            # Find original files that are now missing.
            missing_files = (
                saved_file_set
                - current_file_set
            )

            # A missing file is safe ONLY if we recorded
            # that it had already been deleted.
            unsafe_missing_files = (
                missing_files
                - deleted_file_set
            )

            if unsafe_missing_files:

                return (
                    False,
                    "One or more source files are missing, "
                    "but they were not recorded as safely "
                    "deleted during the interrupted MOVE."
                )

        return True, ""

    # --------------------------------------------------------
    # MARK FILE VERIFIED — EFFICIENT JOURNAL
    # --------------------------------------------------------

    def mark_verified(
        self,
        source_file_path
    ):
        """
        Record one successfully verified file.

        IMPORTANT:

        We DO NOT rewrite the entire resume JSON here.

        Instead we append one line to:

            resume_TIMESTAMP.json.verified

        This is much more efficient for very large
        migrations such as 100,000+ files.
        """

        # Already recorded.
        if (
            source_file_path
            in self._verified_set
        ):
            return

        self._verified_set.add(
            source_file_path
        )

        if not self.progress_file:
            return

        try:

            with open(
                self.progress_file,
                "a",
                encoding="utf-8"
            ) as f:

                # JSON encoding handles Windows paths,
                # spaces, Unicode, etc. safely.
                f.write(
                    json.dumps(
                        source_file_path
                    )
                    + "\n"
                )

                # Flush Python buffer.
                f.flush()

                # Flush operating-system buffer.
                os.fsync(
                    f.fileno()
                )

        except Exception:

            # Resume tracking must never crash
            # the actual migration.
            pass

    # --------------------------------------------------------
    # CHECK IF FILE ALREADY VERIFIED
    # --------------------------------------------------------

    def is_verified(
        self,
        source_file_path
    ):
        """
        Return True if this file was verified
        before the interruption.
        """

        return (
            source_file_path
            in self._verified_set
        )


            # --------------------------------------------------------
    # REMOVE STALE VERIFIED FILE
    # --------------------------------------------------------

    def unmark_verified(self, source_file_path):
        """
        Remove a file from verified progress.

        WHY:
            A destination file may have been deleted or changed
            after an earlier successful verification.

            In that case Resume must NOT blindly skip it.
        """

        if source_file_path not in self._verified_set:
            return

        self._verified_set.discard(
            source_file_path
        )

        # Keep the in-memory state accurate.
        self.state["verified_files"] = list(
            self._verified_set
        )

        self.state["deleted_files"] = list(
            self._deleted_set
        )

        # Rebuild the progress journal.
        #
        # This is normally rare, so rewriting the journal here
        # is acceptable. Normal verification still uses the
        # efficient append-only method.
        if self.progress_file:

            temp_progress = (
                self.progress_file + ".tmp"
            )

            try:

                with open(
                    temp_progress,
                    "w",
                    encoding="utf-8"
                ) as f:

                    for verified_path in self._verified_set:

                        f.write(
                            json.dumps(
                                verified_path
                            )
                            + "\n"
                        )

                    f.flush()
                    os.fsync(
                        f.fileno()
                    )

                os.replace(
                    temp_progress,
                    self.progress_file
                )

            except Exception:

                try:
                    if os.path.exists(
                        temp_progress
                    ):
                        os.remove(
                            temp_progress
                        )
                except Exception:
                    pass
    # --------------------------------------------------------
    # MARK DELETE PENDING
    # --------------------------------------------------------

    def mark_delete_pending(self, source_file_path):
        """
        Record which MOVE source file is about to be deleted.
        """

        self.state["pending_delete"] = (
            source_file_path
        )

        self._save()

    # --------------------------------------------------------
    # CLEAR DELETE PENDING
    # --------------------------------------------------------

    def clear_delete_pending(self):
        """
        Clear the pending-delete marker after the deletion
        has been safely checkpointed.
        """

        self.state["pending_delete"] = None

        self._save()

        # --------------------------------------------------------
    # MARK SOURCE FILE DELETED
    # --------------------------------------------------------

    def mark_deleted(self, source_file_path):
        """
        Record that a MOVE source file was successfully deleted.
        """

        if source_file_path in self._deleted_set:
            return

        self._deleted_set.add(
            source_file_path
        )

        self.state["deleted_files"] = list(
            self._deleted_set
        )


        self._save()

    # --------------------------------------------------------
    # CHECK IF SOURCE ALREADY DELETED
    # --------------------------------------------------------

    def is_deleted(self, source_file_path):
        """
        Return True if this source file was already deleted
        during a previous MOVE attempt.
        """

        return (
            source_file_path
            in self._deleted_set
        )

    # --------------------------------------------------------
    # COMPLETE MIGRATION
    # --------------------------------------------------------

    def complete(
        self,
        success
    ):
        """
        Mark migration complete.

        At completion we write ONE final complete snapshot
        of all verified files into the main JSON.
        """

        # Consolidate journal progress into final JSON.
        self.state["verified_files"] = list(
            self._verified_set
        )

        self.state["status"] = (
            "COMPLETE"
            if success
            else "FAILED"
        )

        self.state["completed_at"] = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        self._save()

    # --------------------------------------------------------
    # MARK INTERRUPTED
    # --------------------------------------------------------

    def mark_interrupted(self):
        """
        Mark migration as interrupted.

        Verified-file progress remains safely stored
        inside the .verified journal.
        """

        self.state["status"] = (
            "INTERRUPTED"
        )

        self.state["interrupted_at"] = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        self._save()


    def mark_abandoned(self):
        """
        Mark this resume checkpoint as intentionally abandoned.

        WHY:
        If the user chooses "No — start a new migration",
        this checkpoint should not appear again on next launch.
        """

        self.state["status"] = "ABANDONED"
        self.state["abandoned_at"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        self._save()

    # --------------------------------------------------------
    # GET VERIFIED COUNT
    # --------------------------------------------------------

    def get_verified_count(self):
        """
        Return number of files already verified.
        """

        return len(
            self._verified_set
        )

    # --------------------------------------------------------
    # INTERNAL — SAFE ATOMIC JSON SAVE
    # --------------------------------------------------------

    def _save(self):
        """
        Safely write migration metadata.

        Process:

            write .tmp
                ↓
            flush to disk
                ↓
            backup previous JSON
                ↓
            atomically replace real JSON

        A logging/checkpoint failure must never crash
        the actual migration.
        """

        if not self.state_file:
            return

        temp_file = (
            self.state_file + ".tmp"
        )

        backup_file = (
            self.state_file + ".bak"
        )

        try:

            # --------------------------------------------
            # Write NEW state to temporary file first
            # --------------------------------------------

            with open(
                temp_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    self.state,
                    f,
                    indent=2
                )

                f.flush()

                os.fsync(
                    f.fileno()
                )

            # --------------------------------------------
            # Backup previous valid state
            # --------------------------------------------

            if os.path.exists(
                self.state_file
            ):

                try:

                    shutil.copy2(
                        self.state_file,
                        backup_file
                    )

                except Exception:
                    pass

            # --------------------------------------------
            # Atomic replacement
            # --------------------------------------------

            os.replace(
                temp_file,
                self.state_file
            )

        except Exception:

            # Remove unfinished temporary file.
            try:

                if os.path.exists(
                    temp_file
                ):
                    os.remove(
                        temp_file
                    )

            except Exception:
                pass

            # Never crash migration because
            # resume-state saving failed.
            pass

    # --------------------------------------------------------
    # GET STATE FILE PATH
    # --------------------------------------------------------

    def get_state_file(self):
        """
        Return current resume JSON path.
        """

        return self.state_file


# ============================================================
# FIND INCOMPLETE MIGRATIONS
# ============================================================

def find_incomplete_migrations(
    logs_folder="logs"
):
    """
    Find migrations that may be resumed.

    IMPORTANT:

    Uses load_resume_state() instead of directly loading
    only the JSON.

    This means the GUI also sees progress stored in the
    .verified journal.
    """

    incomplete = []

    if not os.path.exists(
        logs_folder
    ):
        return incomplete

    for filename in os.listdir(
        logs_folder
    ):

        # Only main resume JSON files.
        if not filename.startswith(
            "resume_"
        ):
            continue

        if not filename.endswith(
            ".json"
        ):
            continue

        filepath = os.path.join(
            logs_folder,
            filename
        )

        # Load main JSON + backup recovery
        # + .verified journal.
        state, verified_set = (
            load_resume_state(
                filepath
            )
        )

        if state is None:
            continue

        if state.get("status") in (
            "IN_PROGRESS",
            "INTERRUPTED"
        ):

            # Ensure popup sees the TRUE progress,
            # including journal entries.
            state["verified_files"] = list(
                verified_set
            )

            state["_state_file"] = (
                filepath
            )

            incomplete.append(
                state
            )

    # Most recent first.
    incomplete.sort(
        key=lambda state: state.get(
            "timestamp",
            ""
        ),
        reverse=True
    )

    return incomplete


# ============================================================
# LOAD RESUME STATE
# ============================================================

def load_resume_state(
    state_file
):
    """
    Load resume information.

    Sources of information:

        1. Main resume JSON
        2. Backup JSON if main is damaged
        3. .verified append-only journal

    Returns:

        (state_dict, verified_set)

    or:

        (None, set())
    """

    state = None

    # --------------------------------------------------------
    # TRY MAIN JSON
    # --------------------------------------------------------

    try:

        with open(
            state_file,
            "r",
            encoding="utf-8"
        ) as f:

            state = json.load(f)

    except Exception:
        pass

    # --------------------------------------------------------
    # MAIN FAILED — TRY BACKUP
    # --------------------------------------------------------

    if state is None:

        backup_file = (
            state_file + ".bak"
        )

        try:

            with open(
                backup_file,
                "r",
                encoding="utf-8"
            ) as f:

                state = json.load(f)

        except Exception:

            return None, set()

    # --------------------------------------------------------
    # LOAD OLD JSON VERIFIED FILES
    # --------------------------------------------------------
    #
    # Backward compatibility:
    # resume files created before Step 22.6 may already
    # contain verified_files directly in JSON.
    # --------------------------------------------------------

    verified_set = set(
        state.get(
            "verified_files",
            []
        )
    )

    # --------------------------------------------------------
    # LOAD NEW APPEND-ONLY VERIFIED JOURNAL
    # --------------------------------------------------------

    progress_file = (
        state_file + ".verified"
    )

    if os.path.exists(
        progress_file
    ):

        try:

            with open(
                progress_file,
                "r",
                encoding="utf-8"
            ) as f:

                for line in f:

                    line = line.strip()

                    if not line:
                        continue

                    try:

                        verified_path = (
                            json.loads(
                                line
                            )
                        )

                        verified_set.add(
                            verified_path
                        )

                    except Exception:

                        # If power dies while writing the
                        # final journal line, ignore only
                        # that damaged line.
                        continue

        except Exception:
            pass

    # --------------------------------------------------------
    # GIVE REST OF PROGRAM COMPLETE VIEW
    # --------------------------------------------------------

    state["verified_files"] = list(
        verified_set
    )

    return (
        state,
        verified_set
    )



