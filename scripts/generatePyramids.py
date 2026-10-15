#!/usr/bin/env python3
"""
Generate a foldable paper template of the web Mercator / XYZ tile pyramid
(see src/lib/tiles.js) as an SVG for import into Illustrator.

THE PHYSICAL ANALOGY
---------------------
At zoom z, the world is a grid of n = 2^z tiles per axis; zoom z+1 quarters
every tile into a 2x2 block (tiles.js: `ancestorChain`). Folding a strip of
paper in half halves its panel count the same way a zoom step halves tile
size per axis — so one square, accordion-folded along each axis down to a
2^N x 2^N grid, physically collapses through every intermediate zoom level
z = 0..N on the way from "whole sheet" to "one finest tile".

THE FORMULA
-----------
Divide an axis of length S into 2^N equal panels. The fold creases are the
2^N - 1 interior grid lines, indexed k = 1 .. 2^N-1 at position x_k = k*S/2^N.

Crease k is shared by every zoom level coarser than the one that first
introduces it. The level that *first* introduces crease k is:

    level(k) = N - v2(k)

where v2(k) is the 2-adic valuation of k (its trailing-zero count in
binary) — i.e. the largest power of two dividing k. Equivalently: level(k)
is the smallest z for which k is a multiple of 2^(N-z).

This falls directly out of the same halving tiles.js uses for tile
indices: the single center crease (k = 2^(N-1)) is level 1 (the first
fold); the quarter-point creases are level 2; and so on down to the odd-k
creases, which only appear at the finest level N. There are exactly
2^z - 1 creases at level <= z on each axis, matching the 2^z tiles-per-axis
count at that zoom.

Fold direction (mountain/valley) just needs to alternate so the stack
accordions flat: valley if k is odd, mountain if k is even.

Each finest-grid cell is labeled with its quadkey — the same base-4,
one-digit-per-zoom-level encoding as `quadkey()` in tiles.js — so the
physical template and the web app describe the same tile with the same
string.
"""

import argparse
import os

# ---------------------------------------------------------------------------
# Tile-pyramid math (ported 1:1 from src/lib/tiles.js — see that file for the
# lon/lat-facing half of this; this script only needs the abstract grid).
# ---------------------------------------------------------------------------


def trailing_zeros(k):
	"""v2(k): the number of trailing zero bits in k (k > 0)."""
	return (k & -k).bit_length() - 1


def fold_level(k, max_zoom):
	"""The zoom level that first introduces crease index k (1 <= k <= 2**max_zoom - 1)."""
	return max_zoom - trailing_zeros(k)


def quadkey(x, y, z):
	"""Same algorithm as quadkey() in tiles.js: one base-4 digit per zoom level."""
	digits = []
	for i in range(z, 0, -1):
		mask = 1 << (i - 1)
		digit = 0
		if x & mask:
			digit += 1
		if y & mask:
			digit += 2
		digits.append(str(digit))
	return "".join(digits)


# ---------------------------------------------------------------------------
# SVG helpers (plain string templates — no dependency, no untrusted input)
# ---------------------------------------------------------------------------

PT = 1 / 72  # 1 point, expressed in inches (our SVG user unit)

FOLD_WEIGHT_MAX_PT = 2.4  # line weight at z = 1 (coarsest fold)
FOLD_WEIGHT_MIN_PT = 0.45  # line weight at z = max_zoom (finest fold)

VALLEY_COLOR = "#1D4F91"  # matches the web app's accent blue
MOUNTAIN_COLOR = "#B5471B"

VALLEY_DASH = "0.16,0.08"
MOUNTAIN_DASH = "0.2,0.05,0.04,0.05"


def lerp(a, b, t):
	return a + (b - a) * t


def fold_weight_pt(z, max_zoom):
	if max_zoom <= 1:
		return FOLD_WEIGHT_MAX_PT
	t = (z - 1) / (max_zoom - 1)
	return lerp(FOLD_WEIGHT_MAX_PT, FOLD_WEIGHT_MIN_PT, t)


