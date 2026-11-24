"""
heatmap.py - soil heat maps for the base station.

The plotting code is the team's soil_heatmap.py (from the merged rover.py), unchanged except
that the settings it used from rover.py are repeated here. save_heatmap() is new.
"""
import csv
import os
import random

VALUE_KEYS = ["moisture_pct", "temp_c", "ec_uScm", "ph"]

np = plt = pe = Rectangle = MaxNLocator = None     # filled in by load_plotting()


def load_plotting():
    """numpy/matplotlib are only needed for heatmaps, so they load on first use."""
    global np, plt, pe, Rectangle, MaxNLocator
    import numpy as _np
    import matplotlib
    matplotlib.use("Agg")      # the rover has no display: draw straight to a file
    import matplotlib.pyplot as _plt
    import matplotlib.patheffects as _pe
    from matplotlib.patches import Rectangle as _Rectangle
    from matplotlib.ticker import MaxNLocator as _MaxNLocator
    np, plt, pe, Rectangle, MaxNLocator = _np, _plt, _pe, _Rectangle, _MaxNLocator


# ---------- Survey settings ----------
GRID_SPACING_FT = 5.0   # real distance between neighboring grid points
LOW_RATING = 60         # points below this rating are outlined as zones to spot check

# ---------- Fertility rating rules (PLACEHOLDERS: replace with values for your target crop) ----------
# column: (ideal_low, ideal_high, zero_low, zero_high, weight)
#   Inside the ideal range scores 100. Outside it, the score falls in a straight
#   line to 0 at zero_low / zero_high. The rating is the weighted average.
RATING_RULES = {
    "ph":           (6.0,   7.0,    4.5,  8.5,    0.4),
    "moisture_pct": (20.0,  40.0,   5.0,  60.0,   0.3),
    "ec_uScm":      (200.0, 1200.0, 50.0, 3000.0, 0.3),
}

# key, title, colormap, vmin, vmax, label format
PANELS = [
    ("rating",       "Fertility rating (0 to 100)", "RdYlGn",  0,    100,  "{:.0f}"),
    ("moisture_pct", "Moisture (%)",                "Blues",   None, None, "{:.1f}"),
    ("ec_uScm",      "EC (\u00b5S/cm)",             "viridis", None, None, "{:.0f}"),
    ("ph",           "pH",                          "RdYlBu",  None, None, "{:.1f}"),
    ("temp_c",       "Temperature (\u00b0C)",       "inferno", None, None, "{:.1f}"),
]

# Smallest range each color scale is allowed to cover. Without this, the colors
# stretch to fit whatever was measured, so sensor noise (like 22.3 vs 22.4 C)
# shows up as opposite ends of the scale. Raise a number to make that map calmer.
MIN_COLOR_SPAN = {
    "moisture_pct": 10.0,   # %
    "ec_uScm":      200.0,  # uS/cm
    "ph":           1.0,    # pH units
    "temp_c":       2.0,    # deg C
}

IDW_POWER = 2      # higher = each reading dominates a smaller area around it
SMOOTH_RES = 150   # pixels per side of the smooth map (lower = faster on a Pi)


def color_limits(key, vals, vmin, vmax):
    """Color scale limits: fixed if given, otherwise the data range widened to the minimum span."""
    if vmin is not None and vmax is not None:
        return vmin, vmax
    lo, hi = float(np.min(vals)), float(np.max(vals))
    span = MIN_COLOR_SPAN.get(key, 0.0)
    if hi - lo < span:
        mid = (lo + hi) / 2
        lo, hi = mid - span / 2, mid + span / 2
    if hi - lo < 1e-9:
        lo, hi = lo - 0.5, hi + 0.5
    return lo, hi


def score(value, ideal_lo, ideal_hi, zero_lo, zero_hi):
    if ideal_lo <= value <= ideal_hi:
        return 100.0
    if value < ideal_lo:
        return max(0.0, 100.0 * (value - zero_lo) / (ideal_lo - zero_lo))
    return max(0.0, 100.0 * (zero_hi - value) / (zero_hi - ideal_hi))


def fertility_rating(pt):
    total = 0.0
    weights = 0.0
    for col, (lo, hi, zlo, zhi, w) in RATING_RULES.items():
        total += w * score(pt[col], lo, hi, zlo, zhi)
        weights += w
    return total / weights


