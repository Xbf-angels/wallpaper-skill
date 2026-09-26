#!/usr/bin/env python3
"""Read-only image audit. Exit 0=technical checks pass, 1=issue, 2=bad arguments.

Requires Pillow. Does not resize, retouch, compose, or grade visual identity/style.
Optional report is created exclusively; existing files are never overwritten.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def inspect_image(path, target=None):
    from PIL import Image

    item = {"path": str(path.resolve()), "issues": []}
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            orientation = image.getexif().get(274, 1)
            item.update(format=image.format, mode=image.mode, width=width,
                        height=height, aspect_height_over_width=round(height / width, 6),
                        exif_orientation=orientation)
            if "A" in image.getbands():
                item["alpha_range"] = list(image.getchannel("A").getextrema())
                if item["alpha_range"][0] < 255:
                    item["issues"].append("final_wallpaper_contains_transparency")
            elif "transparency" in image.info:
                alpha = image.convert("RGBA").getchannel("A").getextrema()
                item["alpha_range"] = list(alpha)
                if alpha[0] < 255:
                    item["issues"].append("final_wallpaper_contains_transparency")
            if orientation != 1:
                item["issues"].append("exif_orientation_requires_review")
            if height <= width:
                item["issues"].append("not_portrait")
            if getattr(image, "n_frames", 1) > 1:
                item["issues"].append("multiple_frames_require_review")
            if target:
                item["target_width"], item["target_height"] = target
                item["exact_dimensions_match"] = (width, height) == target
                if not item["exact_dimensions_match"]:
                    item["issues"].append("target_dimensions_mismatch")
        item["bytes"] = path.stat().st_size
        with path.open("rb") as handle:
            item["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
    except Exception as exc:
        item["issues"].append("read_or_decode_error")
        item["error"] = f"{type(exc).__name__}: {exc}"
    item["technical_status"] = "pass" if not item["issues"] else "needs_review"
    return item


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--target-width", type=int)
    parser.add_argument("--target-height", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if (args.target_width is None) != (args.target_height is None):
        parser.error("target-width and target-height must be supplied together")
    if args.target_width is not None and min(args.target_width, args.target_height) <= 0:
        parser.error("target dimensions must be positive")
    if args.report:
        if args.report.resolve() in {p.resolve() for p in args.images}:
            parser.error("report cannot overwrite an input image")
        if args.report.exists():
            parser.error("report already exists; choose a new versioned path")
        if not args.report.parent.is_dir():
            parser.error("report parent directory does not exist")
    try:
        import PIL  # noqa: F401
    except ImportError:
        parser.error("Pillow is unavailable; use another image metadata tool or configure Pillow")
    target = (args.target_width, args.target_height) if args.target_width is not None else None
    results = [inspect_image(path, target) for path in args.images]
    report = {"visual_identity_and_style": "not_assessed", "images": results,
              "technical_status": "pass" if all(r["technical_status"] == "pass" for r in results) else "needs_review"}
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        try:
            with args.report.open("x", encoding="utf-8") as handle:
                handle.write(content)
        except OSError as exc:
            parser.error(f"cannot create report: {exc}")
    # Escape non-ASCII in stdout for Windows terminals with legacy encodings.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["technical_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
