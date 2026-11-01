import ast
from dataclasses import FrozenInstanceError
from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

from dtcc_qes import comfort


def test_gem_formula_and_nan_propagation():
    speed = np.array([[0, 5, np.nan], [2, 4, 6]], dtype=np.float32)
    std = np.array([[0, .5, 1], [np.nan, 2, 3]], dtype=np.float32)
    before = speed.copy(), std.copy()
    actual = comfort.gust_equivalent_mean(speed, std, peak_factor=3)
    np.testing.assert_array_equal(actual, (speed.astype(float)+3*std.astype(float))/1.85)
    assert actual.dtype == np.float64 and actual.shape == speed.shape
    assert not np.shares_memory(actual, speed) and not np.shares_memory(actual, std)
    np.testing.assert_array_equal(speed, before[0])
    np.testing.assert_array_equal(std, before[1])
    custom = comfort.gust_equivalent_mean([2, 4], [.5, 1], peak_factor=2, gust_ratio=2)
    np.testing.assert_array_equal(custom, [1.5, 3])
    scalar = comfort.gust_equivalent_mean(4., 2., peak_factor=3.)
    assert isinstance(scalar, np.ndarray) and scalar.shape == () and scalar.dtype == np.float64
    assert scalar == pytest.approx(10/1.85)
    assert "gust_equivalent_mean" in comfort.__all__
    with pytest.raises(TypeError):
        comfort.gust_equivalent_mean(speed, std)


@pytest.mark.parametrize("name", ["peak_factor", "gust_ratio"])
@pytest.mark.parametrize("value", [0, -1, np.nan, np.inf, -np.inf, True, None, [3.], np.array([3.]),
                                 np.array(True), 3j, np.array(3j), 10**400])
def test_gem_rejects_bad_factors(name, value):
    options = dict(peak_factor=3., gust_ratio=1.85)
    options[name] = value
    with pytest.raises(ValueError, match=name):
        comfort.gust_equivalent_mean([5.], [1.], **options)


@pytest.mark.parametrize("speed,std", [([-1], [1]), ([1], [-1]), ([np.inf], [1]),
    ([1], [-np.inf]), ([1], [np.inf]), ([1, 2], [1]), ([[1]], [1]), ([1], ["bad"])])
def test_gem_rejects_bad_arrays(speed, std):
    with pytest.raises(ValueError):
        comfort.gust_equivalent_mean(speed, std, peak_factor=3.)


def test_gem_rejects_overflow_without_runtime_warning():
    with np.errstate(all="raise"), pytest.raises(ValueError, match="overflow"):
        comfort.gust_equivalent_mean([1e308], [1e308], peak_factor=3.)


def test_gem_fields_remove_only_mean_only_warning():
    arguments = ([5.], [0.], np.full((1, 2), 5.), [0.], 5., comfort.CITY_OF_LONDON)
    mean = comfort.assess(*arguments, height=1.)
    both = comfort.assess(*arguments, height=1., gem_fields=np.full((1, 2), 6.))
    assert any("Mean speeds only" in warning for warning in mean.warnings)
    assert not any("Mean speeds only" in warning for warning in both.warnings)
    assert all(warning in both.warnings for warning in mean.warnings if "Mean speeds only" not in warning)
    assert any("provenance" in warning.lower() and "unspecified" in warning.lower() for warning in both.warnings)


@pytest.mark.parametrize("identification", [
    dict(source="dtcc_qes.wind"), dict(model="QES-Turb algebraic mixing-length model"),
    dict(numerics_version="dtcc-qes-turbulence-v1"),
])
def test_qes_gem_metadata_and_screening_warning_survive_assess(identification):
    provenance = dict(identification, peak_factor=3., gust_ratio=1.85,
        mean_averaging_time="unspecified", gust_averaging_time="unspecified",
        validity_policy="raw_and_mask", limitations=["not validated for pedestrian gusts"],
        assumptions=dict(peak_factor="user-selected screening assumption"))
    expected = deepcopy(provenance)
    result = comfort.assess([5.], [0.], [[5.]], [0.], 5., comfort.CITY_OF_LONDON,
                            gem_fields=[[6.]], gem_metadata=provenance)
    assert result.metadata["gem"] == expected
    assert any("QES-Turb" in warning and "not validated for pedestrian gusts" in warning
               for warning in result.warnings)
    assert not any("Mean speeds only" in warning for warning in result.warnings)
    provenance["limitations"].append("edited")
    provenance["assumptions"]["peak_factor"] = "edited"
    assert result.metadata["gem"] == expected
    assert result.metadata["speed_measure"] == "mean and GEM"


