"""segimage — thin, dependency-free Python client for the segImage REST API (v1).

    from segimage import SegImage
    client = SegImage("https://jev.fishmaple.cn/segImage")
    res = client.segment("photo.jpg", method="rembg")
    res.save("sticker.png")

Python ≥ 3.8, standard library only. MIT licensed.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

__version__ = "1.2.0"
__all__ = ["SegImage", "SegImageError", "SegmentResult", "Subject", "MultiResult"]

DEFAULT_BASE_URL = "https://jev.fishmaple.cn/segImage"
Method = Literal["rembg", "grabcut", "ai"]
ImageInput = Union[str, "os.PathLike[str]", bytes]


class SegImageError(Exception):
    """Raised for non-2xx responses. ``code`` is e.g. FILE_TOO_LARGE, UNSUPPORTED_IMAGE, VALIDATION_ERROR."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"[{status} {code}] {message}")
        self.status, self.code, self.message = status, code, message


@dataclass
class SegmentResult:
    method: str
    engine: str
    width: int
    height: int
    elapsed_ms: int
    image_png: bytes
    mask_png: Optional[bytes] = None
    rembg_model: Optional[str] = None
    detection: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def save(self, path: str) -> str:
        with open(path, "wb") as f:
            f.write(self.image_png)
        return path


@dataclass
class Subject:
    label: str
    box_px: List[int]
    image_png: bytes

    def save(self, path: str) -> str:
        with open(path, "wb") as f:
            f.write(self.image_png)
        return path


@dataclass
class MultiResult:
    engine: str
    width: int
    height: int
    elapsed_ms: int
    subjects: List[Subject]
    detection: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)


class SegImage:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 300.0, retries: int = 2,
                 user_agent: str = f"segimage-python/{__version__}"):
        """``retries``: extra attempts on connection-level failures (the API is stateless, so retrying is safe)."""
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.timeout = timeout
        self.user_agent = user_agent

    # ---------------------------------------------------------------- public
    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/health")

    def models(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/models")

    def segment(self, image: ImageInput, method: Method = "rembg", *, rembg_model: Optional[str] = None,
                complete: bool = True, smooth: int = 3, despeckle: bool = True, white_border: bool = True,
                points: Optional[Sequence[Tuple[float, float, int]]] = None,
                rect: Optional[Tuple[float, float, float, float]] = None) -> SegmentResult:
        """Cut out one subject. ``points`` = [(x, y, label)] normalized 0..1 (label 1=fg, 0=bg) for grabcut;
        ``rect`` = (x, y, w, h) normalized 0..1."""
        fields: Dict[str, str] = {"method": method, "complete": _b(complete), "smooth": str(int(smooth)),
                                  "despeckle": _b(despeckle), "white_border": _b(white_border)}
        if rembg_model:
            fields["rembg_model"] = rembg_model
        if points:
            fields["points_json"] = json.dumps([{"x": x, "y": y, "label": int(l)} for x, y, l in points])
        if rect:
            fields["rect_json"] = json.dumps(list(rect))
        d = self._request("POST", "/api/v1/segment", fields=fields, image=image)
        return SegmentResult(method=d["method"], engine=d["engine"], width=d["width"], height=d["height"],
                             elapsed_ms=d["elapsed_ms"], image_png=base64.b64decode(d["image_png_b64"]),
                             mask_png=base64.b64decode(d["mask_png_b64"]) if d.get("mask_png_b64") else None,
                             rembg_model=d.get("rembg_model"), detection=d.get("detection"), raw=d)

    def multi(self, image: ImageInput, *, rembg_model: Optional[str] = None, complete: bool = True, smooth: int = 3,
              despeckle: bool = True, white_border: bool = True) -> MultiResult:
        fields = {"complete": _b(complete), "smooth": str(int(smooth)), "despeckle": _b(despeckle), "white_border": _b(white_border)}
        if rembg_model:
            fields["rembg_model"] = rembg_model
        d = self._request("POST", "/api/v1/multi", fields=fields, image=image)
        subs = [Subject(label=s["label"], box_px=s["box_px"], image_png=base64.b64decode(s["image_png_b64"])) for s in d["subjects"]]
        return MultiResult(engine=d["engine"], width=d["width"], height=d["height"], elapsed_ms=d["elapsed_ms"],
                           subjects=subs, detection=d["detection"], raw=d)

    # ---------------------------------------------------------------- internals
    def _request(self, verb: str, path: str, fields: Optional[Dict[str, str]] = None, image: Optional[ImageInput] = None) -> Dict[str, Any]:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        body = None
        if image is not None:
            body, ctype = _multipart(fields or {}, image)
            headers["Content-Type"] = ctype
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=verb)
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                self._raise(e)
            except (urllib.error.URLError, ConnectionError) as e:
                if attempt >= self.retries:
                    raise SegImageError(0, "CONNECTION_ERROR", str(e)) from None
                time.sleep(1.5 * (attempt + 1))
        raise AssertionError("unreachable")

    @staticmethod
    def _raise(e: "urllib.error.HTTPError") -> None:
        text = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(text).get("error") or {}
        except ValueError:
            err = {}
        raise SegImageError(e.code, err.get("code", "HTTP_%d" % e.code), err.get("message", text[:300])) from None


def _b(v: bool) -> str:
    return "true" if v else "false"


def _multipart(fields: Dict[str, str], image: ImageInput) -> Tuple[bytes, str]:
    if isinstance(image, (bytes, bytearray)):
        data, name = bytes(image), "image.jpg"
    else:
        name = os.path.basename(os.fspath(image))
        with open(image, "rb") as f:
            data = f.read()
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    boundary = "----segimage" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode())
    out.append(data + b"\r\n" + f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


if __name__ == "__main__":  # python segimage.py photo.jpg [method] [base_url]
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python segimage.py IMAGE [rembg|grabcut|ai|multi] [BASE_URL]")
    c = SegImage(sys.argv[3] if len(sys.argv) > 3 else DEFAULT_BASE_URL)
    m = sys.argv[2] if len(sys.argv) > 2 else "rembg"
    if m == "multi":
        mr = c.multi(sys.argv[1])
        for i, s in enumerate(mr.subjects, 1):
            print(s.save(f"subject_{i}.png"), s.label)
    else:
        r = c.segment(sys.argv[1], method=m)  # type: ignore[arg-type]
        print(r.save("sticker.png"), r.engine, f"{r.elapsed_ms} ms")
