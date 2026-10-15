"""Multi-subject segmentation. In memory only."""
from __future__ import annotations
import base64, json, re
import cv2
import numpy as np
from app.ai_box import detect, _clip
from app.postprocess import refine, sticker

PROMPT = ('你是图像主体定位助手。找出画面中最多6个不同的主要物体（实物、食物、人物、动物；忽略天空、地面、墙面等背景，以及水印、文字、界面按钮）。'
          '只输出 JSON，不要任何解释：{"objects":[{"label":"中文名","box":[x1,y1,x2,y2],"fg_points":[[x,y],...]}]}。'
          '坐标为相对图片宽高的比例0到1，原点左上；box紧贴物体外轮廓但不要切到物体；每个物体给2到4个位于物体内部、远离边缘的 fg_points。')


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy; u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i
    return i / u if u else 0


def parse_multi(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S) or re.search(r"\[.*\]", text, re.S)
    if not m: raise ValueError("no JSON")
    s = m.group(0)
    try: j = json.loads(s)
    except json.JSONDecodeError: j = json.loads(re.sub(r",\s*([}\]])", r"\1", s))
    objs = j.get("objects", []) if isinstance(j, dict) else j
    out = []
    for o in objs:
        try:
            b = [float(v) for v in o["box"]][:4]
            sc = 1000.0 if max(b) > 1.5 else 1.0
            x1, y1, x2, y2 = [_clip(v / sc) for v in b]
            x1, x2 = sorted((x1, x2)); y1, y2 = sorted((y1, y2))
            if (x2-x1) < 0.03 or (y2-y1) < 0.03: continue
            box = [x1, y1, x2, y2]
            if any(iou(box, p["box"]) > 0.6 for p in out): continue
            fg = []
            for p in o.get("fg_points") or []:
                x, y = float(p[0]) / sc, float(p[1]) / sc
                if x1 <= x <= x2 and y1 <= y <= y2: fg.append([_clip(x), _clip(y)])
            fg = fg or [[(x1+x2)/2, (y1+y2)/2]]
            out.append({"label": str(o.get("label") or f"主体{len(out)+1}"), "box": box, "fg_points": fg})
        except Exception:
            continue
        if len(out) >= 6: break
    if not out: raise ValueError("no objects")
    return {"objects": out}


def _b64(b): return base64.b64encode(b).decode()


def _render(img, masks, labels, boxes_px, wb, smooth, ds, refined=False):
    res = []
    for m, lab, bp in zip(masks, labels, boxes_px):
        if not refined:
            m = refine(img, m, smooth, ds)
        if (m > 127).sum() < 50: continue
        ys, xs = np.where(m > 8)
        res.append({"label": lab, "box_px": bp or [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                    "png_b64": _b64(sticker(img, m, wb))})
    return res


def segment_multi(raw: bytes, wb=True, smooth=3, ds=True, cp=True) -> dict:
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None: raise ValueError("无法解码图片")
    H, W = img.shape[:2]
    det, tried = detect(raw, PROMPT, parse_multi)
    if det:
        objs = det["objects"]
        px = lambda b: [int(b[0]*W), int(b[1]*H), int(b[2]*W), int(b[3]*H)]
        r = max(3, min(W, H) // 60)
        masks, scores = [], []
        for i, o in enumerate(objs):
            x1, y1, x2, y2 = px(o["box"])
            mask = np.full((H, W), cv2.GC_BGD, np.uint8)
            mask[y1:y2, x1:x2] = cv2.GC_PR_FGD
            for j, other in enumerate(objs):  # others → probable BG outside own box
                if j == i: continue
                ox1, oy1, ox2, oy2 = px(other["box"])
                sub = mask[oy1:oy2, ox1:ox2]
                own = np.zeros((H, W), bool); own[y1:y2, x1:x2] = True
                region = np.zeros((H, W), bool); region[oy1:oy2, ox1:ox2] = True
                mask[region & own & (mask == cv2.GC_PR_FGD)] = cv2.GC_PR_BGD
                for x, y in other["fg_points"]:
                    cx, cy = int(x*W), int(y*H)
                    if not (x1 <= cx < x2 and y1 <= cy < y2):
                        cv2.circle(mask, (cx, cy), r, int(cv2.GC_BGD), -1)
            for x, y in o["fg_points"]:
                cv2.circle(mask, (int(x*W), int(y*H)), r, int(cv2.GC_FGD), -1)
            # crop to padded roi for speed
            pad = max(10, (x2-x1+y2-y1)//8)
            X1, Y1, X2, Y2 = max(0, x1-pad), max(0, y1-pad), min(W, x2+pad), min(H, y2+pad)
            sm = mask[Y1:Y2, X1:X2].copy()
            if (sm == cv2.GC_FGD).sum() + (sm == cv2.GC_PR_FGD).sum() == 0 or (sm == cv2.GC_BGD).sum() + (sm == cv2.GC_PR_BGD).sum() == 0:
                sm[0, :] = cv2.GC_BGD
            bgd = np.zeros((1, 65)); fgd = np.zeros((1, 65))
            try:
                cv2.grabCut(img[Y1:Y2, X1:X2], sm, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
            except cv2.error:
                pass
            full = np.zeros((H, W), np.uint8)
            full[Y1:Y2, X1:X2] = np.where((sm == 1) | (sm == 3), 255, 0)
            full = refine(img, full, smooth, ds)
            masks.append(full)
            scores.append(-(x2-x1)*(y2-y1))  # smaller box wins overlaps
        # overlap resolution: each pixel to the smaller-box object
        order = np.argsort(scores)[::-1]
        taken = np.zeros((H, W), bool)
        for k in order:
            hard = masks[k] > 127
            masks[k][taken & hard] = 0
            taken |= hard
        res = _render(img, masks, [o["label"] for o in objs], [px(o["box"]) for o in objs], wb, smooth, ds, refined=True)
        return {"method": "multi_ai+grabcut", "model": det["model"], "fallback": False, "tried": tried,
                "width": W, "height": H, "objects": res}
    # fallback: rembg components
    from rembg import remove
    from app.rembg_seg import get_session
    from PIL import Image
    from io import BytesIO
    rgba = np.array(Image.open(BytesIO(remove(raw, session=get_session()))).convert("RGBA"))
    a = rgba[:, :, 3]
    if cp:
        from app.complete import complete_subject
        a, _ = complete_subject(img, a)
    m = (a > 127).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    comps = sorted([i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > H*W*0.004],
                   key=lambda i: -st[i, cv2.CC_STAT_AREA])[:8]
    masks, labels, boxes = [], [], []
    for idx, i in enumerate(sorted(comps, key=lambda i: (st[i, 1], st[i, 0]))):
        cm = np.where(lab == i, a, 0).astype(np.uint8)
        masks.append(cm); labels.append(f"主体{idx+1}")
        x, y, w, h = st[i, :4]; boxes.append([int(x), int(y), int(x+w), int(y+h)])
    res = _render(img, masks, labels, boxes, wb, smooth, ds)
    return {"method": "multi_fallback_rembg_components", "model": None, "fallback": True, "tried": tried,
            "width": W, "height": H, "objects": res}
