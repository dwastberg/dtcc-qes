"""Fetch a city and return a native DTCC wind field or slice (requires network)."""

import argparse

from dtcc_core import datasets
import dtcc_qes.datasets  # Registers the optional GPL QES dataset.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bounds", nargs=4, type=float, metavar="COORD",
                        help="xmin ymin xmax ymax in EPSG:3006")
    parser.add_argument("--product", choices=("field", "slice"), default="field")
    parser.add_argument("--resolution", type=float, default=2.0, help="Solver cell spacing in metres")
    parser.add_argument("--wind-speed", type=float, default=5.0)
    parser.add_argument("--wind-direction", type=float, default=270.0)
    args = parser.parse_args()
    # The dataset preserves height steps and fills source/region courtyards.
    # Its context records source-to-solid mappings and any tallest-height fallback.
    result = datasets.qes_wind(**vars(args))
    print(result)
    print(result.provenance.processing_steps[-1]["diagnostics"])
    return result


if __name__ == "__main__":
    main()