def test_gem_metadata_validation_and_external_sources():
    arguments = ([5.], [0.], [[5.]], [0.], 5., comfort.CITY_OF_LONDON)
    for metadata in ({}, {"source": "QES-Turb"}):
        with pytest.raises(ValueError, match="gem_metadata.*gem_fields"):
            comfort.assess(*arguments, gem_metadata=metadata)
    with pytest.raises(ValueError, match="gem_metadata.*mapping"):
        comfort.assess(*arguments, gem_fields=[[6.]], gem_metadata="QES-Turb")
    external = {"source": "external wind tunnel", "gust_averaging_time": "3 s"}
    result = comfort.assess(*arguments, gem_fields=[[6.]], gem_metadata=external)
    assert result.metadata["gem"] == external
    assert not any("QES-Turb" in warning for warning in result.warnings)
    assert "gem" not in comfort.assess(*arguments).metadata


@pytest.mark.usefixtures("dtcc_logger")
@pytest.mark.parametrize("method", ["height", "wall_distance"])
def test_gem_from_runs_scales_with_reference_speed(method):
    from fixtures.cities import city_case
    from fixtures.cases import ONE_BUILDING
    from dtcc_qes import wind

    fields, estimates, assessments = [], [], []
    directions = [225., 270.]
    climate_speed, climate_direction, _, _ = random_case(hours=1000)
    for speed in (5., 10.):
        means, gems = [], []
        for direction in directions:
            city, condition, grid, solver = city_case(ONE_BUILDING)
            condition["profile"] = wind.LogProfile(speed,direction)
            solver["solver"] = wind.Solver(tolerance=1e-7*speed/5, max_iterations=2000, precision="float64")
            run = wind.run(city, **condition, **grid, **solver, turbulence=wind.Turbulence(method))
            assert run.diagnostics.converged
            sample = run.sample(1.5, "linear")
            means.append(sample.speed)
            gems.append(comfort.gust_equivalent_mean(sample.speed, sample.streamwise_std, peak_factor=3.))
        fields.append(np.stack(means))
        estimates.append(np.stack(gems))
        assessments.append(comfort.assess(climate_speed, climate_direction, fields[-1], directions, speed,
                           comfort.CITY_OF_LONDON, gem_fields=estimates[-1], height=1.5))
    np.testing.assert_allclose(estimates[1], 2*estimates[0], rtol=1e-4, atol=1e-7, equal_nan=True)
    for attribute in ("comfort", "safety"):
        np.testing.assert_array_equal(getattr(assessments[0], attribute), getattr(assessments[1], attribute))
    assert (assessments[0].comfort >= 0).any()
    assert (assessments[0].comfort == -1).any()


def test_invalid_stress_and_undefined_direction_remain_unassessed():
    from fixtures.turbulence import synthetic

    source = synthetic()
    source.turbulence.stress[:, 0, 0] = [1, 2, 0, 1, 0, 1]
    source.velocity[:, 0, 1] = 0
    source.turbulence.computed[:, 0, 2] = False
    raw = source.turbulence.stress.copy()
    sample = source.sample(1.5, "linear")
    gem = comfort.gust_equivalent_mean(sample.speed, sample.streamwise_std, peak_factor=3.)
    assert np.isnan(gem[0, :3]).all()
    # The invalid GEM direction is unused by the climate; coverage stays conservative.
    fields = np.stack([np.full_like(sample.speed, 5), sample.speed])
    gems = np.stack([np.full_like(gem, 5), gem])
    result = comfort.assess([5.]*4, [0.]*4, fields, [0., 90.], 5., comfort.CITY_OF_LONDON,
        gem_fields=gems, times=np.array(["2023-01-01", "2023-04-01", "2023-07-01", "2023-10-01"],
                                       dtype="datetime64[D]"))
    assert (result.comfort[0, :3] == -1).all() and (result.safety[0, :3] == -1).all()
    for values in result.exceedance.values():
        assert np.isnan(values[0, :3]).all()
    for values in result.seasonal.values():
        assert (values[0, :3] == -1).all()
    assert (result.comfort[1:] >= 0).all()
    np.testing.assert_array_equal(source.turbulence.stress, raw)


