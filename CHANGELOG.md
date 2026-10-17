# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.3.0] - 2026-10-18

### Added
- Local **CLI** (`segimage` / `python -m segimage` / `python -m app`) sharing `app.pipeline` with the FastAPI service: rembg, GrabCut, AI auto-box, multi-subject; file / directory batch / stdin→stdout; `--help` documents flags and models.
- `backend/pyproject.toml` installable package with console script; Quickstart rewritten around install → one-command cutout → flags → local API → SDKs (EN + ZH).
- In-site API docs page: CLI quickstart section (EN/ZH).

### Changed
- Cutout engine extracted to `app.pipeline.run_segment` so the API and CLI do not duplicate the core path.
- Web UI only shows options that apply to the selected method: rembg model (rembg only), smart completion (rembg / ai / multi), despeckle & smooth (server methods, not MediaPipe), white border (all PNG paths).
- CLI `--help` documents which flags are rembg-only vs shared.

## [1.2.1] - 2026-10-16

### Added
- Per-client-IP rate limiting on the cutout endpoints (`POST /api/v1/segment`, `/api/v1/multi`, legacy `/api/segment`). Default `1/10s,5/60s`; exceeding returns HTTP 429 `RATE_LIMITED` (`"rate limited"`, `retry_after`, `Retry-After` header). Configurable via `SEG_RATE_LIMITS`; client IP taken from `X-Real-IP`/`X-Forwarded-For` only from `SEG_TRUSTED_PROXIES`.
- Testing-only notice with commercial contact (stormnetwork@163.com) on the API docs page, OpenAPI, SDKs, READMEs and in 429 responses (`message.en` / `message.zh`).
- SEO: per-language title/description, canonical + hreflang, Open Graph/Twitter card, WebApplication JSON-LD, noscript description, `robots.txt` / `sitemap.xml`.
- Web UI language now follows the browser language (zh* → Chinese, else English); `?lang=` and the saved choice still override.
- Web UI shows a friendly EN/ZH message on 429; SDKs expose `retry_after` / `retryAfter` and never auto-retry 429; OpenAPI documents 429.

## [1.2.0] - 2026-10-14

### Added
- Versioned REST API: `GET /api/v1/health`, `GET /api/v1/models`, `POST /api/v1/segment`, `POST /api/v1/multi`, with a consistent JSON schema, structured errors (`{"ok": false, "error": {"code", "message"}}`) and documented limits.
- OpenAPI 3.1 spec at `/api/openapi.json` and Swagger UI at `/api/docs`.
- Thin SDKs: Python (`sdk/python/segimage.py`, standard library only, typed) and JS/TS (`sdk/js`, fetch + FormData, browser and Node ≥ 18, `.d.ts` typings), plus examples and curl recipes.
- Bilingual web UI: English by default, Chinese toggle, `?lang=en|zh`, choice remembered in localStorage; version badge and GitHub link in header/footer; in-site API & SDK page (`api.html`).
- English `README.md` + `README.zh-CN.md`, `LICENSE` (MIT), `CONTRIBUTING.md`, issue templates.
- `SEGIMAGE_BASE_PATH`, `SEGIMAGE_MAX_BYTES`, `SEGIMAGE_SERVE_UI`, `SEGIMAGE_STATIC_DIR` settings; the backend can serve the web UI itself for a one-command local quickstart.

### Changed
- Positioning generalized beyond food: objects, people, animals, food, documents/cards. AI prompts now prioritize objects/products, people, animals, food and cards/documents and return English labels.
- rembg model labels are now English; legacy `/api/segment` and `/api/health` remain as aliases with the old response shape.
- Fixed hidden point-tool buttons showing in automatic modes.

### Notes
- A pure-vision "document" helper (quadrilateral detection + perspective crop) was prototyped but not shipped: it was not robust on textured backgrounds or partially visible pages. Documented as a tip instead.

## [1.1.0] - 2026-10

### Added
- rembg model selector (`u2netp`, `isnet-general-use`, `u2net`, `silueta`) with a lazy LRU (≤ 2 loaded models) and benchmarks.
- Smart subject completion (pure vision): border colour model, flood fill, trimap + GrabCut, SLIC voting, background-swallow guard; multi-scale container (ellipse) cue.
- Input normalization (EXIF transpose, ≤ 1280 px, JPEG q90) for consistent results.
- README case studies (book, kitten, hanfu) and UI screenshots.

### Fixed
- MediaPipe mask inversion; multi-subject hint text.

### Removed
- BiRefNet-lite (out of memory on a 3.6 GB CPU host).

## [1.0.0] - 2026-10

### Added
- Initial web demo: rembg / U²-Net-p, MediaPipe Interactive Segmenter (in-browser), OpenCV GrabCut.
- AI auto-box using free OpenRouter vision models only, with rembg fallback.
- Multi-subject mode with gallery and ZIP download.
- Mask post-processing (smoothing slider, despeckle) and white sticker border.
- In-memory processing only; no uploads persisted.