def load_survey(path):
    """Read survey points, averaging any grid position recorded more than once."""
    groups = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("x") or not row.get("y"):
                continue
            key = (int(float(row["x"])), int(float(row["y"])))
            groups.setdefault(key, []).append(row)

    points = []
    for (x, y), rows in sorted(groups.items()):
        pt = {"x": x, "y": y, "repeats": len(rows)}
        for col in VALUE_KEYS:
            pt[col] = sum(float(r[col]) for r in rows) / len(rows)
        points.append(pt)
    return points


def demo_points():
    """Fake 6 x 5 survey with a wet side, a salty strip, and an acidic corner."""
    rng = random.Random(7)
    points = []
    for x in range(6):
        for y in range(5):
            if (x, y) == (3, 2):
                continue  # leave one gap to show what a missing point looks like
            points.append({
                "x": x, "y": y, "repeats": 1,
                "moisture_pct": 18 + 4.0 * x + rng.uniform(-2, 2),
                "ec_uScm": 150 + 90 * y + rng.uniform(-30, 30),
                "ph": min(7.2, 5.0 + 0.3 * (x + y)) + rng.uniform(-0.1, 0.1),
                "temp_c": 18 + rng.uniform(-0.5, 0.5),
            })
    return points


def outline_low_zones(ax, points, s):
    for p in points:
        if p["rating"] < LOW_RATING:
            ax.add_patch(Rectangle(((p["x"] - 0.5) * s, (p["y"] - 0.5) * s), s, s,
                                   fill=False, edgecolor="black", linewidth=2.5))


def label_points(ax, points, key, fmt, s):
    for p in points:
        ax.text(p["x"] * s, p["y"] * s, fmt.format(p[key]), ha="center", va="center",
                fontsize=8, path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])


def draw_grid_panel(ax, points, key, cmap_name, vmin, vmax, fmt, s):
    x0 = min(p["x"] for p in points)
    x1 = max(p["x"] for p in points)
    y0 = min(p["y"] for p in points)
    y1 = max(p["y"] for p in points)

    arr = np.full((y1 - y0 + 1, x1 - x0 + 1), np.nan)
    for p in points:
        arr[p["y"] - y0, p["x"] - x0] = p[key]

    lo, hi = color_limits(key, [p[key] for p in points], vmin, vmax)
    cmap = plt.get_cmap(cmap_name).copy()
    cmap.set_bad("#dddddd")  # gray = not measured
    im = ax.imshow(np.ma.masked_invalid(arr), origin="lower", cmap=cmap, vmin=lo, vmax=hi,
                   extent=[(x0 - 0.5) * s, (x1 + 0.5) * s, (y0 - 0.5) * s, (y1 + 0.5) * s])
    label_points(ax, points, key, fmt, s)
    return im


def idw_surface(xy, vals, s):
    """Inverse distance weighted estimate over the survey area (plus a half-step border)."""
    pad = 0.5 * s
    gx, gy = np.meshgrid(np.linspace(xy[:, 0].min() - pad, xy[:, 0].max() + pad, SMOOTH_RES),
                         np.linspace(xy[:, 1].min() - pad, xy[:, 1].max() + pad, SMOOTH_RES))
    gz = np.zeros_like(gx)
    wsum = np.zeros_like(gx)
    for (px, py), v in zip(xy, vals):
        d2 = (gx - px) ** 2 + (gy - py) ** 2
        w = 1.0 / (d2 ** (IDW_POWER / 2) + 1e-9)
        gz += w * v
        wsum += w
    # IDW never goes outside the measured range; the clip just removes rounding noise
    return gx, gy, np.clip(gz / wsum, vals.min(), vals.max())


def draw_smooth_panel(ax, points, key, cmap_name, vmin, vmax, fmt, s):
    xy = np.array([[p["x"] * s, p["y"] * s] for p in points], dtype=float)
    vals = np.array([p[key] for p in points], dtype=float)
    gx, gy, gz = idw_surface(xy, vals, s)

    lo, hi = color_limits(key, vals, vmin, vmax)
    im = ax.contourf(gx, gy, gz, levels=np.linspace(lo, hi, 21), cmap=cmap_name)
    if key == "rating" and gz.min() < LOW_RATING < gz.max():
        ax.contour(gx, gy, gz, levels=[LOW_RATING], colors="black", linewidths=2, linestyles="--")
    ax.scatter(xy[:, 0], xy[:, 1], c="black", s=10)
    label_points(ax, points, key, fmt, s)
    return im


