# ============================================================
# app_paths.py
# Central application path handling
# ============================================================

import os
import sys


def get_app_folder():
    """
    Return the folder where the application is running from.

    During normal Python development:
        returns the project folder containing this file.

    Inside a PyInstaller EXE:
        returns the folder containing AshramFileMigrator.exe.
    """

    if getattr(sys, "frozen", False):
        return os.path.dirname(
            os.path.abspath(sys.executable)
        )

    return os.path.dirname(
        os.path.abspath(__file__)
    )


def get_resource_path(relative_path):
    """
    Return the path to a bundled application resource.

    During development, resources are read from the project folder.
    Inside the packaged EXE, resources are read from PyInstaller's
    internal bundle folder.
    """

    bundle_folder = getattr(
        sys,
        "_MEIPASS",
        get_app_folder()
    )

    return os.path.join(
        bundle_folder,
        relative_path
    )


def get_logs_folder():
    """
    Return the permanent logs folder beside the application.
    Create it automatically if it does not exist.
    """

    folder = os.path.join(
        get_app_folder(),
        "logs"
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    return folder


def get_reports_folder():
    """
    Return the permanent reports folder beside the application.
    Create it automatically if it does not exist.
    """

    folder = os.path.join(
        get_app_folder(),
        "reports"
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    return folder

def get_rclone_executable():
    """
    Return the rclone executable path.

    Priority:
        1. PyInstaller bundled rclone.exe.
        2. rclone.exe beside the application.
        3. rclone.exe inside _internal.
        4. Fall back to system PATH.
    """

    # PyInstaller bundled-resource location.
    if getattr(sys, "frozen", False):

        bundle_folder = getattr(
            sys,
            "_MEIPASS",
            None
        )

        if bundle_folder:

            bundled_rclone = os.path.join(
                bundle_folder,
                "rclone.exe"
            )

            if os.path.isfile(bundled_rclone):
                return bundled_rclone

    # Check beside AshramFileMigrator.exe.
    beside_app = os.path.join(
        get_app_folder(),
        "rclone.exe"
    )

    if os.path.isfile(beside_app):
        return beside_app

    # PyInstaller onedir commonly stores binaries here.
    internal_rclone = os.path.join(
        get_app_folder(),
        "_internal",
        "rclone.exe"
    )

    if os.path.isfile(internal_rclone):
        return internal_rclone

    # Development fallback — use installed rclone from PATH.
    return "rclone"