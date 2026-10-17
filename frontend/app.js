/**
 * segImage frontend
 * - rembg / opencv: POST /segImage/api/segment (server, no persist)
 * - mediapipe: browser Interactive Segmenter via CDN
 */

const API = new URL("../api/segment", window.location.href).pathname.replace(/\/segImage\/segImage\//, "/segImage/");
// When page is /segImage/ or /segImage/index.html → API is /segImage/api/segment
const API_URL = (() => {
  const base = window.location.pathname.replace(/\/index\.html$/, "").replace(/\/$/, "");
  // base like /segImage
  return `${base}/api/segment`;
})();
const HEALTH_URL = API_URL.replace(/\/segment$/, "/health");

const t = (k, v) => (window.I18N ? window.I18N.t(k, v) : k);
const $ = (s) => document.querySelector(s);
const fileInput = $("#file");
const canvas = $("#canvas");
const ctx = canvas.getContext("2d");
const stage = $("#stage");
const statusEl = $("#status");
const resultImg = $("#resultImg");
const resultEmpty = $("#resultEmpty");
const btnRun = $("#btnRun");
const btnDownload = $("#btnDownload");
const whiteBorder = $("#whiteBorder");
const pointHint = $("#pointHint");
const ptools = $("#ptools");
const btnFg = $("#btnFg");
const btnBg = $("#btnBg");
const btnClearPts = $("#btnClearPts");

let imgBitmap = null;
let imgFile = null;
let points = []; // {x,y,label} in canvas pixel coords
let paintLabel = 1;
let lastPngBlob = null;
let mpSegmenter = null;
let mpLoading = null;
let aiBox = null;
let multiObjs = []; // normalized [x1,y1,x2,y2]
const aiInfo = $("#aiInfo");
const btnMpAi = $("#btnMpAi");

function method() {
  return document.querySelector('input[name="method"]:checked')?.value || "rembg";
}

function setStatus(t, ok) {
  statusEl.removeAttribute("data-i18n");
  statusEl.textContent = t;
  statusEl.style.color = ok === false ? "#ff8e8e" : ok === true ? "#3ecf8e" : "";
}

/** Which option controls apply per method (must match server/cli behaviour). */
const OPTS_FOR = {
  // rembg model: rembg only (ai/multi rembg-fallback uses default u2netp if not shown)
  rembg:      { rembgModel: true,  complete: true,  despeckle: true,  smooth: true,  whiteBorder: true },
  mediapipe:  { rembgModel: false, complete: false, despeckle: false, smooth: false, whiteBorder: true },
  opencv:     { rembgModel: false, complete: false, despeckle: true,  smooth: true,  whiteBorder: true },
  ai:         { rembgModel: false, complete: true,  despeckle: true,  smooth: true,  whiteBorder: true },
  multi:      { rembgModel: false, complete: true,  despeckle: true,  smooth: true,  whiteBorder: true },
};

function updateMethodUI() {
  const m = method();
  const needPts = m === "opencv" || m === "mediapipe";
  ptools.hidden = !needPts;
  const opts = OPTS_FOR[m] || OPTS_FOR.rembg;
  document.querySelectorAll(".opts [data-opt]").forEach((el) => {
    const key = el.getAttribute("data-opt");
    el.hidden = !opts[key];
  });
  if (m === "multi") pointHint.textContent = t("hint_multi");
  else if (m === "ai") pointHint.textContent = t("hint_ai");
  else if (m === "rembg") pointHint.textContent = t("hint_rembg");
  else if (m === "mediapipe") pointHint.textContent = t("hint_mp");
  else pointHint.textContent = t("hint_cv");
}

document.querySelectorAll('input[name="method"]').forEach((el) => el.addEventListener("change", updateMethodUI));
updateMethodUI();

btnFg.addEventListener("click", () => {
  paintLabel = 1;
  btnFg.classList.add("active-fg");
  btnBg.classList.remove("active-bg");
});
btnBg.addEventListener("click", () => {
  paintLabel = 0;
  btnBg.classList.add("active-bg");
  btnFg.classList.remove("active-fg");
});
btnFg.click();

btnClearPts.addEventListener("click", () => {
  points = [];
  redraw();
});

function redraw() {
  if (!imgBitmap) return;
  const maxW = stage.clientWidth - 2 || 640;
  const scale = Math.min(1, maxW / imgBitmap.width, 520 / imgBitmap.height);
  canvas.width = Math.round(imgBitmap.width * scale);
  canvas.height = Math.round(imgBitmap.height * scale);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(imgBitmap, 0, 0, canvas.width, canvas.height);
  ctx.font = "bold 14px sans-serif";
  for (const o of multiObjs) {
    const [x1, y1, x2, y2] = o.box_px; const sx = canvas.width / imgBitmap.width, sy = canvas.height / imgBitmap.height;
    ctx.strokeStyle = "#3ecf8e"; ctx.lineWidth = 2; ctx.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy);
    const t = o.label; const tw = ctx.measureText(t).width + 8;
    ctx.fillStyle = "#3ecf8e"; ctx.fillRect(x1 * sx, Math.max(0, y1 * sy - 18), tw, 18);
    ctx.fillStyle = "#06210f"; ctx.fillText(t, x1 * sx + 4, Math.max(14, y1 * sy - 4));
  }
  if (aiBox) {
    const [x1, y1, x2, y2] = aiBox;
    ctx.strokeStyle = "#f5a524"; ctx.lineWidth = 3; ctx.setLineDash([8, 5]);
    ctx.strokeRect(x1 * canvas.width, y1 * canvas.height, (x2 - x1) * canvas.width, (y2 - y1) * canvas.height);
    ctx.setLineDash([]);
  }
  for (const p of points) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
    ctx.fillStyle = p.label === 1 ? "#3ecf8e" : "#ff6b6b";
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

async function loadFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    setStatus(t("st_pickFile"), false);
    return;
  }
  imgFile = file;
  points = [];
  multiObjs = []; $("#multiBox").hidden = true;
  aiBox = null; aiInfo.hidden = true; btnMpAi.hidden = true;
  lastPngBlob = null;
  btnDownload.disabled = true;
  resultImg.hidden = true;
  resultEmpty.hidden = false;
  const url = URL.createObjectURL(file);
  try {
    imgBitmap = await createImageBitmap(await (await fetch(url)).blob());
    stage.classList.add("has-img");
    redraw();
    setStatus(t("st_loaded", { name: file.name, kb: Math.round(file.size / 1024) }), true);
  } finally {
    URL.revokeObjectURL(url);
  }
}

