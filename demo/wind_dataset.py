"""Fetch and solve a city slice; --no-show runs without an interactive plot."""
import argparse
from time import perf_counter
from dtcc_core import datasets
import dtcc_qes  # Registers the QES dataset.


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bounds",nargs=4,type=float,default=[319720,6397660,320720,6398660])
    parser.add_argument("--resolution",type=float,default=2.)
    parser.add_argument("--no-show",action="store_true")
    args=parser.parse_args(argv)
    start=perf_counter()
    result=datasets.qes_wind(bounds=args.bounds,speed=5.,direction=225,resolution=args.resolution,
        product="slice",slice_height=1.75)
    print(f"{perf_counter()-start:.3f} seconds")
    print(result)
    if not args.no_show:
        result.plot(field_name="speedup",presentation=False)
    return result


if __name__=="__main__":
    main()
