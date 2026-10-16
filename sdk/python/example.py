"""Example: python example.py photo.jpg  (set SEGIMAGE_URL to use your own server)"""
import os
import sys

from segimage import SegImage, SegImageError

client = SegImage(os.environ.get("SEGIMAGE_URL", "https://jev.fishmaple.cn/segImage"))
h = client.health()
print("server", h["version"], "max upload", h["limits"]["max_upload_bytes"], "bytes")

img = sys.argv[1] if len(sys.argv) > 1 else "photo.jpg"
res = client.segment(img, method="rembg", rembg_model="u2netp", smooth=3)
print(res.engine, f"{res.width}x{res.height}", f"{res.elapsed_ms} ms ->", res.save("sticker.png"))

# GrabCut with one foreground point in the centre (coordinates normalized 0..1)
gc = client.segment(img, method="grabcut", points=[(0.5, 0.5, 1)], rect=(0.05, 0.05, 0.9, 0.9))
print(gc.engine, "->", gc.save("sticker_grabcut.png"))

try:
    client.segment(b"not an image")
except SegImageError as e:
    print("expected error:", e.code)
