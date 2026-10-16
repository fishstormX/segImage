/* segImage i18n — default follows browser language (zh* → Chinese, else English). ?lang=en|zh overrides; choice remembered in localStorage. */
(function () {
  const VERSION = "1.2.1";
  const D = {
    en: {
      title: "Free Online Background Remover – Remove Image Background | segImage", metaDesc: "Remove image backgrounds free online: cut out objects, products, food, people, pets and ID photos into transparent PNGs or stickers. Open source (rembg, MediaPipe, GrabCut, AI auto-box); uploads are never stored.",
      h1: "segImage — Cutout Lab",
      sub: "Upload an image → pick a method → click / auto segment → export a transparent sticker. Objects, people, animals, food, products, cards. The server never stores uploads.",
      apiDocs: "API & SDK", github: "GitHub", langBtn: "中文",
      m_rembg: "① rembg / U²-Net", m_rembg_s: "Server auto background removal (CPU)",
      m_mp: "② MediaPipe", m_mp_s: "In-browser click-to-segment (no upload)",
      m_ai: "④ AI auto-box", m_ai_s: "Free vision LLM locates the subject + GrabCut",
      m_multi: "⑤ Multi-subject", m_multi_s: "AI lists several objects, one sticker each",
      m_cv: "③ OpenCV GrabCut", m_cv_s: "Server: click foreground / background",
      whiteBorder: "White sticker border", rembgModel: "rembg model", despeckle: "Despeckle",
      complete: "Smart subject completion (pure vision)", completeTip: "Pure vision: border colour model + GrabCut to recover subjects that were only partially cut",
      smooth: "Smoothing",
      fg: "Foreground ●", bg: "Background ●", clearPts: "Clear points",
      pick: "Choose image", run: "Segment", download: "Download PNG",
      drop: "Drag an image here, or click “Choose image”",
      ready: "Ready", preview: "Result", empty: "The cutout will appear here",
      zipAll: "Download all", mpAi: "Run MediaPipe with the AI points",
      notesTitle: "Methods",
      n_rembg: "<b>rembg</b>: U²-Net family, best for a clear single subject (objects, products, animals, food). CPU only, no Meta SAM weights.",
      n_mp: "<b>MediaPipe</b>: Interactive Segmenter — click the object; the model runs locally in your browser.",
      n_ai: "<b>AI auto-box</b>: only free OpenRouter vision models locate the subject (box + fg/bg points), then server GrabCut; falls back to rembg.",
      n_cv: "<b>OpenCV GrabCut</b>: click a few foreground (green) and background (red) points, then segment.",
      n_tip: "<b>Tip — documents / cards:</b> rembg or AI auto-box usually isolate a card or page well; for perspective flattening use a dedicated scanner app.",
      hint_multi: "AI lists multiple objects and cuts each one — no clicks needed",
      hint_ai: "AI finds the subject automatically — no clicks needed",
      hint_rembg: "Automatic mode: no clicks needed, just press “Segment”",
      hint_mp: "Click the object (multiple points OK), then “Segment”; runs entirely in your browser",
      hint_cv: "Green = foreground, red = background; add at least 1 foreground point, then “Segment”",
      st_pickFile: "Please choose an image file", st_loaded: "Loaded {name} ({kb} KB)",
      st_mpLoading: "Loading MediaPipe model (slow the first time)…", st_mpReady: "MediaPipe ready",
      e_upload: "Please upload an image first", e_click: "Click the object you want to segment first",
      e_nomask: "MediaPipe returned no mask", st_mpDone: "MediaPipe done (nothing uploaded)",
      e_gc: "GrabCut needs at least one foreground point",
      st_uploading: "Uploading & segmenting ({m})… the image is discarded right after processing",
      d_testonly: "⚠️ This API is for testing only. For commercial use or partnership inquiries, contact <a href='mailto:stormnetwork@163.com'>stormnetwork@163.com</a> (海口龙华区妙妙鱼传媒工作室 / Miaomiaoyu Media Studio, Longhua District, Haikou). Public instance limits per IP: 1 call / 10 s and 5 calls / 60 s (HTTP 429 when exceeded).", e_req: "Request failed", e_rate: "Too many requests (rate limited). Please wait {s}s and try again. This API is for testing only. For commercial use or partnership inquiries, contact stormnetwork@163.com (海口龙华区妙妙鱼传媒工作室 / Miaomiaoyu Media Studio, Longhua District, Haikou).", st_done: "Done: {m}{note}",
      ai_fallback: "No free model returned a usable box — fell back to rembg.", tried: "Tried", none: "none",
      ai_found: "Detected: <b>{label}</b> · model: <code>{model}</code>",
      multi_fallback: "All free models failed — fell back to rembg connected components.",
      multi_found: "Model: <code>{model}</code> · {n} objects", multi_title: "{n} stickers", dl: "Download",
      st_multiDone: "Multi-subject done: {n}",
      footer: "MIT licensed · uploads processed in memory, never stored",
    },
    zh: {
      title: "免费在线抠图 – 一键去除图片背景 | segImage", metaDesc: "免费在线智能抠图工具：物品、商品、美食、人像、宠物、证件照一键去背景，导出透明 PNG 或贴纸。开源（rembg / MediaPipe / GrabCut / AI 框选），图片不落盘不保存。",
      h1: "segImage — 抠图实验室",
      sub: "上传图片 → 选方案 → 点击/自动分割 → 导出透明贴纸。适用于物品、人物、动物、食物、商品、证件卡片等。服务器不保存任何上传内容。",
      apiDocs: "API 与 SDK", github: "GitHub", langBtn: "EN",
      m_rembg: "① rembg / U²-Net", m_rembg_s: "服务端自动抠图（CPU）",
      m_mp: "② MediaPipe", m_mp_s: "浏览器端点选分割（不上传）",
      m_ai: "④ AI 自动框选", m_ai_s: "免费视觉大模型定位 + GrabCut",
      m_multi: "⑤ 多主体", m_multi_s: "AI 列出多个物体，逐个抠成贴纸",
      m_cv: "③ OpenCV GrabCut", m_cv_s: "服务端：点前景/背景",
      whiteBorder: "白边贴纸效果", rembgModel: "rembg 模型", despeckle: "去碎块",
      complete: "智能补全主体 (纯视觉)", completeTip: "纯视觉：用边缘背景模型+GrabCut 把只抠出一部分的主体补全",
      smooth: "平滑强度",
      fg: "前景 ●", bg: "背景 ●", clearPts: "清除点",
      pick: "选择图片", run: "开始分割", download: "下载 PNG",
      drop: "拖拽图片到这里，或点击「选择图片」",
      ready: "就绪", preview: "结果预览", empty: "分割结果会出现在这里",
      zipAll: "全部下载", mpAi: "用 AI 点自动跑 MediaPipe",
      notesTitle: "方案说明",
      n_rembg: "<b>rembg</b>：U²-Net 系列，适合主体清晰的单个物体（物品、商品、动物、食物）；纯 CPU，未部署 Meta SAM 权重。",
      n_mp: "<b>MediaPipe</b>：Interactive Segmenter，点一下物体即可；模型在浏览器本地跑。",
      n_ai: "<b>AI 自动框选</b>：仅用 OpenRouter 免费视觉模型定位主体（框+前景/背景点），服务端 GrabCut 抠图；都失败时回退 rembg。",
      n_cv: "<b>OpenCV GrabCut</b>：先点几个前景（绿）和背景（红）再分割；也可只点前景。",
      n_tip: "<b>提示 · 证件/卡片/文档：</b>rembg 或 AI 自动框选通常能把卡片/纸张抠出来；如需透视拉正，请用专门的扫描 App。",
      hint_multi: "AI 自动列出多个物体并逐个抠图，无需点选",
      hint_ai: "AI 自动找主体并抠图，无需点选",
      hint_rembg: "自动模式：无需点选，点「开始分割」即可",
      hint_mp: "在图上点击物体（可多点），再点「开始分割」；完全在浏览器运行",
      hint_cv: "绿点=前景，红点=背景；至少点 1 个前景，再点「开始分割」",
      st_pickFile: "请选择图片文件", st_loaded: "已加载 {name}（{kb} KB）",
      st_mpLoading: "正在加载 MediaPipe 模型（首次较慢）…", st_mpReady: "MediaPipe 就绪",
      e_upload: "请先上传图片", e_click: "请先在图上点击要分割的物体",
      e_nomask: "MediaPipe 未返回 mask", st_mpDone: "MediaPipe 分割完成（未上传服务器）",
      e_gc: "GrabCut 请至少点一个前景点",
      st_uploading: "上传并分割中（{m}）… 服务器处理后立即丢弃原始图",
      d_testonly: "⚠️ 此接口仅供测试使用，如有商业使用或合作意向，请联系 <a href='mailto:stormnetwork@163.com'>stormnetwork@163.com</a>（海口龙华区妙妙鱼传媒工作室）。公共实例按 IP 限流：每 10 秒 1 次、每分钟 5 次，超出返回 HTTP 429。", e_req: "请求失败", e_rate: "请求过于频繁（rate limited），请 {s} 秒后再试。此接口仅供测试使用，如有商业使用或合作意向，请联系 stormnetwork@163.com（海口龙华区妙妙鱼传媒工作室）。", st_done: "完成：{m}{note}",
      ai_fallback: "免费模型都没给出可用结果，已回退 rembg 自动抠图。", tried: "尝试", none: "无",
      ai_found: "识别：<b>{label}</b> · 模型：<code>{model}</code>",
      multi_fallback: "免费模型都失败，已回退 rembg 连通块拆分。",
      multi_found: "模型：<code>{model}</code> · {n} 个物体", multi_title: "共 {n} 个贴纸", dl: "下载",
      st_multiDone: "多主体完成：{n} 个",
      footer: "MIT 开源 · 上传内容仅在内存中处理，从不保存",
    },
  };
  const q = new URLSearchParams(location.search).get("lang");
  let lang = (q && q.toLowerCase().startsWith("zh")) ? "zh" : (q && q.toLowerCase().startsWith("en")) ? "en" : null;
  if (lang) { try { localStorage.setItem("segImage.lang", lang); } catch (e) {} }
  else { try { lang = localStorage.getItem("segImage.lang"); } catch (e) {} }
  if (lang !== "zh" && lang !== "en") {
    // no explicit/saved choice: follow the browser language (zh* → zh, anything else → en)
    const bl = (navigator.languages && navigator.languages[0]) || navigator.language || "";
    lang = bl.toLowerCase().startsWith("zh") ? "zh" : "en";
  }
  function t(k, v) {
    let s = (D[lang] && D[lang][k]) ?? D.en[k] ?? k;
    if (v) s = s.replace(/\{(\w+)\}/g, (_, n) => (v[n] ?? ""));
    return s;
  }
  function apply() {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    if (D[lang].title && document.body.dataset.titleKey !== "none") document.title = t(document.body.dataset.titleKey || "title");
    if (!document.body.dataset.titleKey && D[lang].metaDesc) {
      const desc = t(document.body.dataset.descKey || "metaDesc");
      document.querySelectorAll('meta[name="description"],meta[property="og:description"],meta[name="twitter:description"]').forEach((m) => m.setAttribute("content", desc));
      document.querySelectorAll('meta[property="og:title"],meta[name="twitter:title"]').forEach((m) => m.setAttribute("content", document.title));
    }
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    document.querySelectorAll("[data-lang-only]").forEach((el) => { el.hidden = el.dataset.langOnly !== lang; });
    document.querySelectorAll(".ver").forEach((el) => { el.textContent = "v" + VERSION.replace(/\.0$/, ""); });
    document.dispatchEvent(new CustomEvent("langchange", { detail: lang }));
  }
  function setLang(l) {
    lang = l === "zh" ? "zh" : "en";
    try { localStorage.setItem("segImage.lang", lang); } catch (e) {}
    const u = new URL(location.href); u.searchParams.set("lang", lang); history.replaceState(null, "", u);
    apply();
  }
  window.I18N = { t, apply, setLang, get lang() { return lang; }, VERSION, dict: D };
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.querySelectorAll("[data-lang-toggle]").forEach((b) => b.addEventListener("click", () => setLang(lang === "en" ? "zh" : "en")));
  });
})();
