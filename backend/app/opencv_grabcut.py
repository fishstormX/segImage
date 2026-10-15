"""OpenCV GrabCut segmentation — in-memory only."""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import cv2
import numpy as np
from PIL import Image


def _decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片")
    return img


def _encode_png_rgba(rgba: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", rgba)
    if not ok:
        raise ValueError("PNG 编码失败")
    return buf.tobytes()


def _to_sticker(bgr: np.ndarray, mask: np.ndarray, white_border: bool = True, border: int = 6) -> bytes:
    """mask: 0=bg, 255=fg. Return PNG with transparency + optional white border."""
    h, w = mask.shape[:2]
    alpha = (mask > 0).astype(np.uint8) * 255

    if white_border and border > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (border * 2 + 1, border * 2 + 1))
        dil = cv2.dilate(alpha, kernel, iterations=1)
        # white ring = dilated - original
        ring = cv2.subtract(dil, alpha)
        out_h, out_w = h, w
        # expand canvas so border isn't clipped
        pad = border
        canvas = np.zeros((out_h + 2 * pad, out_w + 2 * pad, 4), dtype=np.uint8)
        bgr_p = cv2.copyMakeBorder(bgr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        alpha_p = cv2.copyMakeBorder(alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        ring_p = cv2.copyMakeBorder(ring, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        canvas[:, :, 0:3] = bgr_p
        canvas[:, :, 3] = alpha_p
        # paint white border where ring
        canvas[ring_p > 0, 0:3] = 255
        canvas[ring_p > 0, 3] = 255
        # keep subject pixels
        subj = alpha_p > 0
        canvas[subj, 0:3] = bgr_p[subj]
        canvas[subj, 3] = 255
        rgba = canvas
    else:
        rgba = np.dstack([bgr, alpha])

    # crop to content
    a = rgba[:, :, 3]
    ys, xs = np.where(a > 0)
    if len(xs) == 0:
        return _encode_png_rgba(rgba)
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    return _encode_png_rgba(rgba[y0:y1, x0:x1])


def grabcut_segment(
    image_bytes: bytes,
    points: list[dict[str, Any]] | None = None,
    rect: list[int] | None = None,
    iters: int = 5,
    white_border: bool = True,
    rect_points: bool = False,
    smooth: int = 3,
    despeckle: bool = True,
) -> dict[str, Any]:
    """
    points: [{x, y, label}] label 1=fg, 0=bg (normalized 0-1 or absolute pixels)
    rect: [x, y, w, h] absolute pixels OR normalized if all <= 1.5
    """
    img = _decode_image(image_bytes)
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)

    mode = cv2.GC_INIT_WITH_RECT
    gc_rect = (1, 1, max(1, w - 2), max(1, h - 2))

    if rect and len(rect) == 4:
        rx, ry, rw, rh = [float(v) for v in rect]
        if max(rx, ry, rw, rh) <= 1.5:
            rx, ry, rw, rh = int(rx * w), int(ry * h), int(rw * w), int(rh * h)
        else:
            rx, ry, rw, rh = int(rx), int(ry), int(rw), int(rh)
        rx = max(0, min(rx, w - 2))
        ry = max(0, min(ry, h - 2))
        rw = max(1, min(rw, w - rx))
        rh = max(1, min(rh, h - ry))
        gc_rect = (rx, ry, rw, rh)
        mode = cv2.GC_INIT_WITH_RECT

    if rect and len(rect) == 4 and rect_points:
        rx, ry, rw, rh = gc_rect
        cv2.grabCut(img, mask, gc_rect, bgd, fgd, iters, cv2.GC_INIT_WITH_RECT)
        r = max(3, min(w, h) // 50)
        for p in points or []:
            x, y = float(p["x"]), float(p["y"])
            x, y = int(x * w) if x <= 1.5 else int(x), int(y * h) if y <= 1.5 else int(y)
            x, y = max(0, min(x, w - 1)), max(0, min(y, h - 1))
            cv2.circle(mask, (x, y), r, int(cv2.GC_FGD if int(p.get("label", 1)) == 1 else cv2.GC_BGD), -1)
        cv2.grabCut(img, mask, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    elif points:
        # if we have points, use mask init (optionally after rect)
        if rect and len(rect) == 4:
            cv2.grabCut(img, mask, gc_rect, bgd, fgd, iters, cv2.GC_INIT_WITH_RECT)
            mode = cv2.GC_INIT_WITH_MASK
        else:
            mask[:] = cv2.GC_PR_BGD
            # seed a loose probable FG around points later
            mode = cv2.GC_INIT_WITH_MASK

        for p in points:
            x, y = float(p["x"]), float(p["y"])
            if x <= 1.5 and y <= 1.5:
                x, y = int(x * w), int(y * h)
            else:
                x, y = int(x), int(y)
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            label = int(p.get("label", 1))
            r = max(3, min(w, h) // 40)
            if label == 1:
                cv2.circle(mask, (x, y), r, int(cv2.GC_FGD), -1)
            else:
                cv2.circle(mask, (x, y), r, int(cv2.GC_BGD), -1)

        cv2.grabCut(img, mask, None, bgd, fgd, iters, mode)
    else:
        cv2.grabCut(img, mask, gc_rect, bgd, fgd, iters, cv2.GC_INIT_WITH_RECT)

    binary = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
    # light morphology cleanup
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)

    from app.postprocess import refine, sticker
    binary = refine(img, binary, smooth, despeckle)
    png = sticker(img, binary, white_border)
    mask_png = _encode_png_rgba(np.dstack([binary, binary, binary, binary]))
    return {
        "result_png_b64": base64.b64encode(png).decode("ascii"),
        "mask_png_b64": base64.b64encode(mask_png).decode("ascii"),
        "width": w,
        "height": h,
        "method": "opencv_grabcut",
    }
