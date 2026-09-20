"""Build FolderMaker.ico and FolderMaker_preview.png from a source PNG.

Usage:  python make_icon.py [path/to/icon.png]

Defaults to the Freepik folder icon PNG. The .ico embeds every size
Windows wants (16-256px) so it stays crisp in Explorer, the taskbar,
and the window title bar.
"""
import sys
from PIL import Image

SIZES = [16, 24, 32, 48, 64, 128, 256]

DEFAULT_SOURCE = (
    r"C:\Users\Snapp\Downloads"
    r"\freepik__an_icon_for_desktop_app_app_mainly_does_makin.png"
)


def build(source_png):
    img = Image.open(source_png).convert("RGBA")
    img.thumbnail((256, 256), Image.LANCZOS)  # cap the master at 256

    frames = []
    for s in SIZES:
        f = img.resize((s, s), Image.LANCZOS)
        frames.append(f)

    frames[-1].save("FolderMaker.ico", format="ICO",
                    sizes=[(s, s) for s in SIZES])
    frames[-1].save("FolderMaker_preview.png")
    print(f"Wrote FolderMaker.ico ({', '.join(str(s) for s in SIZES)}px) "
          f"and FolderMaker_preview.png from {source_png}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE)
