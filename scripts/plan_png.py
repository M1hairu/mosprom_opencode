#!/usr/bin/env python3
"""PNG of the hall 219 zoning: pochta render + visitor route overlay.

    python3 scripts/plan_png.py              # both variants -> concept/img/plan-219*-zoned.png
    python3 scripts/plan_png.py --validate   # pochta validator on both zoning files

The base picture is the pochta planner render (PlanDocument v1). The pochta repo is used
read-only. Path: env POCHTA_DIR, default — the sibling directory
../tsifrovoy-dvoynik-otdeleniya-pochty-rossii next to the main checkout of this repo. Pinned commit:
f15ba315efc069aec2a0a18c9f68e4829ff61cb7. Another commit gives a warning, not an error.
Tools: <pochta>/node_modules/.bin/tsx and rsvg-convert. If one is missing, the script
exits with code 2 and names it. `make check` does not call this script.

The overlay is drawn here: the route line (scripts/plan_zones.py route_line: it keeps
0.3 m from stands, columns and walls), the step numbers, the confirmed exits (green),
the candidate exit (orange) and the glass to the workshop (blue). Stop marks keep clear
of the pochta labels. The view box gets a
margin so labels at the edges are not cut off.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_zones as pz  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POCHTA_COMMIT = "f15ba315efc069aec2a0a18c9f68e4829ff61cb7"
POCHTA_NAME = "tsifrovoy-dvoynik-otdeleniya-pochty-rossii"
HELPER = ROOT / "scripts" / "plan_png.mts"
PNG = {"original": ROOT / "concept/img/plan-219-zoned.png",
       "mirror": ROOT / "concept/img/plan-219-mirror-zoned.png"}
VALIDATE_TODAY = "2026-10-24"
MARGIN_M = 1.0
PNG_WIDTH_PX = 2000

RED, GREEN, ORANGE, BLUE = "#DD191C", "#2B8A3E", "#F08C00", "#1C7ED6"


def fail(msg: str) -> None:
    print(f"plan_png: {msg}", file=sys.stderr)
    sys.exit(2)


def main_checkout() -> Path:
    """The main checkout of this repo (a worktree lives inside it, in .claude/worktrees)."""
    try:
        common = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                check=True, capture_output=True, text=True).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return ROOT


def pochta() -> tuple[Path, Path]:
    root = Path(os.environ.get("POCHTA_DIR", main_checkout().parent / POCHTA_NAME)).resolve()
    if not (root / "src/persistence/plan-svg.ts").is_file():
        fail(f"pochta repo not found at {root} (src/persistence/plan-svg.ts). "
             f"Clone it at commit {POCHTA_COMMIT} or set POCHTA_DIR.")
    tsx = root / "node_modules/.bin/tsx"
    if not tsx.is_file():
        fail(f"{tsx} not found. Install the pochta dependencies in its repo.")
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        head = "unknown"
    print(f"pochta {root} commit {head}")
    if head != POCHTA_COMMIT:
        print(f"WARNING: pinned pochta commit is {POCHTA_COMMIT}; the picture can differ")
    return root, tsx


def helper(root: Path, tsx: Path, *args: str) -> str:
    res = subprocess.run([str(tsx), str(HELPER), *args], env={**os.environ, "POCHTA_DIR": str(root)},
                         capture_output=True, text=True)
    if res.returncode:
        fail(f"pochta helper failed ({' '.join(args[:1])}):\n{res.stderr.strip()}")
    return res.stdout


LABEL_RE = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" transform="scale\(1,-1\)"[^>]*font-size="([\d.]+)"[^>]*>([^<]*)<')


def label_boxes(svg: str) -> list[tuple[float, float, float, float]]:
    """Boxes of the pochta labels in plan metres (the pochta labelBox rule)."""
    boxes = []
    for x, y, size, text in LABEL_RE.findall(svg):
        x, y, size = float(x), -float(y), float(size)  # text y is flipped twice: model y = -y
        w, h = len(text) * size * 0.62 + 0.08, size * 1.25
        boxes.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    return boxes


def overlay(plan: dict, labels: list) -> str:
    ext = plan["extensions"]["zoning219"]
    confirmed, candidate = set(ext["exits"]["confirmed"]), ext["exits"]["candidate"]
    stops = pz.route_stops(plan, labels)
    line = pz.route_line(plan, stops)
    g = ['<g data-overlay="route">', '<g transform="scale(1,-1)">']
    g.append(f'<polyline points="{" ".join(f"{x},{y}" for x, y in line)}" fill="none" stroke="{RED}" '
             'stroke-width="0.12" stroke-dasharray="0.5 0.25" stroke-linejoin="round"/>')
    for op in plan["openings"]:
        colour = (GREEN if op["id"] in confirmed else ORANGE if op["id"] == candidate
                  else BLUE if op["id"] == "op_glass_workshop" else None)
        if colour:
            (ax, ay), (bx, by) = pz.opening_segment(plan, op)
            g.append(f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" stroke="{colour}" stroke-width="0.35"/>')
    g += [f'<circle cx="{x}" cy="{y}" r="0.45" fill="{RED}"/>' for x, y in stops]
    g.append("</g>")
    g += [f'<text x="{x}" y="{round(-y + 0.17, 2)}" font-size="0.5" font-family="sans-serif" font-weight="bold" '
          f'fill="#fff" text-anchor="middle">{i}</text>' for i, (x, y) in enumerate(stops, 1)]
    g.append("</g>")
    return "".join(g)


def widen(svg: str) -> str:
    """Add MARGIN_M on every side of the view box; keep the pixel-per-metre scale."""
    m = re.search(r'width="([\d.]+)" height="([\d.]+)" viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', svg)
    if not m:
        fail("pochta SVG root has no width/height/viewBox: the renderer changed")
    w_px, h_px, x, y, w, h = map(float, m.groups())
    k = w_px / w
    new = (f'width="{round((w + 2 * MARGIN_M) * k, 2)}" height="{round((h + 2 * MARGIN_M) * k, 2)}" '
           f'viewBox="{x - MARGIN_M} {y - MARGIN_M} {w + 2 * MARGIN_M} {h + 2 * MARGIN_M}"')
    return svg[:m.start()] + new + svg[m.end():]


TEXT_SCALE = 100


def _upscale_text(m: re.Match) -> str:
    x, y, rest = float(m["x"]), float(m["y"]), m["rest"]
    rest = re.sub(r'font-size="([\d.]+)"', lambda f: f'font-size="{round(float(f[1]) * TEXT_SCALE, 3)}"', rest)
    k = 1 / TEXT_SCALE
    return (f'<text x="{round(x * TEXT_SCALE, 3)}" y="{round(y * TEXT_SCALE, 3)}" '
            f'transform="scale({k},-{k})"{rest}>')


def sharpen_text(svg: str) -> str:
    """Draw pochta labels at 100x font size, scaled down by 0.01.

    rsvg-convert hints a 0.16-unit font badly: "4" in "Колонна A4" loses its stem.
    The picture is the same; only the glyph outlines change.
    """
    return re.sub(r'<text x="(?P<x>[-\d.]+)" y="(?P<y>[-\d.]+)" transform="scale\(1,-1\)"(?P<rest>[^>]*)>',
                  _upscale_text, svg)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--validate", action="store_true", help="run the pochta validator, no PNG")
    args = ap.parse_args()
    root, tsx = pochta()
    if args.validate:
        for variant, path in pz.OUT.items():
            print(f"[{variant}] {path.relative_to(ROOT)}")
            print(helper(root, tsx, "validate", str(path), VALIDATE_TODAY), end="")
        return 0
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        fail("rsvg-convert not found (package librsvg)")
    for variant, path in pz.OUT.items():
        plan = pz.load(path)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.svg"
            helper(root, tsx, "svg", str(path), str(base))
            raw = base.read_text(encoding="utf-8")
            svg = sharpen_text(widen(raw)).replace("</svg>", overlay(plan, label_boxes(raw)) + "</svg>")
            full = Path(tmp) / "full.svg"
            full.write_text(svg, encoding="utf-8")
            subprocess.run([rsvg, "-w", str(PNG_WIDTH_PX), "-b", "white", str(full), "-o", str(PNG[variant])],
                           check=True)
        print(f"[{variant}] {PNG[variant].relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
