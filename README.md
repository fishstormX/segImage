<div align="center">

**English** · [简体中文](README.zh-CN.md)

# ✂️ segImage

**Free online background remover for objects, people, pets, food and ID photos. Export transparent PNG stickers. Open source — uploads are never stored.**

Open-source cutout lab: rembg · MediaPipe · GrabCut · free AI auto-box — with a first-class **CLI**, **SDKs** and **REST API**, plus a privacy-first web demo.

[![version](https://img.shields.io/badge/version-1.3.1-3d8bfd)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](backend/requirements.txt)
[![fastapi](https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![demo](https://img.shields.io/badge/live%20demo-jev.fishmaple.cn%2FsegImage-orange)](https://jev.fishmaple.cn/segImage/)

![hero](docs/images/hero.webp)

</div>

## Get started — CLI · SDK · API

Three equal ways into the same cutout engine. Pick one:

### 🖥️ CLI — local cutout, no server

```bash
pip install -e backend/          # from a clone
segimage photo.jpg -o sticker.png
segimage ./photos/ -o ./stickers/   # batch
```

Same `app.pipeline` as the web demo. MediaPipe is browser-only. → [Quickstart](#quickstart) · `segimage --help`

### 📦 SDK — Python & JS/TS

```python
from segimage import SegImage
c = SegImage("https://jev.fishmaple.cn/segImage")
c.segment(open("photo.jpg", "rb")).image.save("sticker.png")
```

```js
import { SegImage } from "./segimage.js";
const r = await new SegImage("https://jev.fishmaple.cn/segImage").segment(file);
```

→ [Python](sdk/python/segimage.py) · [JS/TS](sdk/js) · [curl recipes](sdk/curl.md)

### 🔌 API — REST `/api/v1/*`

```bash
curl -s -F file=@photo.jpg https://jev.fishmaple.cn/segImage/api/v1/segment
```

→ [In-site docs](https://jev.fishmaple.cn/segImage/api.html) · [Swagger UI](https://jev.fishmaple.cn/segImage/api/docs) · [OpenAPI](https://jev.fishmaple.cn/segImage/api/openapi.json)

> Public API is **for testing only**. Commercial / partnership: [stormnetwork@163.com](mailto:stormnetwork@163.com). Limits: 1 / 10 s · 5 / 60 s per IP.


## Use with an Agent

Copy-paste this into Cursor / ChatGPT / Claude / any coding agent:

```
You are helping me remove image backgrounds with segImage
(https://github.com/fishstormX/segImage — demo https://jev.fishmaple.cn/segImage/).

Prefer the local CLI (same pipeline as the server, uploads never leave the machine):
  pip install -e backend/   # from a clone of the repo
  segimage INPUT.jpg -o OUTPUT.png
  # flags: --method rembg|grabcut|ai|multi  --model u2netp|u2net|isnet-general-use|silueta
  #        --no-border --no-complete --smooth 0-10  --mask mask.png
  # batch: segimage ./photos/ -o ./stickers/

Or call the public REST API (testing only; rate-limited 1/10s, 5/60s per IP):
  curl -s -F file=@INPUT.jpg https://jev.fishmaple.cn/segImage/api/v1/segment
Python/JS SDKs: sdk/python/segimage.py · sdk/js
Docs: https://jev.fishmaple.cn/segImage/api.html
Privacy: local CLI keeps files on disk you choose; the public demo processes in memory and never stores uploads.
```

## Features

- **5 segmentation methods in one UI** — rembg (U²-Net family, server CPU), MediaPipe Interactive Segmenter (in-browser, nothing uploaded), OpenCV GrabCut (click foreground/background), **AI auto-box** (a free vision LLM finds the subject → GrabCut) and **multi-subject** (one sticker per object, ZIP download).
- **Works on any subject** — objects & products, people, animals, food, books, cards and documents.
- **Sticker output** — transparent PNG, auto-cropped, optional white outline.
- **Mask post-processing** — despeckle, hole filling, contour smoothing, guided-filter feathering (`smooth` 0–10).
- **Smart subject completion (pure vision)** — grows a partial model mask to the whole subject using a border colour model, flood fill, trimap + GrabCut and SLIC voting, with a guard against swallowing background.
- **CLI · SDK · API** — see [Get started](#get-started--cli--sdk--api) above; details in Quickstart / API & SDK.
- **Free models only** — the AI modes use only OpenRouter models whose id ends in `:free`; without a key (or when all fail) they fall back to local rembg.
- **Privacy** — uploads are processed in memory and discarded; no database, nothing written to disk.
- **Bilingual UI** — English / 中文 (`?lang=zh`, remembered in your browser).

## Live Demo

👉 **https://jev.fishmaple.cn/segImage/** · API docs: [in-site guide](https://jev.fishmaple.cn/segImage/api.html) · [Swagger UI](https://jev.fishmaple.cn/segImage/api/docs)

The demo runs on a small 4-vCPU box without a GPU — please be gentle, and self-host (or use the CLI) for batch work. **The public API is for testing only**; for commercial use or partnership inquiries contact [stormnetwork@163.com](mailto:stormnetwork@163.com) (妙妙鱼 / fishstormX).

| Desktop | AI auto-box | Multi-subject |
|---|---|---|
| ![rembg](docs/images/ui_desktop_rembg.webp) | ![ai](docs/images/ui_desktop_ai.webp) | ![multi](docs/images/ui_desktop_multi.webp) |

## Quickstart

Requires Python 3.10+ (tested with 3.13). The first rembg run downloads the `u2netp` model (~4.7 MB) to `~/.u2net`.

### 1. Install

```bash
git clone https://github.com/fishstormX/segImage.git
cd segImage/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e .                # installs the `segimage` CLI + API deps
# or: pip install -r requirements.txt
```

### 2. One-command first cutout (CLI)

The CLI uses the **same** `app.pipeline` engine as the FastAPI service (rembg / GrabCut / AI auto-box / multi). MediaPipe is browser-only and is not available from the CLI.

```bash
segimage photo.jpg -o sticker.png
# equivalents:
#   python -m segimage photo.jpg -o sticker.png
#   python -m app photo.jpg -o sticker.png
```

Useful flags:

```bash
segimage photo.jpg -o out.png --method rembg --model u2netp
segimage photo.jpg -o out.png --method rembg --model u2net --no-complete --no-border
segimage photo.jpg -o out.png --method grabcut --rect 0.1,0.1,0.8,0.8
segimage photo.jpg -o out.png --method grabcut --points '[[0.5,0.5,1]]'
segimage desk.jpg  -o subjects/ --method multi          # needs OPENROUTER_API_KEY for best results
segimage ./photos/ -o ./stickers/                       # batch a directory
cat photo.jpg | segimage - -o - > sticker.png           # stdin → stdout
segimage photo.jpg -o out.png --mask mask.png           # also write the alpha mask
segimage --help
```

`--method`: `rembg` (default) · `grabcut` · `ai` · `multi`. `--model`: `u2netp` (default) · `isnet-general-use` · `u2net` · `silueta` (**rembg-only**; also used as the rembg fallback for `ai`/`multi`). `--no-complete` is rembg-only (ignored by grabcut). `--smooth` / `--no-despeckle` apply to rembg · grabcut · ai · multi. `--no-border` applies to every PNG sticker.

### 3. Local API / web UI

```bash
uvicorn app.main:app --port 8765          # serves API + web UI
```

Open http://127.0.0.1:8765/ for the UI and http://127.0.0.1:8765/api/docs for Swagger:

```bash
curl -s http://127.0.0.1:8765/api/v1/health
curl -s -F file=@photo.jpg http://127.0.0.1:8765/api/v1/segment \
  | python3 -c "import sys,json,base64;d=json.load(sys.stdin);open('sticker.png','wb').write(base64.b64decode(d['image_png_b64']));print(d['engine'],d['elapsed_ms'],'ms')"
```

Optional: `export OPENROUTER_API_KEY=...` before starting uvicorn (or before `segimage --method ai|multi`) to enable the AI modes (free OpenRouter models only).

### 4. SDKs (talk to a running server)

Thin HTTP clients — not required for local CLI cutouts: [Python](sdk/python/segimage.py) · [JS/TS](sdk/js) · [curl recipes](sdk/curl.md). See [API & SDK](#api--sdk) below.

## API & SDK

> ⚠️ **This API is for testing only. For commercial use or partnership inquiries, contact stormnetwork@163.com (妙妙鱼 / fishstormX). Public instance limits per IP: 1 call / 10 s and 5 calls / 60 s (HTTP 429 when exceeded).** Self-host for production use; limits are configurable via `SEG_RATE_LIMITS`.

| Route | Description |
|---|---|
| `GET  /api/v1/health` | version, loaded models, limits |
| `GET  /api/v1/models` | rembg models + currently available free vision models |
| `POST /api/v1/segment` | one subject → transparent PNG; `method` = `rembg` \| `grabcut` \| `ai` |
| `POST /api/v1/multi` | up to 6 subjects → one PNG each |
| `GET  /api/docs`, `/api/openapi.json` | Swagger UI / OpenAPI 3.1 spec |
| `POST /api/segment`, `GET /api/health` | legacy aliases (v1.0/1.1 response shape), kept for compatibility |

Form fields (`multipart/form-data`): `file` (≤ 12 MB), `method`, `rembg_model` (`u2netp` default · `isnet-general-use` · `u2net` · `silueta`), `complete` (true), `smooth` (0–10, 3), `despeckle` (true), `white_border` (true), `points_json` / `rect_json` (GrabCut seeds, normalized 0..1).

```jsonc
// 200
{ "ok": true, "version": "1.3.1", "method": "rembg", "engine": "rembg_u2netp+smart_complete",
  "rembg_model": "u2netp", "width": 960, "height": 1280, "elapsed_ms": 1800,
  "image_png_b64": "iVBOR…", "mask_png_b64": "iVBOR…", "detection": null }
// error
{ "ok": false, "error": { "code": "FILE_TOO_LARGE", "message": "File larger than 12 MB" } }
```

Error codes: `EMPTY_FILE`, `BAD_JSON`, `UNKNOWN_MODEL` (400) · `FILE_TOO_LARGE` (413) · `UNSUPPORTED_IMAGE` (415) · `VALIDATION_ERROR` (422) · `SEGMENTATION_FAILED` (500).

**Limits:** 12 MB per upload, rembg input normalized to ≤ 1280 px. No API key / auth — the public instance is best-effort; keep it to a few requests per minute. AI modes depend on free-model rate limits (may take up to ~2 min, then fall back to rembg).

**Python** — single file, standard library only ([sdk/python/segimage.py](sdk/python/segimage.py)):

```python
from segimage import SegImage
client = SegImage("https://jev.fishmaple.cn/segImage")
res = client.segment("photo.jpg", method="rembg")
res.save("sticker.png")
for i, s in enumerate(client.multi("desk.jpg").subjects, 1):
    s.save(f"{i}_{s.label}.png")
```

**JavaScript / TypeScript** — ESM, `fetch` + `FormData`, browser and Node ≥ 18, typings included ([sdk/js](sdk/js)):

```js
import { SegImage } from "./segimage.js";
const client = new SegImage("https://jev.fishmaple.cn/segImage");
const res = await client.segment(file, { method: "grabcut", points: [[0.5, 0.5, 1]] });
img.src = URL.createObjectURL(res.image);
```

More: [sdk/curl.md](sdk/curl.md), [sdk/python/example.py](sdk/python/example.py), [sdk/js/example.mjs](sdk/js/example.mjs).

## Methods comparison

All results below come from the live API (4 vCPU, no GPU; smooth 3, despeckle, white border; input ≤ 1280 px). MediaPipe was driven by one simulated click in headless Chrome. The gold frame marks the best result per case.

### Case 1 · Book cover photo
![case book](docs/images/case_book.webp)

- **Best: rembg U²-Net-p** — clean rectangular outline of the whole book. U²-Net / Silueta / AI auto-box are close.
- ISNet treats the "object" as the cover text and keeps only a few characters; a single MediaPipe click cannot cross the black band.
- Takeaway: for flat objects with large text (books, cards, packaging) salient-object models (U²-Net family) are the most reliable.

### Case 2 · Backlit kitten
![case kitten](docs/images/case_kitten.webp)

- **Best: U²-Net (full) + smart completion** — most complete fur edge and paws. ISNet, Silueta and MediaPipe are usable too (MediaPipe: ~4 s, nothing uploaded).
- Failure modes: U²-Net-p + completion added a strip of carpet; GrabCut with a fixed rect took the bright window as foreground.

### Case 3 · Holographic hanfu portrait (glowing background)
![case hanfu](docs/images/case_hanfu.webp)

- **Best: U²-Net (full) + smart completion**; Silueta is close.
- Hardest category: translucent fabric with colours close to the background. U²-Net-p + completion "completed" background into the subject — the known failure mode of completion; try turning it off.

## Which method should I use?

| Scenario | Recommended | Notes |
|---|---|---|
| One clear object / product / pet / dish | rembg U²-Net-p (default) + completion | fastest (~0.3 s inference); try U²-Net or ISNet if unhappy |
| People / portraits | rembg U²-Net or Silueta | turn completion off if background leaks in |
| Complex or glowing background, translucent materials | rembg U²-Net (full) or Silueta | |
| Flat objects: books, cards, documents, packaging | rembg U²-Net-p / U²-Net | avoid ISNet (keeps only text). For perspective flattening use a scanner app — segImage does not deskew. |
| You want a specific object | MediaPipe click or GrabCut fg/bg points | MediaPipe runs fully in the browser |
| Unknown subject, screenshots | AI auto-box | free models only, often rate-limited; falls back to rembg |
| Several objects → several stickers | Multi-subject | works best when objects are separated |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — (optional) | enables AI auto-box / multi-subject. **Only `:free` models are ever called**; without it AI modes fall back to rembg |
| `SEGIMAGE_BASE_PATH` | `""` | URL prefix when served behind a reverse proxy (e.g. `/segImage`), used by Swagger UI |
| `SEGIMAGE_MAX_BYTES` | `12582912` | upload limit in bytes |
| `SEGIMAGE_SERVE_UI` | `1` | also serve `frontend/` at `/` (set `0` when nginx serves it) |
| `SEGIMAGE_STATIC_DIR` | `../frontend` | where the web UI lives |
| `SEG_RATE_LIMITS` | `1/10s,5/60s` | per-client-IP limits on cutout calls: comma-separated `<count>/<window>` (`s`/`m`/`h`). All rules apply; exceeding returns HTTP 429 `rate limited` with `Retry-After`. Empty / `0` / `off` disables |
| `SEG_TRUSTED_PROXIES` | `127.0.0.1,::1` | peers allowed to set the client IP via `X-Real-IP` / `X-Forwarded-For` (make nginx send `X-Real-IP $remote_addr`) |
| `U2NET_HOME` | `~/.u2net` | rembg model cache |

See [.env.example](.env.example). Never commit a real key; on servers keep it in a root-only `EnvironmentFile` (`chmod 600`).

## Deployment

Tested on Debian + nginx + systemd (no Docker needed):

```bash
mkdir -p /opt/segImage && cp -r backend/* /opt/segImage/
cd /opt/segImage && python3 -m venv venv && venv/bin/pip install -r requirements.txt
mkdir -p /var/cache/segImage/u2net && chown -R www-data:www-data /var/cache/segImage /opt/segImage
install -d -m 700 /etc/segImage && install -m 600 .env.example /etc/segImage/env   # put your key in it
cp deploy/segImage.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now segImage
mkdir -p /var/www/jev/segImage && cp frontend/* /var/www/jev/segImage/   # must match `alias` in deploy/nginx-segImage.conf
# add deploy/nginx-segImage.conf to your server { } block, then:
nginx -t && systemctl reload nginx
curl -s https://<your-domain>/segImage/api/v1/health
```

A Dockerfile is not shipped yet (see Roadmap).

## Privacy

- Uploads are read into memory, processed and dropped at the end of the request; there is no database and nothing is written to disk (systemd `PrivateTmp=true`).
- MediaPipe mode runs entirely in your browser — the image never leaves your device.
- AI modes send a downscaled copy of the image to OpenRouter free models (third party); don't use them for sensitive images.
- The API key lives only on the server; it is never sent to the browser.

## Roadmap

- [ ] Dockerfile + compose
- [ ] Document mode: robust quadrilateral detection + perspective flattening (prototype was not reliable enough for 1.2)
- [ ] Optional GPU backends (SAM 2 / BiRefNet) when memory allows
- [x] Local CLI (`segimage`) sharing the server pipeline
- [ ] Batch endpoint and rate limiting headers
- [ ] Publish SDKs to PyPI / npm

## Contributing

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Please never include API keys, server addresses or personal photos in issues or commits.

## License

[MIT](LICENSE) © 2026 妙妙鱼 / fishstormX

## Acknowledgements

[rembg](https://github.com/danielgatis/rembg) · [U²-Net](https://github.com/xuebinqin/U-2-Net) · [MediaPipe](https://developers.google.com/mediapipe) · [OpenCV](https://opencv.org/) · [OpenRouter](https://openrouter.ai/) · [FastAPI](https://fastapi.tiangolo.com/) · [scikit-image](https://scikit-image.org/)
