#!/usr/bin/env python3
"""D.I.R.T.T. sample-grid planner.

Turns a field outline into an ordered lawn-mower grid of soil-sample points.

  python3 grid_planner.py --corners "40.0000,-88.0000 40.0006,-88.0000 40.0006,-87.9992 40.0000,-87.9992" \
                          --spacing 15 --margin 4 --out field1

Or, for a quick test around the SITL home position:
  python3 grid_planner.py --square 60 --origin 40.0,-88.0 --out test

Writes:
  <out>_points.csv        n, lat, lon                 (read by survey_mission.py)
  <out>.waypoints         QGC WPL 110 mission         (load in Mission Planner / `wp load` to SEE the plan)
  <out>_fence.waypoints   QGC WPL 110 inclusion fence (`fence load` in MAVProxy, or Mission Planner)
  <out>_plan.png          picture of the plan

How it works
  1. Project the corners to a flat local x/y frame in metres (fine for a field).
  2. Rotate so the rows run parallel to the field's longest edge (fewest turns).
  3. Lay a square grid of `spacing` metres over the field, centred so the leftover
     is split evenly, and keep only points at least `margin` metres inside the edge.
  4. Order the points boustrophedon ("lawn-mower"): row 1 left->right, row 2
     right->left, ... starting from the corner nearest the start position.
"""
import argparse, csv, math, sys

R_EARTH = 6378137.0


# ------------------------------------------------------------------ geometry
class LocalFrame:
    """Equirectangular projection about a reference point (metres east/north)."""
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.k = math.cos(math.radians(lat0))

    def to_xy(self, lat, lon):
        return (math.radians(lon - self.lon0) * R_EARTH * self.k,
                math.radians(lat - self.lat0) * R_EARTH)

    def to_ll(self, x, y):
        return (self.lat0 + math.degrees(y / R_EARTH),
                self.lon0 + math.degrees(x / (R_EARTH * self.k)))


def rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def inside(pt, poly):
    x, y = pt
    n, hit = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def edge_dist(pt, poly):
    best = float("inf")
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / L2))
        best = min(best, math.hypot(pt[0] - (x1 + t * dx), pt[1] - (y1 + t * dy)))
    return best


