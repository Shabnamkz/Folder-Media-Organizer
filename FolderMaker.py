#!/usr/bin/env python3
"""
FolderMaker - create numbered folders, and sort episode files into them.

Run:   python main.py
Build: pyinstaller --onefile --windowed --name FolderMaker --icon FolderMaker.ico --add-data "FolderMaker.ico;." main.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter.font import nametofont
from tkinter.ttk import Combobox


def app_icon():
    """Path to the bundled icon when frozen to an exe, else None."""
    if getattr(sys, "frozen", False):
        p = os.path.join(sys._MEIPASS, "FolderMaker.ico")
        return p if os.path.isfile(p) else None
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "FolderMaker.ico")
    return here if os.path.isfile(here) else None


def enable_dpi_awareness():
    """Render sharp on scaled displays (125%/150%). Without this Windows
    bitmap-stretches the whole window, which reads as blur. Must run
    before the Tk window is created."""
    if sys.platform != "win32":
        return
    import ctypes
    for fn in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
               lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1),
               lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try:
            fn()
            return
        except Exception:
            continue


# ----------------------------------------------------------------------
# Theming - light & dark palettes applied to ttk styles, classic tk
# widgets (via tk_setPalette) and the native Windows title bar.
# ----------------------------------------------------------------------

PREFS_FILE = os.path.join(os.path.expanduser("~"), ".foldermaker_prefs.json")

# --- Auto-update ---------------------------------------------------------
# The exe checks GitHub on startup and, if a newer release exists, downloads
# it and swaps itself in place. Version is a manual constant that must match
# the GitHub release tag (v1.2 -> "1.2.0").
APP_VERSION = "1.2.0"
REPO = "Shabnamkz/Folder-Media-Organizer"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/latest"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest/download/FolderMaker.exe"

LIGHT = {
    "bg": "#f5f5f5", "field": "#ffffff", "tree": "#ffffff", "header": "#ededed",
    "btn": "#e6e6e6", "btn_hover": "#efefef", "btn_pressed": "#d9d9d9",
    "tab": "#e9e9e9", "tab_hover": "#f2f2f2",
    "fg": "#1f1f1f", "muted": "#5a5a5a", "hint": "#808080",
    "disabled": "#9c9c9c", "border": "#cfcfcf",
    "select": "#8b5cf6", "select_fg": "#ffffff",
    "accent": "#8b5cf6", "accent_hover": "#7c4ee6", "accent_pressed": "#6d40d6",
    "accent_fg": "#ffffff",
    "bad": "#b00020", "warn": "#a06000",
}

DARK = {
    "bg": "#1e1f22", "field": "#2b2d30", "tree": "#252629", "header": "#313235",
    "btn": "#3a3c40", "btn_hover": "#46494e", "btn_pressed": "#2e3033",
    "tab": "#2e3033", "tab_hover": "#383b3f",
    "fg": "#e4e4e4", "muted": "#a9adb3", "hint": "#8b8f95",
    "disabled": "#666a70", "border": "#45474b",
    "select": "#a78bfa", "select_fg": "#1b0e3b",
    "accent": "#a78bfa", "accent_hover": "#b69cfc", "accent_pressed": "#9472f8",
    "accent_fg": "#1b0e3b",
    "bad": "#ff6b6b", "warn": "#ffb454",
}


def set_file_hidden(path, hidden):
    """Toggle the Windows hidden attribute (a leading dot hides nothing
    there). A hidden file also refuses to be truncated by open(..., "w"),
    so callers must unhide it before rewriting."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        attrs = 0x2 if hidden else 0x80  # FILE_ATTRIBUTE_HIDDEN / NORMAL
        ctypes.windll.kernel32.SetFileAttributesW(os.path.abspath(path), attrs)
    except Exception:
        pass


def load_prefs():
    try:
        with open(PREFS_FILE, encoding="utf-8") as f:
            p = json.load(f)
        return p if isinstance(p, dict) else {}
    except (OSError, ValueError):
        return {}


def save_prefs(prefs):
    try:
        set_file_hidden(PREFS_FILE, False)
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        set_file_hidden(PREFS_FILE, True)
    except OSError:
        pass


