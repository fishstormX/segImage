"""Shared cutout pipeline used by the FastAPI service and the CLI.

All methods run in-process (rembg / GrabCut / AI auto-box / multi). MediaPipe
is browser-only and is not available here.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from app.opencv_grabcut import grabcut_segment

logger = logging.getLogger("segImage")

MAX_BYTES = int(os.environ.get("SEGIMAGE_MAX_BYTES", 12 * 1024 * 1024))
MAX_SIDE = 1280
METHODS = ["rembg", "grabcut", "ai", "multi"]


class SegError(Exception):
    """Domain error with an HTTP-ish status/code for the API layer."""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def run_segment(
    raw: bytes,
    method: str = "rembg",
    *,
    white_border: bool = True,
    smooth: int = 3,
    despeckle: bool = True,
    complete: bool = True,
    rembg_model: Optional[str] = None,
    points: Any = None,
    rect: Any = None,
) -> dict:
    """Run the cutout pipeline. Returns the legacy result dict (result_png_b64 / objects / …)."""
    if not raw:
        raise SegError(400, "EMPTY_FILE", "Empty file")
    if len(raw) > MAX_BYTES:
        raise SegError(413, "FILE_TOO_LARGE", f"File larger than {MAX_BYTES // (1024 * 1024)} MB")
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    try:
        W, H = Image.open(BytesIO(raw)).size
    except (UnidentifiedImageError, OSError):
        raise SegError(415, "UNSUPPORTED_IMAGE", "Not a decodable image (JPEG/PNG/WebP/…)")
    smooth = max(0, min(10, int(smooth)))
    m = (method or "rembg").lower().strip()
    rm = rembg_model or None
    from app.rembg_seg import MODELS

    if rm and rm not in MODELS:
        raise SegError(400, "UNKNOWN_MODEL", f"rembg_model must be one of {list(MODELS)}")
    try:
        if m in ("rembg", "sam", "sam-like", "u2net"):
            from app.rembg_seg import rembg_segment

            return rembg_segment(
                raw, white_border=white_border, smooth=smooth, despeckle=despeckle, complete=complete, model=rm
            )
        if m == "multi":
            from app.multi import segment_multi

            return segment_multi(raw, white_border, smooth, despeckle, complete, rm)
        if m in ("ai", "ai_box"):
            from app.ai_box import detect

            det, tried = detect(raw)
            if det:
                x1, y1, x2, y2 = det["box"]
                pts = [{"x": x, "y": y, "label": 1} for x, y in det["fg_points"]] + [
                    {"x": x, "y": y, "label": 0}
                    for x, y in det["bg_points"]
                    if not (x1 < x < x2 and y1 < y < y2)
                ]
                rect_px = [int(x1 * W), int(y1 * H), max(2, int((x2 - x1) * W)), max(2, int((y2 - y1) * H))]
                r = grabcut_segment(raw, pts, rect_px, 5, white_border, True, smooth, despeckle)
                r.update(
                    method="ai_box+grabcut",
                    label=det["label"],
                    model=det["model"],
                    box=det["box"],
                    box_px=[int(x1 * W), int(y1 * H), int(x2 * W), int(y2 * H)],
                    fg_points=det["fg_points"],
                    bg_points=det["bg_points"],
                    tried=tried,
                    fallback=False,
                )
                return r
            from app.rembg_seg import rembg_segment

            r = rembg_segment(
                raw, white_border=white_border, smooth=smooth, despeckle=despeckle, complete=complete, model=rm
            )
            r.update(method="ai_box→fallback rembg", fallback=True, tried=tried, label=None, model=None, box=None)
            return r
        if m in ("opencv", "grabcut"):
            if not points and not rect:
                rect = [0.05, 0.05, 0.9, 0.9]
            return grabcut_segment(
                raw, points=points, rect=rect, white_border=white_border, smooth=smooth, despeckle=despeckle
            )
    except SegError:
        raise
    except Exception as e:
        logger.exception("segment failed")
        raise SegError(500, "SEGMENTATION_FAILED", f"Segmentation failed: {e}") from e
    raise SegError(400, "UNKNOWN_METHOD", f"method must be one of {METHODS}")
