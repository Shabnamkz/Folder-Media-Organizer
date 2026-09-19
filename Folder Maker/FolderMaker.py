#!/usr/bin/env python3
"""
FolderMaker - create numbered folders, and sort episode files into them.

Run:   python FolderMaker.py
Build: pyinstaller --onefile --windowed --name FolderMaker FolderMaker.py
"""

import json
import os
import re
import shutil
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter.ttk import Combobox

ILLEGAL = set('<>:"/\\|?*')
UNDO_FILE = ".foldermaker_undo.json"


def sanitize_piece(s):
    """Strip characters Windows/macOS/Linux won't allow in a filename."""
    return "".join(c for c in s if c not in ILLEGAL).strip()

MEDIA_EXT = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".ts", ".m2ts",
    ".webm", ".mpg", ".mpeg", ".ogm", ".rmvb", ".divx", ".vob",
    ".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt", ".sup", ".nfo", ".txt",
}


# ----------------------------------------------------------------------
# Episode-number detection
# ----------------------------------------------------------------------

NOISE = re.compile(
    r"\b("
    r"\d{3,4}[pi]|"
    r"[xh]\.?26[45]|hevc|avc|av1|"
    r"10\s?bit|8\s?bit|"
    r"aac|ac3|eac3|flac|opus|dts(?:-hd)?|truehd|ddp?5\.1|"
    r"blu-?ray|bd(?:rip|mux)?|web-?dl|web-?rip|hdtv|dvd(?:rip)?|remux|"
    r"dual[\s.-]?audio|multi[\s.-]?sub|uncensored|repack|proper"
    r")\b",
    re.IGNORECASE,
)
BRACKETS = re.compile(r"[\[\{](.*?)[\]\}]")
PARENS = re.compile(r"\((.*?)\)")
YEAR = re.compile(r"\b(19|20)\d{2}\b")
SPECIAL = re.compile(
    r"\b(ncop|nced|op\d?|ed\d?|sp\d*|ova|oad|special|extra|preview|pv|menu|"
    r"creditless|bonus|trailer)\b",
    re.IGNORECASE,
)

PATTERNS = [
    (re.compile(r"\bs(?P<s>\d{1,2})[\s._-]*e(?P<e>\d{1,4})\b", re.I), True),
    (re.compile(r"\b(?P<s>\d{1,2})x(?P<e>\d{1,4})\b", re.I), True),
    (re.compile(r"\b(?:episode|epis[oó]dio|ep|e)[\s._-]*(?P<e>\d{1,4})\b", re.I), False),
    (re.compile(r"[\s._-]-[\s._-]*(?P<e>\d{1,4})(?:v\d)?\b"), False),
    (re.compile(r"#\s*(?P<e>\d{1,4})\b"), False),
]