def walk_widgets(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk_widgets(child)


# ----------------------------------------------------------------------
# Custom-drawn controls - the clam theme engine can't round checkbox
# borders, tab tops, or swap the indicator mark, so those elements are
# replaced with images drawn at runtime (plain PhotoImages, no Pillow).
# Shapes are rasterized with 3x3 supersampling for smooth edges; the
# corner pixels are filled with the page background, which is uniform
# behind every checkbox and tab, so no alpha channel is needed.
# ----------------------------------------------------------------------

def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb(c):
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def _mix(bg, fg, t):
    return tuple(round(bg[i] + (fg[i] - bg[i]) * t) for i in range(3))


def _rounded_rect(x0, y0, x1, y1, r):
    """inside(x, y) predicate for a rounded rectangle."""
    def inside(x, y):
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False
        cx = min(max(x, x0 + r), x1 - r)
        cy = min(max(y, y0 + r), y1 - r)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    return inside


def _rounded_top(x0, y0, x1, y1, r):
    """inside(x, y) for a rect with only its top corners rounded."""
    def inside(x, y):
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False
        if y >= y0 + r:
            return True
        if x0 + r <= x <= x1 - r:
            return True
        cx = x0 + r if x < x0 + r else x1 - r
        return (x - cx) ** 2 + (y - (y0 + r)) ** 2 <= r * r
    return inside


def _stroke(ax, ay, bx, by, hw):
    """inside(x, y) for a thick line segment from a to b."""
    def inside(x, y):
        dx, dy = bx - ax, by - ay
        dd = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / dd))
        px, py = ax + t * dx, ay + t * dy
        return (x - px) ** 2 + (y - py) ** 2 <= hw * hw
    return inside


def _tick(size, hw):
    """inside(x, y) for a checkmark scaled to a size x size box."""
    s1 = _stroke(size * 0.24, size * 0.53, size * 0.43, size * 0.72, hw)
    s2 = _stroke(size * 0.43, size * 0.72, size * 0.76, size * 0.28, hw)
    return lambda x, y: s1(x, y) or s2(x, y)


def _render(root, w, h, bg, layers):
    """Rasterize shaped color layers over a solid bg; returns a PhotoImage.
    layers is a list of (rgb, inside_fn) painted bottom to top."""
    ss = 3  # supersampling factor
    grid = []
    for y in range(h):
        row = []
        for x in range(w):
            c = _hex_rgb(bg)
            for col, fn in layers:
                hits = 0
                for i in range(ss):
                    for j in range(ss):
                        if fn(x + (i + 0.5) / ss, y + (j + 0.5) / ss):
                            hits += 1
                t = hits / (ss * ss)
                if t:
                    c = _mix(c, col, t)
            row.append(_rgb(c))
        grid.append(row)
    img = tk.PhotoImage(width=w, height=h)
    for y, r_ in enumerate(grid):
        img.put("{" + " ".join(r_) + "}", to=(0, y))
    return img


def _dpi_scale(root):
    """1.0 at 100% display scaling; keeps drawn controls crisp on HiDPI."""
    try:
        return float(root.tk.call("tk", "scaling")) / (96 / 72)
    except tk.TclError:
        return 1.0


def _check_image_set(root, p, s):
    """Build (off, on, off_disabled, on_disabled) PhotoImages for one palette."""
    size = max(13, round(16 * s))       # the square itself
    gap = round(6 * s)                  # breathing room before the label
    w, h = size + gap, size
    r = round(size * 0.30)

    box = _rounded_rect(0.5, 0.5, size - 0.5, size - 0.5, r)
    inner = _rounded_rect(2.5, 2.5, size - 2.5, size - 2.5, max(1.0, r - 2))
    # the tick is drawn in a (size-5)-wide coordinate space; shift it by the
    # inset so that space lands centered on the box instead of its top-left
    tick_shape = _tick(size - 5, size * 0.085)
    tick = lambda x, y: tick_shape(x - 2.5, y - 2.5)

    bg_c = _hex_rgb(p["bg"])
    border_c, field_c = _hex_rgb(p["border"]), _hex_rgb(p["field"])
    accent_c = _hex_rgb(p["accent"])
    white = (255, 255, 255)

    off = _render(root, w, h, p["bg"], [(border_c, box), (field_c, inner)])
    on = _render(root, w, h, p["bg"], [(accent_c, box), (white, tick)])
    off_dis = _render(root, w, h, p["bg"],
                      [(_mix(border_c, bg_c, 0.5), box),
                       (_mix(field_c, bg_c, 0.5), inner)])
    on_dis = _render(root, w, h, p["bg"],
                     [(_mix(accent_c, bg_c, 0.55), box),
                      (_mix(white, bg_c, 0.45), tick)])
    return off, on, off_dis, on_dis


