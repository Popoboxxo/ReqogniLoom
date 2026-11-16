#!/usr/bin/env python3
"""Generate the PWA launcher icons from the design tokens (plan M1, REQ-213).

The PNGs are committed because the Docker build serves ``frontend/public``
verbatim; rasterising at build time would add a native image dependency to the
image. Re-run this script after changing the source colours:

    python3 frontend/scripts/generate-icons.py

Colours are parsed from ``src/styles/tokens.css`` so the icon cannot silently
drift away from the theme. The SVG master in ``public/icons/icon.svg`` uses
the same token names.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "src" / "styles" / "tokens.css"
OUT = ROOT / "public" / "icons"

SCALE = 4  # supersampling for smooth letters and rounded corners
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def token(name: str) -> str:
    match = re.search(rf"--{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{6}})\s*;", TOKENS.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"token --{name} not found in {TOKENS}")
    return match.group(1)


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise SystemExit("no bold TTF font found; install fonts-liberation or fonts-dejavu")


def render(size: int, *, maskable: bool) -> Image.Image:
    """Draw one icon. Maskable variants stay full-bleed with a 40% safe zone."""
    px = size * SCALE
    background = token("palette-navy-900")
    foreground = token("palette-white")
    accent = token("palette-indigo-600")
    image = Image.new("RGB", (px, px), background)
    draw = ImageDraw.Draw(image)

    # The monogram occupies 62% of the canvas; maskable keeps it inside the
    # 80% central safe zone (40% radius) so any platform mask can crop it.
    content = 0.62 if not maskable else 0.58
    text_size = int(px * content * 0.62)
    face = font(text_size)
    text = "RL"
    box = draw.textbbox((0, 0), text, font=face, stroke_width=0)
    text_w, text_h = box[2] - box[0], box[3] - box[1]
    cx, cy = px / 2, px / 2 - px * 0.03
    draw.text(
        (cx - text_w / 2 - box[0], cy - text_h / 2 - box[1]),
        text,
        font=face,
        fill=foreground,
    )

    # Small brand underline; decorative, not required for recognition.
    bar_w = int(px * (0.26 if maskable else 0.3))
    bar_h = max(SCALE, int(px * 0.022))
    bar_y = int(cy + text_h / 2 + px * 0.035)
    draw.rounded_rectangle(
        ((cx - bar_w / 2, bar_y), (cx + bar_w / 2, bar_y + bar_h)),
        radius=bar_h // 2,
        fill=accent,
    )

    if not maskable:
        # Launcher icon: rounded square with transparent corners. Apple
        # touch icons are saved as RGB below (iOS paints corners itself).
        mask = Image.new("L", (px, px), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, px - 1, px - 1), radius=int(px * 0.22), fill=255
        )
        opaque = Image.new("RGB", (px, px), background)
        image = Image.composite(image, opaque, mask)
        return image.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")

    return image.resize((size, size), Image.Resampling.LANCZOS).convert("RGB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = (
        ("icon-192.png", 192, False, "RGBA"),
        ("icon-512.png", 512, False, "RGBA"),
        ("maskable-512.png", 512, True, "RGB"),
        ("apple-touch-180.png", 180, False, "RGB"),
    )
    for name, size, maskable, mode in targets:
        image = render(size, maskable=maskable)
        if mode == "RGB":
            # adam7=False keeps the bytes deterministic across Pillow builds.
            image = image.convert("RGB")
        image.save(OUT / name, optimize=False, compress_level=9)
        print(f"wrote {OUT / name} ({size}x{size}, {mode})")


if __name__ == "__main__":
    main()