# ------------------------------------------------------------------ planner
def plan(corners_ll, spacing, margin, start_ll=None):
    lat0 = sum(c[0] for c in corners_ll) / len(corners_ll)
    lon0 = sum(c[1] for c in corners_ll) / len(corners_ll)
    fr = LocalFrame(lat0, lon0)
    poly = [fr.to_xy(*c) for c in corners_ll]

    # Row direction = longest edge
    n = len(poly)
    i = max(range(n), key=lambda i: math.dist(poly[i], poly[(i + 1) % n]))
    (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
    ang = math.atan2(y2 - y1, x2 - x1)
    rp = [rot(p, -ang) for p in poly]                      # rows now run along x

    xs, ys = [p[0] for p in rp], [p[1] for p in rp]

    def axis(lo, hi):
        span = (hi - lo) - 2 * margin
        if span < 0:
            return []
        k = int(span // spacing)
        start = lo + margin + (span - k * spacing) / 2      # centre the leftover
        return [start + j * spacing for j in range(k + 1)]

    rows = []
    for y in axis(min(ys), max(ys)):
        row = [(x, y) for x in axis(min(xs), max(xs))
               if inside((x, y), rp) and edge_dist((x, y), rp) >= margin - 1e-6]
        if row:
            rows.append(row)
    if not rows:
        sys.exit("No sample points fit - field too small for this spacing/margin.")

    # Try the 4 possible starting corners; keep the one closest to the start
    start = rot(fr.to_xy(*start_ll), -ang) if start_ll else None
    best = None
    for flip_rows in (False, True):
        for flip_first in (False, True):
            rr = rows[::-1] if flip_rows else rows
            order = []
            for k, row in enumerate(rr):
                fwd = (k % 2 == 0) != flip_first
                order += row if fwd else row[::-1]
            d0 = math.dist(start, order[0]) if start else 0.0
            if best is None or d0 < best[0]:
                best = (d0, order)
    order = best[1]

    pts_xy = [rot(p, ang) for p in order]
    pts_ll = [fr.to_ll(*p) for p in pts_xy]
    path = sum(math.dist(pts_xy[k], pts_xy[k + 1]) for k in range(len(pts_xy) - 1))
    return pts_ll, path, fr, len(rows)


# ------------------------------------------------------------------ outputs
def write_wpl(path, home, pts):
    with open(path, "w") as f:
        f.write("QGC WPL 110\n")
        f.write(f"0\t1\t0\t16\t0\t0\t0\t0\t{home[0]:.7f}\t{home[1]:.7f}\t0\t1\n")
        for i, (lat, lon) in enumerate(pts, 1):
            f.write(f"{i}\t0\t3\t16\t0\t0\t0\t0\t{lat:.7f}\t{lon:.7f}\t0\t1\n")


def write_fence(path, corners):
    """Inclusion polygon (MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION = 5001)."""
    with open(path, "w") as f:
        f.write("QGC WPL 110\n")
        for i, (lat, lon) in enumerate(corners):
            f.write(f"{i}\t0\t0\t5001\t{len(corners)}\t0\t0\t0\t{lat:.7f}\t{lon:.7f}\t0\t1\n")


def write_png(path, corners, pts, home, fr, spacing, margin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    poly = [fr.to_xy(*c) for c in corners] + [fr.to_xy(*corners[0])]
    P = [fr.to_xy(*p) for p in pts]
    H = fr.to_xy(*home)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([p[0] for p in poly], [p[1] for p in poly], "-", color="#444", lw=2, label="field edge / fence")
    ax.plot([H[0]] + [p[0] for p in P], [H[1]] + [p[1] for p in P], "-", color="#1F77B4", lw=1.2,
            alpha=0.7, label="planned path")
    ax.scatter([p[0] for p in P], [p[1] for p in P], s=40, color="#D62728", zorder=3, label="sample point")
    for k, p in enumerate(P, 1):
        ax.annotate(str(k), p, textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.scatter([H[0]], [H[1]], marker="*", s=180, color="#2CA02C", zorder=4, label="start / home")
    ax.set_aspect("equal")
    ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)")
    ax.set_title(f"D.I.R.T.T. sample plan: {len(pts)} points, {spacing:g} m grid, {margin:g} m margin")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=4, fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def parse_ll(s):
    lat, lon = (float(v) for v in s.split(","))
    return lat, lon


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--corners", help='field corners in order: "lat,lon lat,lon lat,lon ..."')
    g.add_argument("--square", type=float, help="test field: square of this many metres, NE of --origin")
    ap.add_argument("--origin", type=parse_ll, default=(40.0, -88.0), help="SW corner for --square (lat,lon)")
    ap.add_argument("--home", type=parse_ll,
                    help="start position (default: --origin, or 3 m inside the first corner). "
                         "Must be INSIDE the field or the fence will stop the rover arming.")
    ap.add_argument("--spacing", type=float, default=15.0, help="metres between sample points (default 15)")
    ap.add_argument("--margin", type=float, default=4.0, help="keep points this far inside the edge (default 4)")
    ap.add_argument("--speed", type=float, default=0.5, help="drive speed m/s, for the time estimate")
    ap.add_argument("--probe-s", type=float, default=45.0, help="seconds per sample, for the time estimate")
    ap.add_argument("--out", default="field", help="output file prefix")
    a = ap.parse_args(argv)

    if a.corners:
        corners = [parse_ll(c) for c in a.corners.split()]
        if len(corners) < 3:
            sys.exit("Need at least 3 corners.")
    else:
        # Square whose SW corner is 3 m SW of --origin, so the origin (SITL home)
        # starts just INSIDE the fence rather than on its edge.
        fr = LocalFrame(*a.origin)
        s, o = a.square, -3.0
        corners = [fr.to_ll(o, o), fr.to_ll(o, o + s), fr.to_ll(o + s, o + s), fr.to_ll(o + s, o)]
    if a.home:
        home = a.home
    elif a.square:
        home = a.origin
    else:
        # default start: 3 m in from the first corner, toward the middle of the field
        f0 = LocalFrame(*corners[0])
        cx = sum(f0.to_xy(*c)[0] for c in corners) / len(corners)
        cy = sum(f0.to_xy(*c)[1] for c in corners) / len(corners)
        L = math.hypot(cx, cy) or 1.0
        home = f0.to_ll(3 * cx / L, 3 * cy / L)

    pts, path, fr, nrows = plan(corners, a.spacing, a.margin, home)
    first_leg = math.dist(fr.to_xy(*home), fr.to_xy(*pts[0]))
    last_leg = math.dist(fr.to_xy(*pts[-1]), fr.to_xy(*home))
    total_m = first_leg + path + last_leg
    est_s = total_m / a.speed + len(pts) * a.probe_s

    with open(f"{a.out}_points.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "lat", "lon"])
        for i, (lat, lon) in enumerate(pts, 1):
            w.writerow([i, f"{lat:.7f}", f"{lon:.7f}"])
    write_wpl(f"{a.out}.waypoints", home, pts)
    write_fence(f"{a.out}_fence.waypoints", corners)
    write_png(f"{a.out}_plan.png", corners, pts, home, fr, a.spacing, a.margin)

    print(f"{len(pts)} sample points in {nrows} rows, {a.spacing:g} m spacing, {a.margin:g} m margin")
    print(f"Driving: {total_m:.0f} m (incl. to/from start)  ->  ~{est_s / 60:.0f} min at {a.speed} m/s "
          f"with {a.probe_s:g} s per sample")
    print(f"Wrote {a.out}_points.csv, {a.out}.waypoints, {a.out}_fence.waypoints, {a.out}_plan.png")


if __name__ == "__main__":
    main()