def _tab_image_set(root, p, s):
    """Build {state: PhotoImage} tab backgrounds for one palette."""
    tr = max(5, round(8 * s))          # corner radius
    tw, th = 4 * tr + 40, tr + 26
    shape = _rounded_top(0.5, 0.5, tw - 0.5, th - 0.5, tr)
    return {state: _render(root, tw, th, p["bg"], [(_hex_rgb(p[key]), shape)])
            for state, key in (("", "tab"), ("active", "tab_hover"),
                               ("selected", "btn_hover"))}


def _install_custom_controls(root, style):
    """Create the rounded checkbutton and tab image elements once, for both
    palettes. Elements bake in their images at creation and ttk has no way
    to reconfigure them, so this must run exactly once: regenerating the
    PhotoImages on a later call would orphan (and destroy) the ones the
    live elements still use, blanking the controls out."""
    wanted = ("Checkbutton.round.light", "Checkbutton.round.dark",
              "Notebook.roundtab.light", "Notebook.roundtab.dark")
    if all(n in style.element_names() for n in wanted):
        return  # already installed

    s = _dpi_scale(root)
    keep = []

    for suffix, pal in (("light", LIGHT), ("dark", DARK)):
        off, on, off_dis, on_dis = _check_image_set(root, pal, s)
        keep += [off, on, off_dis, on_dis]
        style.element_create(
            f"Checkbutton.round.{suffix}", "image", off,
            ("disabled selected", on_dis), ("disabled", off_dis),
            ("selected", on))

        tabs = _tab_image_set(root, pal, s)
        keep += list(tabs.values())
        style.element_create(
            f"Notebook.roundtab.{suffix}", "image", tabs[""],
            ("active", tabs["active"]),
            ("selected", tabs["selected"]),
            border=max(5, round(8 * s)), sticky="news")

    style._round_ctrl_images = keep  # prevent PhotoImage GC


def _restyle_elements(root, style, dark):
    """Point the TCheckbutton / TNotebook.Tab layouts at the image elements
    for the current theme."""
    _install_custom_controls(root, style)
    suffix = "dark" if dark else "light"
    check_elem = f"Checkbutton.round.{suffix}"
    tab_elem = f"Notebook.roundtab.{suffix}"

    def swap(node, old_names, new):
        elem, opts = node[0], dict(node[1])
        if elem in old_names:
            elem = new
        if opts.get("children"):
            opts["children"] = [swap(c, old_names, new) for c in opts["children"]]
        return (elem, opts)

    check_old = {"Checkbutton.indicator", "Checkbutton.round.light",
                 "Checkbutton.round.dark"}
    layout = style.layout("TCheckbutton")
    style.layout("TCheckbutton", [swap(n, check_old, check_elem)
                                  for n in layout])

    tab_old = {"Notebook.tab", "Notebook.roundtab.light",
               "Notebook.roundtab.dark"}
    layout = style.layout("TNotebook.Tab")
    style.layout("TNotebook.Tab", [swap(n, tab_old, tab_elem)
                                   for n in layout])


