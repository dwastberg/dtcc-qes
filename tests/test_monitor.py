"""Native S3 observations versus full finalization and public/study sampling."""

from fixtures.support import load_tool
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from dtcc_qes import _qes
from dtcc_qes.result import SolveDiagnostics, WindResult

ROOT = Path(__file__).resolve().parents[1]
study = load_tool("monitor_study_collocation", ROOT/"tools/run_auto_grid_controls.py")


def executable():
    path = Path(os.environ.get("DTCC_QES_MONITOR_EXECUTABLE",
        ROOT/"build"/("openmp" if _qes.openmp_enabled else "serial")/"check_monitor"))
    if not path.exists():
        pytest.skip("Build the native check_monitor target for monitor/public-sampler parity")
    return path


def close(actual, expected):
    actual, expected = np.asarray(actual,float),np.asarray(expected,float)
    np.testing.assert_array_equal(np.isfinite(actual),np.isfinite(expected))
    valid = np.isfinite(expected)
    tolerance = 4*np.spacing(np.asarray(np.maximum(1,np.abs(expected[valid])),np.float32)).astype(float)
    assert np.all(np.abs(actual[valid]-expected[valid]) <= tolerance)


@pytest.mark.parametrize("precision", ["float32","float64"])
@pytest.mark.parametrize("grid", ["uniform","stretched"])
@pytest.mark.parametrize("frame", ["local","world"])
def test_native_monitor_matches_public_planes_and_study_receptors(precision,grid,frame):
    process = subprocess.run([str(executable()),"--dump",precision,grid,frame],
                             capture_output=True,text=True,check=True,timeout=30)
    raw = json.loads(process.stdout)
    x,y,z,faces = (np.asarray(raw[name],np.float32) for name in ("x","y","z","z_faces"))
    velocity = np.zeros((len(z),len(y),len(x),3),np.float32)
    flags = np.zeros(velocity.shape[:-1],np.int32)
    # Native finalization materializes the entire field; the probe transports
    # only query-support layers. Every query uses its original full z axis.
    for slab in raw["materialized"]:
        velocity[slab["layer"]] = np.asarray(slab["velocity"],np.float32).reshape(len(y),len(x),3)
        flags[slab["layer"]] = np.asarray(slab["flags"],np.int32).reshape(len(y),len(x))
    result = WindResult(velocity,x,y,z,flags,tuple(raw["origin"]),None,2.,
                        SolveDiagnostics(37,0,1e-5,False,precision=precision),{},faces)
    n = len(x)*len(y)
    samples = raw["samples"]
    for h,height in enumerate(raw["heights"]):
        expected = result.sample(height,method="linear")
        monitor = samples[h*n:(h+1)*n]
        actual_valid = np.array([s["valid"] for s in monitor]).reshape(len(y),len(x))
        np.testing.assert_array_equal(actual_valid,expected.valid)
        close(np.array([s["velocity"] for s in monitor],float).reshape(len(y),len(x),3),expected.velocity)
    for r,(rx,ry,height) in enumerate(raw["receptors"]):
        if raw["world"]:
            rx -= raw["origin"][0]
            ry -= raw["origin"][1]
        actual = samples[len(raw["heights"])*n+r]
        if rx < x[0] or rx > x[-1] or ry < y[0] or ry > y[-1]:
            assert not actual["valid"]
            continue
        plane = result.sample(height,method="linear")
        points = sorted(set([rx,ry]))
        values = [v.tolist() if good else None for v,good in zip(plane.velocity.reshape(-1,3),plane.valid.ravel())]
        reference = study.collocate(values,x.astype(float),y.astype(float),points)
        expected = reference[points.index(ry)*len(points)+points.index(rx)]
        assert actual["valid"] == (expected is not None)
        if expected is not None:
            close(actual["velocity"],expected)
    assert raw["allocated_bytes"] <= raw["planned_bytes"] < 64*1024**2
