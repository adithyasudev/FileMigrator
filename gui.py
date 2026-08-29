# ============================================================
# gui.py
# ASHRAM FILE MIGRATOR 
# ============================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys
import re
import shutil
import io
import time
import ctypes
from ctypes import wintypes
from cloud_selector import select_cloud_location
from rclone import (
    copy_to_cloud,
    copy_from_cloud,
    copy_cloud_to_cloud,
    delete_cloud_file,
)
from cloudhash import (
    get_cloud_file_info,
    save_cloud_hash_report,
)

from comparator import (
    compare_clouds,
    save_comparison_report,
)

from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime

from hasher import calculate_hashes
from scanner import find_files
from copier import copy_files, find_root_for_file
from verifier import verify_file
from reporter import (
    create_inventory_report,
    create_verification_report,
    create_user_report,
)
from network import validate_paths, is_network_path
from logger import MigrationLogger
from resume import ResumeManager, find_incomplete_migrations, load_resume_state
from selector import _expand_sources
from app_paths import (
    get_logs_folder,
    get_reports_folder,
    get_resource_path,
)


# ============================================================
# COLORS AND STYLE
# ============================================================

BG_DARK = "#2a1201"
BG_PANEL = "#3d1c02"
BG_CARD = "#5c2d0a"
ACCENT = "#e8640c"
ACCENT_HOVER = "#ff7a1a"
BTN_COLOR = "#7a3d10"
BTN_HOVER = "#9e4f18"
BTN_DANGER = "#9e2a2a"
BTN_DANGER_H = "#c23535"
TEXT_WHITE = "#fdf3e7"
TEXT_GREY = "#c4a882"
TEXT_GREEN = "#f5a623"
TEXT_RED = "#ff5555"
TEXT_YELLOW = "#ffd700"

FONT_MAIN = ("Segoe UI", 10,"bold")
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_HEADING = ("Segoe UI", 11, "bold")
FONT_SMALL = ("Segoe UI", 9,"bold")
FONT_MONO = ("Consolas", 11)

# Keep the Windows mutex handle alive for the lifetime
# of the application.
_SINGLE_INSTANCE_MUTEX = None


def acquire_single_instance():
    """
    Allow only one Ashram File Migrator process at a time.
    """

    global _SINGLE_INSTANCE_MUTEX

    if os.name != "nt":
        return True

    kernel32 = ctypes.WinDLL(
        "kernel32",
        use_last_error=True
    )

    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    mutex_handle = kernel32.CreateMutexW(
        None,
        False,
        "Local\\NarayanashramFileMigratorSingleInstance"
    )

    if not mutex_handle:
        return True

    if ctypes.get_last_error() == 183:
        kernel32.CloseHandle(mutex_handle)
        return False

    _SINGLE_INSTANCE_MUTEX = mutex_handle
    return True


def release_single_instance():
    """
    Release the Windows single-instance mutex during shutdown.
    """

    global _SINGLE_INSTANCE_MUTEX

    if os.name != "nt" or not _SINGLE_INSTANCE_MUTEX:
        return

    ctypes.windll.kernel32.CloseHandle(
        _SINGLE_INSTANCE_MUTEX
    )
    _SINGLE_INSTANCE_MUTEX = None

_WINDOW_ICON_HANDLES = []


def apply_windows_window_icon(root):
    """
    Apply the bundled icon directly to the Windows top-level
    window for both the title bar and taskbar.
    """

    if os.name != "nt":
        return

    try:
        icon_path = get_resource_path(
            os.path.join(
                "Assets",
                "app_icon.ico"
            )
        )

        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = wintypes.HANDLE

        small_icon = user32.LoadImageW(
            None,
            icon_path,
            1,
            16,
            16,
            0x0010
        )

        large_icon = user32.LoadImageW(
            None,
            icon_path,
            1,
            32,
            32,
            0x0010
        )

        root.update_idletasks()

        window_handle = root.winfo_id()
        parent_handle = user32.GetParent(
            window_handle
        )

        for handle in {
            window_handle,
            parent_handle
        }:
            if handle:
                user32.SendMessageW(
                    handle,
                    0x0080,
                    0,
                    small_icon
                )
                user32.SendMessageW(
                    handle,
                    0x0080,
                    1,
                    large_icon
                )

        _WINDOW_ICON_HANDLES.extend(
            [
                small_icon,
                large_icon,
            ]
        )

    except Exception:
        pass

# ============================================================
# MAIN APPLICATION CLASS
# ============================================================

class AshramMigratorApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Ashram File Migrator")

        try:
            self.root.iconbitmap(
                get_resource_path(
                    os.path.join(
                        "Assets",
                        "app_icon.ico"
                    )
                )
            )
        except (tk.TclError, OSError):
            pass

        self.root.geometry("1100x900")
        self.root.protocol(
            "WM_DELETE_WINDOW",
            self._on_close
        )
        self.root.minsize(860, 720)
        self.root.configure(bg=BG_DARK)

        self.source_roots = []
        self.source_files = []
        self.operation_var = tk.StringVar(value="COPY")
        self.is_running = False
        self.stop_requested = False
        self.migration_controls = []
        # Resume state — set when resuming an incomplete migration
        self._resume_mode         = False
        self._resume_verified_set = set()
        self._resume_state_file   = None
        self._active_resume = None
        self.cloud_source = None
        self.cloud_destination = None
        self._build_header()
        self._build_status_bar()
        self._build_start_btn()
        self._build_main()
        self._center_window()
        # Check for incomplete migrations on startup
        self.root.after(500, self._check_for_resume)

    def _on_close(self):
        """
        Handle application close safely.

        If a migration is running, do not just destroy the window.
        The active resume state must remain recoverable.
        """

        if self.is_running:

            answer = messagebox.askyesno(
                "Migration In Progress",
                "A migration is currently running.\n\n"
                "Closing now will interrupt the migration.\n"
                "Progress already saved can be resumed next time.\n\n"
                "Close application?"
            )

            if not answer:
                return
            
            # Tell the worker thread to stop safely.
            self.stop_requested = True
            
            if self._active_resume is not None:
                try:
                
                    self._active_resume.mark_interrupted()
                except Exception:
                    pass

        self.root.destroy()







    # --------------------------------------------------------
    # CENTER WINDOW
    # --------------------------------------------------------
    def _check_for_resume(self):
        """
        Check for incomplete migrations when app starts.
        WHY after(500)?
            Wait 500ms so the window fully renders first.
            Showing a dialog before the window is ready
            looks unprofessional.
        """

        logs_folder = get_logs_folder()
        incomplete  = find_incomplete_migrations(logs_folder)

        if not incomplete:
            return

        # Take the most recent incomplete migration
        state = incomplete[0]

        verified_count = len(state.get("verified_files", []))
        total_files    = state.get("total_files", 0)
        operation      = state.get("operation", "COPY")
        destination    = state.get("destination", "")
        source_roots   = state.get("source_roots", [])
        started_at     = state.get("started_at", "unknown time")

        answer = messagebox.askyesno(
            "Incomplete Migration Found",
            f"An incomplete migration was found:\n\n"
            f"  Operation:   {operation}\n"
            f"  Destination: {destination}\n"
            f"  Started at:  {started_at}\n"
            f"  Progress:    {verified_count} / {total_files} files verified\n\n"
            f"Would you like to RESUME this migration?\n\n"
            f"Yes — resume from file {verified_count + 1}\n"
            f"No  — start a new migration"
        )

        if not answer:

            # User chose to start fresh.
            # Abandon every outstanding old checkpoint so
            # historical interrupted migrations do not keep
            # appearing one-by-one on future launches.
            for incomplete_state in incomplete:

                state_file = incomplete_state.get(
                    "_state_file"
                )

                if not state_file:
                    continue

                try:
                    resume = ResumeManager(
                        get_logs_folder()
                    )

                    if resume.load_existing(
                        state_file
                    ):
                        resume.mark_abandoned()

                except Exception:
                    pass

            return
        # Load the state and pre-fill the GUI
        state_file       = state.get("_state_file")
        loaded_state, verified_set = load_resume_state(state_file)

        if not loaded_state:
            messagebox.showerror(
                "Resume Failed",
                "Could not load the saved migration state.\n"
                "Please start a new migration."
            )
            return
        
        # ----------------------------------------------------
        # RESUME SAFETY — SAVED LOCAL DESTINATION MUST EXIST
        # ----------------------------------------------------

        migration_type = loaded_state.get(
            "migration_type",
            "LOCAL_TO_LOCAL"
        )

        if migration_type == "CLOUD_TO_LOCAL":

            saved_destination = loaded_state.get(
                "destination",
                ""
            )

            if (
                not saved_destination
                or not os.path.isdir(saved_destination)
            ):
                messagebox.showerror(
                    "Resume Failed",
                    "The saved destination folder no longer exists.\n\n"
                    f"{saved_destination}\n\n"
                    "The migration will NOT be resumed."
                )
                return

        # RESTORE LOCAL / CLOUD SOURCE AND DESTINATION
        # ----------------------------------------------------

        if migration_type == "CLOUD_TO_LOCAL":

            saved_cloud_source = loaded_state.get(
                "cloud_source"
            )

            if not saved_cloud_source:
                messagebox.showerror(
                    "Resume Failed",
                    "The saved cloud source information is missing."
                )
                return

            self.cloud_source = dict(
                saved_cloud_source
            )

            self.cloud_destination = None

            self.source_roots = []
            self.source_files = []

            remote = self.cloud_source.get(
                "remote",
                ""
            )

            path = self.cloud_source.get(
                "path",
                ""
            )

            source_display = (
                f"{remote}:{path}"
                if path
                else f"{remote}:"
            )

            self._set_source_display(
                (
                    "☁  CLOUD SOURCE\n"
                    f"{source_display}"
                ),
                TEXT_GREEN
                )

            self.dest_var.set(
                destination
            )

        elif migration_type == "CLOUD_TO_CLOUD":

            saved_cloud_source = loaded_state.get(
                "cloud_source"
            )

            saved_cloud_destination = loaded_state.get(
                "cloud_destination"
            )

            if not saved_cloud_source:
                messagebox.showerror(
                    "Resume Failed",
                    "The saved cloud source information is missing."
                )
                return

            if not saved_cloud_destination:
                messagebox.showerror(
                    "Resume Failed",
                    "The saved cloud destination information is missing."
                )
                return

            self.cloud_source = dict(
                saved_cloud_source
            )

            self.cloud_destination = dict(
                saved_cloud_destination
            )

            self.source_roots = []
            self.source_files = []

            source_remote = self.cloud_source.get(
                "remote",
                ""
            )

            source_path = self.cloud_source.get(
                "path",
                ""
            )

            source_display = (
                f"{source_remote}:{source_path}"
                if source_path
                else f"{source_remote}:"
            )

            self._set_source_display(
                (
                    "☁  CLOUD SOURCE\n"
                    f"{source_display}"
                ),
                TEXT_GREEN
            )

            destination_remote = self.cloud_destination.get(
                "remote",
                ""
            )

            destination_path = self.cloud_destination.get(
                "path",
                ""
            )

            destination_display = (
                f"{destination_remote}:{destination_path}"
                if destination_path
                else f"{destination_remote}:"
            )

            self.dest_var.set(
                destination_display
            )

        elif migration_type == "LOCAL_TO_CLOUD":

            saved_cloud_destination = loaded_state.get(
                "cloud_destination"
            )

            if not saved_cloud_destination:
                messagebox.showerror(
                    "Resume Failed",
                    "The saved cloud destination information is missing."
                )
                return

            self.cloud_source = None

            self.cloud_destination = dict(
                saved_cloud_destination
            )

            self.source_roots = source_roots
            self._refresh_source_label()

            destination_remote = self.cloud_destination.get(
                "remote",
                ""
            )

            destination_path = self.cloud_destination.get(
                "path",
                ""
            )

            destination_display = (
                f"{destination_remote}:{destination_path}"
                if destination_path
                else f"{destination_remote}:"
            )

            self.dest_var.set(
                destination_display
            )

        else:

            # LOCAL_TO_LOCAL
            self.cloud_source = None
            self.cloud_destination = None

            self.source_roots = source_roots
            self._refresh_source_label()

            self.dest_var.set(
                destination
            )

         

        # Set operation
        self._select_operation(operation)

        # Store resume state for use during migration
        self._resume_verified_set  = verified_set
        self._resume_state_file    = state_file
        self._resume_mode          = True

        self._log(
            f"RESUME MODE — {verified_count} files already verified",
            "yellow"
        )
        self._log(
            f"Will skip {verified_count} verified files and continue from file {verified_count + 1}",
            "grey"
        )

        messagebox.showinfo(
            "Ready to Resume",
            f"Migration loaded.\n\n"
            f"Already verified: {verified_count} files\n"
            f"Remaining: {total_files - verified_count} files\n\n"
            f"Click START MIGRATION to continue."
        )

    def _center_window(self):
        self.root.update_idletasks()

        requested_w = max(
            self.root.winfo_width(),
            self.root.winfo_reqwidth()
        )

        requested_h = max(
            self.root.winfo_height(),
            self.root.winfo_reqheight()
        )

        # Ask Windows for the usable desktop area.
        # This excludes the taskbar.
        work_area = wintypes.RECT()

        ctypes.windll.user32.SystemParametersInfoW(
            0x0030,          # SPI_GETWORKAREA
            0,
            ctypes.byref(work_area),
            0
        )

        usable_w = (
            work_area.right
            - work_area.left
        )

        usable_h = (
            work_area.bottom
            - work_area.top
        )

        # Never allow the startup window to extend
        # outside the usable desktop.
        w = min(
            requested_w,
            usable_w - 20
        )

        h = min(
            requested_h,
            usable_h - 20
        )

        x = (
            work_area.left
            + (usable_w - w) // 2
        )

        y = (
            work_area.top
            + (usable_h - h) // 2
        )

        self.root.geometry(
            f"{w}x{h}+{x}+{y}"
        )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    def _build_header(self):
        header = tk.Frame(self.root, bg=ACCENT, pady=0)
        header.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            header,
            text="🕉   NARAYANASHRAM FILE MIGRATOR",
            font=FONT_TITLE,
            fg=TEXT_WHITE,
            bg=ACCENT
        ).pack()

        tk.Label(
            header,
            text="Narayanashrama Tapovanam  •  Safe  •  Verified  •  Reliable",
            font=FONT_SMALL,
            fg="#fde8d0",
            bg=ACCENT
        ).pack(pady=(2, 0))

    # --------------------------------------------------------
    # START BUTTON
    # --------------------------------------------------------

    def _build_start_btn(self):
        self.start_btn = tk.Button(
            self.root,
            text="▶   START MIGRATION",
            font=("Segoe UI", 13, "bold"),
            fg=TEXT_WHITE,
            bg=ACCENT,
            activebackground=ACCENT_HOVER,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            cursor="hand2",
            pady=12,
            command=self._start_migration
        )
        self.start_btn.pack(fill=tk.X, side=tk.BOTTOM)

        self.start_btn.bind(
            "<Enter>",
            lambda event: self.start_btn.config(bg=ACCENT_HOVER)
            if self.start_btn["state"] == tk.NORMAL else None
        )
        self.start_btn.bind(
            "<Leave>",
            lambda event: self.start_btn.config(bg=ACCENT)
            if self.start_btn["state"] == tk.NORMAL else None
        )

    # --------------------------------------------------------
    # STATUS BAR
    # --------------------------------------------------------

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=BG_CARD, height=36)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self.status_var = tk.StringVar(value="Ready")

        tk.Label(
            bar,
            textvariable=self.status_var,
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_GREY,
            bg=BG_CARD
        ).place(relx=0.015, rely=0.5, anchor="w")

        tk.Label(
            bar,
            text="🕉   JAI GURU   🕉",
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT,
            bg=BG_CARD
        ).place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            bar,
            text="Narayanashrama Tapovanam — Safe Migration Tool",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_GREY,
            bg=BG_CARD
        ).place(relx=0.985, rely=0.5, anchor="e")

    # --------------------------------------------------------
    # MAIN CONTENT
    # --------------------------------------------------------

    # def _build_main(self):
    #     container = tk.Frame(self.root, bg=BG_DARK)
    #     container.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

    #     left = tk.Frame(container, bg=BG_DARK, width=390)
    #     left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
    #     left.pack_propagate(False)

    #     right = tk.Frame(container, bg=BG_DARK)
    #     right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    #     self._build_controls(left)
    #     self._build_log(right)


    def _build_main(self):
        container = tk.Frame(
            self.root,
            bg=BG_DARK
        )
        container.pack(
            fill=tk.BOTH,
            expand=True,
            padx=12,
            pady=6
        )

        left = tk.Frame(
            container,
            bg=BG_DARK,
            width=500
        )
        left.pack(
            side=tk.LEFT,
            fill=tk.Y,
            padx=(0, 10)
        )
        left.pack_propagate(False)

        right = tk.Frame(
            container,
            bg=BG_DARK
        )
        right.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True
        )

        self._build_controls(left)
        self._build_log(right)

    # --------------------------------------------------------
    # CONTROLS
    # --------------------------------------------------------

    def _build_controls(self, parent):
        op_frame = self._card(parent, "OPERATION")

        op_btn_row = tk.Frame(op_frame, bg=BG_PANEL)
        op_btn_row.pack(fill=tk.X)

        self.copy_op_btn = self._op_btn(
            op_btn_row,
            "✓  COPY",
            "COPY"
        )
        self.copy_op_btn.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(0, 6)
        )

        self.move_op_btn = self._op_btn(
            op_btn_row,
            "⚠  MOVE",
            "MOVE"
        )
        self.move_op_btn.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True
        )

        self._refresh_operation_button_styles()

        self.op_info_label = tk.Label(
            op_frame,
            text="COPY selected  •  Original files will remain unchanged",
            font=FONT_SMALL,
            fg=TEXT_GREEN,
            bg=BG_PANEL
        )
        self.op_info_label.pack(anchor=tk.W, pady=(8, 0))

        src_frame = self._card(parent, "SOURCE")

        self.source_var = tk.StringVar()

        self.source_summary_label = tk.Label(
            src_frame,
            text="No local source selected",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_GREY,
            bg=BG_PANEL
        )

        self.source_summary_label.pack(
            anchor=tk.W,
            pady=(0, 5)
        )

        self.source_entry = tk.Entry(
            src_frame,
            textvariable=self.source_var,
            font=FONT_MAIN,
            bg=BG_CARD,
            fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE,
            relief=tk.FLAT,
            bd=6
        )

        self.source_entry.insert(
            0,
            ""
        )

        self.source_entry.pack(
            fill=tk.X,
            pady=(0, 5)
        )

        self.source_entry.bind(
            "<Return>",
            self._apply_source_entry
        )

        self.migration_controls.append(
            self.source_entry
        )

                # ----------------------------------------------------
        # SCROLLABLE SELECTED-SOURCE DISPLAY
        # ----------------------------------------------------

        source_list_frame = tk.Frame(
            src_frame,
            bg=BG_PANEL
        )

        source_list_frame.pack(
            fill=tk.X,
            pady=(0, 5)
        )

        self.source_label = tk.Text(
            source_list_frame,
            height=3,
            font=FONT_SMALL,
            fg=TEXT_GREY,
            bg=BG_PANEL,
            insertbackground=TEXT_WHITE,
            relief=tk.FLAT,
            wrap=tk.WORD,
            cursor="arrow",
            takefocus=0
        )

        self.source_label.pack(
            fill=tk.X
        )

        self.source_label.insert(
            "1.0",
            "No source selected"
        )

        self.source_label.config(
            state=tk.DISABLED
        )

        def _scroll_source_list(event):
            self.source_label.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )

            return "break"

        self.source_label.bind(
            "<MouseWheel>",
            _scroll_source_list
        )


        # def _resize_source_list(event=None):
        #     window_height = self.root.winfo_height()

        #     if window_height >= 950:
        #         source_height = 12

        #     elif window_height >= 850:
        #         source_height = 8

        #     elif window_height >= 780:
        #         source_height = 5

        #     else:
        #         source_height = 2

        #     self.source_label.config(
        #         height=source_height
        #     )

        def _resize_source_list(event=None):
            window_height = self.root.winfo_height()

            if window_height >= 1000:
                source_height = 5

            elif window_height >= 940:
                source_height = 4

            else:
                source_height = 2

            self.source_label.config(
                height=source_height
            )


        self.root.bind(
            "<Configure>",
            _resize_source_list,
            add="+"
        )


        src_btn_row = tk.Frame(
            src_frame,
            bg=BG_PANEL
        )

        src_btn_row.pack(fill=tk.X)

        self._btn(src_btn_row, "Browse Files", self._browse_file).pack(
            side=tk.LEFT, padx=(0, 6)
        )

        self._btn(src_btn_row, "Browse Folder", self._browse_folder).pack(
            side=tk.LEFT, padx=(0, 6)
        )

        self._btn(
            src_btn_row,
            "☁ Cloud",
            self._browse_cloud_source
        ).pack(
            side=tk.LEFT,
            padx=(0, 6)
        )

        self._btn(
            src_btn_row,
            "Clear",
            self._clear_source,
            danger=True
        ).pack(
            side=tk.LEFT
        )
        
        dst_frame = self._card(parent, "DESTINATION")

        self.dest_var = tk.StringVar()

        self.destination_summary_label = tk.Label(
            dst_frame,
            text="No destination selected",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_GREY,
            bg=BG_PANEL
        )

        self.destination_summary_label.pack(
            anchor=tk.W,
            pady=(0, 5)
        )

        self.dest_entry = tk.Entry(
            dst_frame,
            textvariable=self.dest_var,
            font=FONT_MAIN,
            bg=BG_CARD,
            fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE,
            relief=tk.FLAT,
            bd=6
        )
        self.dest_entry.pack(
            fill=tk.X,
            pady=(0, 8)
        )

        self.dest_entry.bind(
            "<Return>",
            self._apply_destination_entry
        )

        self.migration_controls.append(
            self.dest_entry
        )

        dest_btn_row = tk.Frame(dst_frame, bg=BG_PANEL)
        dest_btn_row.pack(fill=tk.X)

        self._btn(
            dest_btn_row,
            "Browse Folder",
            self._browse_destination
        ).pack(side=tk.LEFT, padx=(0, 6))

        

        self._btn(
            dest_btn_row,
            "☁ Cloud",
            self._browse_cloud_destination
        ).pack(
            side=tk.LEFT,
            padx=(0, 6)
        )

        self._btn(
            dest_btn_row,
            "Clear",
            self._clear_destination,
            danger=True
        ).pack(side=tk.LEFT)

        self.dest_var.trace_add("write", self._update_disk_space)

        disk_frame = self._card(parent, "DISK SPACE")

        self.disk_label = tk.Label(
            disk_frame,
            text="Select a destination folder to check available space",
            font=FONT_SMALL,
            fg=TEXT_GREY,
            bg=BG_PANEL,
            justify=tk.LEFT,
            wraplength=340
        )
        self.disk_label.pack(anchor=tk.W)

        prog_frame = self._card(parent, "PROGRESS")

        progress_header = tk.Frame(
            prog_frame,
            bg=BG_PANEL
        )
        progress_header.pack(fill=tk.X)

        self.progress_label = tk.Label(
            progress_header,
            text="Ready",
            font=("Segoe UI", 11, "bold"),
            fg=TEXT_GREY,
            bg=BG_PANEL
        )
        self.progress_label.pack(side=tk.LEFT)

        self.progress_percent_label = tk.Label(
            progress_header,
            text="0%",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_GREY,
            bg=BG_PANEL
        )
        self.progress_percent_label.pack(side=tk.RIGHT)

        counter_row = tk.Frame(
            prog_frame,
            bg=BG_PANEL
        )
        counter_row.pack(
            fill=tk.X,
            pady=(3, 0)
        )

        self.completed_count_label = tk.Label(
            counter_row,
            text="Completed: 0",
            font=FONT_SMALL,
            fg=TEXT_GREEN,
            bg=BG_PANEL
        )
        self.completed_count_label.pack(
            side=tk.LEFT
        )

        self.failed_count_label = tk.Label(
            counter_row,
            text="Failed: 0",
            font=FONT_SMALL,
            fg=TEXT_GREY,
            bg=BG_PANEL
        )
        self.failed_count_label.pack(
            side=tk.RIGHT
        )

        self.progress_var = tk.DoubleVar(value=0)

        self.progress_bar = tk.Frame(
            prog_frame,
            bg="#f3f3f3",
            height=30,
            highlightthickness=1,
            highlightbackground=ACCENT
        )

        self.progress_bar.pack(
            fill=tk.X,
            pady=(2, 2)
        )

        self.progress_bar.pack_propagate(False)

        self.progress_fill = tk.Frame(
            self.progress_bar,
            bg=ACCENT,
            height=30
        )

        self.progress_fill.place(
            x=0,
            y=0,
            relheight=1,
            relwidth=0
        )


        def _update_custom_progress(*args):
            value = self.progress_var.get()

            value = max(
                0,
                min(100, value)
            )

            self.progress_fill.place_configure(
                relwidth=value / 100
            )


        self.progress_var.trace_add(
            "write",
            _update_custom_progress
        )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    def _build_log(self, parent):
        header_row = tk.Frame(parent, bg=BG_DARK)
        header_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            header_row,
            text="MIGRATION LOG",
            font=FONT_HEADING,
            fg=TEXT_WHITE,
            bg=BG_DARK,
            anchor=tk.CENTER
        ).pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True
        )

        self._btn(header_row, "Clear Log", self._clear_log).pack(side=tk.RIGHT)

        self._btn(
            header_row,
            "Reports Folder",
            self._open_reports_folder
        ).pack(
            side=tk.RIGHT,
            padx=(0, 6)
        )

        self._btn(
            header_row,
            "Technical Report",
            self._export_latest_technical_report
        ).pack(
            side=tk.RIGHT,
            padx=(0, 6)
        )

        self._btn(
            header_row,
            "User Report",
            self._export_latest_user_report
        ).pack(
            side=tk.RIGHT,
            padx=(0, 6)
        )



        log_frame = tk.Frame(parent, bg=BG_PANEL, bd=0)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame,
            font=FONT_MONO,
            bg=BG_PANEL,
            fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE,
            relief=tk.FLAT,
            state=tk.DISABLED,
            wrap=tk.WORD,
            bd=10,
            selectbackground=BG_CARD,
            selectforeground=TEXT_WHITE
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(
            log_frame,
            command=self.log_text.yview,
            bg=BG_CARD,
            troughcolor=BG_PANEL
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        self.log_text.tag_config("green", foreground=TEXT_GREEN)
        self.log_text.tag_config("orange", foreground=TEXT_GREEN)
        self.log_text.tag_config("red", foreground=TEXT_RED)
        self.log_text.tag_config("yellow", foreground=TEXT_YELLOW)
        self.log_text.tag_config("grey", foreground=TEXT_GREY)
        self.log_text.tag_config("white", foreground=TEXT_WHITE)
        self.log_text.tag_config(
            "bold",
            foreground=TEXT_WHITE,
            font=("Segoe UI", 10, "bold")
        )

    # --------------------------------------------------------
    # UI HELPERS
    # --------------------------------------------------------

    def _card(self, parent, title):
        frame = tk.Frame(
            parent,
            bg=BG_PANEL,
            pady=2,
            padx=10
        )

        frame.pack(
            fill=tk.X,
            pady=(0, 3)
        )

        tk.Label(
            frame,
            text=title,
            font=FONT_BOLD,
            fg=TEXT_GREY,
            bg=BG_PANEL
        ).pack(
            anchor=tk.W,
            pady=(0, 3)
        )

        return frame


    def _btn(self, parent, text, command, danger=False):
        base = BTN_DANGER if danger else BTN_COLOR
        hover = BTN_DANGER_H if danger else BTN_HOVER

        btn = tk.Button(
            parent,
            text=text,
            font=FONT_SMALL,
            fg=TEXT_WHITE,
            bg=base,
            activebackground=hover,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=12,
            pady=5,
            command=command
        )

        btn.bind("<Enter>", lambda event: btn.config(bg=hover))
        btn.bind("<Leave>", lambda event: btn.config(bg=base))
        self.migration_controls.append(btn)

        return btn

    def _op_btn(self, parent, text, value):
        btn = tk.Button(
            parent,
            text=text,
            font=FONT_BOLD,
            fg=TEXT_WHITE,
            bg=BTN_COLOR,
            activebackground=ACCENT,
            activeforeground=TEXT_WHITE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=16,
            pady=7,
            command=lambda selected=value: self._select_operation(selected)
        )

        btn.bind(
            "<Enter>",
            lambda event: btn.config(bg=ACCENT)
        )
        btn.bind(
            "<Leave>",
            lambda event: self._refresh_operation_button_styles()
        )
        self.migration_controls.append(btn)
        return btn

    def _refresh_operation_button_styles(self):
        self.copy_op_btn.config(
            bg=BTN_COLOR
        )

        self.move_op_btn.config(
            bg=BTN_COLOR
        )

    # --------------------------------------------------------
    # LOCK / UNLOCK MIGRATION CONTROLS
    # --------------------------------------------------------

    def _set_migration_controls_enabled(self, enabled):

        state = tk.NORMAL if enabled else tk.DISABLED

        for widget in self.migration_controls:
            try:
                widget.config(state=state)
            except tk.TclError:
                pass

    # --------------------------------------------------------
    # OPERATION
    # --------------------------------------------------------

    def _select_operation(self, value):
        self.operation_var.set(value)
        self._refresh_operation_button_styles()

        if value == "COPY":
            self.op_info_label.config(
                text=(
                    "COPY selected  •  "
                    "Original files will remain unchanged"
                ),
                fg=TEXT_GREEN
            )

        else:
            self.op_info_label.config(
                text=(
                    "MOVE selected  •  "
                    "Source deleted only after successful verification"
                ),
                fg=TEXT_YELLOW
            )

    # --------------------------------------------------------
    # LOGGING
    # --------------------------------------------------------

    def _log(self, message, tag="white"):
        def write_log():
            self.log_text.config(state=tk.NORMAL)
            time_str = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{time_str}] {message}\n", tag)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        if threading.current_thread() is threading.main_thread():
            write_log()
        else:
            self.root.after(0, write_log)

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        if not self.is_running:
            self._reset_migration_display()


    def _export_latest_user_report(self):
        reports_folder = get_reports_folder()

        try:
            report_files = [
                os.path.join(
                    reports_folder,
                    filename
                )
                for filename in os.listdir(
                    reports_folder
                )
                if (
                    filename.startswith(
                        "user_report_"
                    )
                    and filename.lower().endswith(
                        ".csv"
                    )
                )
            ]

            if not report_files:
                messagebox.showinfo(
                    "User Report",
                    "No User Report is available yet.\n\n"
                    "Complete a migration first."
                )
                return

            latest_report = max(
                report_files,
                key=os.path.getmtime
            )

            save_path = filedialog.asksaveasfilename(
                title="Save User Report",
                initialfile=os.path.basename(
                    latest_report
                ),
                defaultextension=".csv",
                filetypes=[
                    ("CSV Report", "*.csv"),
                    ("All Files", "*.*")
                ]
            )

            if not save_path:
                return

            source_path = os.path.normcase(
                os.path.abspath(latest_report)
            )

            destination_path = os.path.normcase(
                os.path.abspath(save_path)
            )

            if source_path != destination_path:
                shutil.copy2(
                    latest_report,
                    save_path
                )

            open_report = messagebox.askyesno(
                "User Report Saved",
                "The User Report was saved successfully.\n\n"
                f"{save_path}\n\n"
                "Open the report now?"
            )

            if open_report:
                os.startfile(save_path)

        except Exception as error:
            messagebox.showerror(
                "User Report Error",
                "The User Report could not be saved or opened.\n\n"
                f"Details: {error}"
            )


    def _export_latest_technical_report(self):
        reports_folder = get_reports_folder()

        try:
            technical_prefixes = (
                "verification_report_",
                "cloud_hashes_",
                "cloud_comparison_"
            )

            report_files = [
                os.path.join(
                    reports_folder,
                    filename
                )
                for filename in os.listdir(
                    reports_folder
                )
                if (
                    filename.startswith(
                        technical_prefixes
                    )
                    and filename.lower().endswith(
                        ".csv"
                    )
                )
            ]

            if not report_files:
                messagebox.showinfo(
                    "Technical Report",
                    "No Technical Report is available yet.\n\n"
                    "Complete a migration first."
                )
                return

            latest_report = max(
                report_files,
                key=os.path.getmtime
            )

            save_path = filedialog.asksaveasfilename(
                title="Save Technical Report",
                initialfile=os.path.basename(
                    latest_report
                ),
                defaultextension=".csv",
                filetypes=[
                    ("CSV Report", "*.csv"),
                    ("All Files", "*.*")
                ]
            )

            if not save_path:
                return

            source_path = os.path.normcase(
                os.path.abspath(latest_report)
            )

            destination_path = os.path.normcase(
                os.path.abspath(save_path)
            )

            if source_path != destination_path:
                shutil.copy2(
                    latest_report,
                    save_path
                )

            open_report = messagebox.askyesno(
                "Technical Report Saved",
                "The Technical Report was saved successfully.\n\n"
                f"{save_path}\n\n"
                "Open the report now?"
            )

            if open_report:
                os.startfile(save_path)

        except Exception as error:
            messagebox.showerror(
                "Technical Report Error",
                "The Technical Report could not be saved or opened.\n\n"
                f"Details: {error}"
            )

    def _open_reports_folder(self):
        try:
            reports_folder = get_reports_folder()

            os.makedirs(
                reports_folder,
                exist_ok=True
            )

            os.startfile(
                reports_folder
            )

        except Exception as error:
            messagebox.showerror(
                "Reports Folder Error",
                "The Reports Folder could not be opened.\n\n"
                f"Details: {error}"
            )



    def _apply_source_entry(self, event=None):
        """
        Accept one or more local file/folder paths typed or pasted
        directly into the SOURCE entry.
    
        Multiple paths may be separated by:
        - new lines
        - semicolons
        """

        raw_text = self.source_var.get().strip()

        if not raw_text:
            return

        # --------------------------------------------------------
        # SPLIT MULTIPLE PATHS
        # --------------------------------------------------------

        # Support:
        # path1
        # path2
        #
        # and:
        # path1 ; path2 ; path3

        raw_text = raw_text.replace("\r\n", "\n")
        raw_text = raw_text.replace("\r", "\n")

        parts = []

        for line in raw_text.split("\n"):
            for item in line.split(";"):
                item = item.strip().strip('"')

                if item:
                    parts.append(item)

        if not parts:
            return

        # --------------------------------------------------------
        # VALIDATE ALL PATHS FIRST
        # --------------------------------------------------------

        valid_paths = []
        invalid_paths = []

        for raw_path in parts:
            path = os.path.normpath(raw_path)

            if os.path.exists(path):
                valid_paths.append(path)
            else:
                invalid_paths.append(path)

        if invalid_paths:
            messagebox.showerror(
                "Invalid Source",
                "The following source path(s) do not exist:\n\n"
                + "\n".join(invalid_paths)
            )

            for path in invalid_paths:
                self._log(
                    f"Invalid source path: {path}",
                    "red"
                )

            return

        # --------------------------------------------------------
        # SWITCH FROM CLOUD TO LOCAL
        # --------------------------------------------------------

        if self.cloud_source is not None:
            self.cloud_source = None
            self.source_roots = []
            self.source_files = []

        # --------------------------------------------------------
        # ADD — DO NOT REPLACE EXISTING LOCAL SOURCES
        # --------------------------------------------------------

        added = 0

        for path in valid_paths:
            if path not in self.source_roots:
                self.source_roots.append(path)
                added += 1

        # --------------------------------------------------------
        # REFRESH DISPLAY / INVENTORY
        # --------------------------------------------------------

        self._refresh_source_label()

        if added:
            self._log(
                f"Added {added} source"
                f"{'s' if added != 1 else ''} from manual entry",
                "green"
            )

        self.status_var.set(
            f"Local source ready — "
            f"{len(self.source_files)} file(s)"
        )


    def _browse_file(self):
        paths = filedialog.askopenfilenames(
            title="Select one or more files to migrate"
        )

        if not paths:
            return

        # If the user previously selected a cloud source,
        # choosing local files means they are switching back
        # to LOCAL source mode.
        if self.cloud_source is not None:
            self.cloud_source = None
            self.source_roots = []
            self.source_files = []

        added = 0

        for path in paths:
            path = os.path.normpath(path)
            if path not in self.source_roots:
                self.source_roots.append(path)
                added += 1

        if added:
            self._refresh_source_label()
            self._log(
                f"Added {added} file{'s' if added != 1 else ''}",
                "green"
            )

    def _browse_folder(self):
        path = filedialog.askdirectory(title="Select a folder to migrate")

        if path:

            # Switching from CLOUD source back to LOCAL source.
            if self.cloud_source is not None:
                self.cloud_source = None
                self.source_roots = []
                self.source_files = []

            path = os.path.normpath(path)
            if path not in self.source_roots:
                self.source_roots.append(path)
                self._refresh_source_label()
                self._log(f"Added folder: {path}", "green")


    def _browse_cloud_source(self):
        result = select_cloud_location(
            self.root,
            "Select Cloud Source",
            allow_files=True
        )

        if not result:
            return

        # Cloud and local source selections must not be mixed.
        self.source_roots = []
        self.source_files = []

        self.cloud_source = result

        self.source_summary_label.config(
            text="Cloud source selected",
            fg=TEXT_GREEN
        )

        remote = result["remote"]
        path = result["path"]

        if path:
            display = f"{remote}:{path}"
        else:
            display = f"{remote}:"

        self._set_source_display(
            f"☁  CLOUD SOURCE\n{display}",
            TEXT_GREEN
        )

        self._log(
            f"Cloud source selected: {display}",
            "green"
        )

        self.status_var.set(
            f"Cloud source ready — {display}"
        )

    def _clear_source(self):
        self.source_roots = []
        self.source_files = []
        self.cloud_source = None
        self.source_var.set("")

        self._refresh_source_label()

        self._log(
            "Source selection cleared",
            "grey"
        )

        self._reset_migration_display()


    def _set_source_display(self, text, color=None):
        """
        Safely update the fixed-height scrollable
        SOURCE selection display.
        """

        self.source_label.config(
            state=tk.NORMAL
        )

        self.source_label.delete(
            "1.0",
            tk.END
        )

        self.source_label.insert(
            "1.0",
            text
        )

        if color is not None:
            self.source_label.config(
                fg=color
            )

        self.source_label.config(
            state=tk.DISABLED
        )

        # Return view to the beginning after refresh.
        self.source_label.yview_moveto(0)


    def _refresh_source_label(self):
        if not self.source_roots:
            self.source_summary_label.config(
                text="No local source selected",
                fg=TEXT_GREY
            )
            self.source_var.set("")

            self._set_source_display(
                "No source selected",
                TEXT_GREY
            )

            return

        lines = []

        # Keep the manual-entry box clean.
        # The selected sources are shown in the list below.
        self.source_var.set("")

        for path in self.source_roots:
            kind = "[FILE]  " if os.path.isfile(path) else "[FOLDER]"
            lines.append(f"{kind}  {path}")

        self._set_source_display(
            "\n".join(lines),
            TEXT_GREEN
        )

        self.source_files = self._silent_call(
            _expand_sources,
            self.source_roots
        )

        count = len(self.source_files)

        root_count = len(self.source_roots)

        self.source_summary_label.config(
            text=(
                f"{root_count} source selection"
                f"{'s' if root_count != 1 else ''}"
                f"  •  {count} file"
                f"{'s' if count != 1 else ''} ready"
            ),
            fg=TEXT_GREEN
        )

        self._log(
            f"Source updated — {count} file(s) found",
            "grey"
        )

    def _apply_destination_entry(self, event=None):
        """
        Accept a local destination folder typed or pasted
        directly into the DESTINATION entry.
        """

        raw_path = self.dest_var.get().strip()

        if not raw_path:
            return

        # Allow paths copied with surrounding quotes.
        raw_path = raw_path.strip('"')

        path = os.path.normpath(raw_path)

        # Destination must be an existing folder.
        if not os.path.isdir(path):
            messagebox.showerror(
                "Invalid Destination",
                "The destination folder does not exist:\n\n"
                f"{path}"
            )

            self._log(
                f"Invalid destination path: {path}",
                "red"
            )

            return

        # Manually entering a local destination switches
        # away from cloud-destination mode.
        self.cloud_destination = None

        # Store the normalized accepted destination.
        self.dest_var.set(path)

        self.destination_summary_label.config(
            text="Local destination selected",
            fg=TEXT_GREEN
        )

        self._log(
            f"Destination set: {path}",
            "green"
        )

        self.status_var.set(
            "Local destination ready"
        )

    

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    def _browse_destination(self):
        path = filedialog.askdirectory(
            title=(
                "Select DESTINATION ROOT folder — "
                "program creates subfolders automatically"
            )
        )

        if path:
            path = os.path.normpath(path)

            self.cloud_destination = None
            self.dest_var.set(path)

            self.destination_summary_label.config(
                text="Local destination selected",
                fg=TEXT_GREEN
            )

            self._log(
                f"Destination set: {path}",
                "green"
            )


    def _browse_cloud_destination(self):
        result = select_cloud_location(
            self.root,
            "Select Cloud Destination"
        )

        if not result:
            return

        self.cloud_destination = result

        remote = result["remote"]
        path = result["path"]

        if path:
            display = f"{remote}:{path}"
        else:
            display = f"{remote}:"

        self.dest_var.set(display)

        self.destination_summary_label.config(
            text="Cloud destination selected",
            fg=TEXT_GREEN
        )

        self._log(
            f"Cloud destination selected: {display}",
            "green"
        )

        self.disk_label.config(
            text=(
                "☁ Cloud destination selected\n"
                "Local disk-space check is not required"
            ),
            fg=TEXT_GREEN
        )

        self.status_var.set(
            f"Cloud destination ready — {display}"
        )


    def _clear_destination(self):
        self.dest_var.set("")

        self.destination_summary_label.config(
            text="No destination selected",
            fg=TEXT_GREY
        )

        self.cloud_destination = None

        self._log(
            "Destination selection cleared",
            "grey"
        )

        self._reset_migration_display()


    # --------------------------------------------------------
    # DISK SPACE
    # --------------------------------------------------------



    # --------------------------------------------------------
    # DISK SPACE
    # --------------------------------------------------------

    def _update_disk_space(self, *args):
        path = self.dest_var.get().strip()

        if not path or not os.path.exists(path):
            self.disk_label.config(
                text="Select a destination folder to check available space",
                fg=TEXT_GREY
            )
            return

        try:
            usage = shutil.disk_usage(path)

            def fmt(size):
                for unit in ["bytes", "KB", "MB", "GB", "TB"]:
                    if size < 1024:
                        return f"{size:.1f} {unit}"
                    size /= 1024
                return f"{size:.1f} PB"

            free_pct = (usage.free / usage.total) * 100

            color = (
                TEXT_GREEN if free_pct > 20 else
                TEXT_YELLOW if free_pct > 10 else
                TEXT_RED
            )

            self.disk_label.config(
                text=(
                    f"Total: {fmt(usage.total)}    "
                    f"Used: {fmt(usage.used)}    "
                    f"Free: {fmt(usage.free)} ({free_pct:.1f}%)"
                ),
                fg=color
            )

        except Exception:
            self.disk_label.config(
                text="Could not read disk space",
                fg=TEXT_GREY
            )

    # --------------------------------------------------------
    # START MIGRATION
    # --------------------------------------------------------

    def _start_migration(self):
                # ----------------------------------------------------
        # CLOUD MIGRATION ROUTING
        # ----------------------------------------------------

        source_is_cloud = self.cloud_source is not None
        destination_is_cloud = self.cloud_destination is not None

        if source_is_cloud or destination_is_cloud:

            operation = self.operation_var.get()


            # --------------------------------------------
            # Validate CLOUD SOURCE / LOCAL SOURCE
            # --------------------------------------------

            if not source_is_cloud and not self.source_roots:
                messagebox.showerror(
                    "No Source Selected",
                    "Please select a local or cloud source."
                )
                return

            # --------------------------------------------
            # Validate CLOUD DESTINATION / LOCAL DESTINATION
            # --------------------------------------------

            local_destination = None

            if not destination_is_cloud:

                local_destination = self.dest_var.get().strip()

                if not local_destination:
                    messagebox.showerror(
                        "No Destination",
                        "Please select a local destination folder."
                    )
                    return

                if not os.path.isdir(local_destination):
                    messagebox.showerror(
                        "Destination Not Found",
                        "The selected local destination folder "
                        "does not exist."
                    )
                    return

            # --------------------------------------------
            # Build readable confirmation text
            # --------------------------------------------

            if source_is_cloud:
                source_remote = self.cloud_source["remote"]
                source_path = self.cloud_source["path"]

                source_display = (
                    f"{source_remote}:{source_path}"
                    if source_path
                    else f"{source_remote}:"
                )
            else:
                source_display = self.source_roots[0]

            if destination_is_cloud:
                destination_remote = self.cloud_destination["remote"]
                destination_path = self.cloud_destination["path"]

                destination_display = (
                    f"{destination_remote}:{destination_path}"
                    if destination_path
                    else f"{destination_remote}:"
                )
            else:
                destination_display = local_destination

            confirmed = messagebox.askyesno(
                "Confirm Cloud COPY",
                "Cloud migration is ready.\n\n"
                f"Source:\n{source_display}\n\n"
                f"Destination:\n{destination_display}\n\n"
                "Operation: COPY\n\n"
                "Original source files will be kept.\n\n"
                "Start cloud migration?"
            )

            if not confirmed:
                return

            self.stop_requested = False
            self.is_running = True

            self.start_btn.config(
                state=tk.DISABLED,
                text="☁   CLOUD MIGRATION IN PROGRESS...",
                bg=BG_CARD
            )

            self._set_migration_controls_enabled(False)

            self._clear_log()
            self._start_progress_animation()

            thread = threading.Thread(
                target=self._run_cloud_migration,
                args=(
                    operation,
                    local_destination
                ),
                daemon=True
            )

            thread.start()
            return
        
        if not self.source_roots:
            messagebox.showerror(
                "No Source Selected",
                "Please select at least one source file or folder."
            )
            return

        destination = self.dest_var.get().strip()

        if not destination:
            messagebox.showerror(
                "No Destination",
                "Please select a destination folder."
            )
            return

        if (
            not self._resume_mode
            and not os.path.isdir(destination)
        ):
            messagebox.showerror(
                "Destination Not Found",
                f"This destination folder does not exist:\n{destination}\n\n"
                "Create it first then try again."
            )
            return

        if not self.source_files:

            # STEP 22 — during RESUME, use the saved file list.
            # The real existence/mismatch checks happen later
            # inside validate_resume_context().
            if self._resume_mode and self._resume_state_file:

                loaded_state, _ = load_resume_state(
                    self._resume_state_file
                )

                if loaded_state:
                    self.source_files = loaded_state.get(
                        "all_files",
                        []
                    )

            else:
                self.source_files = self._silent_call(
                    _expand_sources,
                    self.source_roots
                )

        if not self.source_files:
            messagebox.showerror(
                "No Files Found",
                "No files were found in the selected source(s).\n\n"
                "Check that the folder is not empty."
            )
            return

        operation = self.operation_var.get()

        total_count = len(self.source_files)

        if self._resume_mode:
            already_verified_count = len(
                self._resume_verified_set
            )

            remaining_count = max(
                0,
                total_count - already_verified_count
            )

            file_count_text = (
                f"Total files:          {total_count}\n"
                f"Already verified:     {already_verified_count}\n"
                f"Remaining:            {remaining_count}\n"
            )

        else:
            file_count_text = (
                f"Files to migrate:  {total_count}\n"
            )

        if operation == "MOVE":
            confirmed = messagebox.askyesno(
                "Confirm MOVE Operation",
                f"You have selected MOVE.\n\n"
                f"{file_count_text}"
                f"Destination:  {destination}\n\n"
                "Source files will be permanently DELETED\n"
                "after ALL files are verified.\n\n"
                "If any file fails verification, nothing is deleted.\n\n"
                "Proceed?"
            )
        else:
            confirmed = messagebox.askyesno(
                "Confirm COPY Operation",
                f"{file_count_text}"
                f"Destination:  {destination}\n\n"
                "Original files will be kept.\n\n"
                "Start migration?"
            )

        if not confirmed:
            return
        
        self.stop_requested = False
        self.is_running = True
        self.start_btn.config(
            state=tk.DISABLED,
            text="⏳   MIGRATION IN PROGRESS...",
            bg=BG_CARD
        )
        self._set_migration_controls_enabled(False)

        self._clear_log()
        self._start_progress_animation()

        thread = threading.Thread(
            target=self._run_migration,
            args=(operation, destination),
            daemon=True
        )
        thread.start()

    def _run_cloud_migration(
        self,
        operation,
        local_destination=None
    ):
        """
        Route migrations involving cloud storage.

        Supported:
            LOCAL -> CLOUD
            CLOUD -> LOCAL
            CLOUD -> CLOUD

        LOCAL -> LOCAL continues using the existing migration engine.
        """
        logger = None
        cloud_source_info = []
        cloud_source_by_path = {}

        verification_results = []
        verification_failed = 0
        resume = None
        cloud_resume_files = []

        try:
            source_is_cloud = self.cloud_source is not None
            destination_is_cloud = self.cloud_destination is not None

            def cloud_progress(line):
                self._log(
                    f"[CLOUD] {line}",
                    "grey"
                )

                progress_line = line.strip()

                # rclone reports the active file in this format:
                # * filename.ext: 93% / 20 MiB
                if not progress_line.startswith("*"):
                    return

                filename_match = re.match(
                    r"^\*\s+(.+?):\s*\d+(?:\.\d+)?%\s*/",
                    progress_line
                )

                if filename_match is None:
                    return

                cloud_file = filename_match.group(1).strip()

                # Support cloud paths containing folders.
                display_name = cloud_file.replace(
                    "\\",
                    "/"
                ).rsplit("/", 1)[-1]

                # Prevent a long cloud filename from overlapping
                # the percentage displayed on the right.
                if len(display_name) > 34:
                    display_name = (
                        "..."
                        + display_name[-31:]
                    )

                def update_cloud_filename():
                    self.progress_label.config(
                        text=f"Cloud transfer: {display_name}",
                        fg=TEXT_GREEN
                    )

                self.root.after(
                    0,
                    update_cloud_filename
                )


            
            def cloud_stop_requested():
                return self.stop_requested

            # --------------------------------------------
            # PERMANENT CLOUD MIGRATION LOG
            # --------------------------------------------
            logs_folder = get_logs_folder()
            logger = MigrationLogger(logs_folder)


            # --------------------------------------------
            # BUILD READABLE SOURCE / DESTINATION VALUES
            # --------------------------------------------

            if source_is_cloud:
                source_remote = self.cloud_source["remote"]
                source_path = self.cloud_source["path"]

                source_display = (
                    f"{source_remote}:{source_path}"
                    if source_path
                    else f"{source_remote}:"
                )

                source_roots_for_log = [source_display]

            else:
                source_roots_for_log = list(self.source_roots)

            if destination_is_cloud:
                destination_remote = self.cloud_destination["remote"]
                destination_path = self.cloud_destination["path"]

                destination_display = (
                    f"{destination_remote}:{destination_path}"
                    if destination_path
                    else f"{destination_remote}:"
                )

            else:
                destination_display = local_destination

                logger.start(
                operation,
                source_roots_for_log,
                destination_display,
                0
            )

            logger.info(
                "[CLOUD] Cloud migration mode"
            )

            self._log("=" * 45, "grey")
            self._log("CLOUD MIGRATION", "bold")
            self._log(f"Operation:    {operation}", "white")

            reports_folder = get_reports_folder()

            # ------------------------------------------------
            # CLOUD SOURCE INVENTORY
            # ------------------------------------------------

            if source_is_cloud:

                source_remote = self.cloud_source["remote"]
                source_path = self.cloud_source["path"]

                self._log(
                    "Creating cloud source inventory...",
                    "grey"
                )

                ok_inventory, cloud_file_info = get_cloud_file_info(
                    source_remote,
                    source_path
                )

                if not ok_inventory:
                    self._log(
                        f"✗ Cloud inventory failed: {cloud_file_info}",
                        "red"
                    )

                    self._migration_done(
                        success=False
                    )
                    return

                if not cloud_file_info:
                    self._log(
                        "✗ No files found in the selected cloud source.",
                        "red"
                    )

                    self._migration_done(
                        success=False
                    )
                    return
                # Keep the PRE-COPY cloud information in memory.
                # C9 will compare this against the destination
                # after the transfer finishes.

                cloud_source_info = cloud_file_info

                cloud_source_by_path = {
                    item["path"].replace("\\", "/").strip("/"): item
                    for item in cloud_source_info
                }

                inventory_file = save_cloud_hash_report(
                    source_remote,
                    source_path,
                    cloud_file_info,
                    reports_folder
                )

                self._log(
                    f"✓ Cloud inventory created — "
                    f"{len(cloud_file_info)} file(s)",
                    "orange"
                )

                self._log(
                    f"✓ Inventory report: {inventory_file}",
                    "grey"
                )

                logger.info(
                    f"[CLOUD] Files discovered: {len(cloud_file_info)}"
                )

                logger.inventory_created(
                    inventory_file,
                    len(cloud_file_info)
                )

                logger.inventory_report(
                    inventory_file
                )

                # --------------------------------------------
                # CLOUD RESUME STATE
                # --------------------------------------------

                cloud_resume_files = [
                    item["path"].replace("\\", "/").strip("/")
                    for item in cloud_file_info
                ]

                resume = ResumeManager(
                    get_logs_folder()
                )

                self._active_resume = resume

                # --------------------------------------------
                # RESUME EXISTING CLOUD MIGRATION
                # --------------------------------------------

                if self._resume_mode and self._resume_state_file:

                    loaded = resume.load_existing(
                        self._resume_state_file
                    )

                    if not loaded:
                        raise RuntimeError(
                            "Could not load the existing "
                            "cloud resume state."
                        )

                    logger.info(
                        f"[CLOUD RESUME] Existing state loaded — "
                        f"{len(resume._verified_set)} already verified"
                    )
                    # --------------------------------------------
                    # RECONCILE INTERRUPTED CLOUD MOVE DELETE
                    # --------------------------------------------

                    if operation == "MOVE":

                        pending_delete = resume.state.get(
                            "pending_delete"
                        )

                        if pending_delete:

                            pending_delete = (
                                str(pending_delete)
                                .replace("\\", "/")
                                .strip("/")
                            )

                            current_cloud_file_set = {
                                str(path)
                                .replace("\\", "/")
                                .strip("/")
                                for path in cloud_resume_files
                            }

                            if pending_delete in current_cloud_file_set:

                                # File still exists in cloud.
                                # Previous deletion did not complete,
                                # so it is safe to try again later.
                                resume.clear_delete_pending()

                                logger.info(
                                    f"[CLOUD MOVE] Pending delete "
                                    f"still exists — will retry: "
                                    f"{pending_delete}"
                                )

                                self._log(
                                    f"[RESUME] Pending cloud delete "
                                    f"will be retried: {pending_delete}",
                                    "yellow"
                                )

                            else:

                                # File is missing from cloud AND it
                                # was specifically recorded as the
                                # file being deleted when interrupted.
                                # Convert it into a completed deletion
                                # checkpoint before validation.
                                resume.mark_deleted(
                                    pending_delete
                                )

                                resume.clear_delete_pending()

                                logger.info(
                                    f"[CLOUD MOVE] Recovered completed "
                                    f"pending deletion: {pending_delete}"
                                )

                                self._log(
                                    f"[RESUME] Recovered deleted file: "
                                    f"{pending_delete}",
                                    "yellow"
                                )

                    valid, reason = resume.validate_resume_context(
                        operation=operation,
                        source_roots=[source_display],
                        destination=destination_display,
                        source_files=cloud_resume_files
                    )

                    if not valid:
                        resume.mark_interrupted()

                        logger.error(
                            f"[CLOUD RESUME] Validation failed — {reason}"
                        )

                        self._log(
                            f"✗ RESUME VALIDATION FAILED: {reason}",
                            "red"
                        )

                        self._migration_done(
                            success=False
                        )
                        return

                    self._resume_verified_set = set(
                        resume._verified_set
                    )

                    self._log(
                        f"[RESUME] "
                        f"{len(self._resume_verified_set)} "
                        f"already verified",
                        "yellow"
                    )

                    logger.info(
                        f"[CLOUD RESUME] Validation passed"
                    )

                # --------------------------------------------
                # START NEW CLOUD MIGRATION
                # --------------------------------------------

                else:

                    timestamp = datetime.now().strftime(
                        "%Y%m%d_%H%M%S"
                    )

                    resume.start(
                        operation=operation,
                        source_roots=[source_display],
                        destination=destination_display,
                        source_files=cloud_resume_files,
                        timestamp=timestamp
                    )

                    resume.state["migration_type"] = (
                        "CLOUD_TO_LOCAL"
                        if source_is_cloud and not destination_is_cloud
                        else
                        "CLOUD_TO_CLOUD"
                        if source_is_cloud and destination_is_cloud
                        else
                        "LOCAL_TO_CLOUD"
                    )

                    resume.state["cloud_source"] = (
                        dict(self.cloud_source)
                        if self.cloud_source is not None
                        else None
                    )

                    resume.state["cloud_destination"] = (
                        dict(self.cloud_destination)
                        if self.cloud_destination is not None
                        else None
                    )

                    resume._save()

                    logger.info(
                        f"[CLOUD RESUME] State created — "
                        f"{len(cloud_resume_files)} file(s)"
                    )

            # --------------------------------------------
            # LOCAL -> CLOUD RESUME STATE
            # --------------------------------------------

            if not source_is_cloud and destination_is_cloud:

                if len(self.source_roots) != 1:
                    raise RuntimeError(
                        "Cloud upload currently requires exactly "
                        "one local source selection."
                    )

                local_source = self.source_roots[0]

                # Resume paths must be relative to the selected
                # local root because rclone --include expects
                # paths relative to that root.
                cloud_resume_files = [
                    os.path.relpath(
                        file_path,
                        local_source
                    )
                    .replace("\\", "/")
                    .strip("/")
                    for file_path in self.source_files
                ]

                resume = ResumeManager(
                    get_logs_folder()
                )

                self._active_resume = resume

                # ----------------------------------------
                # RESUME EXISTING LOCAL -> CLOUD
                # ----------------------------------------

                if self._resume_mode and self._resume_state_file:

                    loaded = resume.load_existing(
                        self._resume_state_file
                    )

                    if not loaded:
                        raise RuntimeError(
                            "Could not load the existing "
                            "local-to-cloud resume state."
                        )

                    valid, reason = resume.validate_resume_context(
                        operation=operation,
                        source_roots=[local_source],
                        destination=destination_display,
                        source_files=cloud_resume_files
                    )

                    if not valid:

                        resume.mark_interrupted()

                        logger.error(
                            f"[CLOUD RESUME] "
                            f"Validation failed — {reason}"
                        )

                        self._log(
                            f"✗ RESUME VALIDATION FAILED: {reason}",
                            "red"
                        )

                        self._migration_done(
                            success=False
                        )

                        return

                    self._resume_verified_set = set(
                        resume._verified_set
                    )

                    # ----------------------------------------
                    # LOCAL -> CLOUD RESUME RECONCILIATION
                    #
                    # Check what actually exists in the cloud.
                    # A file is safe to skip only when the
                    # cloud copy still matches the local file.
                    # ----------------------------------------

                    destination_remote = (
                        self.cloud_destination["remote"]
                    )

                    destination_path = (
                        self.cloud_destination["path"]
                    )

                    cloud_ok, destination_cloud_info = (
                        get_cloud_file_info(
                            destination_remote,
                            destination_path
                        )
                    )

                    if not cloud_ok:
                        resume.mark_interrupted()

                        self._log(
                            "✗ Could not inspect cloud destination "
                            "for resume validation.",
                            "red"
                        )

                        logger.error(
                            "[CLOUD RESUME] Could not inspect "
                            "local-to-cloud destination"
                        )

                        self._migration_done(
                            success=False
                        )

                        return

                    destination_by_path = {
                        item["path"]
                        .replace("\\", "/")
                        .strip("/"): item

                        for item in destination_cloud_info
                    }

                    for relative_path in cloud_resume_files:

                        local_file = os.path.join(
                            local_source,
                            *relative_path.split("/")
                        )

                        cloud_item = destination_by_path.get(
                            relative_path
                        )

                        still_valid = False

                        if (
                            cloud_item is not None
                            and os.path.isfile(local_file)
                        ):
                            try:
                                local_size = os.path.getsize(
                                    local_file
                                )

                                cloud_size = cloud_item.get(
                                    "size"
                                )

                                local_md5 = (
                                    calculate_hashes(
                                        local_file
                                    )["md5"] or ""
                                ).lower()

                                cloud_md5 = (
                                    cloud_item.get("md5") or ""
                                ).lower()

                                size_matches = (
                                    cloud_size is None
                                    or int(cloud_size)
                                    == local_size
                                )

                                hash_matches = (
                                    bool(cloud_md5)
                                    and cloud_md5
                                    == local_md5
                                )

                                still_valid = (
                                    size_matches
                                    and hash_matches
                                )

                            except Exception as error:

                                still_valid = False

                                logger.info(
                                    f"[CLOUD RESUME] Could not "
                                    f"revalidate {relative_path}: "
                                    f"{error}"
                                )

                        if still_valid:

                            if not resume.is_verified(
                                relative_path
                            ):
                                resume.mark_verified(
                                    relative_path
                                )

                            logger.info(
                                f"[CLOUD RESUME] "
                                f"{relative_path} already exists "
                                f"and matches — safe to skip"
                            )

                        else:

                            if resume.is_verified(
                                relative_path
                            ):
                                resume.unmark_verified(
                                    relative_path
                                )

                    self._resume_verified_set = set(
                        resume._verified_set
                    )

                    self._log(
                        f"[RESUME] "
                        f"{len(self._resume_verified_set)} "
                        f"already verified",
                        "yellow"
                    )

                    logger.info(
                        "[CLOUD RESUME] "
                        "Local-to-cloud validation passed"
                    )

                # ----------------------------------------
                # START NEW LOCAL -> CLOUD
                # ----------------------------------------

                else:

                    timestamp = datetime.now().strftime(
                        "%Y%m%d_%H%M%S"
                    )

                    resume.start(
                        operation=operation,
                        source_roots=[local_source],
                        destination=destination_display,
                        source_files=cloud_resume_files,
                        timestamp=timestamp
                    )

                    resume.state["migration_type"] = (
                        "LOCAL_TO_CLOUD"
                    )

                    resume.state["cloud_source"] = None

                    resume.state["cloud_destination"] = (
                        dict(self.cloud_destination)
                    )

                    resume._save()

                    logger.info(
                        f"[CLOUD RESUME] "
                        f"Local-to-cloud state created — "
                        f"{len(cloud_resume_files)} file(s)"
                    )


            # --------------------------------------------
            # CLOUD RESUME — DETERMINE REMAINING FILES
            # --------------------------------------------

            # --------------------------------------------
            # CLOUD RESUME — REVALIDATE VERIFIED FILES
            # BEFORE DECIDING WHAT RCLONE MAY SKIP
            # --------------------------------------------

            if (
                self._resume_mode
                and source_is_cloud
                and not destination_is_cloud
            ):

                stale_verified_files = set()

                for relative_path in list(
                    self._resume_verified_set
                ):

                    normalized_path = (
                        str(relative_path)
                        .replace("\\", "/")
                        .strip("/")
                    )

                    source_item = cloud_source_by_path.get(
                        normalized_path
                    )

                    destination_file = os.path.join(
                        local_destination,
                        *normalized_path.split("/")
                    )

                    still_valid = False

                    if (
                        source_item is not None
                        and os.path.isfile(destination_file)
                    ):

                        try:
                            source_size = source_item.get(
                                "size"
                            )

                            destination_size = os.path.getsize(
                                destination_file
                            )

                            source_md5 = (
                                source_item.get("md5") or ""
                            ).lower()

                            # Size must always agree when available.
                            size_matches = (
                                source_size is None
                                or int(source_size)
                                == destination_size
                            )

                            hash_matches = True

                            # Google Drive normally provides MD5.
                            # If MD5 exists, use it as the stronger
                            # integrity check.
                            if source_md5:
                                destination_hashes = calculate_hashes(
                                    destination_file
                                )

                                destination_md5 = (
                                    destination_hashes["md5"] or ""
                                ).lower()

                                hash_matches = (
                                    source_md5
                                    == destination_md5
                                )

                            still_valid = (                               
                                size_matches
                                and hash_matches
                            )

                        except Exception as error:
                            still_valid = False

                            logger.info(
                                f"[CLOUD RESUME] Could not "
                                f"revalidate {normalized_path}: "
                                f"{error}"
                            )

                    if still_valid:

                        logger.info(
                            f"[CLOUD RESUME] "
                            f"{normalized_path} remains valid "
                            f"— safe to skip"
                        )

                    else:

                        stale_verified_files.add(
                            normalized_path
                        )

                        resume.unmark_verified(
                            normalized_path
                        )

                        self._log(
                            f"[RESUME] STALE: "
                            f"{normalized_path} "
                            f"will be copied again",
                            "yellow"
                        )

                        logger.info(
                            f"[CLOUD RESUME] "
                            f"{normalized_path} is stale or "
                            f"missing — scheduled for re-copy"
                        )

                # Synchronize GUI's in-memory set with the
                # corrected persistent resume checkpoint.
                self._resume_verified_set = set(
                    resume._verified_set
                )

            # --------------------------------------------
            # CLOUD RESUME — DETERMINE REMAINING FILES
            # --------------------------------------------

            if self._resume_mode:

                remaining_cloud_files = [
                    path
                    for path in cloud_resume_files
                    if path not in self._resume_verified_set
                ]

            else:

                remaining_cloud_files = list(
                    cloud_resume_files
                )

            already_verified_count = (
                len(cloud_resume_files)
                - len(remaining_cloud_files)
            )

            if self._resume_mode:
                self._log(
                    f"[RESUME] Already verified: "
                    f"{already_verified_count}",
                    "yellow"
                )

                self._log(
                    f"[RESUME] Remaining: "
                    f"{len(remaining_cloud_files)}",
                    "grey"
                )

                logger.info(
                    f"[CLOUD RESUME] "
                    f"{already_verified_count} already verified, "
                    f"{len(remaining_cloud_files)} remaining"
                )

            # --------------------------------------------
            # CLOUD -> CLOUD
            # --------------------------------------------
            if source_is_cloud and destination_is_cloud:

                source_remote = self.cloud_source["remote"]
                source_path = self.cloud_source["path"]

                destination_remote = self.cloud_destination["remote"]
                destination_path = self.cloud_destination["path"]

                source_display = (
                    f"{source_remote}:{source_path}"
                    if source_path
                    else f"{source_remote}:"
                )

                destination_display = (
                    f"{destination_remote}:{destination_path}"
                    if destination_path
                    else f"{destination_remote}:"
                )

                self._log(
                    f"Source:       {source_display}",
                    "white"
                )

                self._log(
                    f"Destination:  {destination_display}",
                    "white"
                )

                ok, message = copy_cloud_to_cloud(
                    source_remote,
                    source_path,
                    destination_remote,
                    destination_path,
                    progress_callback=cloud_progress,
                    stop_callback=cloud_stop_requested
                )
                

            # --------------------------------------------
            # CLOUD -> LOCAL
            # --------------------------------------------
            elif source_is_cloud:

                source_remote = self.cloud_source["remote"]
                source_path = self.cloud_source["path"]

                ok, message = copy_from_cloud(
                    source_remote,
                    source_path,
                    local_destination,
                    progress_callback=cloud_progress,
                    stop_callback=cloud_stop_requested,
                    files_from=remaining_cloud_files
                )

            # --------------------------------------------
            # LOCAL -> CLOUD
            # --------------------------------------------
            elif destination_is_cloud:

                destination_remote = self.cloud_destination["remote"]
                destination_path = self.cloud_destination["path"]

                # Start safely with one selected local root.
                if len(self.source_roots) != 1:
                    raise RuntimeError(
                        "Cloud upload currently requires exactly "
                        "one local source selection."
                    )

                local_source = self.source_roots[0]

                upload_files = (
                    remaining_cloud_files
                    if self._resume_mode
                    else None
                )

                ok, message = copy_to_cloud(
                    local_source,
                    destination_remote,
                    destination_path,
                    progress_callback=cloud_progress,
                    stop_callback=cloud_stop_requested,
                    files_from=upload_files
                )

            else:
                raise RuntimeError(
                    "Cloud migration was requested without "
                    "a cloud source or destination."
                )

            if ok:
                self._log(
                    f"✓ {message}",
                    "orange"
                )

                self._log(
                    "CLOUD COPY COMPLETE",
                    "bold"
                )

                logger.info(
                    f"[CLOUD] Transfer successful — {message}"
                )

                
                # ----------------------------------------
                # CLOUD -> LOCAL CHECKSUM VERIFICATION
                # ----------------------------------------

                if source_is_cloud and not destination_is_cloud:

                    self._log(
                        "Verifying downloaded files...",
                        "grey"
                    )

                    logger.info(
                        "[CLOUD] Destination verification started"
                    )

                    previously_verified_count = (
                        len(self._resume_verified_set)
                        if self._resume_mode
                        else 0
                    )

                    newly_verified_count = 0  

                    self._set_counters(
                        completed=0,
                        failed=0
                    )  

                    for source_item in cloud_source_info:

                        relative_path = (
                            source_item["path"]
                            .replace("\\", "/")
                            .strip("/")
                        )

                        destination_file = os.path.join(
                            local_destination,
                            *relative_path.split("/")
                        )

                        source_md5 = (
                            source_item.get("md5") or ""
                        ).lower()

                        source_size = source_item.get("size")

                        try:
                            destination_hashes = calculate_hashes(
                                destination_file
                            )

                            destination_md5 = (
                                destination_hashes["md5"] or ""
                            ).lower()

                            destination_size = os.path.getsize(
                                destination_file
                            )

                            md5_match = (
                                bool(source_md5)
                                and source_md5 == destination_md5
                            )

                            size_match = (
                                source_size is None
                                or source_size == destination_size
                            )

                            verified = (
                                md5_match
                                and size_match
                            )

                            verification_results.append({
                                "source_path": (
                                    f"{source_remote}:{relative_path}"
                                ),
                                "destination_path": destination_file,
                                "source_size": source_size or "",
                                "destination_size": destination_size,
                                "source_md5": source_md5,
                                "destination_md5": destination_md5,
                                "source_sha1": "",
                                "destination_sha1": (
                                    destination_hashes["sha1"]
                                ),
                                "source_sha256": "",
                                "destination_sha256": (
                                    destination_hashes["sha256"]
                                ),
                                "status": (
                                    "VERIFIED"
                                    if verified
                                    else "HASH MISMATCH"
                                )
                            })

                            if verified:

                                was_previously_verified = (
                                    relative_path
                                    in self._resume_verified_set
                                )

                                if was_previously_verified:
                                    self._log(
                                        f"  ↷ REVALIDATED: {relative_path}",
                                        "yellow"
                                    )

                                    logger.info(
                                        f"[CLOUD RESUME] "
                                        f"{relative_path} → "
                                        f"previously verified and "
                                        f"revalidated successfully"
                                    )

                                else:
                                    newly_verified_count += 1

                                    self._log(
                                        f"  ✓ {relative_path}",
                                        "orange"
                                    )

                                    logger.file_verified(
                                        relative_path,
                                        "VERIFIED"
                                    )

                                    if resume is not None:
                                        resume.mark_verified(
                                            relative_path
                                        )

                            else:
                                verification_failed += 1

                                self._log(
                                    f"  ✗ FAILED: {relative_path}",
                                    "red"
                                )

                                logger.file_verified(
                                    relative_path,
                                    "HASH_MISMATCH"
                                )

                        except Exception as error:
                            verification_failed += 1

                            verification_results.append({
                                "source_path": (
                                    f"{source_remote}:{relative_path}"
                                ),
                                "destination_path": destination_file,
                                "source_size": source_size or "",
                                "destination_size": "",
                                "source_md5": source_md5,
                                "destination_md5": "",
                                "source_sha1": "",
                                "destination_sha1": "",
                                "source_sha256": "",
                                "destination_sha256": "",
                                "status": f"ERROR: {error}"
                            })

                            self._log(
                                f"  ✗ ERROR: {relative_path} — {error}",
                                "red"
                            )

                            logger.file_verified(
                                relative_path,
                                "ERROR",
                                str(error)
                            )

                        self._set_counters(
                            completed=(
                                len(verification_results)
                                - verification_failed
                            ),
                            failed=verification_failed
                        )

                # ----------------------------------------
                # FINAL CLOUD VERIFICATION DECISION
                # ----------------------------------------

                if source_is_cloud and not destination_is_cloud:
                    report_path = os.path.join(
                        reports_folder,
                        f"verification_report_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    )

                    create_verification_report(
                        verification_results,
                        [],
                        report_path
                    )

                    self._log(
                        f"✓ Verification report: {report_path}",
                        "grey"
                    )

                    logger.verification_report(
                        report_path
                    )

                    total_verified = (
                        len(cloud_source_info)
                        - verification_failed
                    )

                    all_verified = (
                        len(verification_results)
                        == len(cloud_source_info)
                        and verification_failed == 0
                    )

                    def save_cloud_to_local_user_report(
                        extra_failed_item=None
                    ):
                        user_failed_items = []

                        for result in verification_results:
                            result_status = str(
                                result.get("status", "")
                            )

                            if result_status != "VERIFIED":
                                user_failed_items.append({
                                    "source_path": result.get(
                                        "source_path",
                                        ""
                                    ),
                                    "status": result_status
                                })

                        if extra_failed_item is not None:
                            user_failed_items.append(
                                extra_failed_item
                            )

                        user_failed_count = len(
                            user_failed_items
                        )

                        user_total_files = len(
                            cloud_source_info
                        )

                        user_successful_count = max(
                            0,
                            user_total_files
                            - user_failed_count
                        )

                        user_report_path = os.path.join(
                            reports_folder,
                            "user_report_"
                            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            ".csv"
                        )

                        self._silent_call(
                            create_user_report,
                            user_report_path,
                            operation,
                            "Cloud to Local",
                            user_total_files,
                            user_successful_count,
                            user_failed_count,
                            user_failed_items
                        )

                        self._log(
                            f"✓ User report: {user_report_path}",
                            "grey"
                        )


                    self._log("", "grey")
                    self._log("=" * 45, "grey")
                    self._log(
                        "CLOUD VERIFICATION SUMMARY",
                        "bold"
                    )

                    if (
                        self._resume_mode
                        and operation == "MOVE"
                    ):
                        original_total = len(
                            resume.state.get(
                                "all_files",
                                []
                            )
                        )

                        already_deleted = len(
                            resume.state.get(
                                "deleted_files",
                                []
                            )
                        )

                        self._log(
                            f"  Original files:       "
                            f"{original_total}",
                            "white"
                        )

                        self._log(
                            f"  Current cloud files:  "
                            f"{len(cloud_source_info)}",
                            "white"
                        )

                        self._log(
                            f"  Already deleted:      "
                            f"{already_deleted}",
                            "white"
                        )

                        self._log(
                            f"  Previously verified:  "
                            f"{previously_verified_count}",
                            "white"
                        )

                        self._log(
                            f"  Newly verified:       "
                            f"{newly_verified_count}",
                            "white"
                        )

                        self._log(
                            f"  Failed:               "
                            f"{verification_failed}",
                            "white"
                        )

                    else:
                        self._log(
                            f"  Total files:          "
                            f"{len(cloud_source_info)}",
                            "white"
                        )

                        if self._resume_mode:
                            self._log(
                                f"  Previously verified:  "
                                f"{previously_verified_count}",
                                "white"
                            )

                            self._log(
                                f"  Newly verified:       "
                                f"{newly_verified_count}",
                                "white"
                            )

                        self._log(
                            f"  Verified total:       "
                            f"{total_verified}",
                            "white"
                        )

                        self._log(
                            f"  Failed:               "
                            f"{verification_failed}",
                            "white"
                        )

                    if all_verified:
                        self._log(
                            "✓ ALL CLOUD FILES VERIFIED SUCCESSFULLY",
                            "orange"
                        )

                        logger.info(
                            "[CLOUD] All destination files verified successfully"
                        )

                        # ----------------------------------------
                        # CLOUD MOVE — DELETE SOURCE ONLY AFTER
                        # EVERY FILE HAS VERIFIED SUCCESSFULLY
                        # ----------------------------------------

                        if (
                            operation == "MOVE"
                            and source_is_cloud
                            and not destination_is_cloud
                        ):
                            self._log(
                                "Deleting verified cloud source files...",
                                "yellow"
                            )

                            for source_item in cloud_source_info:

                                relative_path = (
                                    source_item["path"]
                                    .replace("\\", "/")
                                    .strip("/")
                                )

                                # --------------------------------
                                # STOP SAFELY DURING MOVE DELETE
                                # --------------------------------

                                if self.stop_requested:

                                    if resume is not None:
                                        resume.mark_interrupted()

                                    logger.info(
                                        "[CLOUD MOVE] "
                                        "Deletion interrupted — "
                                        "progress preserved for resume"
                                    )

                                    return

                                # --------------------------------
                                # NEVER DELETE THE SAME FILE TWICE
                                # --------------------------------


                                if (
                                    resume is not None
                                    and resume.is_deleted(
                                        relative_path
                                    )
                                ):
                                    self._log(
                                        f"  ↷ SKIP DELETE: "
                                        f"{relative_path} "
                                        f"was already deleted",
                                        "yellow"
                                    )

                                    logger.info(
                                        f"[CLOUD MOVE] "
                                        f"Skip already deleted — "
                                        f"{relative_path}"
                                    )

                                    continue

                                # --------------------------------
                                # BUILD ACTUAL CLOUD FILE PATH
                                # --------------------------------

                                if source_path:
                                    cloud_delete_path = (
                                        f"{source_path.strip('/')}/"
                                        f"{relative_path}"
                                    )
                                else:
                                    cloud_delete_path = (
                                        relative_path
                                    )

                                # --------------------------------
                                # DELETE ONE VERIFIED CLOUD FILE
                                # --------------------------------

                                # Save intent BEFORE touching cloud.
                                # If the application dies during
                                # deletion, resume knows exactly
                                # which file was being processed.
                                if resume is not None:
                                    resume.mark_delete_pending(
                                        relative_path
                                    )

                                delete_ok, delete_message = (
                                    delete_cloud_file(
                                        source_remote,
                                        cloud_delete_path,
                                        progress_callback=cloud_progress,
                                        stop_callback=cloud_stop_requested
                                    )
                                )

                                if not delete_ok:

                                    if resume is not None:
                                        resume.mark_interrupted()

                                    self._log(
                                        f"  ✗ DELETE FAILED: "
                                        f"{relative_path}",
                                        "red"
                                    )

                                    logger.error(
                                        f"[CLOUD MOVE] "
                                        f"Delete failed — "
                                        f"{relative_path} — "
                                        f"{delete_message}"
                                    )

                                    save_cloud_to_local_user_report({
                                        "source_path": (
                                            f"{source_remote}:"
                                            f"{cloud_delete_path}"
                                        ),
                                        "status": (
                                            "DELETION FAILED: "
                                            f"{delete_message}"
                                        )
                                    })

                                    self._migration_done(
                                        success=False
                                    )
                                    return

                                # --------------------------------
                                # SAVE DELETION CHECKPOINT
                                # --------------------------------

                                # --------------------------------
                                # SAVE CHECKPOINT FIRST
                                # --------------------------------

                                if resume is not None:
                                    resume.mark_deleted(
                                        relative_path
                                    )

                                    resume.clear_delete_pending()

                                logger.file_deleted(
                                    relative_path
                                )

                                self._log(
                                    f"  ✓ DELETED: {relative_path}",
                                    "orange"
                                )

                        save_cloud_to_local_user_report()

                        if resume is not None:
                            resume.complete(
                                success=True
                            )
                            self._active_resume = None

                        self._migration_done(
                            success=True
                        )

                    else:
                        self._log(
                            "✗ CLOUD VERIFICATION FAILED",
                            "red"
                        )

                        logger.error(
                            f"[CLOUD] Verification failed — "
                            f"{verification_failed} file(s) failed"
                        )

                        save_cloud_to_local_user_report()

                        self._migration_done(
                            success=False
                        )

                    return


                # ----------------------------------------
                # CLOUD -> CLOUD VERIFY + COMPLETION
                # ----------------------------------------
                if source_is_cloud and destination_is_cloud:

                    def save_cloud_to_cloud_user_report(
                        successful_files,
                        failed_items,
                        total_files=None
                    ):
                        failed_count = len(
                            failed_items
                        )

                        if total_files is None:
                            resolved_total = (
                                int(successful_files)
                                + failed_count
                            )
                        else:
                            resolved_total = int(
                                total_files
                            )

                        user_report_path = os.path.join(
                            reports_folder,
                            "user_report_"
                            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            ".csv"
                        )

                        self._silent_call(
                            create_user_report,
                            user_report_path,
                            operation,
                            "Cloud to Cloud",
                            resolved_total,
                            successful_files,
                            failed_count,
                            failed_items
                        )

                        self._log(
                            f"✓ User report: {user_report_path}",
                            "grey"
                        )


                    logger.info(
                        "[CLOUD] Cloud-to-cloud transfer completed"
                    )

                    self._log(
                        "Verifying cloud destination...",
                        "grey"
                    )

                    logger.info(
                        "[CLOUD] Cloud-to-cloud verification started"
                    )

                    self._set_counters(
                        completed=0,
                        failed=0
                    )

                    compare_ok, compare_results = (
                        self._silent_call(
                            compare_clouds,
                            source_remote,
                            source_path,
                            destination_remote,
                            destination_path
                        )
                    )

                    if not compare_ok:

                        self._set_counters(
                            completed=0,
                            failed=len(cloud_source_info)
                        )

                        self._log(
                            f"✗ CLOUD VERIFICATION ERROR: "
                            f"{compare_results}",
                            "red"
                        )

                        logger.error(
                            f"[CLOUD] Cloud comparison failed — "
                            f"{compare_results}"
                        )

                        if resume is not None:
                            resume.mark_interrupted()

                        self._migration_done(
                            success=False
                        )

                        return

                    different = compare_results[
                        "different"
                    ]

                    only_in_source = compare_results[
                        "only_in_a"
                    ]

                    only_in_destination = compare_results[
                        "only_in_b"
                    ]

                    identical = compare_results[
                        "identical"
                    ]

                    all_identical = (
                        len(different) == 0
                        and len(only_in_source) == 0
                        and len(only_in_destination) == 0
                    )

                    comparison_failed_count = (
                        len(different)
                        + len(only_in_source)
                        + len(only_in_destination)
                    )

                    comparison_report_path = self._silent_call(
                        save_comparison_report,
                        compare_results,
                        reports_folder
                    )

                    self._log(
                        "✓ Technical comparison report: "
                        f"{comparison_report_path}",
                        "grey"
                    )

                    logger.verification_report(
                        comparison_report_path
                    )


                    cloud_to_cloud_failed_items = []

                    for item in different:
                        cloud_to_cloud_failed_items.append({
                            "source_path": (
                                f"{source_remote}:"
                                f"{item['file']}"
                            ),
                            "status": "HASH MISMATCH"
                        })

                    for filename in only_in_source:
                        cloud_to_cloud_failed_items.append({
                            "source_path": (
                                f"{source_remote}:"
                                f"{filename}"
                            ),
                            "status": (
                                "MISSING FROM CLOUD DESTINATION"
                            )
                        })

                    for filename in only_in_destination:
                        cloud_to_cloud_failed_items.append({
                            "source_path": (
                                f"{destination_remote}:"
                                f"{filename}"
                            ),
                            "status": (
                                "EXTRA DESTINATION FILE"
                            )
                        })


                    self._set_counters(
                        completed=len(identical),
                        failed=comparison_failed_count
                    )

                    self._log(
                        "",
                        "grey"
                    )

                    self._log(
                        "=" * 45,
                        "grey"
                    )

                    self._log(
                        "CLOUD-TO-CLOUD VERIFICATION",
                        "bold"
                    )

                    self._log(
                        f"  Identical:             "
                        f"{len(identical)}",
                        "white"
                    )

                    self._log(
                        f"  Different:             "
                        f"{len(different)}",
                        "white"
                    )

                    self._log(
                        f"  Missing destination:   "
                        f"{len(only_in_source)}",
                        "white"
                    )

                    self._log(
                        f"  Extra destination:     "
                        f"{len(only_in_destination)}",
                        "white"
                    )

                    if not all_identical:

                        self._log(
                            "✗ CLOUD-TO-CLOUD VERIFICATION FAILED",
                            "red"
                        )

                        self._log(
                            "Source files will NOT be deleted.",
                            "yellow"
                        )

                        logger.error(
                            "[CLOUD] Cloud-to-cloud verification "
                            "failed — source preserved"
                        )

                        save_cloud_to_cloud_user_report(
                            len(identical),
                            cloud_to_cloud_failed_items
                        )

                        if resume is not None:
                            resume.mark_interrupted()

                        self._migration_done(
                            success=False
                        )

                        return

                    self._log(
                        "✓ ALL CLOUD FILES VERIFIED IDENTICAL",
                        "orange"
                    )

                    logger.info(
                        "[CLOUD] Source and destination "
                        "verified identical"
                    )

                    # ----------------------------------------
                    # CLOUD -> CLOUD MOVE
                    # DELETE SOURCE ONLY AFTER VERIFICATION
                    # ----------------------------------------
                    if operation == "MOVE":

                        self._log(
                            "Deleting verified cloud source files...",
                            "yellow"
                        )

                        logger.info(
                            "[CLOUD MOVE] Safe deletion started"
                        )

                        for source_item in cloud_source_info:

                            relative_path = (
                                source_item["path"]
                                .replace("\\", "/")
                                .strip("/")
                            )

                            # Stop safely if user closes app.
                            if self.stop_requested:

                                if resume is not None:
                                    resume.mark_interrupted()

                                logger.info(
                                    "[CLOUD MOVE] Deletion "
                                    "interrupted — resume saved"
                                )

                                self._migration_done(
                                    success=False
                                )

                                return

                            # Never delete the same file twice.
                            if (
                                resume is not None
                                and resume.is_deleted(
                                    relative_path
                                )
                            ):

                                self._log(
                                    f"  ↷ SKIP DELETE: "
                                    f"{relative_path} "
                                    f"was already deleted",
                                    "yellow"
                                )

                                continue

                            # Build complete source cloud path.
                            if source_path:
                                cloud_delete_path = (
                                    f"{source_path.strip('/')}/"
                                    f"{relative_path}"
                                )
                            else:
                                cloud_delete_path = (
                                    relative_path
                                )

                            # Save deletion intent first.
                            if resume is not None:
                                resume.mark_delete_pending(
                                    relative_path
                                )

                            delete_ok, delete_message = (
                                delete_cloud_file(
                                    source_remote,
                                    cloud_delete_path,
                                    progress_callback=cloud_progress,
                                    stop_callback=cloud_stop_requested
                                )
                            )

                            if not delete_ok:

                                if resume is not None:
                                    resume.mark_interrupted()

                                self._log(
                                    f"  ✗ DELETE FAILED: "
                                    f"{relative_path}",
                                    "red"
                                )

                                logger.error(
                                    f"[CLOUD MOVE] Delete failed — "
                                    f"{relative_path} — "
                                    f"{delete_message}"
                                )

                                save_cloud_to_cloud_user_report(
                                    max(
                                        0,
                                        len(identical) - 1
                                    ),
                                    [{
                                        "source_path": (
                                            f"{source_remote}:"
                                            f"{cloud_delete_path}"
                                        ),
                                        "status": (
                                            "DELETION FAILED: "
                                            f"{delete_message}"
                                        )
                                    }],
                                    total_files=len(identical)
                                )

                                self._migration_done(
                                    success=False
                                )

                                return

                            # Record deletion only AFTER success.
                            if resume is not None:
                                resume.mark_deleted(
                                    relative_path
                                )

                                resume.clear_delete_pending()

                            logger.file_deleted(
                                relative_path
                            )

                            self._log(
                                f"  ✓ DELETED: {relative_path}",
                                "orange"
                            )

                        self._log(
                            "✓ CLOUD MOVE COMPLETE",
                            "bold"
                        )

                        logger.info(
                            "[CLOUD MOVE] Source deletion completed"
                        )

                    save_cloud_to_cloud_user_report(
                        len(identical),
                        [],
                        total_files=len(identical)
                    )

                    if resume is not None:
                        resume.complete(
                            success=True
                        )

                    self._active_resume = None

                    self._migration_done(
                        success=True
                    )

                    return

                # ----------------------------------------
                #  LOCAL -> CLOUD VERIFY + COMPLETION
                # ----------------------------------------

                if not source_is_cloud and destination_is_cloud:

                    logger.info(
                        "[CLOUD] Local-to-cloud transfer completed"
                    )

                    self._log(
                        "Verifying uploaded cloud files...",
                        "grey"
                    )

                    destination_remote = (
                        self.cloud_destination["remote"]
                    )

                    destination_path = (
                        self.cloud_destination["path"]
                    )

                    cloud_ok, destination_cloud_info = (
                        get_cloud_file_info(
                            destination_remote,
                            destination_path
                        )
                    )

                    if not cloud_ok:

                        self._set_counters(
                            completed=0,
                            failed=len(cloud_resume_files)
                        )

                        if resume is not None:
                            resume.mark_interrupted()

                        self._log(
                            "✗ CLOUD VERIFICATION ERROR",
                            "red"
                        )

                        logger.error(
                            "[CLOUD] Could not read cloud destination "
                            "for local-to-cloud verification"
                        )

                        self._migration_done(
                            success=False
                        )

                        return

                    destination_by_path = {
                        item["path"]
                        .replace("\\", "/")
                        .strip("/"): item

                        for item in destination_cloud_info
                    }

                    verification_failed = 0
                    verified_count = 0
                    local_to_cloud_failed_items = []

                    self._set_counters(
                        completed=0,
                        failed=0
                    )

                    for relative_path in cloud_resume_files:

                        local_file = os.path.join(
                            local_source,
                            *relative_path.split("/")
                        )

                        cloud_item = destination_by_path.get(
                            relative_path
                        )

                        verified = False

                        if (
                            cloud_item is not None
                            and os.path.isfile(local_file)
                        ):
                            try:
                                local_size = os.path.getsize(
                                    local_file
                                )

                                cloud_size = cloud_item.get(
                                    "size"
                                )

                                local_md5 = (
                                    calculate_hashes(
                                        local_file
                                    )["md5"] or ""
                                ).lower()

                                cloud_md5 = (
                                    cloud_item.get("md5") or ""
                                ).lower()

                                size_matches = (
                                    cloud_size is None
                                    or int(cloud_size)
                                    == local_size
                                )

                                hash_matches = (
                                    bool(cloud_md5)
                                    and cloud_md5
                                    == local_md5
                                )

                                verified = (
                                    size_matches
                                    and hash_matches
                                )

                            except Exception as error:

                                logger.info(
                                    f"[CLOUD] Verification error "
                                    f"for {relative_path}: {error}"
                                )

                                verified = False

                        if verified:

                            verified_count += 1

                            if resume is not None:
                                resume.mark_verified(
                                    relative_path
                                )

                            self._log(
                                f"  ✓ {relative_path}",
                                "orange"
                            )

                            logger.file_verified(
                                relative_path,
                                "VERIFIED"
                            )

                        else:

                            verification_failed += 1

                            local_to_cloud_failed_items.append({
                                "source_path": local_file,
                                "status": "HASH MISMATCH"
                            })

                            self._log(
                                f"  ✗ FAILED: {relative_path}",
                                "red"
                            )

                            logger.file_verified(
                                relative_path,
                                "HASH_MISMATCH"
                            )


                        self._set_counters(
                            completed=verified_count,
                            failed=verification_failed
                        )

                    self._log(
                        "",
                        "grey"
                    )

                    self._log(
                        "=" * 45,
                        "grey"
                    )

                    self._log(
                        "LOCAL-TO-CLOUD VERIFICATION",
                        "bold"
                    )

                    self._log(
                        f"  Total files:      "
                        f"{len(cloud_resume_files)}",
                        "white"
                    )

                    self._log(
                        f"  Verified:         "
                        f"{verified_count}",
                        "white"
                    )

                    self._log(
                        f"  Failed:           "
                        f"{verification_failed}",
                        "white"
                    )

                    user_report_path = os.path.join(
                        reports_folder,
                        "user_report_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        ".csv"
                    )

                    self._silent_call(
                        create_user_report,
                        user_report_path,
                        operation,
                        "Local to Cloud",
                        len(cloud_resume_files),
                        verified_count,
                        verification_failed,
                        local_to_cloud_failed_items
                    )

                    self._log(
                        f"✓ User report: {user_report_path}",
                        "grey"
                    )


                    if verification_failed != 0:

                        if resume is not None:
                            resume.mark_interrupted()

                        self._log(
                            "✗ CLOUD VERIFICATION FAILED",
                            "red"
                        )

                        logger.error(
                            f"[CLOUD] Local-to-cloud verification "
                            f"failed — {verification_failed} file(s)"
                        )

                        self._migration_done(
                            success=False
                        )

                        return

                    self._log(
                        "✓ ALL CLOUD FILES VERIFIED SUCCESSFULLY",
                        "orange"
                    )

                    logger.info(
                        "[CLOUD] Local-to-cloud verification passed"
                    )

                    if resume is not None:
                        resume.complete(
                            success=True
                        )

                    self._active_resume = None

                    self._migration_done(
                        success=True
                    )

                    return

            else:
                self._log(
                    f"✗ {message}",
                    "red"
                )

                logger.error(
                    f"[CLOUD] Transfer failed — {message}"
                )

                self._migration_done(
                    success=False
                )

        except Exception as error:
            self._log(
                f"✗ CLOUD MIGRATION ERROR: {error}",
                "red"
            )

            if logger is not None:
                try:
                    logger.error(
                        f"[CLOUD] Migration error — {error}"
                    )
                except Exception:
                    pass

            self._migration_done(
                success=False
            )

        finally:
            if logger is not None:
                try:
                    logger.close()
                except Exception:
                    pass

    # --------------------------------------------------------
    # BACKEND HELPER
    # --------------------------------------------------------

    @staticmethod
    def _silent_call(function, *args, **kwargs):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return function(*args, **kwargs)

    # --------------------------------------------------------
    # MIGRATION THREAD
    # --------------------------------------------------------

    def _run_migration(self, operation, destination):

        logger = None

        try:
        
            source_files = self.source_files
            source_roots = self.source_roots
            total_files = len(source_files)

            self._log("=" * 45, "grey")
            self._log(f"Operation:    {operation}", "bold")
            self._log(f"Files:        {total_files}", "white")
            self._log(f"Destination:  {destination}", "white")
            self._log("=" * 45, "grey")

            self._set_status(f"Running {operation} — {total_files} files...")

            reports_folder = get_reports_folder()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Start the migration logger
            # WHY: every migration needs a permanent log file
            logs_folder = get_logs_folder()
            logger = MigrationLogger(logs_folder)
            logger.start(operation, source_roots, destination, total_files)

            # ------------------------------------------------
            # STEP 22.13-A — RESUME LOGGING
            # ------------------------------------------------

            if self._resume_mode:

                resume_count = len(
                    self._resume_verified_set
                )

                logger.info(
                    f"[RESUME] Migration detected"
                )

                logger.info(
                    f"[RESUME] {resume_count} files already verified"
                )

                logger.info(
                    f"[RESUME] Continuing migration..."
                )

                self._log(
                    f"[RESUME] Migration detected",
                    "yellow"
                )

                self._log(
                    f"[RESUME] {resume_count} files already verified",
                    "yellow"
                )

                self._log(
                    "[RESUME] Continuing migration...",
                    "grey"
                )

            # ------------------------------------------------
            # STEP 22 — RESUME STATE
            # ------------------------------------------------

            resume = ResumeManager(logs_folder)
            self._active_resume = resume

            if self._resume_mode and self._resume_state_file:

                loaded = resume.load_existing(
                    self._resume_state_file
                )

                if not loaded:
                    raise RuntimeError(
                        "Could not load existing resume state"
                    )

                valid, reason = resume.validate_resume_context(
                    operation,
                    source_roots,
                    destination,
                    source_files
                )

                if not valid:

                    self._log(
                        f"✗ RESUME VALIDATION FAILED: {reason}",
                        "red"
                    )

                    logger.error(
                        f"RESUME VALIDATION FAILED — {reason}"
                    )

                    resume.mark_interrupted()
                    logger.close()

                    self._migration_done(success=False)
                    return

                skip_count = resume.get_verified_count()

                self._log(
                    f"Resuming — skipping {skip_count} "
                    f"already verified files",
                    "yellow"
                )

            else:

                resume.start(
                    operation,
                    source_roots,
                    destination,
                    source_files,
                    timestamp
                )

        
            self._log("Checking paths...", "grey")
            paths_ok = self._silent_call(
                validate_paths,
                source_roots,
                destination,
                source_files
            )

        
            if not paths_ok:
                

                self._log(
                    "✗ Path validation failed. Migration stopped.",
                    "red"
                )

                logger.paths_checked(False)
                logger.close()

                self._migration_done(success=False)
                return

            self._log(
                "✓ All paths valid",
                "orange"
            )

            logger.paths_checked(True)

            # ------------------------------------------------
            # CHECK DESTINATION FREE SPACE
            # ------------------------------------------------

            self._log("Checking destination free space...", "grey")

            try:
                required_bytes = sum(
                    os.path.getsize(file_path)
                    for file_path in source_files
                )

                disk_usage = shutil.disk_usage(destination)
                free_bytes = disk_usage.free
                

                # Keep a small safety margin.
                # We require at least 5% more free space than
                # the exact source-file size.
                safety_margin = int(required_bytes * 0.05)
                required_with_margin = required_bytes + safety_margin

                def format_size(size):
                    for unit in ["bytes", "KB", "MB", "GB", "TB"]:
                        if size < 1024:
                            return f"{size:.1f} {unit}"
                        size /= 1024
                    return f"{size:.1f} PB"

                self._log(
                    f"  Required: {format_size(required_bytes)}",
                    "white"
                )

                self._log(
                    f"  Available: {format_size(free_bytes)}",
                    "white"
                )

                

                if free_bytes < required_with_margin:

                    self._log(
                        "✗ NOT ENOUGH DESTINATION SPACE",
                        "red"
                    )

                    self._log(
                        f"  Required with safety margin: "
                        f"{format_size(required_with_margin)}",
                        "red"
                    )

                    self._log(
                        "Migration stopped before copying any files.",
                        "red"
                    )

                    # STEP 21 — permanently record the failed
                    # disk-space safety check in the .log file.
                    logger.disk_space_checked(
                        required_bytes=required_bytes,
                        available_bytes=free_bytes,
                        required_with_margin=required_with_margin,
                        ok=False
                    )

                    # This is an early exit, so close the permanent
                    # migration log before returning.
                    logger.close()

                    self._migration_done(success=False)
                    return

                self._log(
                    "✓ Enough destination space available",
                    "orange"
                )
                logger.disk_space_checked(
                    required_bytes=required_bytes,
                    available_bytes=free_bytes,
                    required_with_margin=required_with_margin,
                    ok=True
                )

            except Exception as error:

                self._log(
                    f"✗ Could not check destination space: {error}",
                    "red"
                )
                logger.disk_space_checked(
                    required_bytes=required_bytes,
                    available_bytes=free_bytes,
                    required_with_margin=required_with_margin,
                    ok=False
                )
                self._migration_done(success=False)
                return


            self._log("Creating source inventory...", "grey")

            inventory_file = os.path.join(
                reports_folder,
                f"inventory_{timestamp}.csv"
            )

            try:

                self._silent_call(
                    create_inventory_report,
                    source_files,
                    inventory_file
                )

                self._log(
                    "✓ Inventory saved",
                    "orange"
                )

                logger.inventory_created(
                    inventory_file,
                    total_files
                )

                logger.inventory_report(
                        inventory_file
                )

            except Exception as error:

                self._log(
                    f"✗ Inventory creation failed: {error}",
                    "red"
                )

                logger.error(
                    f"Inventory creation FAILED — {error}"
                )

                logger.close()

                self._migration_done(success=False)
                return

            if self._resume_mode:
                remaining_files = (
                    total_files - len(self._resume_verified_set)
                )

                self._log(
                    f"Resuming copy — "
                    f"{len(self._resume_verified_set)} already verified, "
                    f"{remaining_files} remaining...",
                    "grey"
                )
            else:
                self._log(
                    f"Copying {total_files} files...",
                    "grey"
                )

            copied_count = 0
            failed_count = 0
            session_copied_count = 0

            # Tracks files actually copied during THIS migration.
            successfully_copied_files = set()

            # STEP 22.8 — remember whether a network interruption occurred
            network_interrupted = False

            for number, source_file in enumerate(source_files, start=1):

            #   graceful application shutdown
                if self.stop_requested:
                    resume.mark_interrupted()

                    try:
                        logger.info(
                            "[INTERRUPTED] Application close requested — "
                            "progress saved for resume"
                        )
                    except Exception:
                        pass

                    return

                # ----------------------------------------------------
                # Build expected destination path FIRST
                # ----------------------------------------------------

                matched_root = find_root_for_file(
                    source_file,
                    source_roots
                )

                if matched_root is None:
                    matched_root = os.path.dirname(
                        source_file
                    )

                base = os.path.dirname(
                    matched_root
                )

                relative_path = os.path.relpath(
                    source_file,
                    base
                )

                destination_file = os.path.join(
                    destination,
                    relative_path
                )

                # ----------------------------------------------------
                # STEP 22.9 — REVALIDATE PREVIOUSLY VERIFIED FILE
                # ----------------------------------------------------

                if resume.is_verified(source_file):

                    try:

                        previous_result = self._silent_call(
                            verify_file,
                            source_file,
                            destination_file
                        )

                        if (
                            previous_result.get("status")
                            == "VERIFIED"
                        ):

                            copied_count += 1

                            self._set_counters(
                                completed=copied_count,
                                failed=failed_count
                            )

                            pct = (
                                number / total_files
                            ) * 50

                            self._set_progress(
                                pct,
                                (
                                    f"Not verified: "
                                    f"{os.path.basename(source_file)} "
                                    f"({number}/{total_files})"
                                )
                            )

                            continue

                    except Exception:
                        pass

                    # Destination missing or changed.
                    # Do not trust the old checkpoint.
                    resume.unmark_verified(
                        source_file
                    )

                    self._log(
                        f"⚠ STALE RESUME FILE: "
                        f"{os.path.basename(source_file)} "
                        f"will be copied again",
                        "yellow"
                    )

                # ----------------------------------------------------
                # NORMAL COPY
                # ----------------------------------------------------

                try:

                    os.makedirs(
                        os.path.dirname(destination_file),
                        exist_ok=True
                    )

                    shutil.copy2(
                        source_file,
                        destination_file
                    )
                    session_copied_count += 1

                    # Record that THIS migration copied this file.
                    successfully_copied_files.add(
                        source_file
                    )

                    logger.file_copied(
                        relative_path
                    )

                    copied_count += 1

                except Exception as error:
                    failed_count += 1

                    source_is_network = is_network_path(source_file)
                    destination_is_network = is_network_path(destination)
                    error_text = str(error).lower()

                    permission_denied = (
                        isinstance(error, PermissionError)
                        or "permission denied" in error_text
                        or "access is denied" in error_text
                        or getattr(error, "winerror", None) == 5
                    )

                    path_too_long = (
                        isinstance(error, OSError)
                        and (
                            "filename or extension is too long" in error_text
                            or "file name too long" in error_text
                            or "path too long" in error_text
                            or getattr(error, "winerror", None) == 206
                        )
                    )

                    if path_too_long:
                        category = "PATH TOO LONG"

                        self._log(
                            f"  ✗ PATH TOO LONG: "
                            f"{os.path.basename(source_file)}",
                            "red"
                        )

                        self._log(
                            "    Windows rejected the source/destination path "
                            "because it is too long.",
                            "red"
                        )

                        self._log(
                            "    Shorten the folder/file path and try again.",
                            "yellow"
                        )

                    elif (
                        
                        source_is_network
                        or destination_is_network
                        or isinstance(error, ConnectionError)

                    ):
                        category = "NETWORK INTERRUPTION"
                        network_interrupted = True

                        self._log(
                            f"  ✗ NETWORK INTERRUPTION: "
                            f"{os.path.basename(source_file)} — {error}",
                            "red"
                        )

                        self._log(
                            "    Network source/destination became unavailable.",
                            "red"
                        )

                        self._log(
                            "    Source files will remain safe.",
                            "orange"
                        )
                    elif permission_denied:

                        category = "PERMISSION DENIED"

                        self._log(
                            f"  ✗ PERMISSION DENIED: "
                            f"{os.path.basename(source_file)} — {error}",
                            "red"
                        )

                    else:
                        category = "COPY FAILED"
                        self._log(
                            f"  ✗ Copy failed: "
                            f"{os.path.basename(source_file)} — {error}",
                            "red"
                        )


                    # Every COPY failure reaches this line,
                    # regardless of what type of error occurred.

                    logger.file_copy_failed(
                        os.path.basename(source_file),
                        str(error),
                        category
                    )

                self._set_counters(
                    completed=copied_count,
                    failed=failed_count
                )

                phase_pct = (
                    number / total_files
                ) * 100

                overall_pct = (
                    number / total_files
                ) * 50

                self._set_progress(
                    overall_pct,
                    (
                        f"Copying: "
                        f"{os.path.basename(source_file)} "
                        f"({number}/{total_files})"
                    )
                )

            self._log(
                f"✓ Copy done — Copied: {copied_count}   Failed: {failed_count}",
                "orange" if failed_count == 0 else "yellow"
            )

            
            self._log("Verifying all files...", "grey")
            if self.stop_requested:
                    resume.mark_interrupted()

                    try:
                        logger.info(
                            "[INTERRUPTED] Application close requested — "
                            "verification progress saved for resume"
                        )
                    except Exception:
                        pass

                    return

            verification_results = []
            verified_count = 0
            verification_failed = 0
            self._set_counters(
                completed=0,
                failed=0
            )

            for number, source_file in enumerate(source_files, start=1):
                                # STEP 22 — file was already verified in a
                # previous interrupted migration.
                # Do not treat it as a copy failure.
                if resume.is_verified(source_file):

                    verified_count += 1

                    self._log(
                        f"[SKIP] {os.path.basename(source_file)} "
                        f"— previously verified",
                        "yellow"
                    )

                    logger.info(
                        f"[SKIP] {source_file} — previously verified"
                    )

                    logger.file_verified(
                        os.path.basename(source_file),
                        "VERIFIED"
                    )

                    self._set_counters(
                        completed=verified_count,
                        failed=verification_failed
                    )

                    phase_pct = (
                        verified_count / total_files
                    ) * 100

                    overall_pct = (
                        50
                        + (
                            verified_count
                            / total_files
                        ) * 50
                    )

                    self._set_progress(
                        overall_pct,
                        (
                            f"Already verified: "
                            f"{os.path.basename(source_file)} "
                            f"({number}/{total_files})"
                        )
                    )

                    continue
                matched_root = find_root_for_file(source_file, source_roots)
                if matched_root is None:
                    matched_root = os.path.dirname(source_file)

                base = os.path.dirname(matched_root)
                relative_path = os.path.relpath(source_file, base)
                destination_file = os.path.join(destination, relative_path)
                # Never verify an old/stale destination file when
                # the copy for this source failed during THIS run.
                if source_file not in successfully_copied_files:

                    verification_failed += 1

                    verification_results.append({
                        "source_path": source_file,
                        "destination_path": destination_file,
                        "source_size": "",
                        "destination_size": "",
                        "source_md5": "",
                        "destination_md5": "",
                        "source_sha1": "",
                        "destination_sha1": "",
                        "source_sha256": "",
                        "destination_sha256": "",
                        "status": "COPY FAILED — NOT VERIFIED"
                    })

                    self._log(
                        f"  ✗ NOT VERIFIED: "
                        f"{os.path.basename(source_file)} — copy failed",
                        "red"
                    )

                    logger.file_verified(
                        os.path.basename(source_file),
                        "COPY_FAILED"
                    )

                    self._set_counters(
                        completed=verified_count,
                        failed=verification_failed
                    )

                    pct = 50 + (number / total_files) * 50
                    
                    self._set_progress(
                        pct,
                        (
                            f"Skipping: "
                            f"{os.path.basename(source_file)} "
                            f"({number}/{total_files})"
                        )
                    )

                    continue
                try:


                    result = self._silent_call(
                        verify_file,
                        source_file,
                        destination_file
                    )
                    verification_results.append(result)
                    if result["status"] == "VERIFIED":

                        logger.file_verified(
                            os.path.basename(source_file),
                            "VERIFIED"
                        )

                    else:

                        logger.file_verified(
                            os.path.basename(source_file),
                            "HASH_MISMATCH"
                        )

                    if result["status"] == "VERIFIED":
                        verified_count += 1
                    
                        resume.mark_verified(source_file)
                        self._log(
                            f"  ✓ {os.path.basename(source_file)}",
                            "orange"
                        )
                        
                    else:
                        verification_failed += 1
                        self._log(
                            f"  ✗ FAILED: {os.path.basename(source_file)}",
                            "red"
                        )

                except Exception as error:
                    verification_failed += 1

                    verification_results.append({
                        "source_path": source_file,
                        "destination_path": destination_file,
                        "source_size": "",
                        "destination_size": "",
                        "source_md5": "",
                        "destination_md5": "",
                        "source_sha1": "",
                        "destination_sha1": "",
                        "source_sha256": "",
                        "destination_sha256": "",
                        "status": f"ERROR: {error}"
                    })

                    self._log(
                        f"  ✗ VERIFICATION ERROR: "
                        f"{os.path.basename(source_file)} — {error}",
                        "red"
                    )
                    logger.file_verified(
                        os.path.basename(source_file),
                        "ERROR",
                        str(error)
                    )

                self._set_counters(
                    completed=verified_count,
                    failed=verification_failed
                )
                    
                phase_pct = (
                    verified_count / total_files
                ) * 100

                overall_pct = (
                    50
                    + (
                        verified_count
                        / total_files
                    ) * 50
                )

                self._set_progress(
                    overall_pct,
                    (
                        f"Verifying: "
                        f"{os.path.basename(source_file)} "
                        f"({number}/{total_files})"
                    )
                )

            all_verified = (
                copied_count == total_files
                and failed_count == 0
                and verified_count == total_files
                and verification_failed == 0
            )

            self._log("", "grey")
            self._log("=" * 45, "grey")
            self._log("MIGRATION SUMMARY", "bold")
            self._log(f"  Total files:  {total_files}", "white")
            if self._resume_mode:
                self._log(
                    f"  Previously verified: {len(self._resume_verified_set)}",
                    "white"
                )
            self._log(f"  Copied this session: {session_copied_count}","white")
            self._log(f"  Verified:     {verified_count}", "white")
            self._log(f"  Failed:       {verification_failed}", "white")

            if all_verified:
                self._log("✓ ALL FILES VERIFIED SUCCESSFULLY", "orange")
            else:
                self._log("✗ VERIFICATION FAILED", "red")

            deletion_results = []
            deleted_count = 0
            delete_failed_count = 0

            if operation == "MOVE" and all_verified:
                self._log("Deleting source files...", "yellow")

                for source_file in source_files:
                    if self.stop_requested:
                        resume.mark_interrupted()

                        try:
                            logger.info(
                                "[INTERRUPTED] Application close requested — "
                                "MOVE deletion progress saved for resume"
                            )
                        except Exception:
                            pass

                        return
                    try:
                        if resume.is_deleted(source_file):
                            self._log(
                                f"  ↷ SKIP DELETE: "
                                f"{os.path.basename(source_file)} "
                                f"was already deleted in a previous MOVE run",
                                "yellow"
                            )

                            deleted_count += 1
                            continue

# ********************************************************************************************************************************************


                        os.remove(source_file)
                        resume.mark_deleted(
                            source_file
                        )
                        
                        logger.file_deleted(
                            os.path.basename(source_file)
                        )
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

                        self._log(
                            f"  ✗ Delete failed: {os.path.basename(source_file)}",
                            "red"
                        )

                        logger.file_delete_failed(
                            os.path.basename(source_file),
                            str(error)
                        )

                self._log(
                    f"Deleted successfully: {deleted_count}",
                    "orange"
                )

                self._log(
                    f"Failed to delete: {delete_failed_count}",
                    "red" if delete_failed_count > 0 else "orange"
                )


            elif operation == "MOVE" and not all_verified:
                self._log(
                    "⚠ MOVE cancelled — source files are safe (not deleted)",
                    "yellow"
                )

            report_path = os.path.join(
                reports_folder,
                f"verification_report_{timestamp}.csv"
            )
            self._silent_call(
                create_verification_report,
                verification_results,
                deletion_results,
                report_path
            )
            self._log(f"✓ Report: {report_path}", "grey")

            logger.verification_report(
                    report_path
            )

            user_failed_items = []
            user_failed_paths = set()

            for result in verification_results:
                result_status = str(
                    result.get("status", "")
                )

                if result_status != "VERIFIED":
                    source_path = result.get(
                        "source_path",
                        ""
                    )

                    failed_key = os.path.normcase(
                        os.path.abspath(source_path)
                    ) if source_path else result_status

                    if failed_key not in user_failed_paths:
                        user_failed_paths.add(failed_key)

                        user_failed_items.append({
                            "source_path": source_path,
                            "status": result_status
                        })

            for deletion in deletion_results:
                deletion_status = str(
                    deletion.get("status", "")
                )

                if deletion_status != "DELETED":
                    source_path = deletion.get(
                        "source_path",
                        ""
                    )

                    failed_key = os.path.normcase(
                        os.path.abspath(source_path)
                    ) if source_path else deletion_status

                    if failed_key not in user_failed_paths:
                        user_failed_paths.add(failed_key)

                        user_failed_items.append({
                            "source_path": source_path,
                            "status": deletion_status
                        })

            user_failed_count = len(
                user_failed_items
            )

            user_successful_count = max(
                0,
                total_files - user_failed_count
            )

            user_report_path = os.path.join(
                reports_folder,
                f"user_report_{timestamp}.csv"
            )

            self._silent_call(
                create_user_report,
                user_report_path,
                operation,
                "Local to Local",
                total_files,
                user_successful_count,
                user_failed_count,
                user_failed_items
            )

            self._log(
                f"✓ User report: {user_report_path}",
                "grey"
            )

            try:
                usage = shutil.disk_usage(destination)

                def fmt(size):
                    for unit in ["bytes", "KB", "MB", "GB", "TB"]:
                        if size < 1024:
                            return f"{size:.1f} {unit}"
                        size /= 1024
                    return f"{size:.1f} PB"

                self._log(
                    f"Destination free space: {fmt(usage.free)}",
                    "grey"
                )
            except Exception:
                pass

            self._log("=" * 45, "grey")
            self._log("MIGRATION COMPLETE", "bold")

            # ------------------------------------------------
            # FINAL MIGRATION RESULT
            # ------------------------------------------------

            if operation == "MOVE":
                migration_success = (
                    all_verified
                    and delete_failed_count == 0
                    and deleted_count == total_files
                )
            else:
                migration_success = all_verified

            
                        
           
            
            # ------------------------------------------------
            # Resume state final decision
            # ------------------------------------------------

            move_delete_incomplete = (
                operation == "MOVE"
                and all_verified
                and delete_failed_count > 0
            )

            if network_interrupted:

                resume.mark_interrupted()

                self._log(
                    "⚠ Migration interrupted by network failure — progress saved for resume",
                    "yellow"
                )

            elif move_delete_incomplete:

                resume.mark_interrupted()

                self._log(
                    "⚠ MOVE deletion incomplete — progress saved for resume",
                    "yellow"
                )

            else:

                resume.complete(
                    success=migration_success
                )

            
            # Clear resume mode
            self._resume_mode         = False
            self._resume_verified_set = set()
            self._resume_state_file   = None

            logger.complete(
                operation=operation,
                total=total_files,
                copied=session_copied_count,
                verified=verified_count,
                failed=verification_failed,
                deleted=deleted_count,
                success=migration_success
            )

            log_path = logger.get_log_path()

            if log_path:
                self._log(
                    f"✓ Log saved: {log_path}",
                    "grey"
                )
            else:
                self._log(
                    "⚠ Permanent log unavailable — migration completed without log file",
                    "yellow"
                )

            self._migration_done(success=migration_success)


        except Exception as error:

            self._log(
                f"CRITICAL ERROR: {error}",
                "red"
            )

            if logger is not None:
                try:
                    logger.error(
                        f"CRITICAL: {error}"
                    )

                    logger.close()

                except Exception:
                    pass
            try:
                resume.mark_interrupted()
            except Exception:
                pass

            self._migration_done(success=False)

    # --------------------------------------------------------
    # RESET MIGRATION DISPLAY
    # --------------------------------------------------------

    def _reset_migration_display(self):

        if self.is_running:
            return

        self.progress_var.set(0)
        self._set_counters(
            completed=0,
            failed=0
        )

        self.progress_label.config(
            text="Ready",
            fg=TEXT_GREY
        )

        self.progress_percent_label.config(
            text="0%",
            fg=TEXT_GREY
        )

        self.status_var.set("Ready")



    # --------------------------------------------------------
    # PROGRESS BAR UPDATES
    # --------------------------------------------------------

    # def _start_progress_animation(self):
    #     self.progress_var.set(0)
    #     self.progress_label.config(
    #         text="Preparing migration...",
    #         fg=TEXT_GREEN
    #     )

    # def _set_progress(self, value, label=""):
    #     def update():
    #         value_clamped = max(0, min(100, float(value)))
    #         self.progress_var.set(value_clamped)
    #         self.progress_label.config(
    #             text=f"{label} — {int(value_clamped)}%",
    #             fg=TEXT_GREEN
    #         )

    #     self.root.after(0, update)

    # def _stop_progress_animation(self, success):
    #     if success:
    #         self.progress_var.set(100)
    #     else:
    #         self.progress_var.set(0)

    def _start_progress_animation(self):
        self.progress_var.set(0)
        self._set_counters(
            completed=0,
            failed=0
        )

        self.progress_label.config(
            text="Preparing migration...",
            fg=TEXT_GREEN
        )

        self.progress_percent_label.config(
            text="0%",
            fg=TEXT_GREEN
        )

    def _set_progress(self, value, label=""):
        def update():
            value_clamped = max(
                0,
                min(100, float(value))
            )

            self.progress_var.set(value_clamped)

            self.progress_label.config(
                text=label if label else "Migration in progress...",
                fg=TEXT_GREEN
            )

            self.progress_percent_label.config(
                text=f"{int(value_clamped)}%",
                fg=TEXT_GREEN
            )

        self.root.after(0, update)

    def _stop_progress_animation(self, success):
        if success:
            self.progress_var.set(100)

            self.progress_percent_label.config(
                text="100%",
                fg=TEXT_GREEN
            )

        else:
            self.progress_var.set(0)

            self.progress_percent_label.config(
                text="0%",
                fg=TEXT_RED
            )

    def _set_counters(self, completed=None, failed=None):
        def update():
            if completed is not None:
                self.completed_count_label.config(
                    text=f"Completed: {int(completed)}",
                    fg=TEXT_GREEN
                )

            if failed is not None:
                failed_value = int(failed)

                self.failed_count_label.config(
                    text=f"Failed: {failed_value}",
                    fg=(
                        TEXT_RED
                        if failed_value > 0
                        else TEXT_GREY
                    )
                )

        self.root.after(0, update)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def _reset_source_after_success(self):
        self.source_roots = []
        self.source_files = []
        self.cloud_source = None
        self.source_var.set("")
        self._refresh_source_label()



    def _show_migration_result_dialog(
        self,
        success,
        operation,
        summary_text,
        safety_text
    ):
        """
        Display a professional application-themed migration result dialog.
        """

        dialog = tk.Toplevel(self.root)
        dialog.title(
            f"{operation.title()} Complete"
            if success
            else f"{operation.title()} Incomplete"
        )
        dialog.configure(bg=BG_DARK)
        dialog.resizable(False, False)
        dialog.transient(self.root)

        dialog_width = 620
        dialog_height = 370 if success else 440

        self.root.update_idletasks()

        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()

        dialog_x = root_x + (root_width - dialog_width) // 2
        dialog_y = root_y + (root_height - dialog_height) // 2

        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

        dialog_x = max(
            10,
            min(dialog_x, screen_width - dialog_width - 10)
        )
        dialog_y = max(
            10,
            min(dialog_y, screen_height - dialog_height - 50)
        )

        dialog.geometry(
            f"{dialog_width}x{dialog_height}"
            f"+{dialog_x}+{dialog_y}"
        )

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        header_color = ACCENT

        header = tk.Frame(
            dialog,
            bg=header_color,
            height=62
        )
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header,
            text=(
                f"{operation} COMPLETE  ✓"
                if success
                else f"{operation} INCOMPLETE  ✗"
            ),
            font=("Segoe UI", 13, "bold"),
            fg=TEXT_WHITE,
            bg=header_color
        ).pack(
            side=tk.LEFT,
            padx=24,
            pady=14
        )

        tk.Label(
            header,
            text="100%" if success else "ATTENTION REQUIRED",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_WHITE,
            bg=header_color
        ).pack(
            side=tk.RIGHT,
            padx=18
        )

        # ----------------------------------------------------
        # MAIN CONTENT
        # ----------------------------------------------------

        content = tk.Frame(
            dialog,
            bg=BG_PANEL,
            padx=18,
            pady=12
        )
        content.pack(
            fill=tk.BOTH,
            expand=True,
            padx=10,
            pady=(10, 4)
        )

        # ----------------------------------------------------
        # DRAWN FOLDER ILLUSTRATION
        # ----------------------------------------------------

        icon_canvas = tk.Canvas(
            content,
            width=140,
            height=135,
            bg=BG_PANEL,
            highlightthickness=0
        )
        icon_canvas.pack(
            side=tk.LEFT,
            padx=(0, 16)
        )

        folder_back = "#d48a18"
        folder_front = "#f5a623"
        folder_highlight = "#ffc85c"

        icon_canvas.create_polygon(
            20, 48,
            58, 48,
            72, 63,
            130, 63,
            130, 125,
            20, 125,
            fill=folder_back,
            outline=""
        )

        icon_canvas.create_rectangle(
            20,
            64,
            130,
            125,
            fill=folder_front,
            outline=""
        )

        icon_canvas.create_polygon(
            20, 72,
            130, 72,
            118, 130,
            30, 130,
            fill=folder_highlight,
            outline=""
        )

        badge_color = TEXT_GREEN if success else TEXT_RED

        icon_canvas.create_oval(
            91,
            91,
            137,
            137,
            fill=badge_color,
            outline=BG_PANEL,
            width=4
        )

        if success:
            icon_canvas.create_line(
                103,
                114,
                113,
                124,
                128,
                103,
                fill=TEXT_WHITE,
                width=5,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND
            )
        else:
            icon_canvas.create_line(
                104,
                105,
                126,
                127,
                fill=TEXT_WHITE,
                width=5,
                capstyle=tk.ROUND
            )
            icon_canvas.create_line(
                126,
                105,
                104,
                127,
                fill=TEXT_WHITE,
                width=5,
                capstyle=tk.ROUND
            )

        # ----------------------------------------------------
        # RESULT DETAILS
        # ----------------------------------------------------

        details = tk.Frame(
            content,
            bg=BG_PANEL
        )
        details.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True
        )

        tk.Label(
            details,
            text=summary_text,
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_WHITE,
            bg=BG_PANEL,
            justify=tk.LEFT,
            anchor=tk.W,
            wraplength=320
        ).pack(
            fill=tk.X,
            anchor=tk.W
        )

        tk.Label(
            details,
            text=safety_text,
            font=("Segoe UI", 10),
            fg=TEXT_GREEN if success else TEXT_YELLOW,
            bg=BG_PANEL,
            justify=tk.LEFT,
            anchor=tk.W,
            wraplength=380
        ).pack(
            fill=tk.X,
            anchor=tk.W,
            pady=(12, 0)
        )

        tk.Label(
            details,
            text=(
                "Your User Report and Technical Report are ready."
                if success
                else
                "Review the reports to identify affected files."
            ),
            font=("Segoe UI", 10),
            fg=TEXT_GREY,
            bg=BG_PANEL,
            justify=tk.LEFT,
            anchor=tk.W,
            wraplength=380
        ).pack(
            fill=tk.X,
            anchor=tk.W,
            pady=(12, 0)
        )

        # ----------------------------------------------------
        # BUTTONS
        # ----------------------------------------------------

        button_row = tk.Frame(
            dialog,
            bg=BG_DARK,
            padx=12,
            pady=10
        )
        button_row.pack(fill=tk.X)

        def dialog_button(text, command, accent=False):
            button = tk.Button(
                button_row,
                text=text,
                command=command,
                font=("Segoe UI", 9, "bold"),
                fg=TEXT_WHITE,
                bg=ACCENT if accent else BTN_COLOR,
                activebackground=ACCENT_HOVER,
                activeforeground=TEXT_WHITE,
                relief=tk.FLAT,
                cursor="hand2",
                padx=8,
                pady=5
            )

            button.bind(
                "<Enter>",
                lambda event: button.config(bg=ACCENT_HOVER)
            )

            button.bind(
                "<Leave>",
                lambda event: button.config(
                    bg=ACCENT if accent else BTN_COLOR
                )
            )

            return button

        dialog_button(
            "User Report",
            self._export_latest_user_report
        ).pack(
            side=tk.LEFT,
            padx=(0, 6)
        )

        dialog_button(
            "Technical Report",
            self._export_latest_technical_report
        ).pack(
            side=tk.LEFT,
            padx=(0, 6)
        )

        dialog_button(
            "Reports Folder",
            self._open_reports_folder
        ).pack(
            side=tk.LEFT
        )

        close_button = dialog_button(
            "Close",
            dialog.destroy,
            accent=True
        )
        close_button.pack(side=tk.RIGHT)

        dialog.protocol(
            "WM_DELETE_WINDOW",
            dialog.destroy
        )

        dialog.bind(
            "<Escape>",
            lambda event: dialog.destroy()
        )

        dialog.after(
            100,
            lambda: (
                dialog.grab_set(),
                close_button.focus_set()
            )
        )


    def _migration_done(self, success):
        self.is_running = False

        def finish_ui():
            operation = self.operation_var.get()
            source_is_cloud = self.cloud_source is not None
            destination_is_cloud = self.cloud_destination is not None
            self._stop_progress_animation(success)

            self.start_btn.config(
                state=tk.NORMAL,
                text="▶   START MIGRATION",
                bg=ACCENT
            )
            self._set_migration_controls_enabled(True)

            self.status_var.set(
                f"{operation.title()} completed successfully  ✓"
                if success else
                f"{operation.title()} incomplete — check log for details"
            )

            self.progress_label.config(
                text="Done  ✓" if success else "Failed  ✗ — 0%",
                fg=TEXT_GREEN if success else TEXT_RED
            )

            if success:
                if source_is_cloud and destination_is_cloud:
                    completion_text = (
                        "All files were copied between cloud locations "
                        "and verified successfully."
                        if operation == "COPY"
                        else
                        "All files were moved between cloud locations "
                        "and verified successfully."
                    )

                elif source_is_cloud:
                    completion_text = (
                        "All files were downloaded and verified successfully."
                        if operation == "COPY"
                        else
                        "All files were moved from cloud storage to the "
                        "local destination and verified successfully."
                    )

                elif destination_is_cloud:
                    completion_text = (
                        "All files were uploaded and verified successfully."
                        if operation == "COPY"
                        else
                        "All files were moved to cloud storage and "
                        "verified successfully."
                    )

                else:
                    completion_text = (
                        "All files were copied and verified successfully."
                        if operation == "COPY"
                        else
                        "All files were moved and verified successfully."
                    )

                safety_text = (
                    "Original source files were retained."
                    if operation == "COPY"
                    else
                    "Source files were deleted only after successful verification."
                )

                self._reset_source_after_success()

                self._show_migration_result_dialog(
                    success=True,
                    operation=operation,
                    summary_text=completion_text,
                    safety_text=safety_text
                )
                
            else:
                if operation == "COPY":
                    failure_text = (
                        "The copy did not complete successfully."
                    )

                    failure_safety_text = (
                        "Original source files were not deleted.\n"
                        "Check the Migration Log and reports for "
                        "the affected files."
                    )

                else:
                    failure_text = (
                        "The move did not complete successfully."
                    )

                    failure_safety_text = (
                        "Files that did not pass verification were not "
                        "deleted from the source.\n"
                        "Some successfully verified files may already "
                        "have been moved.\n"
                        "Check the reports for the exact file status."
                    )

                self._show_migration_result_dialog(
                    success=False,
                    operation=operation,
                    summary_text=failure_text,
                    safety_text=failure_safety_text
                )

        self.root.after(0, finish_ui)


