import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys

import numpy as np
import pytest

from dtcc_qes import comfort


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
    np.testing.assert_array_equal(comfort.log_law_transfer(speeds, 10, 0.03, 10, 0.03), speeds)
    factor = np.log(60 / 0.03) / np.log(10 / 0.03) * np.log(10 / 0.5) / np.log(60 / 0.5)
    np.testing.assert_allclose(comfort.log_law_transfer(speeds, 10, 0.03, 10, 0.5), speeds * factor)
    back = comfort.log_law_transfer(comfort.log_law_transfer(speeds, 10, 0.03, 60, 0.5), 60, 0.5, 10, 0.03)
    np.testing.assert_allclose(back, speeds)
    with pytest.raises(ValueError, match="exceed"):
        comfort.log_law_transfer(speeds, 0.01, 0.03, 10, 0.5)


def test_module_depends_only_on_numpy_and_standard_library():
    tree = ast.parse(Path(comfort.__file__).read_text())
    modules = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
               for alias in node.names}
    modules |= {node.module.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.level == 0}
    assert not any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(tree))
    assert modules - set(sys.stdlib_module_names) == {"numpy"}
