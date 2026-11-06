"""Build the AIJ Case A, B, D and E dtcc-core Cities and write them to validation/output/.

    uv run --group validate python validation/build_cities.py [--output DIR] [--resolution M] [--min-detail M]

Writes one .dtcc file and one PNG per City, plus summary.json with geometry
statistics, overlay/merge reports, measurement-point checks and two dtcc-qes
grid checks: the strict default (``qes``) and contact-aware cleaning with
``wind.Footprints`` (``qes_footprints``). See AIJ_CITY_MODELS.md (D, E) and
AIJ_AB_VALIDATION.md (A, B) for what each City contains.
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import shapely
from dtcc_qes import wind
from shapely.geometry import Point

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aij import case_ab, case_d, case_e, cityutil, tables  # noqa: E402


def point_report(city, points, case=None):
    if case in ("A", "B"):  # probes above the roof lie inside the footprint in plan: use 3D distances
        distance = case_ab.surface_distance(points.xyz, case)
        return dict(points=len(points.ids), inside_buildings=[int(i) for i in points.ids[distance <= 0]],
                    min_wall_distance=float(distance.min()))
    union = shapely.union_all([p for _, p, _ in cityutil.footprints(city)])
    inside = [int(i) for i, (x, y, _) in zip(points.ids, points.xyz) if union.contains(Point(x, y))]
    distances = [union.boundary.distance(Point(x, y)) for x, y, _ in points.xyz]
    return dict(points=len(points.ids), inside_buildings=inside, min_wall_distance=float(min(distances)))


def marker_report(points):
    markers = case_e.load().markers
    gaps = np.linalg.norm(markers[:, None, :2] - points.xyz[None, :, :2], axis=2)
    distances, nearest = gaps.min(axis=1), gaps.argmin(axis=1)
    return dict(markers=len(markers), centre_z=sorted({float(z) for z in markers[:, 2]}),
                nearest_point_distance=dict(zip(("min", "median", "max"),
                                                map(float, np.quantile(distances, [0, 0.5, 1])))),
                distinct_points_matched=len(set(nearest.tolist())))


def plot(city, points, path, title):
    records = cityutil.footprints(city)
    heights = [h for *_, h in records]
    norm = matplotlib.colors.Normalize(min(heights), max(heights))
    cmap = matplotlib.colormaps["viridis"]
    fig, ax = plt.subplots(figsize=(10, 10))
    for _, polygon, height in records:
        x, y = polygon.exterior.xy
        ax.fill(x, y, color=cmap(norm(height)), edgecolor="k", linewidth=0.2)
    for _, polygon, *_ in cityutil.elevated_footprints(city):
        x, y = polygon.exterior.xy
        ax.plot(x, y, color="tab:red", linewidth=0.8, linestyle="--")
    ax.scatter(points.xyz[:, 0], points.xyz[:, 1], s=6, color="tab:orange", zorder=3)
    for i, (x, y, _) in zip(points.ids, points.xyz):
        ax.annotate(str(i), (x, y), fontsize=5, xytext=(2, 2), textcoords="offset points")
    fig.colorbar(matplotlib.cm.ScalarMappable(norm, cmap), ax=ax, shrink=0.7, label="height [m]")
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(f"{title}: {len(records)} buildings (dashed red: elevated objects)")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "output")
    parser.add_argument("--resolution", type=float, default=2.0, help="dtcc-qes grid check spacing [m]")
    parser.add_argument("--min-detail", type=float, default=0.1,
                        help="wind.Footprints cleaning detail for the contact-aware check [m]")
    args = parser.parse_args(argv)
    footprints = wind.Footprints(min_detail=args.min_detail)
    args.output.mkdir(parents=True, exist_ok=True)

    points_d, points_e = tables.load_points_d(), tables.load_points_e()
    builds = {
        "aij_a": (case_ab.build_case_ab("A"), tables.load_points_ab("A")),
        "aij_b": (case_ab.build_case_ab("B"), tables.load_points_ab("B")),
        "aij_d": (case_d.build_case_d(), points_d),
        "aij_e_before": (case_e.build_case_e("before"), points_e),
        "aij_e_after": (case_e.build_case_e("after"), points_e),
        "aij_e_before_qes": (case_e.build_case_e_qes("before"), points_e),
        "aij_e_after_qes": (case_e.build_case_e_qes("after"), points_e),
    }
    summary = dict(case_e_markers=marker_report(points_e))
    for name, (built, points) in builds.items():
        built.city.save(args.output / f"{name}.dtcc")
        plot(built.city, points, args.output / f"{name}.png", name)
        summary[name] = dict(
            geometry=cityutil.summary(built.city), report=built.report,
            points=point_report(built.city, points, built.city.attributes["case"][-1]),
            qes=cityutil.qes_check(built.city, args.resolution),
            qes_footprints=cityutil.qes_check(built.city, args.resolution, footprints),
        )
        qes, resolved = summary[name]["qes"], summary[name]["qes_footprints"]
        print(f"{name}: {summary[name]['geometry']['buildings']} buildings, "
              f"{summary[name]['geometry']['city_objects']} elevated objects, "
              f"dtcc-qes strict {'ok ' + str(qes['shape']) if qes['ok'] else 'rejects: ' + qes['error']}; "
              f"Footprints({args.min_detail:g}) "
              + (f"ok, {resolved['counts']['solids']} solids, {len(resolved['fallbacks'])} fallbacks"
                 if resolved["ok"] else "rejects: " + resolved["error"][:120]))
    with open(args.output / "summary.json", "w") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False, default=float)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
