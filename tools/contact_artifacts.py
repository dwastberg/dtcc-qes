"""Measure decomposition artifacts on synthetic rectangular buildings.

The baseline mode bypasses only the adapter contact rejection, within one
synchronous solve. It deliberately exercises the existing parameterizations.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

import numpy as np
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import _city, _qes, wind

ROOT = Path(__file__).resolve().parents[1]
BOUNDS = (0., 0., 0., 240., 120., 100.)
SPEED = 5.0


@dataclass(frozen=True)
class Prism:
    bounds: tuple[float, float, float, float]
    height: float = 10.


def fixtures():
    """Explicit geometry in metres; order in each tuple is input order."""
    west, east = Prism((60, 50, 80, 70)), Prism((80, 50, 100, 70))
    gap = Prism((80.3, 50, 100.3, 70))
    separated = Prism((83, 50, 103, 70))
    low_west, low_east = Prism(west.bounds, 6), Prism(east.bounds, 6)
    return {
        "block": (Prism((60, 50, 100, 70)),),
        "split": (west, east), "split_reversed": (east, west),
        "split_parallel": (Prism((60, 50, 100, 60)), Prism((60, 60, 100, 70))),
        "gap": (west, gap), "gap_reversed": (gap, west),
        "separated": (west, separated), "separated_reversed": (separated, west),
        "near_equal_roofs": (west, Prism(east.bounds, 9.9)),
        "overlap": (Prism((60, 50, 100, 70), 6), east),
        "overlap_reversed": (east, Prism((60, 50, 100, 70), 6)),
        "partition": (low_west, east),
        "inset": (west, Prism((80, 50.05, 100, 69.95))),
        "step_down": (west, low_east), "step_up": (low_west, east),
    }


COMPARISONS = (
    ("split", "split", "block"),
    ("split_reversed", "split_reversed", "block"),
    ("split_parallel", "split_parallel", "block"),
    ("subcell_gap", "gap", "block"),
    ("gap_order", "gap_reversed", "gap"),
    ("separated_order", "separated_reversed", "separated"),
    ("near_equal_roofs", "near_equal_roofs", "block"),
    ("overlap_partition", "overlap", "partition"),
    ("overlap_order", "overlap_reversed", "overlap"),
    ("inset", "inset", "split"),
    ("step_down", "step_down", "block"),
    ("step_up", "step_up", "block"),
)


def make_city(prisms):
    city = City()
    for index, prism in enumerate(prisms):
        left, bottom, right, top = prism.bounds
        value = Building(id=str(index))
        value.measured_height = prism.height
        value.add_geometry(Surface(vertices=np.array([
            [left, bottom, 0], [left, top, 0], [right, top, 0], [right, bottom, 0],
        ], dtype=np.float64)), GeometryType.LOD0)
        city.add_building(value)
    return city


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def source_manifest():
    paths = [Path(__file__), *sorted((ROOT / "src").rglob("*.py")),
             *sorted((ROOT / "src").rglob("*.cpp")), *sorted((ROOT / "src").rglob("*.h")),
             *sorted(ROOT.rglob("CMakeLists.txt"))]
    # Exclude generated build files from provenance.
    paths = sorted({p for p in paths if "build" not in p.relative_to(ROOT).parts})
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    return dict(git_revision=revision, source_sha256=hashes,
        native_extension_sha256=hashlib.sha256(Path(_qes.__file__).read_bytes()).hexdigest(),
        python=platform.python_version(), numpy=np.__version__, platform=platform.platform())


def solve(prisms, args):
    options = dict(speed=SPEED, direction=270., reference_height=10., roughness_length=.1,
        resolution=args.resolution, bounds=BOUNDS, tolerance=float(np.finfo(np.float32).eps),
        max_iterations=args.iterations)
    if args.footprints == "resolve":
        options["footprints"] = wind.Footprints(min_detail=args.min_detail,
            exposed_faces=args.exposed_faces == "on", fallback="error")
    context = (patch.object(_city, "reject_intersections", lambda *a, **kw: None)
               if args.footprints == "baseline" else nullcontext())
    with context:
        result = wind.run(make_city(prisms), **options)
    sample = result.sample(args.height, method="linear")
    if not np.isfinite(result.velocity).all():
        raise ValueError("Nonfinite velocity in synthetic solve")
    return dict(flags=result.cell_flags.copy(), plane=sample.velocity.copy(), valid=sample.valid.copy(),
        metadata=dict(diagnostics=asdict(result.diagnostics), versions=result.metadata["versions"],
            domain=result.metadata["domain"], model=result.metadata["model"],
            condition=result.metadata["condition"],
            velocity_sha256=digest(result.velocity), flags_sha256=digest(result.cell_flags),
            sampled_velocity_sha256=digest(sample.velocity),
            valid_sample_count=int(sample.valid.sum())))


def compare(a, b):
    valid = a["valid"] & b["valid"]
    if not valid.any():
        raise ValueError("Comparison has no common fluid samples")
    speed_a = np.linalg.norm(a["plane"][valid].astype(np.float64), axis=-1)
    speed_b = np.linalg.norm(b["plane"][valid].astype(np.float64), axis=-1)
    difference = np.abs(speed_a - speed_b) / SPEED
    solid_a = np.isin(a["flags"], [0, 2])
    solid_b = np.isin(b["flags"], [0, 2])
    iterations = [r["metadata"]["diagnostics"]["iterations"] for r in (a, b)]
    return dict(max_speed_difference_over_reference=float(difference.max()),
        rms_speed_difference_over_reference=float(np.sqrt(np.mean(difference ** 2))),
        common_fluid_samples=int(valid.sum()), same_solid_mask=bool(np.array_equal(solid_a, solid_b)),
        solid_mask_changed_cells=int(np.count_nonzero(solid_a != solid_b)),
        changed_fluid_flags=int(np.count_nonzero((a["flags"] != b["flags"]) & ~solid_a & ~solid_b)),
        iterations=iterations, same_iterations=iterations[0] == iterations[1],
        velocity_bit_identical=a["metadata"]["velocity_sha256"] == b["metadata"]["velocity_sha256"],
        flags_bit_identical=bool(np.array_equal(a["flags"], b["flags"])))


def run(args):
    if args.footprints == "resolve" and "footprints" not in inspect.signature(wind.run).parameters:
        raise ValueError("Resolve mode requires the public Footprints integration from a later plan step")
    if args.exposed_faces == "on" and args.footprints != "resolve":
        raise ValueError("Exposure on requires resolve mode and native exposure support")
    selected = [row for row in COMPARISONS if not args.case or row[0] in args.case]
    geometries = fixtures()
    snapshots, runs = {}, {}
    for name in dict.fromkeys(name for _, left, right in selected for name in (left, right)):
        print(f"Solving {name} ({args.resolution:g} m, up to {args.iterations} iterations)", file=sys.stderr, flush=True)
        try:
            snapshots[name] = solve(geometries[name], args)
            runs[name] = dict(status="solved", **snapshots[name]["metadata"])
        except ValueError as error:
            if args.footprints != "strict" or "overlapping or touching" not in str(error):
                raise
            runs[name] = dict(status="rejected", reason=str(error))
    comparisons = []
    for name, left, right in selected:
        row = dict(name=name, left=left, right=right)
        if left in snapshots and right in snapshots:
            row.update(status="compared", **compare(snapshots[left], snapshots[right]))
        else:
            row.update(status="rejected", reason="At least one input violates the strict contact contract")
        comparisons.append(row)
    return dict(schema_version=1, created_at=datetime.now(timezone.utc).isoformat(),
        provenance=source_manifest(), settings=dict(footprints=args.footprints,
            contact_check_bypassed=args.footprints == "baseline", exposed_faces=args.exposed_faces,
            min_detail=args.min_detail if args.footprints == "resolve" else None,
            resolution=args.resolution, vertical_grid="uniform", bounds=BOUNDS, sample_height=args.height,
            speed=SPEED, direction=270., reference_height=10., roughness_length=.1,
            max_iterations=args.iterations, tolerance=float(np.finfo(np.float32).eps),
            comparison_policy="all common fluid cell-centre x/y samples; interpolate velocity vertically before speed"),
        fixtures={name: [asdict(p) for p in geometries[name]] for name in runs},
        runs=runs, comparisons=comparisons)


def terminal_table(document):
    lines = ["comparison             max dU/Uref   RMS dU/Uref   same mask   iterations"]
    for row in document["comparisons"]:
        if row["status"] == "rejected":
            lines.append(f"{row['name']:<22} rejected by strict geometry contract")
        else:
            lines.append(f"{row['name']:<22} {row['max_speed_difference_over_reference']:12.6f} "
                f"{row['rms_speed_difference_over_reference']:13.6f} "
                f"{str(row['same_solid_mask']):>11}   {row['iterations']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--footprints", choices=("baseline", "strict", "resolve"), default="baseline")
    parser.add_argument("--exposed-faces", choices=("off", "on"), default="off")
    parser.add_argument("--min-detail", type=float, default=.5)
    parser.add_argument("--resolution", type=float, default=1.)
    parser.add_argument("--iterations", type=int, default=1500)
    parser.add_argument("--height", type=float, default=2.)
    parser.add_argument("--case", choices=[r[0] for r in COMPARISONS], action="append")
    parser.add_argument("--output", type=Path, default=Path("build/contact-artifacts.json"))
    args = parser.parse_args(argv)
    if args.iterations < 1 or not np.isfinite(args.min_detail) or args.min_detail <= 0:
        parser.error("iterations and min-detail must be positive")
    try:
        document = run(args)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    print(terminal_table(document))
    print(f"JSON: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
