# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

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
