"""
Make assets/LinkedInAutoApplierIcon_multi.ico from your icon file.

Your icon has a single 32x32 image. Windows asks for many sizes (taskbar, pinned items, Explorer, Alt-Tab); with only one it
scales on its own and different places can look different. This writes one icon file holding 16 to 256 px versions, scaled
smoothly from yours, which the app window and the exe use. Replace assets/LinkedInAutoApplierIcon.ico with a sharper, bigger
image and run this again to get a crisper result.

    .venv\\Scripts\\python.exe make_icon.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "assets", "LinkedInAutoApplierIcon.ico")
OUT = os.path.join(HERE, "assets", "LinkedInAutoApplierIcon_multi.ico")
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]

im = Image.open(SRC)
best = max(im.info.get("sizes", {im.size}))
im.size = best
im.load()
base = im.convert("RGBA").resize((256, 256), Image.LANCZOS)
base.save(OUT, format="ICO", sizes=SIZES, bitmap_format="bmp")      # classic BMP frames: every Windows icon loader reads them
print("wrote", OUT, "with sizes", [s[0] for s in SIZES])