# ============================================================
# ENTRY POINT
# ============================================================

# if __name__ == "__main__":
#     root = tk.Tk()
#     app = AshramMigratorApp(root)
#     root.mainloop()

# if __name__ == "__main__":

#     try:
#         ctypes.windll.shcore.SetProcessDpiAwareness(1)
#     except Exception:
#         try:
#             ctypes.windll.user32.SetProcessDPIAware()
#         except Exception:
#             pass

#     root = tk.Tk()
#     app = AshramMigratorApp(root)
#     root.mainloop()

# if __name__ == "__main__":

#     if not acquire_single_instance():
#         ctypes.windll.user32.MessageBoxW(
#             None,
#             (
#                 "Ashram File Migrator is already running.\n\n"
#                 "Please use the application that is already open."
#             ),
#             "Ashram File Migrator",
#             0x40
#         )
#         raise SystemExit(0)

#     try:
#         try:
#             ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
#                 "NarayanashramaTapovanam.AshramFileMigrator.1"
#             )
#         except Exception:
#             pass

#         try:
#             ctypes.windll.shcore.SetProcessDpiAwareness(1)
#         except Exception:
#             try:
#                 ctypes.windll.user32.SetProcessDPIAware()
#             except Exception:
#                 pass

#         root = tk.Tk()
#         app = AshramMigratorApp(root)
#         root.mainloop()

