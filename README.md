# Folder Maker

A small Windows desktop tool for organizing TV, anime, and movie collections. No installation, no dependencies once built — just one `.exe`.

It does three things:

1. **Create folders** — generate numbered folders in bulk (`Episode 1` … `Episode 32`)
2. **Sort files into folders** — automatically detect the episode number in a batch of video/subtitle files and move each one into its matching folder
3. **Rename files** — clean up messy release-group filenames into a consistent format, e.g.

   ```
   Yuukoku no Moriarty - 01.[SS][1080][MixFlixTop].mkv
   →  Moriarty the Patriot (S1.E1).mkv
   ```

All three tabs share the same episode-detection engine, which understands common naming styles:

- `S01E05`, `1x05`
- `Episode 12`, `Ep. 12`, `EP07`
- `Show - 01`, `Show - 034`
- Release-group tags like `[SubsPlease]`, `[1080p]`, `[x265]` are ignored automatically
- Openings, endings, specials, and OVAs (`NCOP`, `NCED`, `OVA`, `SP`, etc.) are detected and skipped rather than misfiled

## Dark mode

A **Dark mode** checkbox at the top of the window switches the whole app between light and dark themes -- every tab, table, button, and dialog recolors instantly, and even the native window title bar follows along. Your choice is remembered for next time.

## Screenshots

*(Add a screenshot or two here once you have them — drag an image into this section on GitHub and it'll embed automatically.)*

## Download

Grab the latest `FolderMaker.exe` from the [Releases](../../releases) page — no installation needed, just run it.

> Windows may show a "Windows protected your PC" SmartScreen warning the first time, since the app isn't code-signed. Click **More info → Run anyway**.

## Features in detail

### Create folders
Pick a destination, a base name, and a count. Optionally start numbering from something other than 1, and choose whether numbers get zero-padded (`Episode 01` vs `Episode 1`) so folders sort correctly outside of double digits.

### Sort files into folders
Point it at a folder full of downloaded episodes. It scans every video/subtitle file, guesses the episode number, and shows a preview table before touching anything — files it's unsure about are flagged in orange, and ones it can't parse (or thinks are extras) are flagged in red and skipped. You can double-click any row to correct the episode number by hand.

A **copy instead of move** checkbox lets you test it safely before trusting it with moves. Every run writes an undo log, so **Undo last sort** restores everything (files and folders) if something goes wrong.

### Rename files
Type the show name and season once, pick or type a naming template (`{name}`, `{season}`, `{ep}` placeholders), and it previews the new name for every file in the folder. Files that would collide onto the same new name are flagged and blocked until resolved. Renaming is undoable the same way sorting is.

## Building from source

Requires Python 3.9+ on Windows.

```bat
pip install pyinstaller
pyinstaller --onefile --windowed --name FolderMaker --clean FolderMaker.py
```

Or just run `build_exe.bat`, which checks for Python, installs PyInstaller if needed, and builds `dist\FolderMaker.exe` for you.

## Running from source (no exe)

```bash
python FolderMaker.py
```

Requires `tkinter`, which ships with the standard python.org installer (not always present in Microsoft Store installs of Python).

## Safety notes

- Nothing is renamed, moved, or created without an explicit confirmation dialog.
- Sorting and renaming both write a hidden undo log (`.foldermaker_undo.json` / `.foldermaker_rename_undo.json`) in the working folder, which the in-app **Undo** button reads.
- No files are ever overwritten — if a destination name/path already exists, that file is skipped and reported rather than replaced.