def apply_theme(root, style, dark):
    """Recolor everything: ttk styles, classic tk widgets, tree tags."""
    p = DARK if dark else LIGHT

    style.theme_use("clam")  # fully colorable base, unlike 'vista'

    style.configure(".", background=p["bg"], foreground=p["fg"],
                    fieldbackground=p["field"], bordercolor=p["border"],
                    lightcolor=p["border"], darkcolor=p["border"],
                    troughcolor=p["bg"])

    style.configure("TButton", background=p["btn"], foreground=p["fg"],
                    padding=(12, 6), borderwidth=1)
    style.map("TButton",
              background=[("pressed", p["btn_pressed"]),
                          ("active", p["btn_hover"])],
              foreground=[("disabled", p["disabled"])])

    # Filled teal primary for the one main action per tab.
    style.configure("Accent.TButton", background=p["accent"],
                    foreground=p["accent_fg"], padding=(12, 6),
                    borderwidth=1, bordercolor=p["accent"])
    style.map("Accent.TButton",
              background=[("disabled", p["btn"]),
                          ("pressed", p["accent_pressed"]),
                          ("active", p["accent_hover"])],
              foreground=[("disabled", p["disabled"])],
              bordercolor=[("disabled", p["border"])])

    for w in ("TEntry", "TSpinbox"):
        style.configure(w, fieldbackground=p["field"], foreground=p["fg"],
                        insertcolor=p["fg"], background=p["btn"],
                        arrowcolor=p["fg"], borderwidth=1)
        style.map(w,
                  fieldbackground=[("disabled", p["bg"])],
                  foreground=[("disabled", p["disabled"])],
                  lightcolor=[("focus", p["accent"])],
                  darkcolor=[("focus", p["accent"])],
                  bordercolor=[("focus", p["accent"])])

    style.configure("TCombobox", fieldbackground=p["field"], foreground=p["fg"],
                    background=p["btn"], arrowcolor=p["fg"], borderwidth=1)
    style.map("TCombobox",
              fieldbackground=[("readonly", p["field"]),
                               ("disabled", p["bg"])],
              foreground=[("readonly", p["fg"]),
                          ("disabled", p["disabled"])],
              arrowcolor=[("active", p["accent"])],
              bordercolor=[("focus", p["accent"])])
    # the popdown list is a classic tk listbox, styled via the option DB
    root.option_add("*TCombobox*Listbox.background", p["field"])
    root.option_add("*TCombobox*Listbox.foreground", p["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["select"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["select_fg"])

    style.configure("TCheckbutton", background=p["bg"], foreground=p["fg"])
    style.map("TCheckbutton",
              background=[("active", p["bg"])],
              foreground=[("disabled", p["disabled"])])

    style.configure("TNotebook", background=p["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=p["tab"], foreground=p["muted"],
                    padding=(16, 8), borderwidth=0)
    style.map("TNotebook.Tab",
              foreground=[("selected", p["accent"])])

    style.configure("Treeview", background=p["tree"], foreground=p["fg"],
                    fieldbackground=p["tree"], rowheight=26, borderwidth=1)
    style.configure("Treeview.Heading", background=p["header"],
                    foreground=p["muted"], relief="flat", padding=(8, 5),
                    borderwidth=1)
    style.map("Treeview.Heading", background=[("active", p["btn_hover"])])
    style.map("Treeview", background=[("selected", p["select"])],
              foreground=[("selected", p["select_fg"])])

    style.configure("Vertical.TScrollbar", background=p["btn"],
                    troughcolor=p["bg"], bordercolor=p["bg"],
                    lightcolor=p["btn"], darkcolor=p["btn"],
                    arrowcolor=p["fg"])
    style.map("Vertical.TScrollbar",
              background=[("active", p["btn_hover"]),
                          ("pressed", p["btn_pressed"])])

    style.configure("TSeparator", background=p["border"])
    style.configure("Status.TLabel", background=p["bg"], foreground=p["muted"])
    style.configure("Hint.TLabel", background=p["bg"], foreground=p["hint"])
    style.configure("Title.TLabel", background=p["bg"], foreground=p["fg"])

    # Classic tk widgets (listboxes here, dialogs elsewhere) - one call
    # recolors them all, including ones created later like dialog entries.
    try:
        root.tk_setPalette(background=p["bg"], foreground=p["fg"],
                           selectBackground=p["select"],
                           selectForeground=p["select_fg"],
                           insertBackground=p["fg"],
                           highlightBackground=p["border"],
                           highlightColor=p["accent"],
                           troughColor=p["bg"])
    except tk.TclError:
        pass

    # per-widget bits that styles can't reach
    for w in walk_widgets(root):
        if isinstance(w, tk.Listbox):
            w.configure(background=p["tree"], foreground=p["fg"],
                        selectbackground=p["select"],
                        selectforeground=p["select_fg"],
                        disabledforeground=p["disabled"],
                        relief="flat", borderwidth=0, highlightthickness=1,
                        highlightbackground=p["border"],
                        highlightcolor=p["border"])
        elif isinstance(w, ttk.Treeview):
            w.tag_configure("bad", foreground=p["bad"])
            w.tag_configure("warn", foreground=p["warn"])

    _restyle_elements(root, style, dark)


def set_titlebar_dark(root, dark):
    """Tint the native Windows title bar to match (Win10 1809+)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass

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

    # Try every marker pattern against the raw stem first, before any
    # cleanup happens. This matters because cleanup strips out parenthesised
    # text like "(1080p)" as noise - but release names also put real episode
    # markers in parentheses, e.g. "(S1.E5)" or "(E600)". If we only cleaned
    # first, those markers would be deleted before we ever got to read them.
    for pat, _ in PATTERNS:
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
    def __init__(self, master, dir_var):
        super().__init__(master, padding=14)
        self.columnconfigure(1, weight=1)

        self.dir_var = dir_var  # shared across tabs - the last used folder
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

        ttk.Label(self, text="Base Name").grid(row=r, column=0, sticky="w", pady=8)
        ttk.Entry(self, textvariable=self.name_var).grid(
            row=r, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=8)
        r += 1

        opts = ttk.Frame(self)
        opts.grid(row=r, column=0, columnspan=3, sticky="w")
        ttk.Label(opts, text="How Many").pack(side="left")
        ttk.Spinbox(opts, from_=1, to=9999, width=6,
                    textvariable=self.count_var).pack(side="left", padx=(6, 18))
        ttk.Label(opts, text="Start at").pack(side="left")
        ttk.Spinbox(opts, from_=0, to=9999, width=6,
                    textvariable=self.start_var).pack(side="left", padx=(6, 18))
        ttk.Checkbutton(opts, text="Pad Numbers (01, 02…)",
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

        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel",
                  wraplength=560).grid(row=r, column=0, columnspan=3,
                                       sticky="w", pady=(10, 6))
        r += 1

        self.btn = ttk.Button(self, text="Create Folders", style="Accent.TButton",
                              command=self.create)
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
    def __init__(self, master, dir_var):
        super().__init__(master, padding=14)
        self.columnconfigure(1, weight=1)
        self.rows = []

        self.dir_var = dir_var  # shared across tabs - the last used folder
        self.name_var = tk.StringVar(value="Episode")
        self.pad_var = tk.BooleanVar(value=True)
        self.copy_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(
            value="Choose the folder your episode files are sitting in, then Scan.")

        self._build()
        self.refresh_undo()
        self.dir_var.trace_add("write", lambda *_: self.refresh_undo())

    def _build(self):
        r = 0
        ttk.Label(self, text="Files Are in").grid(row=r, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.dir_var).grid(
            row=r, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Browse…", command=self.browse).grid(row=r, column=2)
        r += 1

        opts = ttk.Frame(self)
        opts.grid(row=r, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(opts, text="Folder Name").pack(side="left")
        ttk.Entry(opts, textvariable=self.name_var, width=14).pack(
            side="left", padx=(6, 16))
        ttk.Checkbutton(opts, text="Pad Numbers", variable=self.pad_var,
                        command=self.fill_table).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(opts, text="Copy Instead of Move",
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
        self.tree.bind("<Double-1>", self.edit_row)
        self.rowconfigure(r, weight=1)
        r += 1

        ttk.Label(self, text="Double-click a row to set its number by hand. "
                             "Rows in red are skipped.",
                  style="Hint.TLabel").grid(row=r, column=0, columnspan=3,
                                          sticky="w", pady=(6, 0))
        r += 1

        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel",
                  wraplength=560).grid(row=r, column=0, columnspan=3,
                                       sticky="w", pady=(8, 8))
        r += 1

        bar = ttk.Frame(self)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew")
        self.undo_btn = ttk.Button(bar, text="Undo Last Sort", command=self.undo)
        self.undo_btn.pack(side="left")
        self.undo_btn.state(["disabled"])
        self.go = ttk.Button(bar, text="Organize Files", style="Accent.TButton",
                             command=self.organize)
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

    def refresh_undo(self):
        """The Undo button only wakes up when there is a record to undo."""
        src = self.dir_var.get().strip()
        has = os.path.isfile(os.path.join(src, UNDO_FILE))
        self.undo_btn.state(["!disabled"] if has else ["disabled"])

    def scan(self):
        self.refresh_undo()
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
            "Set Episode Number",
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
            messagebox.showwarning("Not a Number", "Enter digits only.")
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
            undo_path = os.path.join(src, UNDO_FILE)
            try:
                set_file_hidden(undo_path, False)  # can't truncate while hidden
                with open(undo_path, "w", encoding="utf-8") as f:
                    json.dump(log, f, indent=1)
                set_file_hidden(undo_path, True)
            except OSError:
                pass

        summary = f"{verb}d {done} files into {len(folders)} folders."
        if failed:
            summary += f" {failed} had problems."
            messagebox.showwarning("Finished with Problems",
                                   summary + "\n\n" + "\n".join(errors[:12]))
        else:
            messagebox.showinfo("Finished", summary)
        self.scan()

    def undo(self):
        src = self.dir_var.get().strip()
        path = os.path.join(src, UNDO_FILE)
        if not os.path.isfile(path):
            messagebox.showinfo("Nothing to Undo",
                                "No record of a previous sort in this folder.")
            return
        try:
            with open(path, encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, ValueError):
            messagebox.showerror("Undo", "The undo record is unreadable.")
            return

        if log.get("copied"):
            messagebox.showinfo("Nothing to Undo",
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
    def __init__(self, master, dir_var):
        super().__init__(master, padding=14)
        self.columnconfigure(1, weight=1)
        self.rows = []

        self.dir_var = dir_var  # shared across tabs - the last used folder
        self.show_var = tk.StringVar(value="Show Name")
        self.season_var = tk.StringVar(value="1")
        self.template_var = tk.StringVar(value=TEMPLATE_PRESETS[0])
        self.pad_ep_var = tk.BooleanVar(value=False)
        self.pad_season_var = tk.BooleanVar(value=False)
        self.keep_ext_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(
            value="Choose the folder with the files to rename, then Scan.")

        self._build()
        self.refresh_undo()
        self.dir_var.trace_add("write", lambda *_: self.refresh_undo())

    def _build(self):
        r = 0
        ttk.Label(self, text="Files Are in").grid(row=r, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.dir_var).grid(
            row=r, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Browse…", command=self.browse).grid(row=r, column=2)
        r += 1

        row1 = ttk.Frame(self)
        row1.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Label(row1, text="Show/Movie Name").pack(side="left")
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
        ttk.Checkbutton(row2, text="Pad Episode (01)",
                        variable=self.pad_ep_var,
                        command=self.fill_table).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(row2, text="Pad Season (01)",
                        variable=self.pad_season_var,
                        command=self.fill_table).pack(side="left")
        r += 1

        row3 = ttk.Frame(self)
        row3.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Label(row3, text="{name} = show name above, {season} = season, "
                             "{ep} = episode number. You can type your own "
                             "format too.",
                  style="Hint.TLabel", wraplength=560).pack(side="left")
        ttk.Button(row3, text="Scan", command=self.scan).pack(side="right")
        r += 1

        for v in (self.show_var, self.season_var, self.template_var):
            v.trace_add("write", lambda *_: self.fill_table())

        cols = ("file", "ep", "new")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        self.tree.heading("file", text="Current Name")
        self.tree.heading("ep", text="Ep")
        self.tree.heading("new", text="New Name")
        self.tree.column("file", width=260, anchor="w")
        self.tree.column("ep", width=45, anchor="center")
        self.tree.column("new", width=260, anchor="w")
        self.tree.grid(row=r, column=0, columnspan=2, sticky="nsew")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        sb.grid(row=r, column=2, sticky="nsw")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self.edit_row)
        self.rowconfigure(r, weight=1)
        r += 1

        ttk.Label(self, text="Double-click a row to fix its episode number "
                             "by hand. Rows in red are skipped.",
                  style="Hint.TLabel").grid(row=r, column=0, columnspan=3,
                                          sticky="w", pady=(6, 0))
        r += 1

        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel",
                  wraplength=560).grid(row=r, column=0, columnspan=3,
                                       sticky="w", pady=(8, 8))
        r += 1

        bar = ttk.Frame(self)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew")
        self.undo_btn = ttk.Button(bar, text="Undo Last Rename", command=self.undo)
        self.undo_btn.pack(side="left")
        self.undo_btn.state(["disabled"])
        self.go = ttk.Button(bar, text="Rename Files", style="Accent.TButton",
                             command=self.rename)
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

    def refresh_undo(self):
        """The Undo button only wakes up when there is a record to undo."""
        src = self.dir_var.get().strip()
        has = os.path.isfile(os.path.join(src, RENAME_UNDO_FILE))
        self.undo_btn.state(["!disabled"] if has else ["disabled"])

    def scan(self):
        self.refresh_undo()
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
            "Set Episode Number",
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
            messagebox.showwarning("Not a Number", "Enter digits only.")
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
            undo_path = os.path.join(src, RENAME_UNDO_FILE)
            try:
                set_file_hidden(undo_path, False)  # can't truncate while hidden
                with open(undo_path, "w", encoding="utf-8") as f:
                    json.dump(log, f, indent=1)
                set_file_hidden(undo_path, True)
            except OSError:
                pass

        summary = f"Renamed {done} files."
        if failed:
            summary += f" {failed} had problems."
            messagebox.showwarning("Finished with Problems",
                                   summary + "\n\n" + "\n".join(errors[:12]))
        else:
            messagebox.showinfo("Finished", summary)
        self.scan()

    def undo(self):
        src = self.dir_var.get().strip()
        path = os.path.join(src, RENAME_UNDO_FILE)
        if not os.path.isfile(path):
            messagebox.showinfo("Nothing to Undo",
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

# --- Auto-update implementation -----------------------------------------
# A frozen exe cannot overwrite its own file (Windows locks it), so the
# swap is done by a tiny detached .bat helper that outlives the app: it
# waits for the app's pid to exit, copies the downloaded exe over the
# real one, and relaunches it. Everything runs on the stdlib only.

_UPDATER_BAT = r"""@echo off
setlocal
set PID=%1
set NEW=%2
set DEST=%3
:wait
tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
:copy
copy /y "%NEW%" "%DEST%" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto copy
)
start "" "%DEST%"
del "%~f0"
"""


def _version_tuple(s):
    """Parse 'v1.2' / '1.2.0' / 'v2' into (1, 2, 0) for comparison."""
    s = s.strip().lstrip("vV")
    parts = []
    for chunk in s.split("."):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group()) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check_for_updates(root):
    """If frozen, quietly ask GitHub whether a newer release exists.
    Runs off the UI thread; only touches the UI when there's news."""
    if not getattr(sys, "frozen", False):
        return

    def worker():
        try:
            req = urllib.request.Request(
                RELEASE_API,
                headers={"User-Agent": "FolderMaker",
                         "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                import json as _json
                data = _json.load(r)
            tag = data.get("tag_name", "")
            if _version_tuple(tag) > _version_tuple(APP_VERSION):
                root.after(0, lambda: _offer_update(root, tag))
        except Exception:
            pass  # offline, rate-limited, malformed - never nag

    threading.Thread(target=worker, daemon=True).start()


def _offer_update(root, tag):
    if messagebox.askyesno(
            "Update Available",
            f"A new version is available.\n\n"
            f"Current: {APP_VERSION}\n"
            f"Latest:  {tag.lstrip('vV')}\n\n"
            f"Download and install now?"):
        _run_update(root)


def _run_update(root):
    """Download the latest exe, then hand off to the swap helper."""
    dlg = tk.Toplevel(root)
    dlg.title("Updating")
    dlg.transient(root)
    dlg.resizable(False, False)
    ttk.Label(dlg, text="Downloading the latest version…",
              padding=(24, 16)).pack()
    bar = ttk.Progressbar(dlg, mode="indeterminate", length=260)
    bar.pack(padx=24, pady=(0, 18))
    bar.start(12)
    dlg.grab_set()
    root.update_idletasks()

    dest = os.path.join(tempfile.gettempdir(), "FolderMaker_update.exe")

    def worker():
        try:
            req = urllib.request.Request(DOWNLOAD_URL,
                                         headers={"User-Agent": "FolderMaker"})
            with urllib.request.urlopen(req, timeout=60) as r, \
                    open(dest, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
            root.after(0, lambda: _apply_update(root, dlg, dest))
        except Exception:
            root.after(0, lambda: _update_failed(root, dlg))

    threading.Thread(target=worker, daemon=True).start()


def _apply_update(root, dlg, new_exe):
    """Spawn a detached helper that swaps the exe once we exit, then quit."""
    dlg.destroy()
    current = sys.executable
    if not os.path.isfile(current):
        return  # nothing we can do

    bat = os.path.join(tempfile.gettempdir(), "_foldermaker_updater.bat")
    with open(bat, "w") as f:
        f.write(_UPDATER_BAT)

    flags = 0
    if sys.platform == "win32":
        flags = (subprocess.DETACHED_PROCESS
                 | subprocess.CREATE_NEW_PROCESS_GROUP)
    subprocess.Popen(
        ["cmd", "/c", bat, str(os.getpid()), new_exe, current],
        creationflags=flags, close_fds=True)
    try:
        root.destroy()
    except Exception:
        pass
    os._exit(0)


def _update_failed(root, dlg):
    dlg.destroy()
    messagebox.showerror(
        "Update Failed",
        "Could not download the update. Check your internet connection "
        "and try again, or download it manually from:\n" + RELEASE_PAGE)


# ----------------------------------------------------------------------

def main():
    enable_dpi_awareness()

    prefs = load_prefs()
    dark = bool(prefs.get("dark"))

    root = tk.Tk()
    root.title("Folder Maker")
    root.minsize(680, 600)
    icon = app_icon()
    if icon:
        try:
            root.iconbitmap(default=icon)
        except tk.TclError:
            pass

    style = ttk.Style(root)

    title_font = nametofont("TkDefaultFont").copy()
    title_font.configure(size=max(12, int(title_font.cget("size")) + 3),
                         weight="bold")

    header = ttk.Frame(root, padding=(16, 12, 16, 0))
    header.pack(fill="x")
    ttk.Label(header, text="Folder Maker", style="Title.TLabel",
              font=title_font).pack(side="left")
    dark_var = tk.BooleanVar(value=dark)

    def toggle_theme():
        d = dark_var.get()
        apply_theme(root, style, d)
        set_titlebar_dark(root, d)
        prefs["dark"] = d
        save_prefs(prefs)

    ttk.Checkbutton(header, text="Dark Mode", variable=dark_var,
                    command=toggle_theme).pack(side="right")

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=10, pady=(4, 10))

    # One folder field shared by all three tabs - pick it anywhere and the
    # others follow, and it is remembered for the next launch.
    shared_dir = tk.StringVar(value=prefs.get("last_dir", ""))

    def persist_dir(*_):
        prefs["last_dir"] = shared_dir.get().strip()
        save_prefs(prefs)

    shared_dir.trace_add("write", persist_dir)

    nb.add(CreateTab(nb, shared_dir), text="  Create Folders  ")
    nb.add(RenameTab(nb, shared_dir), text="  Rename Files  ")
    nb.add(SortTab(nb, shared_dir), text="  Sort Files into Folders  ")

    apply_theme(root, style, dark)
    root.after(150, lambda: set_titlebar_dark(root, dark))
    check_for_updates(root)
    root.mainloop()


if __name__ == "__main__":
    main()