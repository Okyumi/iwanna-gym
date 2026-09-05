"""Static HTML dashboard for discovery runs — no plotting libraries.

Reads evaluator JSONL files and train_log.jsonl files and emits one
self-contained HTML page with inline SVG charts: success-by-attempt
curves, deaths-to-first-success, repeated-death rate, environment/
learner SPS over iterations, and wall-clock learning progress.

Usage:
    PYTHONPATH=. python scripts/make_discovery_dashboard.py \
        --eval build/discovery_eval/*.jsonl \
        --train build/discovery_runs/*/train_log.jsonl \
        --out build/discovery_dashboard.html
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import os
import sys

sys.path.insert(0, ".")
from iwanna_gym.discovery import evaluator as E          # noqa: E402

W, H, PAD = 460, 220, 36
COLORS = ["#4477aa", "#ee6677", "#228833", "#ccbb44", "#66ccee",
          "#aa3377", "#bbbbbb"]


def svg_lines(series: dict[str, list[tuple[float, float]]],
              title: str, xlab: str, ylab: str,
              y01: bool = False) -> str:
    pts = [p for s in series.values() for p in s]
    if not pts:
        return f"<p>({html.escape(title)}: no data)</p>"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs) or 1
    y0, y1 = (0.0, 1.0) if y01 else (min(0.0, min(ys)), max(ys) or 1)
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y1 = y0 + 1

    def X(x):
        return PAD + (x - x0) / (x1 - x0) * (W - 2 * PAD)

    def Y(y):
        return H - PAD - (y - y0) / (y1 - y0) * (H - 2 * PAD)

    out = [f'<svg width="{W}" height="{H}" '
           f'style="background:#fff;border:1px solid #ccc">',
           f'<text x="{W/2}" y="14" text-anchor="middle" '
           f'font-size="12" font-weight="bold">{html.escape(title)}</text>',
           f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" '
           f'stroke="#333"/>',
           f'<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{H-PAD}" '
           f'stroke="#333"/>',
           f'<text x="{W/2}" y="{H-6}" text-anchor="middle" '
           f'font-size="10">{html.escape(xlab)}</text>',
           f'<text x="10" y="{H/2}" font-size="10" '
           f'transform="rotate(-90 10 {H/2})" text-anchor="middle">'
           f'{html.escape(ylab)}</text>',
           f'<text x="{PAD-4}" y="{H-PAD+4}" text-anchor="end" '
           f'font-size="9">{y0:.2g}</text>',
           f'<text x="{PAD-4}" y="{PAD+4}" text-anchor="end" '
           f'font-size="9">{y1:.2g}</text>',
           f'<text x="{PAD}" y="{H-PAD+12}" font-size="9">{x0:.3g}</text>',
           f'<text x="{W-PAD}" y="{H-PAD+12}" text-anchor="end" '
           f'font-size="9">{x1:.3g}</text>']
    for i, (name, s) in enumerate(sorted(series.items())):
        if not s:
            continue
        col = COLORS[i % len(COLORS)]
        path = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in s)
        out.append(f'<polyline fill="none" stroke="{col}" '
                   f'stroke-width="1.6" points="{path}"/>')
        out.append(f'<text x="{W-PAD+2}" y="{PAD + 12*i}" font-size="9" '
                   f'fill="{col}">{html.escape(name[:26])}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_bars(vals: dict[str, float], title: str, ylab: str) -> str:
    if not vals:
        return f"<p>({html.escape(title)}: no data)</p>"
    y1 = max(list(vals.values()) + [1e-9])
    n = len(vals)
    bw = (W - 2 * PAD) / max(n, 1)
    out = [f'<svg width="{W}" height="{H}" '
           f'style="background:#fff;border:1px solid #ccc">',
           f'<text x="{W/2}" y="14" text-anchor="middle" font-size="12" '
           f'font-weight="bold">{html.escape(title)}</text>']
    for i, (k, v) in enumerate(sorted(vals.items())):
        bh = (v / y1) * (H - 2 * PAD)
        x = PAD + i * bw
        out.append(f'<rect x="{x+2:.1f}" y="{H-PAD-bh:.1f}" '
                   f'width="{bw-4:.1f}" height="{bh:.1f}" '
                   f'fill="{COLORS[i % len(COLORS)]}"/>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{H-PAD+10}" '
                   f'text-anchor="middle" font-size="8">'
                   f'{html.escape(k[:14])}</text>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{H-PAD-bh-3:.1f}" '
                   f'text-anchor="middle" font-size="9">{v:.2g}</text>')
    out.append(f'<text x="10" y="{H/2}" font-size="10" '
               f'transform="rotate(-90 10 {H/2})" text-anchor="middle">'
               f'{html.escape(ylab)}</text></svg>')
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", nargs="*", default=[])
    ap.add_argument("--train", nargs="*", default=[])
    ap.add_argument("--out", default="build/discovery_dashboard.html")
    args = ap.parse_args()
    eval_files = [f for pat in args.eval for f in sorted(glob.glob(pat))]
    train_files = [f for pat in args.train for f in sorted(glob.glob(pat))]

    parts = ["<meta charset='utf-8'><title>Discovery dashboard</title>",
             "<h1>Discovery benchmark dashboard</h1>",
             "<p>Generated by scripts/make_discovery_dashboard.py — "
             "suites are shown separately; ORACLE files are labeled.</p>"]

    # ---- evaluation charts (per file = one run) ----
    curves, dts, rdr = {}, {}, {}
    for f in eval_files:
        recs = [json.loads(x) for x in open(f, encoding="utf-8")]
        if not recs:
            continue
        name = os.path.basename(f).replace(".jsonl", "")
        if any(r.get("oracle") for r in recs):
            name = "ORACLE:" + name
        K = recs[0].get("attempts_K", 25)
        c = E.success_by_attempt(recs, K)
        curves[name] = [(k + 1, v) for k, v in enumerate(c)]
        a = [r["attempts_to_success"] for r in recs
             if r["attempts_to_success"] is not None]
        d = [r["repeated_death_rate"] for r in recs
             if r["repeated_death_rate"] is not None]
        if a:
            dts[name] = sum(a) / len(a)
        if d:
            rdr[name] = sum(d) / len(d)
    parts.append("<h2>Evaluation</h2>")
    parts.append(svg_lines(curves, "Success by attempt S(k)",
                           "attempt k", "fraction solved", y01=True))
    parts.append(svg_bars(dts, "Mean attempts to first success",
                          "attempts"))
    parts.append(svg_bars(rdr, "Repeated-death rate", "RDR"))

    # ---- training charts ----
    sps, wall_curve = {}, {}
    for f in train_files:
        name = os.path.basename(os.path.dirname(f)) or f
        rows = [json.loads(x) for x in open(f, encoding="utf-8")]
        if not rows:
            continue
        sps[name] = [(r["iteration"], r["end_to_end_sps"]) for r in rows]
        wc = [(r["wall_s"], r["task_success_rate"]) for r in rows
              if r.get("task_success_rate") is not None]
        if wc:
            wall_curve[name] = wc
    parts.append("<h2>Training</h2>")
    parts.append(svg_lines(sps, "End-to-end SPS over iterations",
                           "iteration", "steps/s"))
    parts.append(svg_lines(wall_curve,
                           "Wall-clock learning progress",
                           "wall-clock (s)", "task success rate",
                           y01=True))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"wrote {args.out} ({len(eval_files)} eval, "
          f"{len(train_files)} train files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
