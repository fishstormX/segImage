"""智能补全主体 (pure classical vision): grow a partial saliency mask to the full object.

Pipeline (no AI):
 1. seed = model mask; definite FG = eroded seed core
 2. background model from image borders: k-means colour clusters of border strip (Lab)
    + border-connected flood fill with colour tolerance (bg_conn)
 3. trimap: BG = bg_conn & bg-coloured & far from seed; PR_FG = seed ∪ filled outer contour ∪ (convex hull − bg_conn);
    everything else PR_BG (GrabCut may claim it)
 4. GrabCut (INIT_WITH_MASK, several iterations) on a downscaled image
 5. keep components touching the seed, fill enclosed holes, optional SLIC superpixel vote, safety guard
 6. optional cue: ellipse container (plate/bowl) enclosing the seed → PR_FG
"""
from __future__ import annotations
import cv2
import numpy as np


def _fill_holes(m):
    inv = cv2.bitwise_not(m)
    h, w = m.shape
    ff = inv.copy()
    msk = np.zeros((h + 2, w + 2), np.uint8)
    for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if ff[y, x]:
            cv2.floodFill(ff, msk, (x, y), 0)
    # any remaining inv pixel connected to borders elsewhere
    n, lab = cv2.connectedComponents(inv, 4)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    holes = (inv > 0) & ~np.isin(lab, border)
    out = m.copy(); out[holes] = 255
    return out


