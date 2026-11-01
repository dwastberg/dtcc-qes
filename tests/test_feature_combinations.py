"""Combined contracts; real deterministic deadlines/preflight land in Phase 9.

The full 17-invariant inventory also uses the focused profile, qualification,
comfort, dataset, validation and monitor suites; the phase evidence maps them.
"""

from copy import deepcopy
import json

import numpy as np
import pytest
from dtcc_qes import _qes, wind
from fixtures.cases import ONE_BUILDING
from fixtures.cities import city_case
from fixtures.condition_state import configuration
from fixtures.specs import native_turbulence

pytestmark = pytest.mark.usefixtures("dtcc_logger")
PROFILES = [
    wind.LogProfile(5, 270),
    wind.UniformProfile(5, 270),
    wind.PowerLawProfile(5, 270, 10, 0.2),
    wind.MeasuredProfile(
        [1, 10, 100],
        [2, 5, 7],
        directions=[350, 270, 240],
        reference_height=10,
        below="log",
    ),
]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("grid", [None, wind.VerticalGrid.auto()])
def test_monitoring_and_turbulence_preserve_mean_wind_at_fixed_work(profile, grid):
    city, _, _, _ = city_case(ONE_BUILDING)
    base = dict(bounds=(0, 0, 0, 80, 60, 40), vertical_grid=grid)
    preview = wind.preview_grid(city, profile, **base, turbulence=wind.Turbulence())
    # Freeze the complete physical grid for turbulence A/B comparisons.
    faces = np.r_[0.0, np.cumsum(preview.solver_dz.astype(float))]
    options = dict(
        bounds=(*base["bounds"][:5], float(faces[-1])),
        vertical_grid=wind.VerticalGrid.from_faces(faces),
    )
    solver = wind.Solver(tolerance=float(np.finfo(np.float32).eps), max_iterations=8)
    monitor = wind.MonitorSpec((0, 80, 0, 60))
    monitored = wind.Solver(
        tolerance=solver.tolerance,
        max_iterations=8,
        max_solve_seconds=60,
        monitor=monitor,
    )
    a = wind.run(city, profile, **options, solver=solver)
    b = wind.run(city, profile, **options, solver=solver, turbulence=wind.Turbulence())
    c = wind.run(
        city, profile, **options, solver=monitored, turbulence=wind.Turbulence()
    )
    assert a.diagnostics == b.diagnostics == c.diagnostics
    assert a.diagnostics.iterations == 8
    for result in (b, c):
        np.testing.assert_array_equal(a.velocity, result.velocity)
        np.testing.assert_array_equal(a.z_faces, result.z_faces)
    for field in (
        "stress",
        "tke",
        "co_eps",
        "mixing_length",
        "computed",
        "capped",
        "stress_valid",
    ):
        np.testing.assert_array_equal(
            getattr(b.turbulence, field), getattr(c.turbulence, field)
        )
    assert c.qualification["solver"]["assessment"] == "not_requested"
    assert c.solver["record"]["accuracy_status"] == "not_assessed"
    json.dumps(c.metadata, allow_nan=False)


@pytest.mark.parametrize("precision", ["float32", "float64"])
@pytest.mark.parametrize("method", [0, 1])
def test_reused_native_runner_alternates_log_and_tables_with_turbulence(
    precision, method
):
    grid, model, arrays = configuration()

    def prepared():
        runner = _qes.WindRunner()
        runner.prepare(grid, model, **arrays, turbulence=native_turbulence(method))
        return runner

    options = _qes.SolverOptions()
    options.max_iterations = 8
    options.precision = precision
    log = _qes.WindCondition()
    log.speed = 5
    log.direction = 270
    log.reference_height = 10
    table = _qes.WindCondition()
    table.profile_kind = _qes.ProfileKind.layer_table
    table.layer_u = [2 + i * 0.1 for i in range(grid.nz)]
    table.layer_v = [1 - i * 0.1 for i in range(grid.nz)]
    table.speed = 5
    table.direction = 270
    table.reference_height = 10
    reused = prepared()
    for condition in (log, table, log, table):
        actual = reused.solve(condition, options)
        expected = prepared().solve(condition, options)
        for name in ("velocity", "cell_flags", "x", "y", "z", "z_faces"):
            np.testing.assert_array_equal(actual[name], expected[name])
        assert actual["diagnostics"] == expected["diagnostics"]
        for name in (
            "stress",
            "tke",
            "co_eps",
            "mixing_length",
            "state",
            "stress_valid",
        ):
            np.testing.assert_array_equal(
                actual["turbulence"][name], expected["turbulence"][name]
            )


