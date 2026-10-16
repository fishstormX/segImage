"""segImage API — uploads are processed in memory only and never persisted.

Routes
  v1 (stable):  GET  /api/v1/health   GET /api/v1/models
                POST /api/v1/segment  POST /api/v1/multi
  legacy alias: GET  /api/health      POST /api/segment   (unchanged response shape, used by the web UI)
  docs:         GET  /api/docs (Swagger UI)  GET /api/openapi.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.opencv_grabcut import grabcut_segment
from app.ratelimit import client_ip, limiter
from app.version import __version__

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("segImage")

BASE_PATH = os.environ.get("SEGIMAGE_BASE_PATH", "").rstrip("/")  # e.g. "/segImage" behind nginx
MAX_BYTES = int(os.environ.get("SEGIMAGE_MAX_BYTES", 12 * 1024 * 1024))
MAX_SIDE = 1280
METHODS = ["rembg", "grabcut", "ai", "multi"]

app = FastAPI(
    title="segImage API",
    version=__version__,
    description=(
        "**This API is for testing only. For commercial use or partnership inquiries, contact stormnetwork@163.com (海口龙华区妙妙鱼传媒工作室 / Miaomiaoyu Media Studio, Longhua District, Haikou).** 此接口仅供测试使用，如有商业使用或合作意向，请联系 stormnetwork@163.com（海口龙华区妙妙鱼传媒工作室）。 Per-IP rate limits apply "
        "(default 1 call / 10 s and 5 calls / 60 s; HTTP 429 `rate limited` with Retry-After when exceeded). "
        "Background removal & subject cutout (stickers). Methods: rembg (U²-Net family), OpenCV GrabCut, "
        "AI auto-box (free OpenRouter vision models only, falls back to rembg), multi-subject. "
        f"Uploads are processed in memory and never stored. Max upload {MAX_BYTES // (1024 * 1024)} MB; "
        f"rembg inputs are normalized to ≤{MAX_SIDE}px long side."
    ),
    docs_url=None, redoc_url=None, openapi_url="/api/openapi.json",
    servers=[{"url": BASE_PATH or "/"}],
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

LIMITED_PATHS = {"/api/segment", "/api/v1/segment", "/api/v1/multi"}


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    if limiter.enabled and request.method == "POST" and request.url.path.rstrip("/") in LIMITED_PATHS:
        ip = client_ip(request.client.host if request.client else None, request.headers)
        wait = limiter.hit(ip)
        if wait is not None:
            msg = f"rate limited, retry after {wait}s. This API is for testing only. For commercial use or partnership inquiries, contact stormnetwork@163.com (海口龙华区妙妙鱼传媒工作室 / Miaomiaoyu Media Studio, Longhua District, Haikou)."
            return JSONResponse(status_code=429, headers={"Retry-After": str(wait)},
                                content={"ok": False, "error": {"code": "RATE_LIMITED", "message": msg},
                                         "detail": msg, "retry_after": wait,
                                         "message": {"en": f"Rate limited, retry after {wait}s. This API is for testing only. For commercial use or partnership inquiries, contact stormnetwork@163.com (海口龙华区妙妙鱼传媒工作室 / Miaomiaoyu Media Studio, Longhua District, Haikou).",
                                                     "zh": f"请求过于频繁，请 {wait} 秒后再试。此接口仅供测试使用，如有商业使用或合作意向，请联系 stormnetwork@163.com（海口龙华区妙妙鱼传媒工作室）。"}})
    return await call_next(request)


_rembg_ready = False
_rembg_error: Optional[str] = None


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


@app.exception_handler(APIError)
async def _api_error(_: Request, e: APIError):
    # `detail` kept for backward compatibility with the legacy UI
    return JSONResponse(status_code=e.status, content={"ok": False, "error": {"code": e.code, "message": e.message}, "detail": e.message})


from fastapi.exceptions import RequestValidationError


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    msg = "; ".join(f"{'.'.join(str(x) for x in err.get('loc', [])[1:])}: {err.get('msg')}" for err in e.errors())
    return JSONResponse(status_code=422, content={"ok": False, "error": {"code": "VALIDATION_ERROR", "message": msg}, "detail": msg})


def _warmup_rembg():
    global _rembg_ready, _rembg_error
    try:
        from app.rembg_seg import get_session
        get_session()
        _rembg_ready = True
    except Exception as e:  # pragma: no cover
        _rembg_error = str(e)
        logger.warning("rembg warmup failed: %s", e)


@app.on_event("startup")
def startup():
    threading.Thread(target=_warmup_rembg, daemon=True).start()


def _truthy(v: Any) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


async def _run(raw: bytes, method: str, *, white_border=True, smooth=3, despeckle=True, complete=True,
               rembg_model: Optional[str] = None, points=None, rect=None) -> dict:
    """Shared engine. Returns the legacy result dict."""
    if not raw:
        raise APIError(400, "EMPTY_FILE", "Empty file")
    if len(raw) > MAX_BYTES:
        raise APIError(413, "FILE_TOO_LARGE", f"File larger than {MAX_BYTES // (1024 * 1024)} MB")
    from PIL import Image, UnidentifiedImageError
    from io import BytesIO
    try:
        W, H = Image.open(BytesIO(raw)).size
    except (UnidentifiedImageError, OSError):
        raise APIError(415, "UNSUPPORTED_IMAGE", "Not a decodable image (JPEG/PNG/WebP/…)")
    smooth = max(0, min(10, int(smooth)))
    m = (method or "rembg").lower().strip()
    rm = rembg_model or None
    from app.rembg_seg import MODELS
    if rm and rm not in MODELS:
        raise APIError(400, "UNKNOWN_MODEL", f"rembg_model must be one of {list(MODELS)}")
    try:
        if m in ("rembg", "sam", "sam-like", "u2net"):
            from app.rembg_seg import rembg_segment
            return await asyncio.to_thread(lambda: rembg_segment(raw, white_border=white_border, smooth=smooth, despeckle=despeckle, complete=complete, model=rm))
        if m == "multi":
            from app.multi import segment_multi
            return await asyncio.to_thread(segment_multi, raw, white_border, smooth, despeckle, complete, rm)
        if m in ("ai", "ai_box"):
            from app.ai_box import detect
            det, tried = await asyncio.to_thread(detect, raw)
            if det:
                x1, y1, x2, y2 = det["box"]
                pts = [{"x": x, "y": y, "label": 1} for x, y in det["fg_points"]] + \
                      [{"x": x, "y": y, "label": 0} for x, y in det["bg_points"] if not (x1 < x < x2 and y1 < y < y2)]
                rect_px = [int(x1 * W), int(y1 * H), max(2, int((x2 - x1) * W)), max(2, int((y2 - y1) * H))]
                r = await asyncio.to_thread(grabcut_segment, raw, pts, rect_px, 5, white_border, True, smooth, despeckle)
                r.update(method="ai_box+grabcut", label=det["label"], model=det["model"], box=det["box"],
                         box_px=[int(x1 * W), int(y1 * H), int(x2 * W), int(y2 * H)],
                         fg_points=det["fg_points"], bg_points=det["bg_points"], tried=tried, fallback=False)
                return r
            from app.rembg_seg import rembg_segment
            r = await asyncio.to_thread(lambda: rembg_segment(raw, white_border=white_border, smooth=smooth, despeckle=despeckle, complete=complete, model=rm))
            r.update(method="ai_box→fallback rembg", fallback=True, tried=tried, label=None, model=None, box=None)
            return r
        if m in ("opencv", "grabcut"):
            if not points and not rect:
                rect = [0.05, 0.05, 0.9, 0.9]
            return await asyncio.to_thread(lambda: grabcut_segment(raw, points=points, rect=rect, white_border=white_border, smooth=smooth, despeckle=despeckle))
    except APIError:
        raise
    except Exception as e:
        logger.exception("segment failed")
        raise APIError(500, "SEGMENTATION_FAILED", f"Segmentation failed: {e}")
    raise APIError(400, "UNKNOWN_METHOD", f"method must be one of {METHODS}")


def _parse_json(s: Optional[str], name: str):
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        raise APIError(400, "BAD_JSON", f"{name} is not valid JSON")


# ---------------------------------------------------------------- v1 schema
class Detection(BaseModel):
    label: Optional[str] = None
    model: Optional[str] = Field(None, description="Free OpenRouter model that answered (always ends with :free)")
    box: Optional[list[float]] = Field(None, description="[x1,y1,x2,y2] normalized 0..1")
    fg_points: Optional[list[list[float]]] = None
    bg_points: Optional[list[list[float]]] = None
    fallback: bool = False
    tried: list[dict] = []


class SegmentResponse(BaseModel):
    ok: bool = True
    version: str = __version__
    method: str
    engine: str = Field(..., description="Concrete engine used, e.g. rembg_u2netp+smart_complete")
    rembg_model: Optional[str] = None
    width: int
    height: int
    elapsed_ms: int
    image_png_b64: str = Field(..., description="Transparent PNG sticker (base64)")
    mask_png_b64: Optional[str] = None
    detection: Optional[Detection] = None


class SubjectOut(BaseModel):
    label: str
    box_px: list[int]
    image_png_b64: str


class MultiResponse(BaseModel):
    ok: bool = True
    version: str = __version__
    method: str = "multi"
    engine: str
    width: int
    height: int
    elapsed_ms: int
    subjects: list[SubjectOut]
    detection: Detection


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    ok: bool = False
    error: ErrorBody


ERRORS = {400: {"model": ErrorResponse, "description": "EMPTY_FILE / BAD_JSON / UNKNOWN_METHOD / UNKNOWN_MODEL"},
          413: {"model": ErrorResponse, "description": "FILE_TOO_LARGE"},
          415: {"model": ErrorResponse, "description": "UNSUPPORTED_IMAGE"},
          422: {"model": ErrorResponse, "description": "VALIDATION_ERROR (e.g. unknown method, smooth out of range)"},
          429: {"model": ErrorResponse, "description": "RATE_LIMITED — per-IP limit exceeded (default 1/10s and 5/60s); "
                 "see the Retry-After header / retry_after field. This API is for testing only. For commercial use or partnership inquiries, contact stormnetwork@163.com (海口龙华区妙妙鱼传媒工作室 / Miaomiaoyu Media Studio, Longhua District, Haikou). 此接口仅供测试使用，如有商业使用或合作意向，请联系 stormnetwork@163.com（海口龙华区妙妙鱼传媒工作室）。",
                 "headers": {"Retry-After": {"description": "seconds to wait", "schema": {"type": "integer"}}}},
          500: {"model": ErrorResponse, "description": "SEGMENTATION_FAILED"}}


def _health():
    from app.rembg_seg import MODELS, DEFAULT_MODEL, _sessions
    return {"ok": True, "version": __version__, "rembg_ready": _rembg_ready, "rembg_error": _rembg_error,
            "rembg_models": MODELS, "rembg_default": DEFAULT_MODEL, "rembg_loaded": list(_sessions),
            "methods": {"rembg": "server rembg (U²-Net family) + optional smart completion",
                        "grabcut": "server OpenCV GrabCut seeded by points/rect",
                        "ai": "free OpenRouter vision model box → GrabCut (fallback: rembg)",
                        "multi": "free vision model lists ≤6 subjects → one sticker each (fallback: rembg components)",
                        "mediapipe": "browser-only (web UI), never uploaded"},
            "limits": {"max_upload_bytes": MAX_BYTES, "max_side_px": MAX_SIDE,
                       "rate_limits": [{"calls": n, "per_seconds": w} for n, w in limiter.rules]},
            "persist": False}


@app.get("/api/v1/health", tags=["v1"], summary="Service health, version and limits")
def v1_health():
    return _health()


@app.get("/api/v1/models", tags=["v1"], summary="Available rembg models and free AI vision models")
def v1_models():
    from app.rembg_seg import MODELS, DEFAULT_MODEL
    try:
        from app.ai_box import free_vision_models
        free = free_vision_models()
    except Exception:
        free = []
    return {"ok": True, "version": __version__,
            "rembg": [{"id": k, "label": v, "default": k == DEFAULT_MODEL} for k, v in MODELS.items()],
            "ai_free_vision_models": free, "ai_policy": "only OpenRouter models whose id ends with ':free'; never paid"}


def _to_detection(r: dict) -> Optional[Detection]:
    if "tried" not in r:
        return None
    return Detection(label=r.get("label"), model=r.get("model"), box=r.get("box"), fg_points=r.get("fg_points"),
                     bg_points=r.get("bg_points"), fallback=bool(r.get("fallback")), tried=r.get("tried") or [])


@app.post("/api/v1/segment", tags=["v1"], response_model=SegmentResponse, responses=ERRORS,
          summary="Cut out one subject → transparent PNG sticker")
async def v1_segment(
    file: UploadFile = File(..., description="Image (JPEG/PNG/WebP), ≤ 12 MB"),
    method: Literal["rembg", "grabcut", "ai"] = Form("rembg"),
    rembg_model: Optional[str] = Form(None, description="u2netp (default) | isnet-general-use | u2net | silueta"),
    complete: bool = Form(True, description="Smart subject completion (pure vision)"),
    smooth: int = Form(3, ge=0, le=10, description="Edge smoothing 0–10 (0 = off)"),
    despeckle: bool = Form(True, description="Remove small islands, fill holes"),
    white_border: bool = Form(True, description="Add white sticker outline"),
    points_json: Optional[str] = Form(None, description='GrabCut seeds: [{"x":0.5,"y":0.5,"label":1}] (0..1, label 1=fg 0=bg)'),
    rect_json: Optional[str] = Form(None, description="GrabCut rect [x,y,w,h] (0..1); default whole image with 5% margin"),
):
    t = time.time()
    raw = await file.read()
    r = await _run(raw, method, white_border=white_border, smooth=smooth, despeckle=despeckle, complete=complete,
                   rembg_model=rembg_model, points=_parse_json(points_json, "points_json"), rect=_parse_json(rect_json, "rect_json"))
    raw = None
    return SegmentResponse(method=method, engine=r.get("method", method), rembg_model=r.get("model") if method == "rembg" else None,
                           width=r["width"], height=r["height"], elapsed_ms=int((time.time() - t) * 1000),
                           image_png_b64=r["result_png_b64"], mask_png_b64=r.get("mask_png_b64"), detection=_to_detection(r))


@app.post("/api/v1/multi", tags=["v1"], response_model=MultiResponse, responses=ERRORS,
          summary="Find up to 6 subjects and return one sticker per subject")
async def v1_multi(
    file: UploadFile = File(...),
    rembg_model: Optional[str] = Form(None),
    complete: bool = Form(True), smooth: int = Form(3, ge=0, le=10), despeckle: bool = Form(True), white_border: bool = Form(True),
):
    t = time.time()
    raw = await file.read()
    r = await _run(raw, "multi", white_border=white_border, smooth=smooth, despeckle=despeckle, complete=complete, rembg_model=rembg_model)
    raw = None
    return MultiResponse(engine=r["method"], width=r["width"], height=r["height"], elapsed_ms=int((time.time() - t) * 1000),
                         subjects=[SubjectOut(label=o["label"], box_px=o["box_px"], image_png_b64=o["png_b64"]) for o in r["objects"]],
                         detection=Detection(model=r.get("model"), fallback=bool(r.get("fallback")), tried=r.get("tried") or []))


# ---------------------------------------------------------------- legacy aliases (web UI)
@app.get("/api/health", include_in_schema=False)
def health():
    return _health()


@app.post("/api/segment", include_in_schema=False)
async def segment(file: UploadFile = File(...), method: str = Form("rembg"), white_border: str = Form("true"),
                  points_json: Optional[str] = Form(None), rect_json: Optional[str] = Form(None), smooth: int = Form(3),
                  despeckle: str = Form("true"), complete: str = Form("true"), rembg_model: str = Form("")):
    raw = await file.read()
    m = (method or "rembg").lower()
    r = await _run(raw, m, white_border=_truthy(white_border), smooth=smooth, despeckle=_truthy(despeckle), complete=_truthy(complete),
                   rembg_model=rembg_model or None, points=_parse_json(points_json, "points_json"), rect=_parse_json(rect_json, "rect_json"))
    raw = None
    return JSONResponse(r)


@app.get("/api/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url=f"{BASE_PATH}/api/openapi.json", title="segImage API docs")


# Optional: serve the web UI from the same process (local quickstart). Behind nginx the UI is static.
_ui = os.environ.get("SEGIMAGE_STATIC_DIR") or str(Path(__file__).resolve().parents[2] / "frontend")
if os.environ.get("SEGIMAGE_SERVE_UI", "1") == "1" and Path(_ui, "index.html").is_file():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_ui, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", 8765)))
