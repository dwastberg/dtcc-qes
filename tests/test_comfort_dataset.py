"""Historical-weather contract and actual native comfort dataset integration."""

from copy import deepcopy
from datetime import UTC, datetime
import json

import numpy as np
import pytest
from dtcc_core import datasets
from dtcc_core.model import Bounds, FieldSlice, Point, TimeSeries, TimeSeriesCollection

from dtcc_qes import comfort, wind
from dtcc_qes._comfort_weather import adapt_climate, resolve_period
from dtcc_qes.comfort_dataset import QESWindComfortArgs, _buffered_city, _vertical_grid
from fixtures.datasets import source_city, fetched

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def args(**updates):
    return QESWindComfortArgs(**dict(dict(bounds=[0, 0, 30, 24],
        start="2023-01-01", end="2024-01-01", resolution=4.), **updates))


@pytest.fixture
def weather():
    times = np.arange(np.datetime64("2023-01-01", "ns"), np.datetime64("2024-01-01", "ns"),
                      np.timedelta64(1, "h"))
    location = "smhi:42"
    result = TimeSeriesCollection(locations={location: dict(station_id=42,
        station_name="Test station", point=Point(x=15, y=12, z=100), elevation=100)},
        attributes=dict(source="smhi", retrieval_time="2026-11-16T00:00:00Z"))
    for name, values, unit in (("wind_speed", np.tile([0., 2., 8., 12.], len(times)//4), "m/s"),
                                ("wind_direction", np.arange(len(times)) % 360., "degrees")):
        key = (location, name)
        result.series[key] = TimeSeries(name=name, times=times, values=values, unit=unit,
                                       association="sample", role="observed")
        result.series_metadata[key] = dict(height_above_ground_m=10., source="smhi",
            temporal_semantics="10 minute sample, hourly", quality_available=True)
        result.observations[key] = {str(t): {"quality": "G", "source_period": "corrected-archive"} for t in times}
    return result


@pytest.mark.parametrize("now,start,end", [
    (datetime(2026, 11, 16, tzinfo=UTC), "2025-10-01", "2026-10-01"),
    (datetime(2026, 1, 1, tzinfo=UTC), "2024-12-01", "2025-12-01"),
    (datetime(2024, 4, 30, tzinfo=UTC), "2023-03-01", "2024-03-01"),
])
def test_default_period(now, start, end):
    actual = resolve_period(now=now)
    assert actual == (str(np.datetime64(start, "ns")), str(np.datetime64(end, "ns")))


def test_dates_overrides_and_roundtrip():
    assert resolve_period(end="2024-02-29T06:00Z")[0].startswith("2023-02-28T06:00")
    assert resolve_period(years=(2020, 2021))[1].startswith("2022-01-01")
    request = args(start="2023-01-01T01:00+01:00")
    assert QESWindComfortArgs(**request.model_dump()) == request
    assert request.start.startswith("2023-01-01T00:00")
    assert datasets.qes_wind_comfort.validate(dict(bounds=Bounds(xmin=0,ymin=0,xmax=10,ymax=10))).bounds == [0,0,10,10]
    json.dumps(datasets.qes_wind_comfort.describe(), allow_nan=False)


def test_cell_limit_default_and_request_identity():
    default = args()
    custom = args(max_cells=75_000_000)
    assert default.max_cells == 50_000_000
    assert custom.model_dump()["max_cells"] == 75_000_000
    assert QESWindComfortArgs(**custom.model_dump()) == custom
    assert default.model_dump() != custom.model_dump()
    assert datasets.qes_wind_comfort.show_options()["properties"]["max_cells"]["default"] == 50_000_000


@pytest.mark.parametrize("update", [dict(start="2024-01-01", end="2023-01-01"),
    dict(start="2023-01-01T00:30"), dict(years=(2020, 2021)), dict(speed=5.),
    dict(direction=0.), dict(profile={}), dict(station_id=42), dict(criterion="unknown"),
    dict(bounds=[0,0,float("nan"),10]), dict(resolution=0.), dict(exposure="unknown"),
    dict(max_cells=0), dict(max_cells=-1), dict(max_cells=True), dict(max_cells=50_000_000.),
    dict(max_cells=2**63)])
def test_invalid_args(update, fetched):
    with pytest.raises((ValueError, TypeError)):
        datasets.qes_wind_comfort(**dict(dict(bounds=[0,0,20,20], start="2023-01-01", end="2024-01-01"), **update))
    assert not fetched


def test_weather_alignment_quality_calm_and_reference(weather):
    key = ("smhi:42", "wind_direction")
    stamps = weather[key].times
    weather[key].values[0] = np.nan  # Missing calm direction remains a valid hour.
    weather.observations[key][str(stamps[1])]["quality"] = "Y"
    weather.series[key] = weather[key].between(stamps[1], "2024-01-01")
    before = deepcopy(weather[("smhi:42", "wind_speed")].values)
    climate = adapt_climate(weather, args(exposure="suburban"))
    assert climate.metadata["valid_hours"] == 8759
    assert climate.metadata["calm_hours"] == 2190
    assert np.isnan(climate.speeds[1])
    assert climate.speeds[0] == 0
    expected = comfort.log_law_transfer([8.], 10., .03, 10., .3,
                                       from_law="standard", to_law="shifted")[0]
    assert climate.speeds[2] == expected
    assert climate.metadata["counts"]["wind_direction"]["quality_rejected"] == 1
    np.testing.assert_array_equal(before, weather[("smhi:42", "wind_speed")].values)
    json.dumps(climate.metadata, allow_nan=False)


def test_weather_reference_uses_agl_never_station_elevation(weather):
    weather.series_metadata[("smhi:42", "wind_speed")]["height_above_ground_m"] = None
    climate = adapt_climate(weather, args())
    assert climate.metadata["transfer"]["from_height"] == 10
    assert climate.metadata["transfer"]["height_assumed"]
    assert any("assumed 10 m" in warning for warning in climate.warnings)


@pytest.mark.parametrize("damage,match", [
    ("quality", "coverage"), ("season", "coverage"), ("missing", "coverage"),
    ("mixed_stations", "same station"), ("upstream", "retrieval failed"),
    ("height", "heights"), ("unit", "unit"), ("relocation", "relocated"),
])
def test_bad_weather_fails_before_city_fetch(weather, fetched, monkeypatch, damage, match):
    key = ("smhi:42", "wind_speed")
    if damage == "quality":
        weather.observations[key] = {}
    elif damage == "season":
        weather[key].values[:2000] = np.nan
    elif damage == "missing":
        weather.series[key] = weather[key].between("2023-02-01", "2024-01-01")
    elif damage == "mixed_stations":
        weather.series[("smhi:43", "wind_direction")] = weather.series.pop(("smhi:42", "wind_direction"))
    elif damage == "upstream":
        weather.attributes["upstream_errors"] = [{"reason": "unavailable"}]
    elif damage == "height":
        weather.series_metadata[key]["height_above_ground_m"] = 0.
    elif damage == "unit":
        weather[key].unit = "km/h"
    else:
        weather.locations["smhi:42"]["position_history"] = [
            dict(longitude=12., latitude=57., height=100.), dict(longitude=13., latitude=57., height=100.)]
    monkeypatch.setattr(datasets, "weather_history", lambda **_: weather)
    with pytest.raises(ValueError, match=match):
        datasets.qes_wind_comfort(**args().model_dump())
    assert not fetched


def test_open_meteo_is_explicit_and_preserves_reanalysis(weather):
    for meta in weather.series_metadata.values():
        meta.update(source="open_meteo", temporal_semantics="instantaneous", quality_available=False)
    weather.observations.clear()
    climate = adapt_climate(weather, args(weather_source="open_meteo"))
    assert climate.metadata["coverage"] == 1
    assert climate.metadata["source"] == "open_meteo"
    assert climate.metadata["series"]["wind_speed"]["temporal_semantics"] == "instantaneous"


@pytest.mark.parametrize("criterion,height", [("nen8100", 1.75), ("city_of_london", 1.5)])
def test_native_dataset_product(weather, fetched, monkeypatch, tmp_path, criterion, height):
    calls = []
    historical = datasets.weather_history
    def fetch(**kwargs):
        calls.append(kwargs)
        return weather
    monkeypatch.setattr(datasets, "weather_history", fetch)
    # Validation goes through the real installed Core model even in fixtures.
    fetch.ArgsModel = historical.ArgsModel
    created = []
    factory = wind._prepared_model
    def prepare(*a, **kw):
        assert a[1].grid.max_cells == 50_000_000
        model = factory(*a, **kw)
        created.append(model)
        return model
    monkeypatch.setattr(wind, "_prepared_model", prepare)
    obj = datasets.qes_wind_comfort(**args(criterion=criterion, max_cells=50_000_000).model_dump())
    assert isinstance(obj, FieldSlice)
    assert len(created) == 1 and created[0].closed
    assert len(fetched) == 1
    assert fetched[0]["bounds"] == [-40.,-40.,70.,64.]
    assert calls[0]["parameters"] == ["wind_speed", "wind_direction"]
    assert calls[0]["max_distance_m"] == 100000
    assert obj.field("valid").values.any()
    assert np.all(obj.points[:,2] == height)
    assert np.all((obj.points[:,0]>=0) & (obj.points[:,0]<30))
    assert np.all((obj.points[:,1]>=0) & (obj.points[:,1]<24))
    context = obj.dataset_context
    step = context.provenance.processing_steps[-1]
    assert context.request.parameters["max_cells"] == 50_000_000
    assert step["domain"]["max_cells"] == 50_000_000
    assert context.health["completed_directions"] == 16
    assert context.health["solver_converged"]
    assert len(step["directions"]) == 16
    assert step["weather"]["start"] == args().start
    assert step["weather"]["selection"]["station_id"] == 42
    assert step["assessment"]["field_height"] == height
    assert step["preparation"]["footprints"]
    if criterion == "nen8100":
        assert "sitting" in obj.field_names
        assert "comfort_summer" not in obj.field_names
    else:
        assert "comfort_summer" in obj.field_names
        assert step["assessment"]["gem"]["peak_factor"] == 3.
        assert any("unvalidated" in warning.lower() for warning in context.warnings)
    json.dumps(context.model_dump(mode="json"), allow_nan=False)
    geojson = obj.to_geojson()
    assert geojson["features"][0]["properties"]["comfort"] >= -1
    assert "safety" in geojson["features"][0]["properties"]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    obj.write_artifact(tmp_path / "comfort.png")
    obj.write_artifact(tmp_path / "comfort.geojson", format="geojson")
    obj.plot(show=False)
    obj.plot_wind_rose(show=False)
    assert (tmp_path / "comfort.png").stat().st_size > 1000
    plt.close("all")


def test_direction_failure_releases_model(weather, fetched, monkeypatch):
    monkeypatch.setattr(datasets, "weather_history", lambda **_: weather)
    # Build directly so this tests release on failure, independently of validation.
    created = []
    factory = wind._prepared_model
    def prepare(*a, **kw):
        model = factory(*a, **kw)
        created.append(model)
        def fail(*_, **__):
            raise RuntimeError("required direction failed")
        model.run = fail
        return model
    monkeypatch.setattr(wind, "_prepared_model", prepare)
    with pytest.raises(RuntimeError, match="required direction"):
        datasets.qes_wind_comfort.build(args())
    assert created[0].closed


def test_explicit_vertical_centres():
    for height in (1.5, 1.75):
        faces = np.asarray(_vertical_grid(height, 2., 40.).faces, dtype=np.float32)
        assert height in (faces[:-1]+faces[1:])/2


def test_buffer_stabilises_with_small_height_changes(source_city, monkeypatch):
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        # Different terrain extents can perturb lidar-derived heights.
        source_city.buildings[0].measured_height = 10.01 if len(calls) == 1 else 10.02
        return source_city
    monkeypatch.setattr(datasets, "city", fetch)
    _, bounds, buffer = _buffered_city(args(), [0, 0, 30, 24])
    assert len(calls) == 2
    assert buffer == 60
    assert bounds == [-60, -60, 90, 84]


def test_resource_guard_aborts_before_native_storage(weather, fetched, monkeypatch):
    monkeypatch.setattr(datasets, "weather_history", lambda **_: weather)
    with pytest.raises(ValueError, match="cells|cell"):
        datasets.qes_wind_comfort(**args(max_cells=10).model_dump())


def test_unknown_quality_cannot_turn_missing_hours_into_calm(weather):
    key = ("smhi:42", "wind_speed")
    weather.observations[key][str(weather[key].times[0])]["quality"] = "unknown"
    climate = adapt_climate(weather, args())
    assert climate.metadata["missing_hours"] == 1
    assert climate.metadata["calm_hours"] == 2189
    assert np.isnan(climate.speeds[0])


@pytest.mark.parametrize("criterion", ["nen8100", "city_of_london"])
def test_nonconverged_direction_warns_and_completes(weather, fetched, monkeypatch, caplog, criterion):
    from dataclasses import replace

    monkeypatch.setattr(datasets, "weather_history", lambda **_: weather)
    factory = wind._prepared_model
    created = []
    def prepare(*a, **kw):
        model = factory(*a, **kw)
        created.append(model)
        run = model.run
        calls = 0
        def solve(profile):
            nonlocal calls
            calls += 1
            # A real capped native solve exercises warning handling and metadata.
            if calls == 4:
                return run(profile, solver=replace(a[3], max_iterations=1))
            return run(profile)
        model.run = solve
        return model
    monkeypatch.setattr(wind, "_prepared_model", prepare)
    result = datasets.qes_wind_comfort.build(args(criterion=criterion))
    context = result.dataset_context
    runs = context.provenance.processing_steps[-1]["directions"]
    assert created[0].closed
    assert len(runs) == context.health["completed_directions"] == 16
    assert not context.health["solver_converged"]
    assert not runs[3]["diagnostics"]["converged"]
    assert runs[3]["solver"]["stop_estimate"]["termination"] == "iteration_limit"
    assert all(run["diagnostics"]["converged"] for i, run in enumerate(runs) if i != 3)
    assert any("67.5 degrees did not converge" in warning for warning in context.warnings)
    assert "Wind solve did not converge after 1 iterations" in caplog.text
    assert result.field("valid").values.any()
    json.dumps(context.model_dump(mode="json"), allow_nan=False)