def _border_bg(lab_img, seed, strip):
    H, W = seed.shape
    bmask = np.zeros((H, W), bool)
    bmask[:strip], bmask[-strip:], bmask[:, :strip], bmask[:, -strip:] = True, True, True, True
    near_seed = cv2.dilate(seed, np.ones((strip * 3,) * 2, np.uint8)) > 0
    pts = lab_img[bmask & ~near_seed].reshape(-1, 3).astype(np.float32)
    if len(pts) < 50:
        pts = lab_img[bmask].reshape(-1, 3).astype(np.float32)
    k = min(6, max(1, len(pts) // 200))
    _, _, centers = cv2.kmeans(pts, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 2, cv2.KMEANS_PP_CENTERS)
    flat = lab_img.reshape(-1, 3).astype(np.float32)
    d = np.min(np.linalg.norm(flat[:, None, :] - centers[None], axis=2), axis=1).reshape(H, W)
    return d, bmask & ~near_seed


def _flood_from_border(blur_bgr, seeds_mask, tol):
    H, W = seeds_mask.shape
    reached = np.zeros((H + 2, W + 2), np.uint8)
    ys, xs = np.where(seeds_mask)
    step = max(1, len(xs) // 300)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    img = blur_bgr.copy()
    for x, y in zip(xs[::step], ys[::step]):
        if reached[y + 1, x + 1]:
            continue
        cv2.floodFill(img, reached, (int(x), int(y)), 0, (tol,) * 3, (tol,) * 3, flags)
    return reached[1:-1, 1:-1] > 0


def _slic_vote(rgb, m, n=500):
    try:
        from skimage.segmentation import slic
    except Exception:
        return m
    seg = slic(rgb, n_segments=n, compactness=12, start_label=0)
    fg = (m > 127).astype(np.float32)
    cnt = np.bincount(seg.ravel()); s = np.bincount(seg.ravel(), fg.ravel())
    ratio = s / np.maximum(cnt, 1)
    return ((ratio[seg] > 0.5) * 255).astype(np.uint8)


def complete_subject(bgr: np.ndarray, alpha: np.ndarray, use_container: bool = True, use_slic: bool = True,
                     iters: int = 5) -> tuple[np.ndarray, dict]:
    H0, W0 = alpha.shape
    seed0 = (alpha > 127).astype(np.uint8) * 255
    if seed0.sum() == 0:
        return alpha, {"used": False, "reason": "empty seed"}
    s = min(1.0, 640 / max(H0, W0))
    img = cv2.resize(bgr, (int(W0 * s), int(H0 * s)), interpolation=cv2.INTER_AREA) if s < 1 else bgr.copy()
    seed = cv2.resize(seed0, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    H, W = seed.shape
    md = min(H, W)
    strip = max(3, md // 60)
    blur = cv2.bilateralFilter(img, 7, 40, 7)
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB)

    dist, bseeds = _border_bg(lab, seed, strip)
    bg_col = dist < 12
    bg_conn = _flood_from_border(blur, bseeds & bg_col, tol=6)
    far = cv2.distanceTransform(255 - seed, cv2.DIST_L2, 5) > md * 0.04

    # outer contour fill + convex hull
    filled = _fill_holes(seed)
    hull = np.zeros_like(seed)
    cnts, _ = cv2.findContours(seed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = [c for c in cnts if cv2.contourArea(c) > 0.02 * seed.sum() / 255]
    if big:
        cv2.fillPoly(hull, [cv2.convexHull(np.vstack(big))], 255)

    info = {"used": True}
    gc = np.full((H, W), cv2.GC_PR_BGD, np.uint8)
    gc[(hull > 0) & ~bg_conn] = cv2.GC_PR_FGD
    gc[filled > 0] = cv2.GC_PR_FGD
    core = cv2.erode(seed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * strip + 1,) * 2))
    gc[core > 0] = cv2.GC_FGD
    gc[bg_conn & bg_col & far] = cv2.GC_BGD

    if use_container:
        try:
            from app.container import detect_containers, _ell_mask
            sa = (seed > 0).mean()
            if sa > 0.05:
                valid = []
                for ell, score in detect_containers(img)[:30]:
                    em = _ell_mask(img.shape, ell) > 0
                    inside = ((seed > 0) & em).sum() / max(1, (seed > 0).sum())
                    area = em.mean()
                    if inside > 0.85 and area < 0.9 and 1.1 * sa < area < 2.5 * sa and score > 0.3:
                        valid.append((area, score, em))
                if valid:  # outermost plausible rim wins
                    area, score, em = max(valid, key=lambda v: v[0])
                    gc[em & (gc != cv2.GC_FGD)] = cv2.GC_PR_FGD
                    info["container"] = {"score": round(score, 2), "area": round(float(area), 3)}
        except Exception as e:  # optional cue
            info["container_err"] = str(e)

    if (gc == cv2.GC_BGD).sum() + (gc == cv2.GC_PR_BGD).sum() < 30:
        gc[:strip, :] = cv2.GC_PR_BGD
    bgd = np.zeros((1, 65)); fgd = np.zeros((1, 65))
    try:
        cv2.grabCut(img, gc, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    except cv2.error as e:
        return alpha, {"used": False, "reason": str(e)}
    out = np.where((gc == 1) | (gc == 3), 255, 0).astype(np.uint8)
    out = cv2.morphologyEx(out, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # keep components overlapping the seed core
    n, labm = cv2.connectedComponents(out, connectivity=8)
    keep = np.unique(labm[(core > 0) | (seed > 0)]); keep = keep[keep > 0]
    out = np.isin(labm, keep).astype(np.uint8) * 255
    out = _fill_holes(out)
    if use_slic:
        out = _slic_vote(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), out)
        out = np.maximum(out, core)
        out = _fill_holes(out)

    # safety guard: don't explode into background
    a_seed = (seed > 0).mean(); a_out = (out > 0).mean()
    info["seed_area"] = round(float(a_seed), 3); info["out_area"] = round(float(a_out), 3)
    if a_out > 0.92 or a_out > 2.5 * a_seed + 0.05:
        info["guard"] = "grew too much → kept seed ∪ hull-limited"
        out = np.maximum(seed, np.where(hull > 0, out, 0).astype(np.uint8))
    out = cv2.resize(out, (W0, H0), interpolation=cv2.INTER_LINEAR)
    out = (out > 127).astype(np.uint8) * 255
    # preserve original soft alpha where seed already confident
    res = np.maximum(out, alpha)
    return res, info