def one_direction(values, total, low=1.0):
    """Hourly speeds ``values`` padded with ``low`` to ``total`` hours, all from north."""
    speeds = np.r_[values, np.full(total - len(values), low)]
    return speeds, np.zeros(total)


def assess_uniform(speeds, directions, criterion, **options):
    """A single cell with speed-up 1 from the only simulated direction."""
    return comfort.assess(speeds, directions, np.full((1, 1, 1), 5.0), [0.0], 5.0, criterion, **options)


def hourly_pedestrian_speeds(speeds, directions, fields, field_directions, reference_speed):
    """Brute force: (T, ...) pedestrian speeds, one hour at a time."""
    ratios = np.asarray(fields) / reference_speed
    distances = np.abs((np.asarray(directions)[:, None] - np.asarray(field_directions)[None, :] + 180) % 360 - 180)
    return ratios[np.argmin(distances, axis=1)] * np.asarray(speeds)[:, None, None]


def random_case(seed=3, hours=2000):
    rng = np.random.default_rng(seed)
    speeds = np.round(rng.weibull(2.0, hours) * 6.0, 1)
    directions = rng.uniform(0, 360, hours)
    field_directions = np.array([10.0, 100.0, 170.0, 250.0, 300.0])
    fields = rng.uniform(0, 10, (5, 4, 6))
    fields[2, 1, 1] = 0
    return speeds, directions, fields, field_directions


@pytest.mark.parametrize("threshold", [0.0, 2.5, 5.0, 9.0])
def test_exceedance_matches_hourly_brute_force(threshold):
    speeds, directions, fields, field_directions = random_case()
    pedestrian = hourly_pedestrian_speeds(speeds, directions, fields, field_directions, 5.0)
    np.testing.assert_array_equal(
        comfort.exceedance(speeds, directions, fields, field_directions, 5.0, threshold),
        (pedestrian > threshold).mean(axis=0))


@pytest.mark.parametrize("fraction", [0.05, 0.2, 0.00022])
def test_speed_at_exceedance_brackets_exact_quantile(fraction):
    speeds, directions, fields, field_directions = random_case(seed=5)
    pedestrian = hourly_pedestrian_speeds(speeds, directions, fields, field_directions, 5.0)
    expected = np.empty(fields.shape[1:])
    for index in np.ndindex(expected.shape):
        values = pedestrian[(slice(None),) + index]
        candidates = np.r_[0.0, np.unique(values)]
        above = (values[None, :] > candidates[:, None]).mean(axis=1)
        expected[index] = candidates[np.argmax(above <= fraction)]
    result = comfort.speed_at_exceedance(speeds, directions, fields, field_directions, 5.0, fraction,
                                         tolerance=0.01)
    assert np.all(result >= expected) and np.all(result <= expected + 0.01)


def test_nearest_direction_wraps_and_breaks_ties_towards_earlier_field():
    directions = [355, 44, 46, 45, 150, 145, 360, 730, -20]
    hourly = comfort._Hourly(np.ones(len(directions)), directions, [0, 90, 200])
    np.testing.assert_array_equal(hourly.sectors, [0, 0, 1, 0, 2, 1, 0, 0, 0])
    unordered = comfort._Hourly(np.ones(len(directions)), directions, [200, 90, 360])
    np.testing.assert_array_equal(unordered.sectors, [2, 2, 1, 1, 0, 0, 2, 2, 2])


