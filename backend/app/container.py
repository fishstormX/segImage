"""Pure classical-vision container (plate/bowl) detection + GrabCut. No AI."""
from __future__ import annotations
import cv2
import numpy as np


def _support(edges_d, ell, W, H, n=240):
    (cx, cy), (MA, ma), ang = ell
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    a, b, th = MA / 2, ma / 2, np.deg2rad(ang)
    xs = cx + a * np.cos(t) * np.cos(th) - b * np.sin(t) * np.sin(th)
    ys = cy + a * np.cos(t) * np.sin(th) + b * np.sin(t) * np.cos(th)
    inside = (xs >= 1) & (xs < W - 1) & (ys >= 1) & (ys < H - 1)
    frac_in = inside.mean()
    if frac_in < 0.35:
        return 0.0, frac_in
    hit = edges_d[ys[inside].astype(int), xs[inside].astype(int)] > 0
    return hit.mean(), frac_in


def detect_container(bgr: np.ndarray):
    """Return ((cx,cy),(MA,ma),angle) in original pixels, score; or (None, 0)."""
    H0, W0 = bgr.shape[:2]
    s = 600 / max(H0, W0)
    s = min(1.0, s)
    img = cv2.resize(bgr, (int(W0 * s), int(H0 * s)), interpolation=cv2.INTER_AREA) if s < 1 else bgr
    H, W = img.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    v = np.median(gray)
    edges = cv2.Canny(gray, int(max(10, 0.5 * v)), int(min(255, 1.2 * v)))
    edges_d = cv2.dilate(edges, None, iterations=2)
    md = min(H, W)
    cands = []
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        if len(c) < 0.4 * md:
            continue
        if len(c) >= 5:
            cands.append(cv2.fitEllipse(c))
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.5, minDist=md / 4, param1=120, param2=40,
                               minRadius=int(md * 0.25), maxRadius=int(max(H, W) * 0.75))
    if circles is not None:
        for x, y, r in circles[0][:8]:
            cands.append(((float(x), float(y)), (2 * float(r), 2 * float(r)), 0.0))
    best, bscore = None, 0.0
    for e in cands:
        (cx, cy), (MA, ma), _ = e
        if not (np.isfinite([cx, cy, MA, ma]).all()) or min(MA, ma) < 0.35 * md or max(MA, ma) > 2.2 * max(H, W):
            continue
        if min(MA, ma) / max(MA, ma) < 0.4:
            continue
        if not (-0.2 * W < cx < 1.2 * W and -0.2 * H < cy < 1.2 * H):
            continue
        sup, frac_in = _support(edges_d, e, W, H)
        area = np.pi * MA * ma / 4 / (H * W)
        score = sup * area ** 0.7
        if sup > 0.4 and score > bscore:
            best, bscore = e, score
    if best is None:
        return None, 0.0
    (cx, cy), (MA, ma), ang = best
    return ((cx / s, cy / s), (MA / s, ma / s), ang), float(bscore)


def _ell_mask(shape, e, k=1.0):
    m = np.zeros(shape[:2], np.uint8)
    (cx, cy), (MA, ma), ang = e
    cv2.ellipse(m, ((cx, cy), (max(1, MA * k), max(1, ma * k)), ang), 255, -1)
    return m


def container_mask(bgr: np.ndarray, ell, seed_alpha: np.ndarray | None = None) -> np.ndarray:
    """GrabCut seeded by ellipse: inner shrink = FG, ellipse = PR_FG, thin ring = PR_BG, outside = BG."""
    H, W = bgr.shape[:2]
    mask = np.full((H, W), cv2.GC_BGD, np.uint8)
    mask[_ell_mask(bgr.shape, ell, 1.06) > 0] = cv2.GC_PR_BGD
    mask[_ell_mask(bgr.shape, ell, 1.0) > 0] = cv2.GC_PR_FGD
    mask[_ell_mask(bgr.shape, ell, 0.85) > 0] = cv2.GC_FGD
    if seed_alpha is not None:
        mask[(seed_alpha > 127) & (mask != cv2.GC_BGD)] = cv2.GC_FGD
    if (mask == cv2.GC_BGD).sum() < 50:  # bowl fills frame: use image border as BG hint
        mask[:2, :] = mask[-2:, :] = cv2.GC_PR_BGD
    # downscale GrabCut for speed
    s = min(1.0, 700 / max(H, W))
    small = cv2.resize(bgr, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    sm = cv2.resize(mask, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    bgd = np.zeros((1, 65)); fgd = np.zeros((1, 65))
    try:
        cv2.grabCut(small, sm, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        pass
    out = np.where((sm == 1) | (sm == 3), 255, 0).astype(np.uint8)
    out = cv2.resize(out, (W, H), interpolation=cv2.INTER_LINEAR)
    out = (out > 127).astype(np.uint8) * 255
    # keep holes filled & guarantee the inner core
    out[_ell_mask(bgr.shape, ell, 0.85) > 0] = 255
    return out


def maybe_container(bgr: np.ndarray, alpha: np.ndarray, force: bool = False):
    """If a container is detected and the subject mostly sits inside it, return expanded mask."""
    ell, score = detect_container(bgr)
    if ell is None:
        return alpha, None
    em = _ell_mask(bgr.shape, ell, 1.0) > 0
    fg = alpha > 127
    inside = (fg & em).sum() / max(1, fg.sum())
    if not force and inside < 0.7:
        return alpha, {"ellipse": ell, "score": score, "used": False, "inside": float(inside)}
    m = container_mask(bgr, ell, alpha)
    m = np.maximum(m, alpha)
    return m, {"ellipse": [list(map(float, ell[0])), list(map(float, ell[1])), float(ell[2])],
               "score": score, "used": True, "inside": float(inside)}
