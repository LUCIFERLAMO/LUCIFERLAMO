#!/usr/bin/env python3
"""Build the animated "target range" contribution graph for the profile README.

Reads the real contribution calendar from the GitHub GraphQL API and writes a
single SVG: planted charges detonate and blow away clusters of squares, then
the squares grow back. Standard library only.

    GH_TOKEN=... python scripts/build_range.py --user LUCIFERLAMO --out range.svg
    python scripts/build_range.py --sample --out range.svg      # no network
"""
import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.request
from html import escape

W, H = 838, 212
CELL, PITCH = 11, 14
GX, GY = 44, 66
LOOP = 17.0          # seconds
REGROW = 15.0        # squares start growing back here
RADIUS = 48          # blast radius in px
LV = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
HIT, ASH = "#ff4d63", "#7a1626"
RED, REDT, BG, PANEL, LINE = "#c8102e", "#ff4d63", "#080808", "#0f1216", "#262b33"
TEXT, MUTED = "#e6e6e6", "#8b949e"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SLOTS = [(1.0, 3.4), (5.4, 7.8), (9.8, 12.2)]  # (plant, detonate)

QUERY = ("query($login:String!){user(login:$login){contributionsCollection{contributionCalendar"
         "{weeks{contributionDays{contributionLevel date weekday}}}}}}")
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


# ---------------------------------------------------------------- data
def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "range-generator"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    user = (data.get("data") or {}).get("user")
    if data.get("errors") or not user:
        sys.exit(f"GraphQL failed: {data.get('errors') or data}")
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    grid, first_dates = [], []
    for wk in weeks:
        col = [0] * 7
        for day in wk["contributionDays"]:
            col[day["weekday"]] = LEVELS.get(day["contributionLevel"], 0)
        grid.append(col)
        first_dates.append(dt.date.fromisoformat(wk["contributionDays"][0]["date"]))
    return grid, first_dates


def sample():
    rng = random.Random(47)
    grid = []
    for _ in range(53):
        active = rng.random() < 0.66
        col = [0] * 7
        for d in range(7):
            p = 0.38 if d in (0, 6) else 0.72
            if active and rng.random() < p:
                col[d] = rng.choices([1, 2, 3, 4], [4, 3, 2, 1])[0]
        grid.append(col)
    start = dt.date.today() - dt.timedelta(days=dt.date.today().weekday() + 1 + 52 * 7)
    return grid, [start + dt.timedelta(days=7 * i) for i in range(53)]


# ---------------------------------------------------------------- svg helpers
def f(n):
    s = f"{float(n):.2f}".rstrip("0").rstrip(".")
    return s or "0"


def tag(name, children="", **kw):
    a = " ".join(f'{k.rstrip("_").replace("_", "-")}="{escape(str(v), quote=True)}"' for k, v in kw.items())
    return f"<{name} {a}>{children}</{name}>" if a else f"<{name}>{children}</{name}>"


def rect(x, y, w, h, fill, **kw):
    return tag("rect", x=f(x), y=f(y), width=f(w), height=f(h), fill=fill, **kw)


def text(x, y, s, size, fill, weight=None, anchor=None, ls=None):
    kw = dict(x=f(x), y=f(y), fill=fill, font_family=MONO, font_size=size)
    if weight:
        kw["font_weight"] = weight
    if anchor:
        kw["text_anchor"] = anchor
    if ls is not None:
        kw["letter_spacing"] = ls
    return tag("text", escape(s), **kw)


def anim(kind, attr, frames, calc="linear"):
    frames = sorted(frames, key=lambda k: k[0])
    if frames[0][0] > 0:
        frames.insert(0, (0, frames[0][1]))
    if frames[-1][0] < LOOP:
        frames.append((LOOP, frames[-1][1]))
    common = dict(values=";".join(str(v) for _, v in frames),
                  keyTimes=";".join(f"{min(t / LOOP, 1):.4f}" for t, _ in frames),
                  dur=f"{f(LOOP)}s", repeatCount="indefinite", calcMode=calc)
    if kind == "animate":
        return tag("animate", attributeName=attr, **common)
    return tag("animateTransform", attributeName="transform", type=attr, **common)


def center(w, d):
    return GX + w * PITCH + CELL / 2, GY + d * PITCH + CELL / 2