fileInput.addEventListener("change", () => loadFile(fileInput.files?.[0]));
stage.addEventListener("dragover", (e) => { e.preventDefault(); });
stage.addEventListener("drop", (e) => {
  e.preventDefault();
  loadFile(e.dataTransfer.files?.[0]);
});

canvas.addEventListener("click", (e) => {
  if (!imgBitmap) return;
  const m = method();
  if (m !== "opencv" && m !== "mediapipe") return;
  const r = canvas.getBoundingClientRect();
  const x = ((e.clientX - r.left) / r.width) * canvas.width;
  const y = ((e.clientY - r.top) / r.height) * canvas.height;
  points.push({ x, y, label: paintLabel });
  redraw();
});

window.addEventListener("resize", () => redraw());

async function ensureMediaPipe() {
  if (mpSegmenter) return mpSegmenter;
  if (mpLoading) return mpLoading;
  mpLoading = (async () => {
    setStatus(t("st_mpLoading"));
    const vision = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/+esm");
    const { InteractiveSegmenter, FilesetResolver } = vision;
    const wasm = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/wasm"
    );
    mpSegmenter = await InteractiveSegmenter.createFromOptions(wasm, {
      baseOptions: {
        modelAssetPath:
          "https://storage.googleapis.com/mediapipe-models/interactive_segmenter/magic_touch/float32/1/magic_touch.tflite",
        delegate: "GPU",
      },
      outputCategoryMask: true,
      outputConfidenceMasks: false,
    });
    setStatus(t("st_mpReady"), true);
    return mpSegmenter;
  })();
  try {
    return await mpLoading;
  } catch (e) {
    mpLoading = null;
    throw e;
  }
}

function canvasToBlob(type = "image/png") {
  return new Promise((resolve) => canvas.toBlob(resolve, type));
}

