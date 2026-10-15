"""Mask cleanup + sticker rendering (in memory)."""
from __future__ import annotations
import cv2
import numpy as np


def _guided(I: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    try:
        return cv2.ximgproc.guidedFilter(I, p, r, eps)
    except Exception:
        box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
        mI, mp = box(I), box(p)
        a = (box(I * p) - mI * mp) / (box(I * I) - mI * mI + eps)
        b = mp - a * mI
        return box(a) * I + box(b)


def refine(bgr: np.ndarray, alpha: np.ndarray, strength: int = 3, despeckle: bool = True) -> np.ndarray:
    """alpha uint8 0-255 → cleaned soft alpha uint8. strength 0 = off (binary only)."""
    h, w = alpha.shape[:2]
    m = (alpha > 127).astype(np.uint8) * 255
    s = max(0, min(10, int(strength)))
    unit = max(1, round(min(h, w) / 400))
    if despeckle:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * unit + 1,) * 2)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=2)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
        if n > 1:
            areas = st[1:, cv2.CC_STAT_AREA]
            big = areas.max()
            keep = [i + 1 for i, a in enumerate(areas) if a >= max(big * 0.15, h * w * 0.002)]
            m = np.isin(lab, keep).astype(np.uint8) * 255
        # fill internal holes: flood background from border
        inv = cv2.bitwise_not(m)
        n, lab = cv2.connectedComponents(inv, 4)
        border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
        holes = ~np.isin(lab, list(border)) & (inv > 0)
        m[holes] = 255
    if s == 0:
        return m
    # contour smoothing: blur + re-threshold
    sig = s * unit * 0.8
    m = (cv2.GaussianBlur(m, (0, 0), sig) > 127).astype(np.uint8) * 255
    # edge-aware refinement + feathering
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    a = _guided(gray, m.astype(np.float32) / 255, r=2 + s * unit, eps=1e-3)
    a = cv2.GaussianBlur(np.clip(a, 0, 1), (0, 0), 0.5 + s * 0.15 * unit)
    a = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    a[(cv2.erode(m, None, iterations=2 * unit) > 0)] = 255  # solid core
    a[(cv2.dilate(m, None, iterations=3 * unit) == 0)] = 0  # no halo specks
    return a


def sticker(bgr: np.ndarray, alpha: np.ndarray, white_border: bool = True, border: int | None = None) -> bytes:
    h, w = alpha.shape[:2]
    if border is None:
        border = max(4, round(min(h, w) / 70))
    pad = border + 2 if white_border else 0
    bgr_p = cv2.copyMakeBorder(bgr, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    a_p = cv2.copyMakeBorder(alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    if white_border:
        binm = (a_p > 127).astype(np.uint8) * 255
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * border + 1,) * 2)
        ring = cv2.GaussianBlur(cv2.dilate(binm, k), (0, 0), 1.0).astype(np.float32) / 255
        fa = a_p.astype(np.float32) / 255
        rgb = bgr_p.astype(np.float32) * fa[..., None] + 255 * (1 - fa[..., None])
        out_a = np.maximum(fa, ring)
        out = np.dstack([rgb, out_a * 255]).astype(np.uint8)
    else:
        out = np.dstack([bgr_p, a_p])
    ys, xs = np.where(out[:, :, 3] > 8)
    if len(xs):
        out = out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    ok, buf = cv2.imencode(".png", out)
    return buf.tobytes()