# ---------------------------------------------------------------- charge sites
def pick_sites(grid):
    n = len(grid)
    scored = []
    for w in range(3, n - 3):
        for d in range(1, 6):
            cx, cy = center(w, d)
            score = 0
            for w2 in range(max(0, w - 5), min(n, w + 6)):
                for d2 in range(7):
                    x, y = center(w2, d2)
                    if grid[w2][d2] and math.hypot(x - cx, y - cy) <= RADIUS:
                        score += grid[w2][d2]
            scored.append((score, -abs(d - 3), w, d))
    scored.sort(reverse=True)
    sites = []
    for score, _, w, d in scored:
        if score > 0 and all(abs(w - s[0]) >= 10 for s in sites):
            sites.append((w, d))
        if len(sites) == len(SLOTS):
            break
    for w in (12, n // 2, n - 8):  # quiet graph: fall back to evenly spaced sites
        if len(sites) < len(SLOTS) and all(abs(w - s[0]) >= 10 for s in sites):
            sites.append((w, 3))
    return sorted(sites)


# ---------------------------------------------------------------- build
def build(grid, first_dates, label):
    n = len(grid)
    inner = rect(0, 0, W, H, BG) + rect(0, 0, W, 3, RED)
    inner += text(24, 32, "TARGET RANGE", 12, TEXT, "700", ls=4)
    inner += text(W - 24, 32, f"REMOTE CHARGE  //  {label}", 10, MUTED, anchor="end", ls=2)

    last = None
    for w, day in enumerate(first_dates):
        key = (day + dt.timedelta(days=6)).month
        if key != last and (last is None or w - lastw >= 3):
            inner += text(GX + w * PITCH, GY - 10, (day + dt.timedelta(days=6)).strftime("%b"), 9.5, MUTED)
            last, lastw = key, w
    for d, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        inner += text(GX - 10, GY + d * PITCH + 9, name, 9.5, MUTED, anchor="end")

    hit, fx = {}, ""
    for (cw, cd), (tp, td) in zip(pick_sites(grid), SLOTS):
        cx, cy = center(cw, cd)
        for w in range(n):
            for d in range(7):
                x, y = center(w, d)
                dist = math.hypot(x - cx, y - cy)
                if dist <= RADIUS and grid[w][d] and (w, d) not in hit:
                    th = td + dist / 110.0
                    ang = math.atan2(y - cy, x - cx)
                    dx, dy = round(math.cos(ang) * 9, 1), round(math.sin(ang) * 9, 1)
                    c0 = LV[grid[w][d]]
                    hit[(w, d)] = (
                        anim("animate", "fill", [(0, c0), (th, c0), (th + 0.06, HIT), (th + 0.4, ASH), (REGROW, ASH), (REGROW + 0.01, c0)]) +
                        anim("animate", "opacity", [(0, 1), (th + 0.02, 1), (th + 0.55, 0), (REGROW, 0), (REGROW + 0.7, 1)]) +
                        anim("animateTransform", "translate", [(0, "0,0"), (th, "0,0"), (th + 0.55, f"{dx},{dy}"), (REGROW, f"{dx},{dy}"), (REGROW + 0.01, "0,0")]))
        blink, t, on = [(0, 0.15)], tp + 0.2, True
        while t < td - 0.2:
            blink.append((t, 1 if on else 0.15))
            on, t = not on, t + 0.32
        blink.append((td, 0.15))
        device = (rect(-7, -5, 14, 10, "#1b1f24", stroke="#5b6068", stroke_width=1) +
                  tag("line", x1="0", y1="-5", x2="0", y2="-11", stroke="#5b6068", stroke_width="1.2") +
                  tag("circle", anim("animate", "opacity", blink, "discrete"), cx="0", cy="0", r="2.2", fill=REDT))
        fx += tag("g", device + anim("animate", "opacity", [(0, 0), (tp, 0), (tp + 0.15, 1), (td - 0.01, 1), (td, 0)]),
                  transform=f"translate({f(cx)} {f(cy)})", opacity="0")
        fx += tag("circle", anim("animate", "r", [(0, 2), (td, 2), (td + 0.3, 46)]) +
                  anim("animate", "opacity", [(0, 0), (td, 0), (td + 0.01, 0.9), (td + 0.35, 0)]),
                  cx=f(cx), cy=f(cy), r="2", fill=REDT, opacity="0")
        fx += tag("circle", anim("animate", "r", [(0, 2), (td, 2), (td + 0.9, 84)]) +
                  anim("animate", "opacity", [(0, 0), (td, 0), (td + 0.01, 0.85), (td + 0.9, 0)]) +
                  anim("animate", "stroke-width", [(0, 4), (td, 4), (td + 0.9, 1)]),
                  cx=f(cx), cy=f(cy), r="2", fill="none", stroke=RED, stroke_width="4", opacity="0")

    for w in range(n):
        for d in range(7):
            inner += tag("rect", hit.get((w, d), ""), x=f(GX + w * PITCH), y=f(GY + d * PITCH), width=str(CELL),
                         height=str(CELL), rx="2", fill=LV[grid[w][d]])
    inner += fx
    ly = GY + 7 * PITCH
    inner += text(24, ly + 22, "Every green square is a contribution on the record.", 10.5, MUTED)
    lx = GX + n * PITCH - 5 * PITCH - 62
    inner += text(lx, ly + 22, "Less", 9.5, MUTED, anchor="end")
    for k in range(5):
        inner += rect(lx + 8 + k * PITCH, ly + 13, CELL, CELL, LV[k], rx="2")
    inner += text(lx + 8 + 5 * PITCH + 4, ly + 22, "More", 9.5, MUTED)
    inner += rect(0.5, 0.5, W - 1, H - 1, "none", stroke=LINE)
    desc = "Contribution grid where planted charges detonate and wipe clusters of squares, then the squares grow back."
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{escape(desc, quote=True)}"><title>{escape(desc)}</title>{inner}</svg>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", action="store_true", help="use a made-up grid, no network")
    a = ap.parse_args()
    if a.sample:
        grid, dates = sample()
        label = "SAMPLE GRID"
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not (a.user and token):
            sys.exit("need --user and GH_TOKEN (or use --sample)")
        grid, dates = fetch(a.user, token)
        label = "UPDATED " + dt.date.today().isoformat()
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(build(grid, dates, label))
    print(f"wrote {a.out} ({len(grid)} weeks)")


if __name__ == "__main__":
    main()
