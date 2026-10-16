/**
 * segimage — thin fetch-based client for the segImage REST API (v1). Works in browsers and Node ≥ 18.
 * NOTE: This API is for testing only. For commercial use or partnership inquiries, contact stormnetwork@163.com (海口龙华区妙妙鱼传媒工作室 / Miaomiaoyu Media Studio, Longhua District, Haikou). Public instance limits per IP: 1 call / 10 s and 5 calls / 60 s (HTTP 429 when exceeded).
 *   On 429 a SegImageError with status 429 and `retryAfter` is thrown (no automatic retry).
 * MIT licensed.
 *   import { SegImage } from "./segimage.js";
 *   const client = new SegImage("https://jev.fishmaple.cn/segImage");
 *   const res = await client.segment(fileOrBlob, { method: "rembg" });
 *   img.src = URL.createObjectURL(res.image);   // Blob (image/png)
 */
export const VERSION = "1.2.1";
export const DEFAULT_BASE_URL = "https://jev.fishmaple.cn/segImage";

export class SegImageError extends Error {
  constructor(status, code, message) {
    super(`[${status} ${code}] ${message}`);
    this.name = "SegImageError"; this.status = status; this.code = code; this.detail = message;
  }
}

const b64ToBlob = (b64) => {
  const bin = typeof atob === "function" ? atob(b64) : Buffer.from(b64, "base64").toString("binary");
  const u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return new Blob([u], { type: "image/png" });
};

export class SegImage {
  constructor(baseUrl = DEFAULT_BASE_URL, { timeoutMs = 300000, fetch: f } = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
    this._fetch = f || globalThis.fetch.bind(globalThis);
  }

  health() { return this._req("GET", "/api/v1/health"); }
  models() { return this._req("GET", "/api/v1/models"); }

  /** image: Blob | File | ArrayBuffer | Uint8Array */
  async segment(image, { method = "rembg", rembgModel, complete = true, smooth = 3, despeckle = true, whiteBorder = true, points, rect } = {}) {
    const fd = this._form(image, { method, rembg_model: rembgModel, complete, smooth, despeckle, white_border: whiteBorder });
    if (points) fd.append("points_json", JSON.stringify(points.map((p) => (Array.isArray(p) ? { x: p[0], y: p[1], label: p[2] ?? 1 } : p))));
    if (rect) fd.append("rect_json", JSON.stringify(rect));
    const d = await this._req("POST", "/api/v1/segment", fd);
    return { ...d, image: b64ToBlob(d.image_png_b64), mask: d.mask_png_b64 ? b64ToBlob(d.mask_png_b64) : null };
  }

  async multi(image, { rembgModel, complete = true, smooth = 3, despeckle = true, whiteBorder = true } = {}) {
    const fd = this._form(image, { rembg_model: rembgModel, complete, smooth, despeckle, white_border: whiteBorder });
    const d = await this._req("POST", "/api/v1/multi", fd);
    return { ...d, subjects: d.subjects.map((s) => ({ ...s, image: b64ToBlob(s.image_png_b64) })) };
  }

  _form(image, fields) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null) fd.append(k, String(v));
    const blob = image instanceof Blob ? image : new Blob([image]);
    fd.append("file", blob, image && image.name ? image.name : "image.jpg");
    return fd;
  }

  async _req(verb, path, body) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), this.timeoutMs);
    try {
      const r = await this._fetch(this.baseUrl + path, { method: verb, body, signal: ctl.signal, headers: { Accept: "application/json" } });
      const text = await r.text();
      let d; try { d = JSON.parse(text); } catch { d = null; }
      if (!r.ok) {
        const e = (d && d.error) || {};
        const err = new SegImageError(r.status, e.code || `HTTP_${r.status}`, e.message || text.slice(0, 300));
        if (r.status === 429) err.retryAfter = Number(r.headers.get("Retry-After")) || null; // not retried automatically
        throw err;
      }
      return d;
    } finally { clearTimeout(timer); }
  }
}
export default SegImage;
