#!/usr/bin/env python3
"""Split keymap-drawer/charybdis.svg into one standalone SVG per layer.

The upstream keymap-drawer action only emits the combined charybdis.svg (all layers
stacked vertically). The README embeds the per-layer files produced here so each
layer can sit cleanly in its own section.

Every layer is written with a viewBox taken from the original drawing's own
inter-layer pitch, so the output matches the upstream layout exactly instead of
guessing a bounding box. Rotated thumb keys and the labels beneath them are the
tallest elements; using the layer pitch leaves room for them without clipping.

Usage:  python3 tools/split_keymap_svg.py [keymap-drawer/charybdis.svg]
"""

from __future__ import annotations

import math
import re
import sys
import xml.dom.minidom
from pathlib import Path

LAYER_OPEN = re.compile(r'<g transform="translate\(40, \d+\)" class="layer-(\w+)">$')
G_OPEN = re.compile(r"<g(?=[ >])")
G_CLOSE = re.compile(r"</g>")
ROTATED = re.compile(r"translate\(-?[\d.]+, (-?[\d.]+)\) rotate\(")
KEY_SIDE = 52  # drawn key box is 52x52, centred on the key position

# Room above the layer for its "<LAYER>:" caption text.
TOP_PAD = 22


def find_matching_close(lines: list[str], start: int) -> int:
    """Return the index of the `</g>` that closes the group opened at `start`."""
    depth = 1
    i = start + 1
    while i < len(lines) and depth > 0:
        depth += len(G_OPEN.findall(lines[i])) - len(G_CLOSE.findall(lines[i]))
        i += 1
    return i - 1


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    svg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "keymap-drawer" / "charybdis.svg"
    if not svg_path.is_file():
        print(f"error: {svg_path} not found", file=sys.stderr)
        return 1

    lines = svg_path.read_text(encoding="utf-8").split("\n")

    # Shared assets: the outer <svg> tag is dropped because each output supplies
    # its own, but the glyph <defs> and the <style> block are reused verbatim.
    defs_end = next(i for i, l in enumerate(lines) if "</defs>" in l)
    style_start = next(i for i, l in enumerate(lines) if "<style>" in l)
    style_end = next(i for i, l in enumerate(lines) if "</style>" in l)
    glyphs = lines[1 : defs_end + 1]
    style = lines[style_start : style_end + 1]

    # Layer groups, in document order, with their vertical offset.
    layers = []
    for i, line in enumerate(lines):
        m = LAYER_OPEN.match(line)
        if m:
            offset = int(re.search(r"translate\(40, (\d+)\)", line).group(1))
            layers.append((i, offset, m.group(1)))
    if not layers:
        print("error: no layer groups found", file=sys.stderr)
        return 1

    width = int(re.search(r'width="(\d+)"', lines[0]).group(1))
    total_h = int(re.search(r'height="(\d+)"', lines[0]).group(1))
    out_dir = svg_path.parent / "layers"
    out_dir.mkdir(parents=True, exist_ok=True)

    half_diagonal = KEY_SIDE / 2 * math.sqrt(2)
    failures = 0

    for n, (start, offset, name) in enumerate(layers):
        end = find_matching_close(lines, start)
        seg = list(lines[start : end + 1])
        seg[0] = re.sub(r"translate\(40, \d+\)", "translate(40, 0)", seg[0])
        body = "\n".join(seg)

        ys = [float(m.group(1)) for m in re.finditer(r"translate\(\d+, (-?[\d.]+)\)", body)]
        rotated = [float(m.group(1)) + half_diagonal for m in ROTATED.finditer(body)]
        bottom = max(ys + rotated + [0.0])

        # Height = distance to the next layer (or to the bottom of the drawing),
        # so each output covers exactly the band the upstream layout allotted it.
        if n + 1 < len(layers):
            height = layers[n + 1][1] - offset
        else:
            height = total_h - offset

        doc = [
            f'<svg width="{width}" height="{height + TOP_PAD}" viewBox="0 -{TOP_PAD} {width} {height + TOP_PAD}" '
            'class="keymap" xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">',
            *glyphs,
            *style,
            *seg,
            "</svg>",
        ]
        dest = out_dir / f"{name}.svg"
        dest.write_text("\n".join(doc), encoding="utf-8")

        try:
            xml.dom.minidom.parse(str(dest))
        except Exception as exc:  # noqa: BLE001 - report, do not abort the batch
            print(f"  {name}.svg  INVALID XML: {exc}", file=sys.stderr)
            failures += 1
            continue
        print(f"  {name}.svg  {height}px (content bottom {bottom:.0f})")

    if failures:
        print(f"error: {failures} layer file(s) failed XML validation", file=sys.stderr)
        return 1
    print(f"wrote {len(layers)} layer file(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