#     finally:
#         release_single_instance()

#         _WINDOW_ICON_HANDLES = []


# def apply_windows_window_icon(root):
#     """
#     Apply the bundled icon directly to the Windows top-level
#     window for both the title bar and taskbar.
#     """

#     if os.name != "nt":
#         return

#     try:
#         icon_path = get_resource_path(
#             os.path.join(
#                 "Assets",
#                 "app_icon.ico"
#             )
#         )

#         user32 = ctypes.windll.user32

#         user32.LoadImageW.restype = wintypes.HANDLE

#         small_icon = user32.LoadImageW(
#             None,
#             icon_path,
#             1,       # IMAGE_ICON
#             16,
#             16,
#             0x0010  # LR_LOADFROMFILE
#         )

#         large_icon = user32.LoadImageW(
#             None,
#             icon_path,
#             1,       # IMAGE_ICON
#             32,
#             32,
#             0x0010  # LR_LOADFROMFILE
#         )

#         root.update_idletasks()

#         window_handle = root.winfo_id()
#         parent_handle = user32.GetParent(
#             window_handle
#         )

#         for handle in {
#             window_handle,
#             parent_handle
#         }:
#             if handle:
#                 user32.SendMessageW(
#                     handle,
#                     0x0080,  # WM_SETICON
#                     0,       # ICON_SMALL
#                     small_icon
#                 )
#                 user32.SendMessageW(
#                     handle,
#                     0x0080,  # WM_SETICON
#                     1,       # ICON_BIG
#                     large_icon
#                 )

#         # Keep the icon handles alive while the application runs.
#         _WINDOW_ICON_HANDLES.extend(
#             [
#                 small_icon,
#                 large_icon,
#             ]
#         )

#     except Exception:
#         pass

if __name__ == "__main__":

    if not acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            None,
            (
                "Ashram File Migrator is already running.\n\n"
                "Please use the application that is already open."
            ),
            "Ashram File Migrator",
            0x40
        )
        raise SystemExit(0)

    try:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "NarayanashramaTapovanam.AshramFileMigrator.1"
            )
        except Exception:
            pass

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        root = tk.Tk()

        # Keep the window transparent while its layout,
        # position, and icon are prepared.
        root.attributes("-alpha", 0.0)

        app = AshramMigratorApp(root)

        apply_windows_window_icon(root)

        # Reveal the completed window without changing
        # its calculated responsive dimensions.
        root.update_idletasks()
        root.attributes("-alpha", 1.0)
        root.lift()

        root.mainloop()
        
    finally:
        release_single_instance()