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
  statusEl.textContent = t;
  statusEl.style.color = ok === false ? "#ff8e8e" : ok === true ? "#3ecf8e" : "";
}

function updateMethodUI() {
  const m = method();
  const needPts = m === "opencv" || m === "mediapipe";
  ptools.hidden = !needPts;
  if (m === "ai") pointHint.textContent = "AI 自动找主体并抠图，无需点选";
  else if (m === "rembg") pointHint.textContent = "自动模式：无需点选，点「开始分割」即可";
  else if (m === "mediapipe") pointHint.textContent = "在图上点击物体（可多点），再点「开始分割」；完全在浏览器运行";
  else pointHint.textContent = "绿点=前景，红点=背景；至少点 1 个前景，再点「开始分割」";
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
    setStatus("请选择图片文件", false);
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
    setStatus(`已加载 ${file.name}（${Math.round(file.size / 1024)} KB）`, true);
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
    setStatus("正在加载 MediaPipe 模型（首次较慢）…");
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
    setStatus("MediaPipe 就绪", true);
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
  if (!imgBitmap) throw new Error("请先上传图片");
  if (!points.length) throw new Error("请先在图上点击要分割的物体");
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
  if (!mask) throw new Error("MediaPipe 未返回 mask");
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
      bin[y * out.width + x] = v > 0 ? 1 : 0;
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
  setStatus("MediaPipe 分割完成（未上传服务器）", true);
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
  if (!imgFile) throw new Error("请先上传图片");
  if (methodName === "opencv" && !points.some((p) => p.label === 1)) {
    throw new Error("GrabCut 请至少点一个前景点");
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
  setStatus(`上传并分割中（${methodName}）… 服务器处理后立即丢弃原始图`);
  const res = await fetch(API_URL, { method: "POST", body: fd });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(text || res.statusText); }
  if (!res.ok) throw new Error(data.detail || data.message || text || "请求失败");
  if (methodName === "multi") { showMulti(data); return; }
  const bin = Uint8Array.from(atob(data.result_png_b64), (c) => c.charCodeAt(0));
  const blob = new Blob([bin], { type: "image/png" });
  showResult(blob);
  if (methodName === "ai") showAi(data);
  const note = data.note ? ` · ${data.note}` : "";
  setStatus(`完成：${data.method}${note}`, true);
}

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function showAi(data) {
  aiInfo.hidden = false;
  const tried = (data.tried || []).map((t) => `${esc(t.model)}${t.ok ? " ✓" : " ✗"}`).join("，");
  if (data.fallback) {
    aiBox = null;
    aiInfo.innerHTML = `免费模型都没给出可用结果，已回退 rembg 自动抠图。<br><small>尝试：${tried || "无"}</small>`;
    btnMpAi.hidden = true;
  } else {
    aiBox = data.box;
    points = [
      ...(data.fg_points || []).map(([x, y]) => ({ x: x * canvas.width, y: y * canvas.height, label: 1 })),
      ...(data.bg_points || []).map(([x, y]) => ({ x: x * canvas.width, y: y * canvas.height, label: 0 })),
    ];
    aiInfo.innerHTML = `识别：<b>${esc(data.label)}</b> · 模型：<code>${esc(data.model)}</code><br><small>尝试：${tried}</small>`;
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
  const tried = (data.tried || []).map((t) => `${esc(t.model)}${t.ok ? " ✓" : " ✗"}`).join("，");
  aiInfo.hidden = false;
  aiInfo.innerHTML = data.fallback ? `免费模型都失败，已回退 rembg 连通块拆分。<br><small>尝试：${tried || "无"}</small>`
    : `模型：<code>${esc(data.model)}</code> · ${multiObjs.length} 个物体<br><small>尝试：${tried}</small>`;
  $("#multiBox").hidden = false; $("#multiTitle").textContent = `共 ${multiObjs.length} 个贴纸`;
  const g = $("#gallery"); g.innerHTML = "";
  multiObjs.forEach((o, i) => {
    const d = document.createElement("div"); d.className = "gal checker";
    const url = URL.createObjectURL(b64blob(o.png_b64));
    d.innerHTML = `<img src="${url}"><div>${esc(o.label)}</div>`;
    const b = document.createElement("button"); b.className = "btn"; b.textContent = "下载";
    b.onclick = () => dl(b64blob(o.png_b64), `${i + 1}_${o.label}.png`); d.appendChild(b); g.appendChild(d);
  });
  if (multiObjs[0]) showResult(b64blob(multiObjs[0].png_b64));
  setStatus(`多主体完成：${multiObjs.length} 个`, true);
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
    sel.innerHTML = Object.entries(h.rembg_models).map(([k, v]) => `<option value="${k}">${v}${k === h.rembg_default ? "（默认）" : ""}</option>`).join("");
    sel.value = h.rembg_default;
  }
}).catch(() => {});
