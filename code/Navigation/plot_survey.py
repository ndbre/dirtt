#!/usr/bin/env python3
"""Plot a survey run: planned sample points vs the path the rover actually drove.

  python3 plot_survey.py test_points.csv survey_<time>_samples.csv survey_<time>_track.csv [--fence test_fence.waypoints]

Writes survey_<time>.png (the report figure) and prints the stop-accuracy stats.
"""
import argparse, csv, math, statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = 6378137.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("points"); ap.add_argument("samples"); ap.add_argument("track")
    ap.add_argument("--fence", help="<out>_fence.waypoints from grid_planner.py")
    ap.add_argument("--out")
    a = ap.parse_args()

    pts = [(float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(a.points))]
    smp = list(csv.DictReader(open(a.samples)))
    trk = list(csv.DictReader(open(a.track)))
    lat0, lon0 = pts[0]
    k = math.cos(math.radians(lat0))
    xy = lambda lat, lon: (math.radians(lon - lon0) * R * k, math.radians(lat - lat0) * R)

    fig, ax = plt.subplots(figsize=(8, 7))
    if a.fence:
        fence = [xy(float(l.split("\t")[8]), float(l.split("\t")[9]))
                 for l in open(a.fence).read().splitlines()[1:] if l.strip()]
        fence.append(fence[0])
        ax.plot(*zip(*fence), "-", color="#444", lw=2, label="field edge / fence")
    T = [xy(float(r["lat"]), float(r["lon"])) for r in trk]
    ax.plot(*zip(*T), "-", color="#1F77B4", lw=1.3, label="actual path")
    P = [xy(*p) for p in pts]
    ax.scatter(*zip(*P), s=90, facecolors="none", edgecolors="#D62728", lw=1.8, zorder=3,
               label="planned sample point")
    ok = [r for r in smp if r["status"] == "OK"]
    S = [xy(float(r["lat"]), float(r["lon"])) for r in ok]
    if S:
        ax.scatter(*zip(*S), s=22, color="#D62728", zorder=4, label="probe position")
    skipped = [r for r in smp if r["status"] != "OK"]
    if skipped:
        K = [xy(float(r["planned_lat"]), float(r["planned_lon"])) for r in skipped]
        ax.scatter(*zip(*K), marker="x", s=80, color="k", zorder=5, label="skipped")
    for i, p in enumerate(P, 1):
        ax.annotate(str(i), p, textcoords="offset points", xytext=(6, 5), fontsize=8)
    ax.scatter(*T[0], marker="*", s=200, color="#2CA02C", zorder=5, label="start")

    errs = [float(r["error_m"]) for r in ok]
    t_total = float(trk[-1]["t"]) - float(trk[0]["t"])
    drive = sum(math.dist(T[i], T[i + 1]) for i in range(len(T) - 1))
    stats = (f"{len(ok)}/{len(pts)} sampled, {len(skipped)} skipped | stop error mean "
             f"{statistics.mean(errs):.2f} m, max {max(errs):.2f} m | {drive:.0f} m in {t_total / 60:.1f} min"
             if errs else "no samples")
    ax.set_title("D.I.R.T.T. survey run - planned vs actual\n" + stats, fontsize=10)
    ax.set_aspect("equal"); ax.grid(alpha=0.3)
    ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3, fontsize=8, frameon=False)
    out = a.out or a.samples.replace("_samples.csv", ".png")
    fig.tight_layout(); fig.savefig(out, dpi=150)
    print(stats); print("Wrote", out)


if __name__ == "__main__":
    main()
