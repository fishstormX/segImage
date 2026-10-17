"""Command-line cutout — same pipeline as the FastAPI service.

Examples
  segimage photo.jpg -o sticker.png
  segimage photo.jpg -o out.png --method rembg --model u2netp
  segimage photo.jpg -o out.png --method grabcut --rect 0.1,0.1,0.8,0.8
  segimage desk.jpg -o subjects/ --method multi
  cat photo.jpg | segimage - -o - > sticker.png
  segimage ./photos/ -o ./stickers/ --method rembg
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from app.pipeline import METHODS, SegError, run_segment
from app.rembg_seg import DEFAULT_MODEL, MODELS
from app.version import __version__

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _truthy_flag(v: Optional[str], default: bool) -> bool:
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


def _parse_points(s: Optional[str]) -> Any:
    if not s:
        return None
    data = json.loads(s)
    if isinstance(data, list) and data and isinstance(data[0], (list, tuple)):
        # [[x,y,label], ...] → [{"x","y","label"}]
        return [{"x": float(p[0]), "y": float(p[1]), "label": int(p[2]) if len(p) > 2 else 1} for p in data]
    return data


def _parse_rect(s: Optional[str]) -> Any:
    if not s:
        return None
    if s.strip().startswith("["):
        return json.loads(s)
    parts = [float(x) for x in re.split(r"[,\s]+", s.strip()) if x]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("rect must be x,y,w,h (normalized 0..1) or a JSON array")
    return parts


def _read_input(path: str) -> bytes:
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        data = Path(path).read_bytes()
    if not data:
        raise SegError(400, "EMPTY_FILE", "Empty file")
    return data


def _write_bytes(path: str, data: bytes) -> None:
    if path == "-":
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)


def _default_out(inp: str, method: str) -> str:
    if inp == "-":
        return "-"
    p = Path(inp)
    if method == "multi":
        return str(p.with_name(p.stem + "_subjects"))
    return str(p.with_name(p.stem + "_sticker.png"))


def _save_single(result: dict, out: str, *, also_mask: Optional[str], quiet: bool) -> None:
    png = base64.b64decode(result["result_png_b64"])
    _write_bytes(out, png)
    if also_mask and result.get("mask_png_b64"):
        _write_bytes(also_mask, base64.b64decode(result["mask_png_b64"]))
    if not quiet and out != "-":
        engine = result.get("method", "?")
        print(f"wrote {out}  ({engine}, {result.get('width')}x{result.get('height')})", file=sys.stderr)


def _save_multi(result: dict, out: str, quiet: bool) -> None:
    objs = result.get("objects") or []
    if out == "-":
        raise SegError(400, "BAD_OUTPUT", "multi method cannot write to stdout; pass -o DIR")
    dest = Path(out)
    # If user passed foo.png by mistake, treat as directory foo/
    if dest.suffix.lower() in IMAGE_EXTS:
        dest = dest.with_suffix("")
    dest.mkdir(parents=True, exist_ok=True)
    for i, o in enumerate(objs, 1):
        label = re.sub(r"[^\w\-]+", "_", str(o.get("label") or f"subject{i}")).strip("_") or f"subject{i}"
        path = dest / f"{i:02d}_{label}.png"
        path.write_bytes(base64.b64decode(o["png_b64"]))
        if not quiet:
            print(f"wrote {path}", file=sys.stderr)
    if not quiet:
        print(f"{len(objs)} subject(s) → {dest}/  ({result.get('method', 'multi')})", file=sys.stderr)


def _iter_inputs(path: str) -> Iterable[str]:
    if path == "-":
        yield "-"
        return
    p = Path(path)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
        if not files:
            raise SegError(400, "EMPTY_FILE", f"No images in directory: {path}")
        for f in files:
            yield str(f)
        return
    if not p.is_file():
        raise SegError(400, "EMPTY_FILE", f"Not a file or directory: {path}")
    yield path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="segimage",
        description=(
            "segImage CLI — local background removal / sticker cutout "
            "(same engine as the REST API: rembg, GrabCut, AI auto-box, multi). "
            "MediaPipe is browser-only and not available here."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  segimage photo.jpg -o sticker.png\n"
            "  segimage photo.jpg -o out.png --method rembg --model u2netp --no-complete\n"
            "  segimage photo.jpg -o out.png --method grabcut --rect 0.1,0.1,0.8,0.8\n"
            "  segimage desk.jpg -o subjects/ --method multi\n"
            "  cat photo.jpg | segimage - -o - > sticker.png\n"
            "  segimage ./photos/ -o ./stickers/\n"
            "\n"
            f"models: {', '.join(MODELS)} (default {DEFAULT_MODEL})\n"
            "The public demo API is for testing only; for commercial use contact "
            "stormnetwork@163.com (海口龙华区妙妙鱼传媒工作室)."
        ),
    )
    p.add_argument("input", help="image file, directory of images, or '-' for stdin")
    p.add_argument("-o", "--output", help="output PNG path, directory (batch/multi), or '-' for stdout")
    p.add_argument(
        "-m",
        "--method",
        choices=METHODS,
        default="rembg",
        help="cutout method (default: rembg). 'ai' and 'multi' need OPENROUTER_API_KEY for best results",
    )
    p.add_argument(
        "--model",
        dest="rembg_model",
        choices=list(MODELS),
        default=None,
        help=f"rembg model (default: {DEFAULT_MODEL})",
    )
    p.add_argument("--smooth", type=int, default=3, help="edge smoothing 0–10 (default: 3)")
    p.add_argument("--no-despeckle", action="store_true", help="disable small-island / hole cleanup")
    p.add_argument("--no-complete", action="store_true", help="disable smart subject completion")
    p.add_argument("--no-border", action="store_true", help="disable white sticker outline")
    p.add_argument(
        "--points",
        help='GrabCut seeds JSON, e.g. \'[{"x":0.5,"y":0.5,"label":1}]\' or [[0.5,0.5,1]]',
    )
    p.add_argument("--rect", type=_parse_rect, help="GrabCut rect x,y,w,h (normalized 0..1)")
    p.add_argument("--mask", help="also write the alpha mask PNG to this path (single-subject only)")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress progress on stderr")
    p.add_argument("-V", "--version", action="version", version=f"segimage {__version__}")
    return p


def process_one(
    inp: str,
    out: str,
    *,
    method: str,
    rembg_model: Optional[str],
    smooth: int,
    despeckle: bool,
    complete: bool,
    white_border: bool,
    points: Any,
    rect: Any,
    mask_path: Optional[str],
    quiet: bool,
) -> None:
    raw = _read_input(inp)
    t0 = time.time()
    result = run_segment(
        raw,
        method,
        white_border=white_border,
        smooth=smooth,
        despeckle=despeckle,
        complete=complete,
        rembg_model=rembg_model,
        points=points,
        rect=rect,
    )
    raw = None
    elapsed = int((time.time() - t0) * 1000)
    if method == "multi":
        _save_multi(result, out, quiet)
    else:
        _save_single(result, out, also_mask=mask_path, quiet=quiet)
    if not quiet:
        print(f"{elapsed} ms", file=sys.stderr)


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        points = _parse_points(args.points)
    except json.JSONDecodeError as e:
        print(f"error: --points is not valid JSON: {e}", file=sys.stderr)
        return 2

    inputs = list(_iter_inputs(args.input))
    batch = len(inputs) > 1 or (args.input != "-" and Path(args.input).is_dir())

    try:
        if batch:
            out_root = Path(args.output) if args.output else Path(args.input) / "stickers"
            if str(out_root) == "-":
                raise SegError(400, "BAD_OUTPUT", "batch mode cannot write to stdout; pass -o DIR")
            out_root.mkdir(parents=True, exist_ok=True)
            for inp in inputs:
                stem = Path(inp).stem
                if args.method == "multi":
                    out = str(out_root / stem)
                else:
                    out = str(out_root / f"{stem}_sticker.png")
                mask = str(out_root / f"{stem}_mask.png") if args.mask else None
                if not args.quiet:
                    print(f"→ {inp}", file=sys.stderr)
                process_one(
                    inp,
                    out,
                    method=args.method,
                    rembg_model=args.rembg_model,
                    smooth=args.smooth,
                    despeckle=not args.no_despeckle,
                    complete=not args.no_complete,
                    white_border=not args.no_border,
                    points=points,
                    rect=args.rect,
                    mask_path=mask,
                    quiet=args.quiet,
                )
        else:
            inp = inputs[0]
            out = args.output or _default_out(inp, args.method)
            process_one(
                inp,
                out,
                method=args.method,
                rembg_model=args.rembg_model,
                smooth=args.smooth,
                despeckle=not args.no_despeckle,
                complete=not args.no_complete,
                white_border=not args.no_border,
                points=points,
                rect=args.rect,
                mask_path=args.mask,
                quiet=args.quiet,
            )
    except SegError as e:
        print(f"error: {e.code}: {e.message}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
