"""segImage API — uploads processed in memory only; never persisted to disk."""
from __future__ import annotations

import json
import logging
import threading
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.opencv_grabcut import grabcut_segment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("segImage")

MAX_BYTES = 12 * 1024 * 1024

app = FastAPI(title="segImage", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_rembg_ready = False
_rembg_error = None


def _warmup_rembg():
    global _rembg_ready, _rembg_error
    try:
        from app.rembg_seg import get_session

        get_session()
        _rembg_ready = True
        logger.info("rembg u2netp session ready")
    except Exception as e:
        _rembg_error = str(e)
        logger.warning("rembg warmup failed: %s", e)


@app.on_event("startup")
def startup():
    # Listen immediately; load model in background
    threading.Thread(target=_warmup_rembg, daemon=True).start()


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "rembg_ready": _rembg_ready,
        "rembg_error": _rembg_error,
        "methods": {
            "rembg": "server rembg/U²-Net-p (SAM-like auto; no GPU on host)",
            "opencv": "server OpenCV GrabCut (FG/BG clicks)",
            "mediapipe": "browser MediaPipe Interactive Segmenter (no server upload)",
        },
        "persist": False,
        "sam_note": "Full Meta SAM skipped: no GPU, ~3.6GiB RAM. Using rembg U2Net-p instead.",
    }


@app.post("/api/segment")
async def segment(
    file: UploadFile = File(...),
    method: str = Form("rembg"),
    white_border: str = Form("true"),
    points_json: Optional[str] = Form(None),
    rect_json: Optional[str] = Form(None),
    smooth: int = Form(3),
    despeckle: str = Form("true"),
    complete: str = Form("true"),
):
    cp = str(complete).lower() in ("1", "true", "yes", "on")
    ds = str(despeckle).lower() in ("1", "true", "yes", "on")
    method = (method or "rembg").lower().strip()
    wb = str(white_border).lower() in ("1", "true", "yes", "on")

    raw = await file.read()
    try:
        if not raw:
            raise HTTPException(400, "空文件")
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "图片过大（上限 12MB）")

        points = None
        rect = None
        try:
            if points_json:
                points = json.loads(points_json)
            if rect_json:
                rect = json.loads(rect_json)
        except json.JSONDecodeError as e:
            raise HTTPException(400, "points_json / rect_json 不是合法 JSON") from e

        try:
            if method in ("rembg", "sam", "sam-like", "u2net"):
                from app.rembg_seg import rembg_segment

                result = rembg_segment(raw, white_border=wb, smooth=smooth, despeckle=ds, complete=cp)
            elif method in ("multi",):
                import asyncio
                from app.multi import segment_multi
                result = await asyncio.to_thread(segment_multi, raw, wb, smooth, ds, cp)
                return JSONResponse(result)
            elif method in ("ai", "ai_box"):
                import asyncio
                from app.ai_box import detect
                det, tried = await asyncio.to_thread(detect, raw)
                if det:
                    from PIL import Image
                    from io import BytesIO
                    W, H = Image.open(BytesIO(raw)).size
                    x1, y1, x2, y2 = det["box"]
                    pts = [{"x": x, "y": y, "label": 1} for x, y in det["fg_points"]] + \
                          [{"x": x, "y": y, "label": 0} for x, y in det["bg_points"]
                           if not (x1 < x < x2 and y1 < y < y2)]
                    rect_px = [int(x1 * W), int(y1 * H), max(2, int((x2 - x1) * W)), max(2, int((y2 - y1) * H))]
                    result = await asyncio.to_thread(grabcut_segment, raw, pts, rect_px, 5, wb, True, smooth, ds)
                    result.update(method="ai_box+grabcut", label=det["label"], model=det["model"],
                                  box=det["box"], box_px=[int(x1*W), int(y1*H), int(x2*W), int(y2*H)],
                                  fg_points=det["fg_points"], bg_points=det["bg_points"],
                                  tried=tried, fallback=False)
                else:
                    from app.rembg_seg import rembg_segment
                    result = rembg_segment(raw, white_border=wb, smooth=smooth, despeckle=ds, complete=cp)
                    result.update(method="ai_box→fallback rembg", fallback=True, tried=tried,
                                  label=None, model=None, box=None)
            elif method in ("opencv", "grabcut"):
                result = grabcut_segment(raw, points=points, rect=rect, white_border=wb, smooth=smooth, despeckle=ds)
            else:
                raise HTTPException(400, f"未知 method: {method}")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("segment failed")
            raise HTTPException(500, f"分割失败: {e}") from e

        return JSONResponse(result)
    finally:
        raw = None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, reload=False)
