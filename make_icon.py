"""
Make the app icons from your icon image.

    python make_icon.py

Reads assets/LinkedInAutoApplierIcon.png (preferred; a square PNG, 256 px or bigger, transparent background) or, failing that, an
existing assets/LinkedInAutoApplierIcon.ico, and writes assets/LinkedInAutoApplierIcon_multi.ico and assets/LinkedInAutoApplierIcon.ico:
one file holding 16 to 256 px versions. Windows asks for many sizes (taskbar, pinned items, Explorer, Alt-Tab); with only one it
scales on its own and different places can look different. The app window and the exe use these files.
Replace the PNG with a sharper, bigger image and run this again for a crisper result.
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
PNG = os.path.join(ASSETS, "LinkedInAutoApplierIcon.png")
ICO = os.path.join(ASSETS, "LinkedInAutoApplierIcon.ico")
MULTI = os.path.join(ASSETS, "LinkedInAutoApplierIcon_multi.ico")
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]

src = PNG if os.path.exists(PNG) else ICO
im = Image.open(src)
if src.endswith(".ico"):
    im.size = max(im.info.get("sizes", {im.size}))
im.load()
base = im.convert("RGBA")
if base.width != base.height:                                  # pad to a square so nothing is stretched
    side = max(base.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(base, ((side - base.width) // 2, (side - base.height) // 2), base)
    base = square
base = base.resize((256, 256), Image.LANCZOS)
for out in (MULTI, ICO):
    base.save(out, format="ICO", sizes=SIZES, bitmap_format="bmp")      # classic BMP frames: every Windows icon loader reads them
    print("wrote", out, "from", os.path.basename(src), "with sizes", [s[0] for s in SIZES])