def _strip(name):
    s = BRACKETS.sub(" ", name)
    s = PARENS.sub(" ", s)
    s = NOISE.sub(" ", s)
    s = YEAR.sub(" ", s)
    s = re.sub(r"[_.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def detect_episode(filename):
    """Return (episode|None, note). note is a warning shown to the user."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename

    if SPECIAL.search(stem) or SPECIAL.search(_strip(stem)):
        return None, "special / extra"

    # Explicit SxxExx / 1x05 markers are unambiguous, so check the raw stem
    # first - before parentheses/brackets get stripped out. Otherwise a name
    # like "Show (S1.E5)" loses its marker when "(S1.E5)" is removed as if
    # it were junk like "(1080p)".
    for pat, has_season in PATTERNS[:2]:
        m = pat.search(stem)
        if m:
            return int(m.group("e")), ""

    cleaned = _strip(stem)
    for pat, _ in PATTERNS:
        m = pat.search(cleaned)
        if m:
            return int(m.group("e")), ""

    nums = re.findall(r"\b(\d{1,4})\b", cleaned)
    if len(nums) == 1:
        return int(nums[0]), "guessed"
    if nums:
        return int(nums[-1]), "check this"
    return None, "no number found"


# ----------------------------------------------------------------------
# Tab 1 - create empty folders
# ----------------------------------------------------------------------

class CreateTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=14)
        self.columnconfigure(1, weight=1)

        self.dir_var = tk.StringVar()
        self.name_var = tk.StringVar(value="Episode")
        self.count_var = tk.StringVar(value="12")
        self.start_var = tk.StringVar(value="1")
        self.pad_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Pick a folder to get started.")

        self._build()
        for v in (self.name_var, self.count_var, self.start_var,
                  self.dir_var, self.pad_var):
            v.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def _build(self):
        r = 0
        ttk.Label(self, text="Create in").grid(row=r, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.dir_var).grid(
            row=r, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Browse…", command=self.browse).grid(row=r, column=2)
        r += 1

        ttk.Label(self, text="Base name").grid(row=r, column=0, sticky="w", pady=8)
        ttk.Entry(self, textvariable=self.name_var).grid(
            row=r, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=8)
        r += 1

        opts = ttk.Frame(self)
        opts.grid(row=r, column=0, columnspan=3, sticky="w")
        ttk.Label(opts, text="How many").pack(side="left")
        ttk.Spinbox(opts, from_=1, to=9999, width=6,
                    textvariable=self.count_var).pack(side="left", padx=(6, 18))
        ttk.Label(opts, text="Start at").pack(side="left")
        ttk.Spinbox(opts, from_=0, to=9999, width=6,
                    textvariable=self.start_var).pack(side="left", padx=(6, 18))
        ttk.Checkbutton(opts, text="Pad numbers (01, 02…)",
                        variable=self.pad_var).pack(side="left")
        r += 1

        ttk.Separator(self).grid(row=r, column=0, columnspan=3, sticky="ew", pady=12)
        r += 1

        ttk.Label(self, text="Preview").grid(row=r, column=0, sticky="w")
        r += 1

        box = ttk.Frame(self)
        box.grid(row=r, column=0, columnspan=3, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.rowconfigure(r, weight=1)
        self.preview = tk.Listbox(box, height=8, activestyle="none",
                                  borderwidth=1, relief="solid",
                                  highlightthickness=0)
        self.preview.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.preview.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.preview.config(yscrollcommand=sb.set)
        r += 1

        ttk.Label(self, textvariable=self.status_var, foreground="#555",
                  wraplength=560).grid(row=r, column=0, columnspan=3,
                                       sticky="w", pady=(10, 6))
        r += 1

        self.btn = ttk.Button(self, text="Create folders", command=self.create)
        self.btn.grid(row=r, column=2, sticky="e")

    def browse(self):
        d = filedialog.askdirectory(title="Choose destination")
        if d:
            self.dir_var.set(os.path.normpath(d))

    def planned(self):
        name = self.name_var.get().strip()
        if not name:
            return [], "Enter a base name."
        if ILLEGAL & set(name):
            return [], 'A name cannot contain  < > : " / \\ | ? *'
        try:
            count = int(self.count_var.get())
            start = int(self.start_var.get())
        except ValueError:
            return [], "How many and Start at must be whole numbers."
        if count < 1:
            return [], "How many must be at least 1."
        if count > 5000:
            return [], "More than 5000 folders - lower the count."
        last = start + count - 1
        w = len(str(last)) if self.pad_var.get() else 0
        return [f"{name} {str(i).zfill(w)}" for i in range(start, last + 1)], ""

    def refresh(self):
        self.preview.delete(0, tk.END)
        names, err = self.planned()
        if err:
            self.status_var.set(err)
            self.btn.state(["disabled"])
            return

        target = self.dir_var.get().strip()
        existing = set()
        if target and os.path.isdir(target):
            try:
                existing = set(os.listdir(target))
            except OSError:
                pass
        for n in names:
            self.preview.insert(
                tk.END, "  " + n + ("   (already exists)" if n in existing else ""))

        if not target:
            self.status_var.set(f"{len(names)} folders ready - choose a destination.")
            self.btn.state(["disabled"])
        elif not os.path.isdir(target):
            self.status_var.set("That destination doesn't exist.")
            self.btn.state(["disabled"])
        else:
            clash = sum(1 for n in names if n in existing)
            msg = f"{len(names)} folders will be created."
            if clash:
                msg += f" {clash} already exist and will be skipped."
            self.status_var.set(msg)
            self.btn.state(["!disabled"])

    def create(self):
        names, err = self.planned()
        if err:
            return
        target = self.dir_var.get().strip()
        if not messagebox.askyesno(
                "Confirm", f"Create {len(names)} folders in:\n{target}\n\n"
                           f"First: {names[0]}\nLast:  {names[-1]}"):
            return
        made = skipped = 0
        for n in names:
            p = os.path.join(target, n)
            if os.path.exists(p):
                skipped += 1
                continue
            try:
                os.mkdir(p)
                made += 1
            except OSError as e:
                messagebox.showerror("Error", f"{n}: {e}")
                break
        messagebox.showinfo("Finished",
                            f"Created {made}. Skipped {skipped} (already existed).")
        self.refresh()


# ----------------------------------------------------------------------
# Tab 2 - sort existing files into folders
# ----------------------------------------------------------------------

class SortTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=14)
        self.columnconfigure(1, weight=1)
        self.rows = []

        self.dir_var = tk.StringVar()
        self.name_var = tk.StringVar(value="Episode")
        self.pad_var = tk.BooleanVar(value=True)
        self.copy_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(
            value="Choose the folder your episode files are sitting in, then Scan.")

        self._build()

    def _build(self):
        r = 0
        ttk.Label(self, text="Files are in").grid(row=r, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.dir_var).grid(
            row=r, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Browse…", command=self.browse).grid(row=r, column=2)
        r += 1

        opts = ttk.Frame(self)
        opts.grid(row=r, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(opts, text="Folder name").pack(side="left")
        ttk.Entry(opts, textvariable=self.name_var, width=14).pack(
            side="left", padx=(6, 16))
        ttk.Checkbutton(opts, text="Pad numbers", variable=self.pad_var,
                        command=self.fill_table).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(opts, text="Copy instead of move",
                        variable=self.copy_var).pack(side="left")
        ttk.Button(opts, text="Scan", command=self.scan).pack(side="right")
        self.name_var.trace_add("write", lambda *_: self.fill_table())
        r += 1

        cols = ("file", "ep", "dest")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        self.tree.heading("file", text="File")
        self.tree.heading("ep", text="Ep")
        self.tree.heading("dest", text="Goes into")
        self.tree.column("file", width=300, anchor="w")
        self.tree.column("ep", width=50, anchor="center")
        self.tree.column("dest", width=170, anchor="w")
        self.tree.grid(row=r, column=0, columnspan=2, sticky="nsew")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        sb.grid(row=r, column=2, sticky="nsw")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.tag_configure("bad", foreground="#b00020")
        self.tree.tag_configure("warn", foreground="#a06000")
        self.tree.bind("<Double-1>", self.edit_row)
        self.rowconfigure(r, weight=1)
        r += 1

        ttk.Label(self, text="Double-click a row to set its number by hand. "
                             "Rows in red are skipped.",
                  foreground="#777").grid(row=r, column=0, columnspan=3,
                                          sticky="w", pady=(6, 0))
        r += 1

        ttk.Label(self, textvariable=self.status_var, foreground="#555",
                  wraplength=560).grid(row=r, column=0, columnspan=3,
                                       sticky="w", pady=(8, 8))
        r += 1

        bar = ttk.Frame(self)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew")
        ttk.Button(bar, text="Undo last sort", command=self.undo).pack(side="left")
        self.go = ttk.Button(bar, text="Organize files", command=self.organize)
        self.go.pack(side="right")
        self.go.state(["disabled"])

    def browse(self):
        d = filedialog.askdirectory(title="Choose the folder containing your episodes")
        if d:
            self.dir_var.set(os.path.normpath(d))
            self.scan()

    def folder_for(self, ep):
        width = 0
        if self.pad_var.get():
            top = max((r["ep"] for r in self.rows if r["ep"] is not None),
                      default=ep)
            width = len(str(max(top, ep)))
        base = self.name_var.get().strip() or "Episode"
        return f"{base} {str(ep).zfill(width)}"

    def scan(self):
        src = self.dir_var.get().strip()
        self.rows = []
        if not os.path.isdir(src):
            self.status_var.set("That folder doesn't exist.")
            self.fill_table()
            return

        try:
            entries = sorted(os.listdir(src))
        except OSError as e:
            self.status_var.set(f"Could not read that folder: {e}")
            return

        for fn in entries:
            full = os.path.join(src, fn)
            if not os.path.isfile(full):
                continue
            if os.path.splitext(fn)[1].lower() not in MEDIA_EXT:
                continue
            ep, note = detect_episode(fn)
            self.rows.append({"file": fn, "ep": ep, "note": note})

        self.fill_table()

    def fill_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            if row["ep"] is None:
                dest, tag = f"- skipped ({row['note']})", "bad"
            else:
                dest = self.folder_for(row["ep"])
                tag = "warn" if row["note"] else ""
            self.tree.insert("", "end", iid=str(i),
                             values=(row["file"],
                                     row["ep"] if row["ep"] is not None else "?",
                                     dest),
                             tags=(tag,) if tag else ())

        ok = [r for r in self.rows if r["ep"] is not None]
        if not self.rows:
            self.status_var.set("No video or subtitle files found here.")
            self.go.state(["disabled"])
            return

        msg = f"{len(ok)} of {len(self.rows)} files matched."
        if len(self.rows) - len(ok):
            msg += f" {len(self.rows) - len(ok)} will be skipped."
        self.status_var.set(msg)
        self.go.state(["!disabled"] if ok else ["disabled"])

    def edit_row(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        row = self.rows[i]
        answer = simpledialog.askstring(
            "Set episode number",
            f"{row['file']}\n\nEpisode number (leave blank to skip this file):",
            initialvalue="" if row["ep"] is None else str(row["ep"]),
            parent=self)
        if answer is None:
            return
        answer = answer.strip()
        if not answer:
            row["ep"], row["note"] = None, "skipped by you"
        elif answer.isdigit():
            row["ep"], row["note"] = int(answer), ""
        else:
            messagebox.showwarning("Not a number", "Enter digits only.")
            return
        self.fill_table()

    def organize(self):
        src = self.dir_var.get().strip()
        jobs = [r for r in self.rows if r["ep"] is not None]
        if not jobs:
            return

        verb = "Copy" if self.copy_var.get() else "Move"
        folders = sorted({self.folder_for(r["ep"]) for r in jobs})
        tail = ("Originals stay where they are."
                if self.copy_var.get() else "You can undo this afterwards.")
        if not messagebox.askyesno(
                "Confirm",
                f"{verb} {len(jobs)} files into {len(folders)} folders inside:\n"
                f"{src}\n\n"
                f"Example: {jobs[0]['file']}\n  -> {self.folder_for(jobs[0]['ep'])}"
                f"\n\n{tail}"):
            return

        log = {"when": datetime.now().isoformat(timespec="seconds"),
               "root": src, "copied": self.copy_var.get(),
               "moves": [], "folders": []}
        done = failed = 0
        errors = []

        for r in jobs:
            folder = self.folder_for(r["ep"])
            dest_dir = os.path.join(src, folder)
            if not os.path.isdir(dest_dir):
                try:
                    os.mkdir(dest_dir)
                    log["folders"].append(dest_dir)
                except OSError as e:
                    errors.append(f"{folder}: {e}")
                    failed += 1
                    continue

            source = os.path.join(src, r["file"])
            target = os.path.join(dest_dir, r["file"])
            if os.path.exists(target):
                errors.append(f"{r['file']}: already in {folder}")
                failed += 1
                continue
            try:
                if self.copy_var.get():
                    shutil.copy2(source, target)
                else:
                    shutil.move(source, target)
                    log["moves"].append([source, target])
                done += 1
            except OSError as e:
                errors.append(f"{r['file']}: {e}")
                failed += 1

        if log["moves"] or log["folders"]:
            try:
                with open(os.path.join(src, UNDO_FILE), "w", encoding="utf-8") as f:
                    json.dump(log, f, indent=1)
            except OSError:
                pass

        summary = f"{verb}d {done} files into {len(folders)} folders."
        if failed:
            summary += f" {failed} had problems."
            messagebox.showwarning("Finished with problems",
                                   summary + "\n\n" + "\n".join(errors[:12]))
        else:
            messagebox.showinfo("Finished", summary)
        self.scan()

    def undo(self):
        src = self.dir_var.get().strip()
        path = os.path.join(src, UNDO_FILE)
        if not os.path.isfile(path):
            messagebox.showinfo("Nothing to undo",
                                "No record of a previous sort in this folder.")
            return
        try:
            with open(path, encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, ValueError):
            messagebox.showerror("Undo", "The undo record is unreadable.")
            return

        if log.get("copied"):
            messagebox.showinfo("Nothing to undo",
                                "The last run was a copy, so your originals "
                                "never moved.")
            return

        if not messagebox.askyesno(
                "Undo",
                f"Put {len(log['moves'])} files back where they were?\n\n"
                f"(from the sort on {log.get('when', 'an earlier run')})"):
            return

        back = 0
        for source, target in log["moves"]:
            if os.path.isfile(target) and not os.path.exists(source):
                try:
                    shutil.move(target, source)
                    back += 1
                except OSError:
                    pass
        removed = 0
        for folder in log["folders"]:
            try:
                os.rmdir(folder)
                removed += 1
            except OSError:
                pass
        try:
            os.remove(path)
        except OSError:
            pass

        messagebox.showinfo(
            "Undo", f"Restored {back} files and removed {removed} empty folders.")
        self.scan()


# ----------------------------------------------------------------------
# Tab 3 - rename files to a clean "Show Name (S1.E1)" style
# ----------------------------------------------------------------------

RENAME_UNDO_FILE = ".foldermaker_rename_undo.json"

TEMPLATE_PRESETS = [
    "{name} (S{season}.E{ep})",
    "{name} - S{season}E{ep}",
    "{name} S{season}E{ep}",
    "{name} - {ep}",
]


class RenameTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=14)
        self.columnconfigure(1, weight=1)
        self.rows = []

        self.dir_var = tk.StringVar()
        self.show_var = tk.StringVar(value="Show Name")
        self.season_var = tk.StringVar(value="1")
        self.template_var = tk.StringVar(value=TEMPLATE_PRESETS[0])
        self.pad_ep_var = tk.BooleanVar(value=False)
        self.pad_season_var = tk.BooleanVar(value=False)
        self.keep_ext_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(
            value="Choose the folder with the files to rename, then Scan.")

        self._build()

    def _build(self):
        r = 0
        ttk.Label(self, text="Files are in").grid(row=r, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.dir_var).grid(
            row=r, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Browse…", command=self.browse).grid(row=r, column=2)
        r += 1

        row1 = ttk.Frame(self)
        row1.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Label(row1, text="Show/movie name").pack(side="left")
        ttk.Entry(row1, textvariable=self.show_var, width=28).pack(
            side="left", padx=(6, 18))
        ttk.Label(row1, text="Season").pack(side="left")
        ttk.Spinbox(row1, from_=0, to=99, width=4,
                    textvariable=self.season_var).pack(side="left", padx=(6, 0))
        r += 1

        row2 = ttk.Frame(self)
        row2.grid(row=r, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Label(row2, text="Format").pack(side="left")
        ttk.Combobox(row2, textvariable=self.template_var,
                     values=TEMPLATE_PRESETS, width=28).pack(
            side="left", padx=(6, 18))
        ttk.Checkbutton(row2, text="Pad episode (01)",
                        variable=self.pad_ep_var,
                        command=self.fill_table).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(row2, text="Pad season (01)",
                        variable=self.pad_season_var,
                        command=self.fill_table).pack(side="left")
        r += 1

        row3 = ttk.Frame(self)
        row3.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Label(row3, text="{name} = show name above, {season} = season, "
                             "{ep} = episode number. You can type your own "
                             "format too.",
                  foreground="#777", wraplength=560).pack(side="left")
        ttk.Button(row3, text="Scan", command=self.scan).pack(side="right")
        r += 1

        for v in (self.show_var, self.season_var, self.template_var):
            v.trace_add("write", lambda *_: self.fill_table())

        cols = ("file", "ep", "new")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        self.tree.heading("file", text="Current name")
        self.tree.heading("ep", text="Ep")
        self.tree.heading("new", text="New name")
        self.tree.column("file", width=260, anchor="w")
        self.tree.column("ep", width=45, anchor="center")
        self.tree.column("new", width=260, anchor="w")
        self.tree.grid(row=r, column=0, columnspan=2, sticky="nsew")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        sb.grid(row=r, column=2, sticky="nsw")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.tag_configure("bad", foreground="#b00020")
        self.tree.tag_configure("warn", foreground="#a06000")
        self.tree.bind("<Double-1>", self.edit_row)
        self.rowconfigure(r, weight=1)
        r += 1

        ttk.Label(self, text="Double-click a row to fix its episode number "
                             "by hand. Rows in red are skipped.",
                  foreground="#777").grid(row=r, column=0, columnspan=3,
                                          sticky="w", pady=(6, 0))
        r += 1

        ttk.Label(self, textvariable=self.status_var, foreground="#555",
                  wraplength=560).grid(row=r, column=0, columnspan=3,
                                       sticky="w", pady=(8, 8))
        r += 1

        bar = ttk.Frame(self)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew")
        ttk.Button(bar, text="Undo last rename", command=self.undo).pack(side="left")
        self.go = ttk.Button(bar, text="Rename files", command=self.rename)
        self.go.pack(side="right")
        self.go.state(["disabled"])

    def browse(self):
        d = filedialog.askdirectory(title="Choose the folder with files to rename")
        if d:
            self.dir_var.set(os.path.normpath(d))
            self.scan()

    def new_name(self, ep, ext):
        show = sanitize_piece(self.show_var.get().strip()) or "Show"
        try:
            season = int(self.season_var.get())
        except ValueError:
            season = 1
        ep_str = str(ep).zfill(2) if self.pad_ep_var.get() else str(ep)
        season_str = str(season).zfill(2) if self.pad_season_var.get() else str(season)
        try:
            base = self.template_var.get().format(
                name=show, season=season_str, ep=ep_str)
        except (KeyError, IndexError, ValueError):
            base = f"{show} (S{season_str}.E{ep_str})"
        base = sanitize_piece(base)
        return base + (ext if self.keep_ext_var.get() else "")

    def scan(self):
        src = self.dir_var.get().strip()
        self.rows = []
        if not os.path.isdir(src):
            self.status_var.set("That folder doesn't exist.")
            self.fill_table()
            return
        try:
            entries = sorted(os.listdir(src))
        except OSError as e:
            self.status_var.set(f"Could not read that folder: {e}")
            return

        for fn in entries:
            if not os.path.isfile(os.path.join(src, fn)):
                continue
            if os.path.splitext(fn)[1].lower() not in MEDIA_EXT:
                continue
            ep, note = detect_episode(fn)
            self.rows.append({"file": fn, "ep": ep, "note": note})

        self.fill_table()

    def fill_table(self):
        self.tree.delete(*self.tree.get_children())
        seen_new_names = {}
        for i, row in enumerate(self.rows):
            ext = os.path.splitext(row["file"])[1]
            if row["ep"] is None:
                new, tag = f"- skipped ({row['note']})", "bad"
            else:
                new = self.new_name(row["ep"], ext)
                tag = "warn" if row["note"] else ""
                seen_new_names.setdefault(new, []).append(i)
            self.tree.insert("", "end", iid=str(i),
                             values=(row["file"],
                                     row["ep"] if row["ep"] is not None else "?",
                                     new),
                             tags=(tag,) if tag else ())

        # Flag collisions (two source files that would land on the same new name).
        for new, idxs in seen_new_names.items():
            if len(idxs) > 1:
                for i in idxs:
                    self.tree.item(str(i), tags=("bad",))

        ok = [r for r in self.rows if r["ep"] is not None]
        if not self.rows:
            self.status_var.set("No matching files found here.")
            self.go.state(["disabled"])
            return
        msg = f"{len(ok)} of {len(self.rows)} files will be renamed."
        collisions = sum(len(v) for v in seen_new_names.values() if len(v) > 1)
        if collisions:
            msg += f" {collisions} would collide on the same name - fix those first."
        self.status_var.set(msg)
        self.go.state(["!disabled"] if ok and not collisions else ["disabled"])

    def edit_row(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        row = self.rows[i]
        answer = simpledialog.askstring(
            "Set episode number",
            f"{row['file']}\n\nEpisode number (leave blank to skip this file):",
            initialvalue="" if row["ep"] is None else str(row["ep"]),
            parent=self)
        if answer is None:
            return
        answer = answer.strip()
        if not answer:
            row["ep"], row["note"] = None, "skipped by you"
        elif answer.isdigit():
            row["ep"], row["note"] = int(answer), ""
        else:
            messagebox.showwarning("Not a number", "Enter digits only.")
            return
        self.fill_table()

    def rename(self):
        src = self.dir_var.get().strip()
        jobs = [r for r in self.rows if r["ep"] is not None]
        if not jobs:
            return

        example_new = self.new_name(jobs[0]["ep"], os.path.splitext(jobs[0]["file"])[1])
        if not messagebox.askyesno(
                "Confirm",
                f"Rename {len(jobs)} files in:\n{src}\n\n"
                f"Example:\n{jobs[0]['file']}\n  -> {example_new}"):
            return

        log = {"when": datetime.now().isoformat(timespec="seconds"),
               "root": src, "renames": []}
        done = failed = 0
        errors = []

        for r in jobs:
            ext = os.path.splitext(r["file"])[1]
            new = self.new_name(r["ep"], ext)
            old_path = os.path.join(src, r["file"])
            new_path = os.path.join(src, new)
            if os.path.exists(new_path):
                errors.append(f"{r['file']}: '{new}' already exists")
                failed += 1
                continue
            try:
                os.rename(old_path, new_path)
                log["renames"].append([old_path, new_path])
                done += 1
            except OSError as e:
                errors.append(f"{r['file']}: {e}")
                failed += 1

        if log["renames"]:
            try:
                with open(os.path.join(src, RENAME_UNDO_FILE), "w",
                         encoding="utf-8") as f:
                    json.dump(log, f, indent=1)
            except OSError:
                pass

        summary = f"Renamed {done} files."
        if failed:
            summary += f" {failed} had problems."
            messagebox.showwarning("Finished with problems",
                                   summary + "\n\n" + "\n".join(errors[:12]))
        else:
            messagebox.showinfo("Finished", summary)
        self.scan()

    def undo(self):
        src = self.dir_var.get().strip()
        path = os.path.join(src, RENAME_UNDO_FILE)
        if not os.path.isfile(path):
            messagebox.showinfo("Nothing to undo",
                                "No record of a previous rename in this folder.")
            return
        try:
            with open(path, encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, ValueError):
            messagebox.showerror("Undo", "The undo record is unreadable.")
            return

        if not messagebox.askyesno(
                "Undo",
                f"Rename {len(log['renames'])} files back to their original "
                f"names?\n\n(from the rename on {log.get('when', 'an earlier run')})"):
            return

        back = 0
        for old_path, new_path in log["renames"]:
            if os.path.isfile(new_path) and not os.path.exists(old_path):
                try:
                    os.rename(new_path, old_path)
                    back += 1
                except OSError:
                    pass
        try:
            os.remove(path)
        except OSError:
            pass

        messagebox.showinfo("Undo", f"Restored {back} original file names.")
        self.scan()


# ----------------------------------------------------------------------

def main():
    root = tk.Tk()
    root.title("Folder Maker")
    root.minsize(680, 600)
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)
    nb.add(CreateTab(nb), text="  Create folders  ")
    nb.add(SortTab(nb), text="  Sort files into folders  ")
    nb.add(RenameTab(nb), text="  Rename files  ")
    root.mainloop()


if __name__ == "__main__":
    main()