async function runMediaPipe() {
  if (!imgBitmap) throw new Error(t("e_upload"));
  if (!points.length) throw new Error(t("e_click"));
  const segmenter = await ensureMediaPipe();
  // draw clean image without points for segmentation
  const off = document.createElement("canvas");
  off.width = canvas.width;
  off.height = canvas.height;
  const octx = off.getContext("2d");
  octx.drawImage(imgBitmap, 0, 0, off.width, off.height);

  // MediaPipe wants keypoint in normalized or pixel — use last FG point preferentially
  const fg = [...points].reverse().find((p) => p.label === 1) || points[points.length - 1];
  const result = segmenter.segment(off, {
    keypoint: { x: fg.x / off.width, y: fg.y / off.height },
  });

  const mask = result.categoryMask;
  if (!mask) throw new Error(t("e_nomask"));
  const mw = mask.width;
  const mh = mask.height;
  const data = mask.getAsUint8Array(); // 0 bg, 1 fg typically

  const out = document.createElement("canvas");
  out.width = off.width;
  out.height = off.height;
  const ox = out.getContext("2d");
  ox.drawImage(off, 0, 0);
  const imgData = ox.getImageData(0, 0, out.width, out.height);
  const px = imgData.data;

  // category mask may be different size — nearest sample
  const bin = new Uint8Array(out.width * out.height);
  for (let y = 0; y < out.height; y++) {
    for (let x = 0; x < out.width; x++) {
      const mx = Math.min(mw - 1, Math.floor((x / out.width) * mw));
      const my = Math.min(mh - 1, Math.floor((y / out.height) * mh));
      const v = data[my * mw + mx];
      bin[y * out.width + x] = v === 0 ? 1 : 0; // InteractiveSegmenter: category 0 = selected object
    }
  }

  // optional white border via dilation
  const border = whiteBorder.checked ? 5 : 0;
  let ring = null;
  if (border > 0) {
    ring = new Uint8Array(bin.length);
    for (let y = 0; y < out.height; y++) {
      for (let x = 0; x < out.width; x++) {
        if (bin[y * out.width + x]) continue;
        let near = false;
        for (let dy = -border; dy <= border && !near; dy++) {
          for (let dx = -border; dx <= border; dx++) {
            const nx = x + dx, ny = y + dy;
            if (nx < 0 || ny < 0 || nx >= out.width || ny >= out.height) continue;
            if (bin[ny * out.width + nx]) { near = true; break; }
          }
        }
        if (near) ring[y * out.width + x] = 1;
      }
    }
  }

  for (let i = 0; i < bin.length; i++) {
    const o = i * 4;
    if (bin[i]) {
      px[o + 3] = 255;
    } else if (ring && ring[i]) {
      px[o] = 255; px[o + 1] = 255; px[o + 2] = 255; px[o + 3] = 255;
    } else {
      px[o + 3] = 0;
    }
  }
  ox.putImageData(imgData, 0, 0);

  // crop
  let minX = out.width, minY = out.height, maxX = 0, maxY = 0;
  for (let y = 0; y < out.height; y++) {
    for (let x = 0; x < out.width; x++) {
      if (px[(y * out.width + x) * 4 + 3] > 0) {
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
      }
    }
  }
  const cw = Math.max(1, maxX - minX + 1);
  const ch = Math.max(1, maxY - minY + 1);
  const cropped = document.createElement("canvas");
  cropped.width = cw;
  cropped.height = ch;
  cropped.getContext("2d").drawImage(out, minX, minY, cw, ch, 0, 0, cw, ch);

  const blob = await new Promise((r) => cropped.toBlob(r, "image/png"));
  showResult(blob);
  setStatus(t("st_mpDone"), true);
}

function showResult(blob) {
  lastPngBlob = blob;
  btnDownload.disabled = !blob;
  const url = URL.createObjectURL(blob);
  resultImg.onload = () => URL.revokeObjectURL(url);
  resultImg.src = url;
  resultImg.hidden = false;
  resultEmpty.hidden = true;
}

async function runServer(methodName) {
  if (!imgFile) throw new Error(t("e_upload"));
  if (methodName === "opencv" && !points.some((p) => p.label === 1)) {
    throw new Error(t("e_gc"));
  }
  const fd = new FormData();
  fd.append("file", imgFile, imgFile.name || "upload.jpg");
  fd.append("method", methodName === "opencv" ? "opencv" : methodName === "ai" ? "ai" : methodName === "multi" ? "multi" : "rembg");
  fd.append("smooth", $("#smooth").value);
  fd.append("rembg_model", $("#rembgModel").value);
  fd.append("complete", $("#complete").checked ? "true" : "false");
  fd.append("despeckle", $("#despeckle").checked ? "true" : "false");
  fd.append("white_border", whiteBorder.checked ? "true" : "false");
  if (methodName === "opencv") {
    // normalize to 0-1 relative to displayed canvas → map to original via canvas/natural
    const pts = points.map((p) => ({
      x: p.x / canvas.width,
      y: p.y / canvas.height,
      label: p.label,
    }));
    fd.append("points_json", JSON.stringify(pts));
  }
  setStatus(t("st_uploading", { m: methodName }));
  const res = await fetch(API_URL, { method: "POST", body: fd });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(text || res.statusText); }
  if (res.status === 429) throw new Error(t("e_rate", { s: data.retry_after || res.headers.get("Retry-After") || 10 }).replace(/<[^>]+>/g, ""));
  if (!res.ok) throw new Error((data.error && data.error.message) || data.detail || data.message || text || t("e_req"));
  if (methodName === "multi") { showMulti(data); return; }
  const bin = Uint8Array.from(atob(data.result_png_b64), (c) => c.charCodeAt(0));
  const blob = new Blob([bin], { type: "image/png" });
  showResult(blob);
  if (methodName === "ai") showAi(data);
  const note = data.note ? ` · ${data.note}` : "";
  setStatus(t("st_done", { m: data.method, note }), true);
}

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function showAi(data) {
  aiInfo.hidden = false;
  const tried = (data.tried || []).map((t) => `${esc(t.model)}${t.ok ? " ✓" : " ✗"}`).join(", ");
  if (data.fallback) {
    aiBox = null;
    aiInfo.innerHTML = `${t("ai_fallback")}<br><small>${t("tried")}: ${tried || t("none")}</small>`;
    btnMpAi.hidden = true;
  } else {
    aiBox = data.box;
    points = [
      ...(data.fg_points || []).map(([x, y]) => ({ x: x * canvas.width, y: y * canvas.height, label: 1 })),
      ...(data.bg_points || []).map(([x, y]) => ({ x: x * canvas.width, y: y * canvas.height, label: 0 })),
    ];
    aiInfo.innerHTML = `${t("ai_found", { label: esc(data.label), model: esc(data.model) })}<br><small>${t("tried")}: ${tried}</small>`;
    btnMpAi.hidden = false;
  }
  redraw();
}
btnMpAi.addEventListener("click", async () => {
  btnMpAi.disabled = true;
  try { await runMediaPipe(); } catch (e) { setStatus(String(e.message || e), false); }
  finally { btnMpAi.disabled = false; }
});