def svg_line(x1, y1, x2, y2, stroke, width_pt, dash=None, extra=""):
	dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
	return (
		f'<line x1="{x1:.4f}" y1="{y1:.4f}" x2="{x2:.4f}" y2="{y2:.4f}" '
		f'stroke="{stroke}" stroke-width="{width_pt * PT:.4f}"{dash_attr} '
		f'stroke-linecap="round" {extra}/>'
	)


def svg_rect(x, y, w, h, stroke="#000", width_pt=1.2, fill="none"):
	return (
		f'<rect x="{x:.4f}" y="{y:.4f}" width="{w:.4f}" height="{h:.4f}" '
		f'fill="{fill}" stroke="{stroke}" stroke-width="{width_pt * PT:.4f}"/>'
	)


def svg_text(x, y, text, size_pt, anchor="middle", color="#000", family="Helvetica, Arial, sans-serif", weight="normal"):
	return (
		f'<text x="{x:.4f}" y="{y:.4f}" font-family="{family}" font-size="{size_pt * PT:.4f}" '
		f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{text}</text>'
	)


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------


def build_grid_svg(max_zoom, sheet_w, sheet_h, margin, labels):
	"""The foldable grid itself — fills the full sheet (centered on whichever
	axis has slack), no reserved legend space. See build_appendix_svg() for
	the instructions/formula/legend, which live in a separate file."""
	n = 2**max_zoom
	square_side = min(sheet_w, sheet_h) - 2 * margin
	grid_x0 = (sheet_w - square_side) / 2
	grid_y0 = (sheet_h - square_side) / 2
	grid_x1, grid_y1 = grid_x0 + square_side, grid_y0 + square_side
	cell = square_side / n

	parts = []
	parts.append(
		f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_w}in" height="{sheet_h}in" '
		f'viewBox="0 0 {sheet_w} {sheet_h}">'
	)
	parts.append(f'<rect x="0" y="0" width="{sheet_w}" height="{sheet_h}" fill="white"/>')

	# sheet cut line
	parts.append(svg_rect(0.05, 0.05, sheet_w - 0.1, sheet_h - 0.1, stroke="#000", width_pt=0.75))

	# --- grid: z0 boundary (the square itself) ---
	parts.append('<g id="z0-boundary">')
	parts.append(svg_rect(grid_x0, grid_y0, square_side, square_side, stroke="#000", width_pt=1.6))
	parts.append("</g>")

	# --- fold creases, grouped by direction so Illustrator imports them as
	#     separate, independently-toggleable sublayers ---
	valley_lines = []
	mountain_lines = []
	level_first_pos = {}  # z -> (axis, position) for the margin tick labels

	for k in range(1, n):
		z = fold_level(k, max_zoom)
		w = fold_weight_pt(z, max_zoom)
		is_valley = k % 2 == 1
		color = VALLEY_COLOR if is_valley else MOUNTAIN_COLOR
		dash = VALLEY_DASH if is_valley else MOUNTAIN_DASH

		# vertical crease (divides columns) at x = grid_x0 + k*cell
		x = grid_x0 + k * cell
		line = svg_line(x, grid_y0, x, grid_y1, color, w, dash)
		(valley_lines if is_valley else mountain_lines).append(line)
		level_first_pos.setdefault(("x", z), x)

		# horizontal crease (divides rows) at y = grid_y0 + k*cell
		y = grid_y0 + k * cell
		line = svg_line(grid_x0, y, grid_x1, y, color, w, dash)
		(valley_lines if is_valley else mountain_lines).append(line)
		level_first_pos.setdefault(("y", z), y)

	parts.append('<g id="valley-folds">')
	parts.extend(valley_lines)
	parts.append("</g>")
	parts.append('<g id="mountain-folds">')
	parts.extend(mountain_lines)
	parts.append("</g>")

	# --- zoom-level tick labels along the top/left margins ---
	parts.append('<g id="zoom-level-ticks">')
	for z in range(1, max_zoom + 1):
		x = level_first_pos.get(("x", z))
		if x is not None:
			parts.append(svg_line(x, grid_y0 - 0.12, x, grid_y0 - 0.02, "#000", 0.6))
			parts.append(svg_text(x, grid_y0 - 0.16, f"z{z}", 6.5, anchor="middle"))
		y = level_first_pos.get(("y", z))
		if y is not None:
			parts.append(svg_line(grid_x0 - 0.12, y, grid_x0 - 0.02, y, "#000", 0.6))
			parts.append(svg_text(grid_x0 - 0.16, y + 0.025, f"z{z}", 6.5, anchor="end"))
	parts.append("</g>")

	# --- quadkey labels on the finest cells ---
	if labels:
		font_pt = max(4.0, min(7.0, cell * 0.4 * 72))
		parts.append('<g id="quadkey-labels" fill="#888">')
		for row in range(n):
			for col in range(n):
				cx = grid_x0 + (col + 0.5) * cell
				cy = grid_y0 + (row + 0.5) * cell + font_pt * PT * 0.32
				qk = quadkey(col, row, max_zoom)
				parts.append(svg_text(cx, cy, qk, font_pt, anchor="middle", color="#888"))
		parts.append("</g>")

	parts.append("</svg>")
	return "\n".join(parts)


