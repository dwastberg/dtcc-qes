# Research verification retained with V2

Production stays on main's legacy covariance. D1 tested research commit
`4eb119d` without changing its hashed native sources. The original D1 manifest
and report live in `docs/data/unified-v2/covariance-d1/`. The scripts below are
copies of the verification additions, adapted only to accept an explicit
research checkout. Use its installed Python environment:

```sh
export DTCC_QES_RESEARCH_ROOT=/path/to/research/checkout
/path/to/research/.venv/bin/python -m pytest research/unified_v2/test_covariance_limiter_v2.py -q
/path/to/research/.venv/bin/python research/unified_v2/verify_covariance_v2.py --output /tmp/new-d1-receipt
```

The replay requires the five frozen directed-improvements traces and samples
in that checkout, launches no wind solve, freezes all inputs before execution,
and enforces a 900-second total ceiling and 120-second subprocess ceilings.
The historical component bound remains offline only. Timing repetitions are
not physical observations.

`prior_geometry_witnesses.json` retains the closed campaign's E coarsening
witness patches. They compare a coarse cell with a fine raster, rather than
physical component polygons; they must not be presented as physical truth.
Stage C's exact physical comparison on archived E at 1.5 m is unavailable
because of roof crossings. Its prior rejection is preserved.