def test_speed_up_uses_reference_speed_per_direction():
    speeds, directions, fields, field_directions = random_case()
    expected = comfort.exceedance(speeds, directions, fields, field_directions, 5.0, 4.0)
    np.testing.assert_array_equal(
        comfort.exceedance(speeds, directions, 2 * fields, field_directions, 10.0, 4.0), expected)
    references = np.array([1.0, 2.0, 4.0, 8.0, 0.5])
    scaled = fields * (references / 5.0)[:, None, None]
    np.testing.assert_allclose(
        comfort.exceedance(speeds, directions, scaled, field_directions, references, 4.0), expected)


@pytest.mark.parametrize("above,grade", [(0, "A"), (24, "A"), (25, "B"), (49, "B"), (50, "C"),
                                         (99, "C"), (100, "D"), (199, "D"), (200, "E"), (1000, "E")])
def test_nen8100_comfort_classes_are_half_open(above, grade):
    result = assess_uniform(*one_direction(np.full(above, 6.0), 1000), comfort.NEN8100)
    assert comfort.NEN8100.comfort.labels[result.comfort.item()] == grade
    assert result.exceedance[5.0].item() == above / 1000


@pytest.mark.parametrize("above,label", [(0, "no risk"), (5, "no risk"), (6, "limited risk"),
                                         (29, "limited risk"), (30, "dangerous")])
def test_nen8100_danger_limits(above, label):
    result = assess_uniform(*one_direction(np.full(above, 16.0), 10000), comfort.NEN8100)
    assert comfort.NEN8100.safety.labels[result.safety.item()] == label


def test_nen8100_activity_ratings_follow_comfort_class():
    result = assess_uniform(*one_direction(np.full(60, 6.0), 1000), comfort.NEN8100)
    assert comfort.NEN8100.comfort.labels[result.comfort.item()] == "C"
    labels = comfort.NEN8100.activity_labels
    assert [labels[result.activity(name).item()] for name in ("traversing", "strolling", "sitting")] == [
        "good", "moderate", "poor"]
    with pytest.raises(ValueError, match="activity"):
        result.activity("cycling")


@pytest.mark.parametrize("values,label", [
    ([3.0] * 50, "frequent sitting"),
    ([5.0] * 50 + [3.0], "occasional sitting"),
    ([5.0] * 51, "standing"),
    ([7.0] * 51, "walking"),
    ([9.0] * 51, "uncomfortable"),
])
def test_city_of_london_comfort_allows_exactly_five_percent(values, label):
    result = assess_uniform(*one_direction(values, 1000), comfort.CITY_OF_LONDON)
    assert comfort.CITY_OF_LONDON.comfort.labels[result.comfort.item()] == label


@pytest.mark.parametrize("above,label", [(22, "safe"), (23, "unsafe")])
def test_city_of_london_safety_limit(above, label):
    result = assess_uniform(*one_direction(np.full(above, 16.0), 100_000), comfort.CITY_OF_LONDON)
    assert comfort.CITY_OF_LONDON.safety.labels[result.safety.item()] == label


def test_gust_equivalent_mean_takes_worse_of_mean_and_gem():
    speeds, directions, fields, field_directions = random_case()
    fields *= 0.3  # speed-ups up to 0.6 spread cells over the comfort classes
    rng = np.random.default_rng(11)
    gem = fields * rng.uniform(0.6, 1.6, fields.shape)
    options = dict(criterion=comfort.CITY_OF_LONDON)
    mean_only = comfort.assess(speeds, directions, fields, field_directions, 5.0, **options)
    gem_only = comfort.assess(speeds, directions, gem, field_directions, 5.0, **options)
    both = comfort.assess(speeds, directions, fields, field_directions, 5.0, gem_fields=gem, **options)
    np.testing.assert_array_equal(both.comfort, np.maximum(mean_only.comfort, gem_only.comfort))
    np.testing.assert_array_equal(both.safety, np.maximum(mean_only.safety, gem_only.safety))
    for speed, fraction in both.exceedance.items():
        np.testing.assert_array_equal(fraction, np.maximum(mean_only.exceedance[speed], gem_only.exceedance[speed]))
    assert len(set(both.comfort.ravel())) > 2
    assert (both.comfort > mean_only.comfort).any() and (both.comfort == mean_only.comfort).any()
    assert any("Mean speeds only" in warning for warning in mean_only.warnings)
    assert not any("Mean speeds only" in warning for warning in both.warnings)
    assert both.metadata["speed_measure"] == "mean and GEM"
    with pytest.raises(ValueError, match="mean speeds"):
        comfort.assess(speeds, directions, fields, field_directions, 5.0, comfort.NEN8100, gem_fields=gem)
    with pytest.raises(ValueError, match="same shape"):
        comfort.assess(speeds, directions, fields, field_directions, 5.0, gem_fields=gem[:, :2], **options)