def build_appendix_svg(max_zoom, cell, page_w, page_h, margin=0.75):
	"""The instructions/formula/legend/preview-diagrams, as their own page —
	kept separate from the grid file so the grid can fill the full sheet."""
	n = 2**max_zoom
	x0 = margin
	parts = []
	parts.append(
		f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_w}in" height="{page_h}in" '
		f'viewBox="0 0 {page_w} {page_h}">'
	)
	parts.append(f'<rect x="0" y="0" width="{page_w}" height="{page_h}" fill="white"/>')
	parts.append('<g id="appendix" font-family="Helvetica, Arial, sans-serif">')

	ly = margin
	parts.append(svg_text(x0, ly + 0.26, "Web Mercator Tile Pyramid — Fold Template", 15, anchor="start", weight="bold"))
	ly += 0.5
	parts.append(
		svg_text(
			x0,
			ly + 0.2,
			f"z0 → z{max_zoom}  ·  {n}×{n} finest grid  ·  cell {cell:.3f}in  ·  {n - 1} creases per axis",
			9,
			anchor="start",
		)
	)
	ly += 0.35

	# line-style key
	key_y = ly + 0.3
	parts.append(svg_line(x0, key_y, x0 + 0.6, key_y, VALLEY_COLOR, FOLD_WEIGHT_MAX_PT, VALLEY_DASH))
	parts.append(svg_text(x0 + 0.7, key_y + 0.03, "valley fold (odd k)", 8, anchor="start"))
	parts.append(svg_line(x0 + 2.6, key_y, x0 + 3.2, key_y, MOUNTAIN_COLOR, FOLD_WEIGHT_MAX_PT, MOUNTAIN_DASH))
	parts.append(svg_text(x0 + 3.3, key_y + 0.03, "mountain fold (even k)", 8, anchor="start"))
	ly = key_y + 0.3
	parts.append(
		svg_text(
			x0,
			ly + 0.2,
			"line weight = fold level: bold = z1 (center crease) … thin = "
			f"z{max_zoom} (finest crease)  —  level(k) = {max_zoom} − v₂(k)",
			8,
			anchor="start",
		)
	)
	ly += 0.4
	for line in (
		"Fold 1: accordion-fold every vertical crease (alternating valley/mountain) to collapse columns.",
		"Fold 2: accordion-fold every horizontal crease the same way to collapse rows.",
		"Partially unfold either axis to reveal any intermediate zoom level z — the grid's z-ticks mark which crease belongs to which level.",
	):
		parts.append(svg_text(x0, ly + 0.2, line, 8, anchor="start"))
		ly += 0.26
	ly += 0.14
	parts.append(
		svg_text(
			x0,
			ly + 0.2,
			f"Cell labels are quadkeys (tiles.js quadkey(x, y, z) at z = {max_zoom}) — same tile ID the web app uses.",
			8,
			anchor="start",
			color="#666",
		)
	)
	ly += 0.5

	# --- mini reference diagrams: z0..min(4, max_zoom) nested grids ---
	preview_count = min(4, max_zoom) + 1
	preview_size = 0.95
	preview_gap = 0.35
	preview_y = ly + 0.3
	for i in range(preview_count):
		z = i
		px = x0 + i * (preview_size + preview_gap)
		py = preview_y
		parts.append(svg_rect(px, py, preview_size, preview_size, stroke="#333", width_pt=0.8))
		m = 2**z
		step = preview_size / m
		for j in range(1, m):
			parts.append(svg_line(px + j * step, py, px + j * step, py + preview_size, "#999", 0.4))
			parts.append(svg_line(px, py + j * step, px + preview_size, py + j * step, "#999", 0.4))
		parts.append(svg_text(px + preview_size / 2, py + preview_size + 0.18, f"z{z}  ({m}×{m})", 7, anchor="middle"))

	parts.append("</g>")
	parts.append("</svg>")
	return "\n".join(parts)


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--max-zoom", type=int, default=4, help="finest zoom level depicted, z0..zN (default: 4)")
	parser.add_argument("--sheet-width", type=float, default=12.0, help="grid sheet width in inches (default: 12)")
	parser.add_argument("--sheet-height", type=float, default=18.0, help="grid sheet height in inches (default: 18)")
	parser.add_argument(
		"--margin",
		type=float,
		default=0.0,
		help="grid margin in inches (default: 0 — fills the sheet edge to edge on the limiting axis; scale for print margins yourself)",
	)
	parser.add_argument("--no-labels", action="store_true", help="omit per-cell quadkey labels")
	parser.add_argument(
		"--out",
		default=os.path.join(os.path.dirname(__file__), "tile_pyramid_fold_template.svg"),
		help="output path for the fold grid SVG",
	)
	parser.add_argument("--appendix-width", type=float, default=8.5, help="appendix page width in inches (default: 8.5)")
	parser.add_argument("--appendix-height", type=float, default=11.0, help="appendix page height in inches (default: 11)")
	parser.add_argument(
		"--out-appendix",
		default=os.path.join(os.path.dirname(__file__), "tile_pyramid_fold_template_appendix.svg"),
		help="output path for the instructions/legend appendix SVG",
	)
	args = parser.parse_args()

	if args.max_zoom < 1:
		parser.error("--max-zoom must be >= 1")

	square_side = min(args.sheet_width, args.sheet_height) - 2 * args.margin
	cell = square_side / (2**args.max_zoom)

	if cell < 0.2:
		print(
			f"warning: finest cell is {cell:.3f}in at z{args.max_zoom} — likely too small to "
			"crease/label cleanly by hand. Consider a lower --max-zoom.",
		)

	grid_svg = build_grid_svg(args.max_zoom, args.sheet_width, args.sheet_height, args.margin, labels=not args.no_labels)
	with open(args.out, "w") as f:
		f.write(grid_svg)

	appendix_svg = build_appendix_svg(args.max_zoom, cell, args.appendix_width, args.appendix_height)
	with open(args.out_appendix, "w") as f:
		f.write(appendix_svg)

	n = 2**args.max_zoom
	print(f"wrote {args.out}")
	print(f"wrote {args.out_appendix}")
	print(f"z0..z{args.max_zoom}  ·  finest grid {n}x{n}  ·  cell {cell:.3f}in  ·  {n - 1} creases/axis")


if __name__ == "__main__":
	main()
