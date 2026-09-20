"""Generate FolderMaker.ico - a blue folder with numbered rows inside."""
from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 24, 32, 48, 64, 128, 256]
MASTER = 256


def font(size):
    for path in ("arial.ttf", "C:\\Windows\\Fonts\\arialbd.ttf",
                 "C:\\Windows\\Fonts\\arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def folder_icon(size):
    """Draw the icon at the given size, scaled from a 256 master for crispness."""
    s = MASTER
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Palette
    tab_dark = (38, 92, 166, 255)      # darker blue for the folder tab
    body_top = (74, 144, 226, 255)     # lighter blue body top
    body_bot = (52, 120, 204, 255)     # body bottom (for a subtle gradient feel)
    row_bg = (255, 255, 255, 70)       # translucent white row cards
    row_bg_hi = (255, 255, 255, 110)
    badge = (255, 209, 102, 255)       # warm yellow number badges
    badge_text = (60, 50, 20, 255)
    outline = (28, 70, 130, 255)

    # --- Folder tab (top-left) ---
    tab = [(44, 52), (44, 78), (150, 78), (150, 70), (210, 70), (210, 52)]
    d.polygon(tab, fill=tab_dark)

    # --- Folder body (rounded rectangle) ---
    body = (30, 70, 226, 214)
    # vertical gradient by stacking 1px rows
    for y in range(body[1], body[3]):
        t = (y - body[1]) / (body[3] - body[1])
        r = int(body_top[0] + (body_bot[0] - body_top[0]) * t)
        g = int(body_top[1] + (body_bot[1] - body_top[1]) * t)
        b = int(body_top[2] + (body_bot[2] - body_top[2]) * t)
        d.line([(body[0], y), (body[2], y)], fill=(r, g, b, 255))
    # round the bottom corners by punching transparent corners
    corner = 14
    d.rectangle([body[0], body[3] - corner, body[0] + corner, body[3]],
                fill=(0, 0, 0, 0))
    d.rectangle([body[2] - corner, body[3] - corner, body[2], body[3]],
                fill=(0, 0, 0, 0))
    d.pieslice([body[0], body[3] - 2 * corner, body[0] + 2 * corner, body[3]],
               180, 270, fill=body_bot)
    d.pieslice([body[2] - 2 * corner, body[3] - 2 * corner, body[2], body[3]],
               270, 360, fill=body_bot)
    # outline
    d.rounded_rectangle(body, radius=corner, outline=outline, width=3)
    d.line([(44, 78), (150, 78)], fill=outline, width=3)
    d.line([(150, 70), (210, 70)], fill=outline, width=3)
    d.line([(150, 70), (150, 78)], fill=outline, width=3)

    # --- Three numbered rows inside the folder ---
    f_num = font(26)
    row_h = 34
    row_w = 150
    row_x0 = 52
    for i, y in enumerate([92, 132, 172], start=1):
        # row card
        d.rounded_rectangle([row_x0, y, row_x0 + row_w, y + row_h],
                            radius=7, fill=row_bg_hi if i == 1 else row_bg)
        # number badge
        bx, by, br = row_x0 + 8, y + 5, 24
        d.ellipse([bx, by, bx + br, by + br], fill=badge)
        label = f"{i:02d}"
        bbox = d.textbbox((0, 0), label, font=f_num)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((bx + (br - tw) / 2 - bbox[0], by + (br - th) / 2 - bbox[1] - 1),
               label, font=f_num, fill=badge_text)
        # row "line" (like a filename placeholder)
        d.rounded_rectangle([row_x0 + 44, y + 13, row_x0 + row_w - 12, y + 21],
                            radius=3, fill=(255, 255, 255, 150))

    # Scale down to requested size with high-quality resampling
    return img.resize((size, size), Image.LANCZOS)


def main():
    images = [folder_icon(s) for s in SIZES]
    master = images[-1]  # 256 is the largest
    master.save("FolderMaker.ico", format="ICO",
                sizes=[(s, s) for s in SIZES])
    # also save a PNG preview
    folder_icon(256).save("FolderMaker_preview.png")
    print("Wrote FolderMaker.ico and FolderMaker_preview.png")


if __name__ == "__main__":
    main()
