"""AI auto-box via OpenRouter FREE vision models only. In-memory only."""
from __future__ import annotations
import base64, json, logging, os, re, time
from io import BytesIO
import requests
from PIL import Image

log = logging.getLogger("segImage.ai")
OR = "https://openrouter.ai/api/v1"
PROMPT = ('你是图像主体定位助手。观察这张图片，找出画面中最主要、最适合抠出来的一个主体'
          '（优先级：实物/商品、人物、动物、食物、证件/卡片/文档；忽略天空、地面、墙面、桌面等背景，以及水印、文字叠加和界面元素）。'
          '只输出 JSON，不要任何解释：{"label":"short English name","box":[x1,y1,x2,y2],"fg_points":[[x,y],...],"bg_points":[[x,y],...]}。'
          '规则：坐标为相对图片宽高的比例0到1，原点左上；box紧贴外轮廓宁大勿切；fg_points 3到5个点在主体内部远离边缘；bg_points 2到4个点在主体外背景；多个候选时选面积最大、最居中的。')
PREF = [r"qwen.*vl", r"gemini", r"llama.*vision", r"gemma", r"nemotron.*omni", r"inkling", r""]
EXCLUDE = re.compile(r"safety|guard", re.I)
_cache = {"t": 0, "models": []}
_blocked: dict[str, float] = {}  # model -> until (403 permanent-ish)


def free_vision_models() -> list[str]:
    if time.time() - _cache["t"] < 3600 and _cache["models"]:
        return _cache["models"]
    d = requests.get(f"{OR}/models", timeout=20).json()["data"]
    ids = [m["id"] for m in d
           if m["id"].endswith(":free")
           and "image" in ((m.get("architecture") or {}).get("input_modalities") or [])
           and not EXCLUDE.search(m["id"])]
    def rank(i):
        for n, p in enumerate(PREF):
            if re.search(p, i, re.I):
                return (n, "small" in i, i)
    ids.sort(key=rank)
    _cache.update(t=time.time(), models=ids)
    return ids


def _data_url(img_bytes: bytes) -> str:
    im = Image.open(BytesIO(img_bytes)).convert("RGB")
    im.thumbnail((1024, 1024))
    b = BytesIO(); im.save(b, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def _clip(v):
    return min(1.0, max(0.0, float(v)))


def parse(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON")
    s = m.group(0)
    try:
        j = json.loads(s)
    except json.JSONDecodeError:
        j = json.loads(re.sub(r",\s*([}\]])", r"\1", s.replace("'", '"')))
    box = [_clip(v) for v in j["box"]][:4]
    if len(box) != 4:
        raise ValueError("bad box")
    # tolerate 0-1000 scale
    if any(float(v) > 1.5 for v in j["box"]):
        sc = 1000.0 if max(float(v) for v in j["box"]) <= 1000 else None
        if not sc: raise ValueError("box scale")
        box = [_clip(float(v) / sc) for v in j["box"]]
    x1, y1, x2, y2 = box
    x1, x2 = sorted((x1, x2)); y1, y2 = sorted((y1, y2))
    if x2 - x1 < 0.02 or y2 - y1 < 0.02:
        raise ValueError("box too small")
    def pts(k):
        out = []
        for p in j.get(k) or []:
            try:
                x, y = float(p[0]), float(p[1])
                if x > 1.5 or y > 1.5: x, y = x / 1000, y / 1000
                out.append([_clip(x), _clip(y)])
            except Exception:
                pass
        return out
    fg = pts("fg_points") or [[(x1 + x2) / 2, (y1 + y2) / 2]]
    return {"label": str(j.get("label") or "物体"), "box": [x1, y1, x2, y2],
            "fg_points": fg, "bg_points": pts("bg_points")}


def detect(img_bytes: bytes, prompt: str = PROMPT, parser=None) -> tuple[dict | None, list[dict]]:
    parser = parser or parse
    key = os.environ.get("OPENROUTER_API_KEY")
    tried = []
    if not key:
        return None, [{"model": None, "error": "no key"}]
    url = _data_url(img_bytes)
    try:
        models = free_vision_models()
    except Exception as e:
        return None, [{"model": None, "error": f"model list: {e}"}]
    for mid in models:
        if not mid.endswith(":free"):  # hard guard
            continue
        if _blocked.get(mid, 0) > time.time():
            tried.append({"model": mid, "error": "skipped (403 cached)"}); continue
        try:
            r = requests.post(f"{OR}/chat/completions", timeout=(10, 150 if "reasoning" in mid else 75), headers={
                "Authorization": f"Bearer {key}", "HTTP-Referer": "https://jev.fishmaple.cn/segImage/",
                "X-Title": "segImage"}, json={
                "model": mid, "temperature": 0, "max_tokens": 4000,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": url}}]}]})
            if r.status_code == 403:
                _blocked[mid] = time.time() + 6 * 3600
            if r.status_code != 200:
                raise ValueError(f"HTTP {r.status_code}: {r.text[:160]}")
            body = r.json()
            used = body.get("model") or mid
            if not str(used).endswith(":free") and used != mid.removesuffix(":free"):
                log.warning("routed model %s for %s", used, mid)
            if "choices" not in body:
                raise ValueError(f"no choices: {str(body)[:120]}")
            msg = body["choices"][0]["message"]
            res = parser((msg.get("content") or "").strip() or (msg.get("reasoning") or ""))
            res["model"] = mid
            tried.append({"model": mid, "ok": True})
            return res, tried
        except Exception as e:
            log.info("model %s failed: %s", mid, e)
            tried.append({"model": mid, "error": str(e)[:200]})
    return None, tried