def year_of_hours():
    return np.datetime64("2023-01-01T00") + np.arange(8760).astype("timedelta64[h]")


def test_city_of_london_reports_worst_season_and_summer():
    times = year_of_hours()
    speeds = np.where(np.arange(8760) < 300, 7.0, 1.0)  # windy first days of January only
    directions = np.zeros(8760)
    annual = assess_uniform(speeds, directions, comfort.CITY_OF_LONDON)
    seasonal = assess_uniform(speeds, directions, comfort.CITY_OF_LONDON, times=times)
    labels = comfort.CITY_OF_LONDON.comfort.labels
    assert labels[annual.comfort.item()] == "frequent sitting"
    assert any("Pass times" in warning for warning in annual.warnings)
    assert labels[seasonal.comfort.item()] == "walking"
    assert labels[seasonal.seasonal["winter"].item()] == "walking"
    assert labels[seasonal.seasonal["summer"].item()] == "frequent sitting"
    assert seasonal.metadata["comfort_period"] == "worst season"
    assert seasonal.safety.item() == annual.safety.item() == 0
    assert not any("Pass times" in warning for warning in seasonal.warnings)
    with pytest.raises(ValueError, match="autumn"):
        assess_uniform(speeds[:5000], directions[:5000], comfort.CITY_OF_LONDON, times=times[:5000])
    with pytest.raises(ValueError, match="datetime64"):
        assess_uniform(speeds, directions, comfort.CITY_OF_LONDON, times=np.arange(8760))
    nen = assess_uniform(speeds, directions, comfort.NEN8100, times=times)
    assert nen.metadata["comfort_period"] == "all hours" and nen.seasonal == {}


def test_missing_and_calm_hours():
    speeds = [6.0, np.nan, 1.0, 0.0, np.inf]
    directions = [0.0, 0.0, np.nan, np.nan, 0.0]
    result = assess_uniform(speeds, directions, comfort.NEN8100)
    assert (result.metadata["hours"], result.metadata["missing_hours"], result.metadata["calm_hours"]) == (2, 3, 1)
    assert result.exceedance[5.0].item() == 0.5
    assert result.metadata["hours_per_direction"] == [2]


def test_invalid_cells_are_marked():
    speeds, directions, fields, field_directions = random_case()
    fields[3, 0, 2] = np.nan
    result = comfort.assess(speeds, directions, fields, field_directions, 5.0, comfort.NEN8100)
    assert result.comfort[0, 2] == result.safety[0, 2] == result.activity("sitting")[0, 2] == -1
    assert np.isnan(result.exceedance[5.0][0, 2])
    assert (result.comfort >= 0).sum() == fields[0].size - 1
    assert np.isnan(comfort.speed_at_exceedance(speeds, directions, fields, field_directions, 5.0, 0.05)[0, 2])


def test_probe_points_and_field_lists():
    speeds, directions, fields, field_directions = random_case()
    points = fields.reshape(len(fields), -1)
    np.testing.assert_array_equal(
        comfort.assess(speeds, directions, points, field_directions, 5.0).comfort,
        comfort.assess(speeds, directions, list(fields), field_directions, 5.0).comfort.ravel())


