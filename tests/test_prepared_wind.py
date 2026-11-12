"""Public preparation reuse: exact fresh-run parity, ownership and lifecycle."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import fields, replace
import gc
import importlib.util
from pathlib import Path
import threading

import numpy as np
import pytest
from shapely.geometry import box

from dtcc_core.model import Bounds, City
from dtcc_qes import _qes, _footprints, comfort, wind
from fixtures.cases import ONE_BUILDING
from fixtures.cities import city_case
from fixtures.footprints import building, city as footprint_city

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def without_clocks(value):
    if isinstance(value, dict):
        return {k: without_clocks(v) for k, v in value.items() if k not in ("timings", "elapsed_seconds")}
    if isinstance(value, list):
        return [without_clocks(v) for v in value]
    return value


def assert_same(actual, expected):
    for name in ("velocity", "cell_flags", "x", "y", "z", "z_faces"):
        a, b = getattr(actual, name), getattr(expected, name)
        assert a.dtype == b.dtype and a.shape == b.shape
        assert a.tobytes() == b.tobytes(), name
    assert actual.diagnostics == expected.diagnostics
    assert actual.origin == expected.origin and actual.crs == expected.crs
    assert actual.resolution == expected.resolution
    assert without_clocks(actual.metadata) == without_clocks(expected.metadata)
    assert (actual.turbulence is None) == (expected.turbulence is None)
    if actual.turbulence is not None:
        for field in fields(actual.turbulence):
            a, b = getattr(actual.turbulence, field.name), getattr(expected.turbulence, field.name)
            if isinstance(a, np.ndarray):
                assert a.dtype == b.dtype and a.shape == b.shape
                assert a.tobytes() == b.tobytes(), field.name
            else:
                assert a == b, field.name
    for height in (1.5, 1.75):
        a, b = actual.sample(height, method="linear"), expected.sample(height, method="linear")
        for name in ("velocity", "valid", "stress", "stress_valid"):
            np.testing.assert_array_equal(getattr(a, name), getattr(b, name))


@pytest.mark.parametrize("vertical", [None, wind.VerticalGrid.from_faces(np.r_[0, 1, 2, np.arange(4, 42, 2)]),
                                     wind.VerticalGrid.auto()])
@pytest.mark.parametrize("turbulence", [None, wind.Turbulence("height"), wind.Turbulence("wall_distance")])
def test_direction_order_and_precision_changes_match_fresh(vertical, turbulence):
    source, condition, grid, _ = city_case(ONE_BUILDING)
    profile = condition["profile"]
    options = dict(grid, vertical_grid=vertical, turbulence=turbulence)
    solver = wind.Solver(max_iterations=80)
    with wind.prepare(source, profile, **options, solver=solver) as model:
        for direction, precision in ((270, "float32"), (33, "float64"), (225, "float32"), (270, "float32")):
            current = profile.with_direction(direction)
            control = replace(solver, precision=precision)
            assert_same(model.run(current, solver=control), wind.run(source, current, **options, solver=control))


def test_cleaning_and_native_preparation_happen_once_and_outputs_are_independent(monkeypatch):
    source = footprint_city(building("podium", box(15, 15, 35, 35), 6),
                            building("tower", box(20, 20, 30, 30), 12))
    options = dict(bounds=(0, 0, 0, 60, 60, 60), footprints=wind.Footprints(min_detail=.1),
                   turbulence=wind.Turbulence(), solver=wind.Solver(max_iterations=40))
    profile = wind.LogProfile(5, 270)
    counts = dict(python=0, cleaning=0, native=0)
    original_city, original_clean, original_runner = wind._prepare_city, _footprints.prepare_footprints, _qes.WindRunner
    def prepare_city(*args, **kwargs):
        counts["python"] += 1
        return original_city(*args, **kwargs)
    def clean(*args, **kwargs):
        counts["cleaning"] += 1
        return original_clean(*args, **kwargs)
    class Runner:
        def __init__(self):
            self.native = original_runner()
        def prepare(self, *args, **kwargs):
            counts["native"] += 1
            return self.native.prepare(*args, **kwargs)
        def solve(self, *args, **kwargs):
            return self.native.solve(*args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(wind, "_prepare_city", prepare_city)
        patch.setattr(_footprints, "prepare_footprints", clean)
        patch.setattr(_qes, "WindRunner", Runner)
        with wind.prepare(source, profile, **options) as model:
            first = model.run(profile)
            original_metadata, original_velocity = deepcopy(first.metadata), first.velocity.copy()
            second = model.run(profile.with_direction(45))
            assert first.metadata == original_metadata
            np.testing.assert_array_equal(first.velocity, original_velocity)
            first.metadata["footprints"]["solids"].clear()
            first.metadata["terrain"].clear()
            first.metadata["ignored_city_objects"]["injected"] = 1
            first.metadata["domain"]["vertical_grid"]["effective_faces"].clear()
            first.velocity[:] = 0
            first.turbulence.stress[:] = 0
            third = model.run(profile)
            assert counts == dict(python=1, cleaning=1, native=1)
    assert_same(third, wind.run(source, profile, **options))
    assert_same(second, wind.run(source, profile.with_direction(45), **options))


def test_city_and_bounds_are_snapshots_and_new_preparation_uses_edits():
    source, condition, grid, _ = city_case(ONE_BUILDING)
    profile = condition["profile"]
    bounds = Bounds(xmin=0, ymin=0, zmin=0, xmax=80, ymax=60, zmax=40)
    solver = wind.Solver(max_iterations=30)
    expected = wind.run(source, profile, **grid, solver=solver)
    with wind.prepare(source, profile, bounds=bounds, solver=solver) as model:
        source.buildings[0].measured_height = 12
        source.buildings[0].lod0.vertices[:, 0] += 2
        bounds.xmax = 90
        assert_same(model.run(profile), expected)
    with wind.prepare(source, profile, bounds=bounds, solver=solver) as changed:
        actual = changed.run(profile)
    assert_same(actual, wind.run(source, profile, bounds=bounds, solver=solver))
    assert actual.velocity.shape != expected.velocity.shape


@pytest.mark.parametrize("mode", ["bounded", "adaptive"])
def test_control_and_monitoring_reset_between_conditions(mode):
    source, condition, grid, _ = city_case(ONE_BUILDING)
    profile = condition["profile"]
    solver = wind.Solver(max_iterations=300, max_solve_seconds=30,
        monitor=wind.MonitorSpec((0, 80, 0, 60), history_limit=20),
        policy="pedestrian-v1" if mode == "adaptive" else None)
    with wind.prepare(source, profile, **grid, solver=solver) as model:
        for direction in (270, 45, 270):
            current = profile.with_direction(direction)
            actual = model.run(current)
            assert_same(actual, wind.run(source, current, **grid, solver=solver))
            assert actual.metadata["timings"]["native"]["preparation_seconds"] == 0
            assert actual.solver["record"]["timings"]["preparation_seconds"] > 0


def test_profiles_and_speed_changes_reuse_geometry_and_refresh_layer_metadata():
    source, condition, grid, _ = city_case(ONE_BUILDING)
    options = dict(grid, vertical_grid=wind.VerticalGrid.auto(), solver=wind.Solver(max_iterations=20))
    profiles = [wind.UniformProfile(3, 20), wind.PowerLawProfile(4, 120, 10, .2),
                wind.MeasuredProfile([1, 10, 100], [2, 5, 7], directions=[10, 20, 30],
                                     reference_height=10, below="log"), condition["profile"].scaled(2)]
    with wind.prepare(source, **condition, **options) as model:
        for profile in profiles:
            assert_same(model.run(profile), wind.run(source, profile, **options))
        assert_same(model.run(speed=2, direction=45), wind.run(source, speed=2, direction=45, **options))


def test_invalid_conditions_and_failures_allow_retry():
    source, condition, grid, _ = city_case(ONE_BUILDING)
    profile = condition["profile"]
    solver = wind.Solver(max_iterations=20)
    expected = wind.run(source, profile, **grid, solver=solver)
    with wind.prepare(source, profile, **grid, solver=solver) as model:
        for change in (dict(reference_height=20), dict(roughness_length=.2)):
            with pytest.raises(ValueError, match="must match the prepared model"):
                model.run(replace(profile, **change))
        with pytest.raises(TypeError, match="both speed and direction"):
            model.run(direction=90)
        with pytest.raises(ValueError, match="mutually exclusive"):
            model.run(profile, direction=90)
        with pytest.raises(TypeError, match="solver must be Solver"):
            model.run(profile, solver={})
        with pytest.raises(TypeError):
            model.run(profile, resolution=4)
        with pytest.raises(ValueError, match="above last measurement"):
            model.run(wind.MeasuredProfile([1, 10], [2, 5], direction=270, reference_height=10,
                                          below="log", above="error"))
        with pytest.raises(wind.ConvergenceError):
            model.run(profile, solver=replace(solver, max_iterations=1, raise_on_failure=True))
        deadline = wind.Solver(max_solve_seconds=1e-12, monitor=wind.MonitorSpec((0, 80, 0, 60)))
        with pytest.raises(wind.BudgetExhaustedError):
            model.run(profile, solver=deadline)
        # Fails after native profile initialization, exercising workspace recovery.
        with pytest.raises((ValueError, RuntimeError), match="finite|Finite"):
            model.run(wind.LogProfile(1e38, 270))
        assert_same(model.run(profile), expected)


def resource_objects():
    return {k: v["objects"] for k, v in _qes._resource_usage().items() if isinstance(v, dict)}


def test_context_closes_resources_even_when_exception_traceback_is_retained():
    gc.collect()
    before = resource_objects()
    source, condition, grid, _ = city_case(ONE_BUILDING)
    with pytest.raises(wind.ConvergenceError) as retained:
        with wind.prepare(source, **condition, **grid,
                          solver=wind.Solver(max_iterations=1, raise_on_failure=True)) as model:
            model.run(**condition)
    assert retained.value is not None and model.closed
    assert resource_objects() == before
    model.close()
    with pytest.raises(RuntimeError, match="closed"):
        model.run(speed=5, direction=270)
    with pytest.raises(RuntimeError, match="closed"):
        with model:
            pass


def test_concurrent_calls_and_close_fail_without_corrupting_active_run(monkeypatch):
    source, condition, grid, _ = city_case(ONE_BUILDING)
    solver = wind.Solver(max_iterations=20)
    expected = wind.run(source, **condition, **grid, solver=solver)
    entered, release = threading.Event(), threading.Event()
    original = wind._solve_prepared
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    with wind.prepare(source, **condition, **grid, solver=solver) as model:
        monkeypatch.setattr(wind, "_solve_prepared", blocked)
        with ThreadPoolExecutor(1) as pool:
            pending = pool.submit(model.run, **condition)
            try:
                assert entered.wait(10)
                with pytest.raises(RuntimeError, match="already in use"):
                    model.run(**condition)
                with pytest.raises(RuntimeError, match="already in use"):
                    model.close()
            finally:
                release.set()
            assert_same(pending.result(timeout=10), expected)
        assert_same(model.run(**condition), expected)


def test_preflight_exception_does_not_keep_closed_native_model_alive(monkeypatch):
    gc.collect()
    before = resource_objects()
    source, condition, grid, _ = city_case(ONE_BUILDING)
    def fail(*args, **kwargs):
        raise ValueError("Injected preflight failure")
    with pytest.raises(ValueError, match="preflight failure") as retained:
        with wind.prepare(source, **condition, **grid) as model:
            # Exercise a pre-solve failure regardless of build qualification.
            monkeypatch.setattr(wind, "_preflight_eligibility", fail)
            model.run(**condition)
    assert retained.value is not None
    assert model.closed and resource_objects() == before


def test_preparation_timings_are_reported_once_and_copied():
    with wind.prepare(City(), speed=5, direction=270, bounds=(0, 0, 0, 24, 24, 32)) as model:
        setup = model.preparation_timings
        assert setup["total_seconds"] >= setup["city_preparation_seconds"] + setup["native_preparation_seconds"]
        setup["total_seconds"] = -1
        assert model.preparation_timings["total_seconds"] > 0
        for direction in (270, 90):
            timing = model.run(speed=5, direction=direction).metadata["timings"]
            assert timing["city_preparation_seconds"] == timing["native"]["preparation_seconds"] == 0
            assert timing["public_call_seconds"] > timing["condition_preparation_seconds"] > 0


def test_comfort_example_matches_fresh_fields_and_both_criteria():
    path = Path(__file__).resolve().parents[1] / "examples/wind_comfort.py"
    spec = importlib.util.spec_from_file_location("prepared_comfort_example", path)
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    directions = np.arange(0., 360., 30.)
    source = example.example_city()
    actual = example.directional_results(source, directions)
    solver = wind.Solver(max_solve_seconds=10, monitor=wind.MonitorSpec((0, 80, 0, 60)), raise_on_failure=True)
    expected = [wind.run(source, wind.LogProfile(example.REFERENCE_SPEED, float(direction)), resolution=2.,
        bounds=(0, 0, 0, 80, 60, 40), vertical_grid=wind.VerticalGrid.from_faces(example.FACES),
        turbulence=wind.Turbulence(), solver=solver) for direction in directions]
    for a, b in zip(actual, expected):
        assert_same(a, b)
    speeds, climate_directions, times = example.synthetic_climate()
    for criterion in (comfort.NEN8100, comfort.CITY_OF_LONDON):
        options = dict(height=example.PEDESTRIAN_HEIGHT, times=times,
                       peak_factor=example.PEAK_FACTOR, gust_ratio=example.GUST_RATIO)
        a = comfort.assess_results(actual, speeds, climate_directions, criterion, **options)
        b = comfort.assess_results(expected, speeds, climate_directions, criterion, **options)
        for name in ("comfort", "safety"):
            np.testing.assert_array_equal(getattr(a, name), getattr(b, name))
        for name in ("exceedance", "seasonal"):
            for key in getattr(a, name):
                np.testing.assert_array_equal(getattr(a, name)[key], getattr(b, name)[key])
        assert a.metadata == b.metadata and a.warnings == b.warnings
