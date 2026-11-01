"""Fetch a city and return a native DTCC wind field or slice (requires network)."""

import argparse
import json
from pathlib import Path

from dtcc_core import datasets
import dtcc_qes.datasets  # Registers the optional GPL QES dataset.
from dtcc_qes import wind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bounds", nargs=4, type=float, metavar="COORD",
                        help="xmin ymin xmax ymax in EPSG:3006")
    parser.add_argument("--product", choices=("field", "slice"), default="field")
    parser.add_argument("--resolution", type=float, default=2.0, help="Horizontal spacing; also vertical spacing in uniform mode")
    parser.add_argument("--vertical-grid", choices=("uniform", "auto"), default="uniform",
                        help="auto uses experimental vertical layers and requires --product slice")
    parser.add_argument("--pedestrian-height", type=float, default=1.5)
    parser.add_argument("--growth-rate", type=float, default=1.15)
    parser.add_argument("--solver-precision", choices=("float32", "float64"), default="float32")
    parser.add_argument("--slice-height", type=float)
    parser.add_argument("--slice-sampling", choices=("nearest", "linear"), default="nearest",
                        help="linear supports horizontal slices; display x/y sampling remains nearest")
    parser.add_argument("--speed", type=float)
    parser.add_argument("--direction", type=float)
    parser.add_argument("--profile",type=Path,help="Path to a versioned profile JSON payload")
    parser.add_argument("--turbulence",choices=("height","wall_distance"))
    args = parser.parse_args()
    # The dataset preserves height steps and fills source/region courtyards.
    # Its context records source-to-solid mappings and any tallest-height fallback.
    request = vars(args)
    precision = request.pop("solver_precision")
    request["solver"] = wind.Solver(precision=precision).to_dict()
    profile=request.pop("profile")
    if profile is not None:
        request["profile"] = json.loads(profile.read_text())
    for name in ("speed","direction"):
        if request[name] is None:
            request.pop(name)
    turbulence=request.pop("turbulence")
    if turbulence is not None:
        request["turbulence"] = wind.Turbulence(turbulence).to_dict()
    result = datasets.qes_wind(**request)
    print(result)
    print(result.provenance.processing_steps[-1]["diagnostics"])
    return result


if __name__ == "__main__":
    main()