def draw_summary(ax, points, title_note, smooth):
    ax.axis("off")
    n = len(points)
    avg = {c: sum(p[c] for p in points) / n for c in VALUE_KEYS + ["rating"]}
    low = sorted([p for p in points if p["rating"] < LOW_RATING], key=lambda p: p["rating"])

    lines = [
        title_note,
        "",
        f"Points measured: {n}",
        f"Grid spacing: {GRID_SPACING_FT:g} ft",
        "",
        "Averages",
        f"  Rating:      {avg['rating']:.0f}",
        f"  Moisture:    {avg['moisture_pct']:.1f} %",
        f"  EC:          {avg['ec_uScm']:.0f} \u00b5S/cm",
        f"  pH:          {avg['ph']:.2f}",
        f"  Temperature: {avg['temp_c']:.1f} \u00b0C",
        "",
        f"Spot check (rating < {LOW_RATING}): {len(low)} points",
    ]
    for p in low[:10]:
        lines.append(f"  ({p['x']}, {p['y']})  rating {p['rating']:.0f}")
    if len(low) > 10:
        lines.append(f"  ...and {len(low) - 10} more")
    lines += ["", "Rating thresholds are placeholders."]
    if smooth:
        lines += ["Colors between dots are estimated", "from the nearest readings."]

    ax.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", family="monospace",
            fontsize=9, transform=ax.transAxes)


def make_figure(points, smooth, title, title_note):
    s = GRID_SPACING_FT
    for p in points:
        p["rating"] = fertility_rating(p)

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for ax, (key, panel_title, cmap, vmin, vmax, fmt) in zip(axes.flat, PANELS):
        if smooth:
            im = draw_smooth_panel(ax, points, key, cmap, vmin, vmax, fmt, s)
        else:
            im = draw_grid_panel(ax, points, key, cmap, vmin, vmax, fmt, s)
        if key == "rating":
            if smooth:
                low = [p for p in points if p["rating"] < LOW_RATING]
                if low:
                    ax.scatter([p["x"] * s for p in low], [p["y"] * s for p in low], s=350,
                               facecolors="none", edgecolors="black", linewidths=2.5)
            else:
                outline_low_zones(ax, points, s)
        fig.colorbar(im, ax=ax, shrink=0.8, ticks=MaxNLocator(6))
        xs = sorted({p["x"] for p in points})
        ys = sorted({p["y"] for p in points})
        ax.set_xlim((xs[0] - 0.5) * s, (xs[-1] + 0.5) * s)
        ax.set_ylim((ys[0] - 0.5) * s, (ys[-1] + 0.5) * s)
        ax.set_xticks([x * s for x in range(xs[0], xs[-1] + 1)])
        ax.set_yticks([y * s for y in range(ys[0], ys[-1] + 1)])
        ax.set_title(panel_title)
        ax.set_xlabel("x (ft)")
        ax.set_ylabel("y (ft)")
        ax.set_aspect("equal")

    draw_summary(axes.flat[5], points, title_note, smooth)
    fig.tight_layout()
    return fig


def save_heatmap(survey_csv, out_png, title="Soil survey"):
    """Draw the heat maps for every point in survey_csv (needs columns x, y and VALUE_KEYS).
    Fewer than 3 points: a plain grid instead of the smooth map. Returns the PNG path or None."""
    if np is None:
        load_plotting()
    if not os.path.exists(survey_csv):
        return None
    points = load_survey(survey_csv)
    if not points:
        return None
    smooth = len(points) >= 3
    note = f"{len(points)} point(s), {os.path.basename(survey_csv)}"
    fig = make_figure(points, smooth, title, note)
    tmp = out_png + ".tmp.png"
    fig.savefig(tmp, dpi=110)
    plt.close(fig)
    os.replace(tmp, out_png)        # the web page never sees a half-written image
    return out_png