def test_disabled_features_do_not_construct_native_options(monkeypatch):
    city, _, grid, _ = city_case(ONE_BUILDING)
    monkeypatch.setattr(
        _qes,
        "TurbulenceSettings",
        lambda: pytest.fail("constructed turbulence options"),
    )
    monkeypatch.setattr(
        wind.Solver,
        "_native",
        lambda *a: pytest.fail("constructed native monitor/control"),
    )
    result = wind.run(city, speed=5, direction=270, **grid)
    assert result.turbulence is None and result.solver["record"] is None


@pytest.mark.parametrize(
    "profile,precision,turbulence",
    [
        (PROFILES[1], "float32", None),
        (PROFILES[0], "float64", None),
        (PROFILES[0], "float32", wind.Turbulence()),
    ],
)
def test_excluded_adaptive_raises_before_native_allocation(
    profile, precision, turbulence, monkeypatch
):
    city, _, grid, _ = city_case(ONE_BUILDING)
    solver = wind.Solver(
        max_solve_seconds=60,
        monitor=wind.MonitorSpec((0, 80, 0, 60)),
        policy="pedestrian-v1",
        precision=precision,
        raise_on_failure=True,
    )
    monkeypatch.setattr(
        _qes, "WindRunner", lambda: pytest.fail("allocated native runner")
    )
    with pytest.raises(wind.UnacceptedResultError) as error:
        wind.run(city, profile, solver=solver, turbulence=turbulence, **grid)
    assert error.value.diagnostics is None and error.value.record is None
    assert error.value.exclusions


@pytest.mark.parametrize("converged", [False, True])
def test_completed_work_deadline_turbulence_warning_and_wind_basis(
    converged, monkeypatch, caplog
):
    # Exercise Python mapping with a manufactured native record. Phase 9 adds
    # pure-C++ clock execution to establish the real completed sweep count.
    city, condition, grid, _ = city_case(ONE_BUILDING)
    original = _qes.WindRunner

    class DeadlineRunner:
        def __init__(self):
            self.runner = original()

        def prepare(self, *a, **kw):
            self.runner.prepare(*a, **kw)

        def solve(self, *a, **kw):
            native = self.runner.solve(*a, **kw)
            native["diagnostics"]["converged"] = converged
            native["control"]["termination_reason"] = "time_limit"
            return native

    monkeypatch.setattr(_qes, "WindRunner", DeadlineRunner)
    solver = wind.Solver(
        max_iterations=8, max_solve_seconds=60, monitor=wind.MonitorSpec((0, 80, 0, 60))
    )
    result = wind.run(
        city, **condition, **grid, solver=solver, turbulence=wind.Turbulence()
    )
    basis = result.qualification["turbulence"]["wind_basis"]
    assert basis["execution"] == "time_limit" and basis["legacy_converged"] == converged
    assert basis["assessment"] == "not_requested"
    warnings = [
        r for r in caplog.records if r.name == "dtcc-qes" and r.levelname == "WARNING"
    ]
    assert len(warnings) == 1 and "screening output" in warnings[0].message
    before = deepcopy(result.solver["record"])
    result.qualification["turbulence"]["wind_basis"]["execution"] = "edited"
    assert result.solver["record"] == before