@pytest.mark.parametrize("change,message", [
    (dict(speeds=[[1.0]]), "one-dimensional"),
    (dict(speeds=[]), "one-dimensional"),
    (dict(directions=[0.0, 0.0]), "one-dimensional"),
    (dict(speeds=[-1.0]), "nonnegative"),
    (dict(speeds=[np.nan]), "No valid hours"),
    (dict(fields=np.ones((2, 1, 1))), "one field per field direction"),
    (dict(fields=np.ones(1)), r"\(D, \.\.\.\)"),
    (dict(fields=-np.ones((1, 1, 1))), "nonnegative"),
    (dict(fields=np.full((1, 1, 1), np.inf)), "nonnegative"),
    (dict(field_directions=[0.0, 360.0], fields=np.ones((2, 1, 1))), "distinct"),
    (dict(field_directions=[np.nan]), "finite"),
    (dict(reference_speed=0.0), "positive"),
    (dict(reference_speed=[1.0, 2.0]), "one value per field direction"),
    (dict(criterion="NEN 8100"), "Criterion"),
])
def test_invalid_inputs_rejected(change, message):
    arguments = dict(speeds=[6.0], directions=[0.0], fields=np.ones((1, 1, 1)), field_directions=[0.0],
                     reference_speed=5.0, criterion=comfort.NEN8100)
    arguments.update(change)
    with pytest.raises(ValueError, match=message):
        comfort.assess(**arguments)


def test_criteria_tables_validate_and_are_immutable():
    with pytest.raises(ValueError, match="decrease"):
        comfort.Rating(("a", "b", "c"), ((5.0, 0.05), (4.0, 0.05)))
    with pytest.raises(ValueError, match="one more label"):
        comfort.Rating(("a",), ((5.0, 0.05),))
    with pytest.raises(ValueError, match="fractions"):
        comfort.Rating(("a", "b"), ((5.0, 5.0),))
    with pytest.raises(FrozenInstanceError):
        comfort.NEN8100.height = 2.0
    melbourne = comfort.Criterion(
        name="custom", height=1.5,
        comfort=comfort.Rating(("sitting", "standing", "walking", "uncomfortable"),
                               tuple((speed, 0.2) for speed in (3.0, 4.0, 5.0))),
        safety=comfort.Rating(("safe", "unsafe"), ((20.0, 0.001),)))
    result = assess_uniform(*one_direction(np.full(250, 3.5), 1000), melbourne, height=1.0)
    assert melbourne.comfort.labels[result.comfort.item()] == "standing"
    assert any("1 m" in warning for warning in result.warnings)


def test_log_law_transfer():
    speeds = np.array([0.0, 3.0, np.nan])
    np.testing.assert_allclose(comfort.log_law_transfer(speeds, 10, 0.03, 10, 0.03,
                                                     to_law="standard"), speeds)
    factor = np.log(60 / 0.03) / np.log(10 / 0.03) * np.log(10 / 0.5) / np.log(60 / 0.5)
    np.testing.assert_allclose(comfort.log_law_transfer(speeds, 10, 0.03, 10, 0.5,to_law="standard"), speeds * factor)
    back = comfort.log_law_transfer(comfort.log_law_transfer(speeds, 10, 0.03, 60, 0.5),
                                    60, 0.5, 10, 0.03,from_law="shifted",to_law="standard")
    np.testing.assert_allclose(back, speeds)
    with pytest.raises(ValueError, match="exceed"):
        comfort.log_law_transfer(speeds, 0.01, 0.03, 10, 0.5)


def test_module_depends_only_on_numpy_and_standard_library():
    pending,seen=[Path(comfort.__file__)],set()
    while pending:
        path=pending.pop()
        if path in seen:
            continue
        seen.add(path)
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.level:
                assert node.level==1 and node.module is not None
                pending.append(path.parent/(node.module+".py"))
            elif isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module]
                assert all(n.split('.')[0] in set(sys.stdlib_module_names)|{"numpy"} for n in names)
    import subprocess
    subprocess.run([sys.executable,"-c",f'''
import sys,types,importlib
pkg=types.ModuleType("isolated_comfort");pkg.__path__=[{str(Path(comfort.__file__).parent)!r}]
sys.modules[pkg.__name__]=pkg
module=importlib.import_module("isolated_comfort.comfort")
assert module.log_law_transfer([5],10,.1,10,.1).shape==(1,)
assert not any(n.startswith(("dtcc_core","dtcc_qes")) for n in sys.modules)
'''],check=True,capture_output=True,text=True)
