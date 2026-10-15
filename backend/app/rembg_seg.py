"""rembg / U²-Net automatic matting — SAM-like auto segment, in-memory only."""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import cv2
import numpy as np
from PIL import Image
from rembg import remove, new_session

import threading
from collections import OrderedDict

MODELS = {  # name -> label ; only models verified to run on this CPU/RAM
    "u2netp": "U²-Net-p（快）",
    "isnet-general-use": "ISNet 通用",
    "u2net": "U²-Net 完整",
    "silueta": "Silueta",
}
DEFAULT_MODEL = "u2netp"
MAX_LOADED = 2
_sessions: "OrderedDict[str, object]" = OrderedDict()
_lock = threading.Lock()


def get_session(model: str | None = None):
    model = model if model in MODELS else DEFAULT_MODEL
    with _lock:
        if model in _sessions:
            _sessions.move_to_end(model)
            return _sessions[model]
        while len(_sessions) >= MAX_LOADED:
            _sessions.popitem(last=False)  # evict LRU to bound RAM
            import gc; gc.collect()
        s = new_session(model)
        _sessions[model] = s
        return s


def _to_sticker_from_rgba(rgba: np.ndarray, white_border: bool = True, border: int = 6) -> bytes:
    if rgba.shape[2] == 3:
        alpha = np.full(rgba.shape[:2], 255, dtype=np.uint8)
        rgba = np.dstack([rgba, alpha])
    # rgba is RGB(A) from PIL; convert to BGRA for OpenCV encode path consistency
    bgr = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR)
    alpha = rgba[:, :, 3]
    if white_border and border > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (border * 2 + 1, border * 2 + 1))
        dil = cv2.dilate(alpha, kernel, iterations=1)
        ring = cv2.subtract(dil, alpha)
        pad = border
        canvas = np.zeros((bgr.shape[0] + 2 * pad, bgr.shape[1] + 2 * pad, 4), dtype=np.uint8)
        bgr_p = cv2.copyMakeBorder(bgr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        alpha_p = cv2.copyMakeBorder(alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        ring_p = cv2.copyMakeBorder(ring, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        canvas[:, :, 0:3] = bgr_p
        canvas[ring_p > 0, 0:3] = 255
        canvas[ring_p > 0, 3] = 255
        subj = alpha_p > 0
        canvas[subj, 0:3] = bgr_p[subj]
        canvas[subj, 3] = 255
        out = canvas
    else:
        out = np.dstack([bgr, alpha])
    a = out[:, :, 3]
    ys, xs = np.where(a > 0)
    if len(xs):
        out = out[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    ok, buf = cv2.imencode(".png", out)
    if not ok:
        raise ValueError("PNG 编码失败")
    return buf.tobytes()


def normalize_input(image_bytes: bytes, max_side: int = 1280, quality: int = 90) -> bytes:
    """Same preprocessing as the offline tests: EXIF-rotate, RGB, long side ≤ max_side, JPEG q90 (in memory)."""
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    im.thumbnail((max_side, max_side))
    b = BytesIO(); im.save(b, "JPEG", quality=quality)
    return b.getvalue()


def rembg_segment(image_bytes: bytes, white_border: bool = True, smooth: int = 3, despeckle: bool = True, complete: bool = True, model: str | None = None) -> dict[str, Any]:
    model = model if model in MODELS else DEFAULT_MODEL
    image_bytes = normalize_input(image_bytes)
    session = get_session(model)
    # rembg returns PNG bytes with alpha — never write to disk
    out_bytes = remove(image_bytes, session=session)
    img = Image.open(BytesIO(out_bytes)).convert("RGBA")
    rgba = np.array(img)
    from app.postprocess import refine, sticker as mk
    src = np.array(Image.open(BytesIO(image_bytes)).convert("RGB"))
    bgr = cv2.cvtColor(src, cv2.COLOR_RGB2BGR)
    a0 = rgba[:, :, 3]
    info = None
    if complete:
        from app.complete import complete_subject
        a0, info = complete_subject(bgr, a0)
    mask = refine(bgr, a0, smooth, despeckle)
    sticker = mk(bgr, mask, white_border)
    mask_rgb = np.dstack([mask, mask, mask, mask])
    ok, mbuf = cv2.imencode(".png", mask_rgb)
    return {
        "result_png_b64": base64.b64encode(sticker).decode("ascii"),
        "mask_png_b64": base64.b64encode(mbuf.tobytes()).decode("ascii") if ok else "",
        "width": rgba.shape[1],
        "height": rgba.shape[0],
        "method": f"rembg_{model}" + ("+smart_complete" if complete else ""),
        "complete_info": info,
        "model": model,
        "note": f"CPU 无 GPU：rembg {MODELS[model]}，非 Meta SAM 权重",
    }
