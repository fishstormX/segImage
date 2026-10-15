"""rembg / U²-Net automatic matting — SAM-like auto segment, in-memory only."""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import cv2
import numpy as np
from PIL import Image
from rembg import remove, new_session

_session = None


def get_session():
    global _session
    if _session is None:
        # u2netp is small (~4MB) and fits low-RAM VPS; honest SAM-alternative
        _session = new_session("u2netp")
    return _session


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


def rembg_segment(image_bytes: bytes, white_border: bool = True, smooth: int = 3, despeckle: bool = True, complete: bool = True) -> dict[str, Any]:
    session = get_session()
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
        "method": "rembg_u2netp" + ("+smart_complete" if complete else ""),
        "complete_info": info,
        "note": "CPU 无 GPU：使用 rembg(U²-Net-p) 自动抠图，非 Meta SAM 权重",
    }
