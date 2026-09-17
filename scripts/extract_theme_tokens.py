"""One-off helper: parses frontend/src/styles/tokens.css and prints the
dark_tokens/light_tokens dicts for the seed migration in
backend/admin_ops/migrations/0004_theme_palette.py.

Not part of the shipped app -- run once, paste the output into the
migration, keep for future re-extraction if tokens.css changes before the
next re-seed.

The script applies the same cascade a browser applies: every theme block
(``:root[data-theme="x"]``) overlays the bare semantic ``:root`` block, so
a theme that only overrides a handful of properties still resolves to a
complete token map. The output is cross-checked against admin_ops'
CANONICAL_COLOR_TOKEN_KEYS (77 keys) and exits non-zero on any mismatch,
so an incomplete extraction can never silently reach the migration.

Usage:
    python scripts/extract_theme_tokens.py > /tmp/theme_seed_data.txt
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS_CSS = ROOT / "frontend/src/styles/tokens.css"

# Keep in sync with backend/admin_ops/models.py::CANONICAL_COLOR_TOKEN_KEYS.
_canonical_source = ROOT / "backend/admin_ops/models.py"


def _load_canonical_keys() -> frozenset[str]:
    text = _canonical_source.read_text(encoding="utf-8")
    match = re.search(r"CANONICAL_COLOR_TOKEN_KEYS = frozenset\(\{(.*?)\}\)", text, re.S)
    if not match:
        raise SystemExit("Could not locate CANONICAL_COLOR_TOKEN_KEYS in models.py")
    return frozenset(re.findall(r'"(--color-[\w-]+)"', match.group(1)))


_DECL_RE = re.compile(r"^\s*(--[\w-]+)\s*:\s*([^;]+);", re.MULTILINE)
_BLOCK_RE = re.compile(r'^:root(\[data-theme="([a-z]+)"\])?\s*\{', re.MULTILINE)


def _block_body(text: str, start: int) -> str:
    """Return the body of the ``{...}`` block opening at *start*."""
    depth = 1
    i = start
    while depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start : i - 1]


def extract_blocks(text: str) -> dict[str, dict[str, str]]:
    """Parse all top-level ``:root`` blocks into ``{block_id: declarations}``."""
    blocks: dict[str, dict[str, str]] = {}
    for m in _BLOCK_RE.finditer(text):
        theme_id = m.group(2) or "root"
        body = _block_body(text, m.end())
        decls = {d.group(1): d.group(2).strip() for d in _DECL_RE.finditer(body)}
        # Merge multiple bare `:root { }` blocks in declaration order.
        blocks.setdefault(theme_id, {}).update(decls)
    return blocks


def resolve_theme(blocks: dict[str, dict[str, str]], theme_id: str | None) -> dict[str, str]:
    """Apply the CSS cascade: named block overlays ALL bare ``:root`` blocks."""
    resolved: dict[str, str] = {}
    for key, decls in blocks.items():
        if key == "root" or key == theme_id:
            resolved.update(decls)
    return resolved


def main() -> None:
    canonical = _load_canonical_keys()
    text = TOKENS_CSS.read_text(encoding="utf-8")
    blocks = extract_blocks(text)

    themes = {
        "DEFAULT_DARK": None,
        "DEFAULT_LIGHT": "light",
        "BAUHAUS_DARK": "bauhaus",
        "NORDIC_DARK": "nordic",
        "SEPIA_DARK": "sepia",
    }
    ok = True
    for name, theme_id in themes.items():
        resolved = {
            k: v for k, v in resolve_theme(blocks, theme_id).items()
            if k.startswith("--color-")
        }
        keys = set(resolved)
        missing = sorted(canonical - keys)
        print(f"{name} = {json.dumps({k: resolved[k] for k in sorted(resolved)}, indent=2)}")
        print()
        if missing:
            ok = False
            print(f"# !! {name}: missing {len(missing)} canonical keys: {missing}", file=sys.stderr)

    if not ok:
        raise SystemExit("Extraction incomplete — fix block markers and re-run.")
    print(f"# All {len(canonical)} canonical keys present in every extracted theme.", file=sys.stderr)


if __name__ == "__main__":
    main()
