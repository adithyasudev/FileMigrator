import tkinter as tk
from tkinter import ttk, messagebox

from rclone import (
    list_remotes,
    check_remote,
    list_files,
)


class CloudSelectorDialog:
    def __init__(
        self,
        parent,
        title="Select Cloud Location",
        allow_files=False
    ):
        self.parent = parent
        self.result = None
        self.allow_files = allow_files

        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.title(title)
        self.window.geometry("620x500")
        self.window.minsize(500, 400)
        self.window.resizable(True, True)
        self.window.transient(parent)

        self.remote_var = tk.StringVar()
        self.path_var = tk.StringVar()

        # Folder currently being displayed in the list.
        # Kept separate from path_var so single-click preview
        # does not interfere with double-click navigation.
        self.current_path = ""

        self._build_ui()
        self._center_on_parent()

        self.listbox.insert(
            tk.END,
            "Loading cloud locations..."
        )

        self.window.deiconify()
        self.window.lift()
        self.window.grab_set()
        self.window.update()

        self._load_remotes()

    def _center_on_parent(self):
        """
        Centre the Cloud selector over the main application
        while keeping it inside the visible screen.
        """

        self.window.update_idletasks()
        self.parent.update_idletasks()

        width = max(
            self.window.winfo_width(),
            self.window.winfo_reqwidth()
        )

        height = max(
            self.window.winfo_height(),
            self.window.winfo_reqheight()
        )

        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()

        x = (
            parent_x
            + (parent_width - width) // 2
        )

        y = (
            parent_y
            + (parent_height - height) // 2
        )

        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        x = max(
            10,
            min(x, screen_width - width - 10)
        )

        y = max(
            10,
            min(y, screen_height - height - 50)
        )

        self.window.geometry(
            f"{width}x{height}+{x}+{y}"
        )

    def _build_ui(self):
        main = ttk.Frame(self.window, padding=15)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Cloud Remote"
        ).pack(anchor="w")

        self.remote_combo = ttk.Combobox(
            main,
            textvariable=self.remote_var,
            state="readonly"
        )
        self.remote_combo.pack(fill="x", pady=(5, 10))

        self.remote_combo.bind(
            "<<ComboboxSelected>>",
            self._on_remote_selected
        )

        ttk.Label(
            main,
            text="Cloud Path"
        ).pack(anchor="w")

        self.path_entry = ttk.Entry(
            main,
            textvariable=self.path_var
        )
        self.path_entry.pack(fill="x", pady=(5, 10))

        nav_row = ttk.Frame(main)
        nav_row.pack(
            fill="x",
            pady=(0, 10)
        )

        ttk.Button(
            nav_row,
            text="Back to Parent Folder",
            command=self._go_up_one_level
        ).pack(side="left")

        ttk.Button(
            nav_row,
            text="List Folder",
            command=self._list_path_entry
        ).pack(
            side="left",
            padx=(8, 0)
        )

        self.listbox = tk.Listbox(main)
        self.listbox.pack(
            fill="both",
            expand=True
        )


        self.listbox.bind(
            "<<ListboxSelect>>",
            self._preview_selected_folder
        )

        self.listbox.bind(
            "<Double-Button-1>",
            self._open_selected_folder
        )

        button_row = ttk.Frame(main)
        button_row.pack(fill="x", pady=(12, 0))

        size_grip = ttk.Sizegrip(
            button_row
        )
        size_grip.pack(
            side="right",
            anchor="se",
            padx=(8, 0)
        )

        ttk.Button(
            button_row,
            text="Cancel",
            command=self.window.destroy
        ).pack(side="right", padx=(8, 0))

        ttk.Button(
            button_row,
            text="Select",
            command=self._select_location
        ).pack(side="right")

    def _load_remotes(self):
        ok, remotes = list_remotes()

        if not ok:
            messagebox.showerror(
                "Cloud Error",
                str(remotes),
                parent=self.window
            )
            return

        self.remote_combo["values"] = remotes

        if remotes:
            self.remote_combo.current(0)
            self._on_remote_selected()

    def _on_remote_selected(self, event=None):
        remote = self.remote_var.get()

        if not remote:
            return

        ok, message = check_remote(remote)

        if not ok:
            messagebox.showerror(
                "Cloud Connection Failed",
                str(message),
                parent=self.window
            )
            return

        self.current_path = ""
        self.path_var.set("")
        self._list_current_folder()

    def _list_current_folder(self):
        remote = self.remote_var.get()
        path = self.current_path

        if not remote:
            return

        ok, items = list_files(
            remote,
            path
        )

        if not ok:
            messagebox.showerror(
                "Cloud Error",
                str(items),
                parent=self.window
            )
            return

        self.listbox.delete(0, tk.END)

        for item in items:
            name = item.get(
                "Name",
                item.get("Path", "")
            )

            is_dir = item.get(
                "IsDir",
                False
            )

            prefix = "[DIR] " if is_dir else "[FILE] "

            self.listbox.insert(
                tk.END,
                prefix + name
            )
    def _preview_selected_folder(self, event=None):
        """
        Single click:
        - folder → preview folder path
        - file   → preview file path when files are allowed
        """

        selection = self.listbox.curselection()

        if not selection:
            return

        value = self.listbox.get(
            selection[0]
        )

        if value.startswith("[DIR] "):
            item_name = value[6:]

        elif (
            self.allow_files
            and value.startswith("[FILE] ")
        ):
            item_name = value[7:]

        else:
            return

        if self.current_path:
            selected_path = (
                f"{self.current_path}/"
                f"{item_name}"
            )
        else:
            selected_path = item_name

        self.path_var.set(
            selected_path
        )
    def _list_path_entry(self):
        """
        Navigate to the path manually typed into Cloud Path.
        """

        self.current_path = (
            self.path_var.get()
            .replace("\\", "/")
            .strip("/")
        )

        self._list_current_folder()


    

    def _go_up_one_level(self):
        """
        Move to the parent cloud folder.
        """

        current = (
            self.current_path
            .replace("\\", "/")
            .strip("/")
        )

        if not current:
            self.path_var.set("")
            return

        parts = current.split("/")

        if len(parts) > 1:
            self.current_path = "/".join(
                parts[:-1]
            )
        else:
            self.current_path = ""

        self.path_var.set(
            self.current_path
        )

        self._list_current_folder()






    def _open_selected_folder(self, event=None):
        """
        Double click:
        enter the selected cloud folder.
        """

        selection = self.listbox.curselection()

        if not selection:
            return

        value = self.listbox.get(
            selection[0]
        )

        if not value.startswith("[DIR] "):
            return

        folder_name = value[6:]

        if self.current_path:
            new_path = (
                f"{self.current_path}/"
                f"{folder_name}"
            )
        else:
            new_path = folder_name

        self.current_path = new_path

        self.path_var.set(
            new_path
        )

        self._list_current_folder()

    def _select_location(self):
        remote = self.remote_var.get()
        path = self.path_var.get().strip()

        selection = self.listbox.curselection()

        if selection:

            value = self.listbox.get(
                selection[0]
            )

            if (
                value.startswith("[FILE] ")
                and not self.allow_files
            ):
                messagebox.showwarning(
                    "Folder Required",
                    "Please select a cloud folder "
                    "for the destination.",
                    parent=self.window
                )
                return

        if not remote:
            messagebox.showwarning(
                "Select Cloud",
                "Please select a cloud remote.",
                parent=self.window
            )
            return

        self.result = {
            "remote": remote,
            "path": path
        }

        self.window.destroy()


def select_cloud_location(
    parent,
    title="Select Cloud Location",
    allow_files=False
):
    dialog = CloudSelectorDialog(
        parent,
        title,
        allow_files=allow_files
    )

    parent.wait_window(
        dialog.window
    )

    return dialog.result