btnRun.addEventListener("click", async () => {
  btnRun.disabled = true;
  try {
    const m = method();
    if (m === "mediapipe") await runMediaPipe();
    else await runServer(m);
  } catch (e) {
    console.error(e);
    setStatus(String(e.message || e), false);
  } finally {
    btnRun.disabled = false;
  }
});

btnDownload.addEventListener("click", () => {
  if (!lastPngBlob) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(lastPngBlob);
  a.download = "sticker.png";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
});

// health ping
fetch(HEALTH_URL).then(r => r.json()).then(j => {
  console.log("segImage health", j);
}).catch(() => {});

$("#smooth").addEventListener("input", (e) => { $("#smoothVal").textContent = e.target.value; });

const b64blob = (b) => new Blob([Uint8Array.from(atob(b), (c) => c.charCodeAt(0))], { type: "image/png" });
function dl(blob, name) { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
function showMulti(data) {
  multiObjs = data.objects || []; aiBox = null; points = [];
  const tried = (data.tried || []).map((t) => `${esc(t.model)}${t.ok ? " ✓" : " ✗"}`).join(", ");
  aiInfo.hidden = false;
  aiInfo.innerHTML = data.fallback ? `${t("multi_fallback")}<br><small>${t("tried")}: ${tried || t("none")}</small>`
    : `${t("multi_found", { model: esc(data.model), n: multiObjs.length })}<br><small>${t("tried")}: ${tried}</small>`;
  $("#multiBox").hidden = false; $("#multiTitle").textContent = t("multi_title", { n: multiObjs.length });
  const g = $("#gallery"); g.innerHTML = "";
  multiObjs.forEach((o, i) => {
    const d = document.createElement("div"); d.className = "gal checker";
    const url = URL.createObjectURL(b64blob(o.png_b64));
    d.innerHTML = `<img src="${url}"><div>${esc(o.label)}</div>`;
    const b = document.createElement("button"); b.className = "btn"; b.textContent = t("dl");
    b.onclick = () => dl(b64blob(o.png_b64), `${i + 1}_${o.label}.png`); d.appendChild(b); g.appendChild(d);
  });
  if (multiObjs[0]) showResult(b64blob(multiObjs[0].png_b64));
  setStatus(t("st_multiDone", { n: multiObjs.length }), true);
  redraw();
}
$("#btnZip").addEventListener("click", async () => {
  if (window.JSZip) {
    const z = new JSZip(); multiObjs.forEach((o, i) => z.file(`${i + 1}_${o.label}.png`, o.png_b64, { base64: true }));
    dl(await z.generateAsync({ type: "blob" }), "stickers.zip");
  } else for (const [i, o] of multiObjs.entries()) { dl(b64blob(o.png_b64), `${i + 1}_${o.label}.png`); await new Promise((r) => setTimeout(r, 400)); }
});

fetch(HEALTH_URL).then((r) => r.json()).then((h) => {
  const sel = $("#rembgModel");
  if (h.rembg_models) {
    sel.innerHTML = Object.entries(h.rembg_models).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
    sel.value = h.rembg_default;
  }
}).catch(() => {});
document.addEventListener("langchange", () => { try { updateMethodUI(); } catch (e) {} });
