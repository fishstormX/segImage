# Contributing to segImage

Thanks for helping! Bug reports, test images (that you have the right to share), docs and code are all welcome.

## Dev setup

```bash
git clone https://github.com/fishstormX/segImage.git && cd segImage/backend
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8765     # UI at http://127.0.0.1:8765/, docs at /api/docs
```

The frontend is plain HTML/JS (`frontend/`), no build step. UI strings live in `frontend/i18n.js` — please add both `en` and `zh` entries.

## Guidelines

- Keep the API backward compatible within `v1`; add fields rather than renaming. Update `CHANGELOG.md`.
- **Free models only**: AI features must only call OpenRouter models whose id ends in `:free`, and must fall back to local rembg.
- **No persistence**: never write uploads to disk or logs.
- **No secrets**: never commit API keys, `.env` files, server addresses or private photos. Grep your staged changes for your key prefix before pushing.
- Prefer general solutions over per-image hacks; include before/after results on a few diverse images in your PR.
- Python: type hints, small functions; JS: ES modules, no frameworks.

## Pull requests

1. Fork and create a branch from `main`.
2. Verify locally: `curl -s localhost:8765/api/v1/health` and a `POST /api/v1/segment` with a sample image; run `python sdk/python/example.py <img>` against your server (`SEGIMAGE_URL=http://127.0.0.1:8765`).
3. Describe what changed and why; attach screenshots for UI changes.

By contributing you agree that your contributions are licensed under the MIT License.
