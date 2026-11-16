"""Adapt installed DTCC Core historical weather without fetching data ourselves."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json

import numpy as np
from dtcc_core import datasets
from dtcc_core.model import TimeSeriesCollection

from . import comfort

WEATHER_POLICY = "paired-hourly-v1"
EXPOSURES = {"open": 0.03, "suburban": 0.3, "urban": 1.0}


def resolve_period(start=None, end=None, years=None, *, now=None):
    """Resolve half-open UTC dates; default ends on first of previous month."""
    if years is not None:
        if start is not None or end is not None:
            raise ValueError("years conflicts with start/end")
        first, last = years
        if first > last:
            raise ValueError("years must be an inclusive increasing pair")
        start, end = f"{first:04d}-01-01", f"{last + 1:04d}-01-01"
    if end is None:
        today = now or datetime.now(UTC)
        month = np.datetime64(f"{today.year:04d}-{today.month:02d}", "M") - np.timedelta64(1, "M")
        end = str(month.astype("datetime64[D]"))
    # Core owns UTC parsing, including offsets; use its public ArgsModel.
    from dtcc_core.datasets.weather_history import WeatherHistoryDatasetArgs
    model = WeatherHistoryDatasetArgs
    if start is None:
        probe = model(source="open_meteo", location=(0, 0), crs="EPSG:4326",
                      start="1900-01-01", end=end, max_days=150000)
        end = probe.end
        stamp = np.datetime64(end)
        month = stamp.astype("datetime64[M]")
        previous = month - np.timedelta64(12, "M")
        offset = stamp - month.astype("datetime64[ns]")
        # Calendar subtraction clamps leap day rather than spilling into March.
        last_day = (previous + np.timedelta64(1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
        candidate = previous.astype("datetime64[ns]") + offset
        start = str(min(candidate, last_day.astype("datetime64[ns]") +
                        (stamp - stamp.astype("datetime64[D]"))))
    parsed = model(source="open_meteo", location=(0, 0), crs="EPSG:4326",
                   start=start, end=end)
    if any(np.datetime64(value, "ns").astype(np.int64) % 3_600_000_000_000
           for value in (parsed.start, parsed.end)):
        raise ValueError("start/end must fall on UTC hour boundaries")
    return parsed.start, parsed.end


@dataclass
class WindClimate:
    speeds: np.ndarray
    directions: np.ndarray
    times: np.ndarray
    metadata: dict
    warnings: list[str]
    context: object


def fetch_climate(args, xy):
    historical = getattr(datasets, "weather_history", None)
    if historical is None:
        raise RuntimeError("Installed dtcc-core must provide datasets.weather_history")
    options = dict(source=args.weather_source, location=((xy[0]+xy[2])/2, (xy[1]+xy[3])/2),
                   crs="EPSG:3006", parameters=["wind_speed", "wind_direction"],
                   start=args.start, end=args.end, strict_live=args.strict_live)
    if args.weather_source == "smhi":
        options["max_distance_m"] = 100_000.0
    weather = historical(**options)
    return adapt_climate(weather, args)


def adapt_climate(weather, args):
    if not isinstance(weather, TimeSeriesCollection):
        raise TypeError("weather_history must return a TimeSeriesCollection")
    if weather.attributes.get("upstream_errors"):
        raise ValueError("Historical weather retrieval failed; inspect upstream_errors")
    speed_keys = [key for key in weather if key[1] == "wind_speed"]
    if len(speed_keys) != 1 or len(weather) != 2:
        raise ValueError("Historical weather needs one station with paired speed and direction")
    speed_key = speed_keys[0]
    direction_key = (speed_key[0], "wind_direction")
    if direction_key not in weather:
        raise ValueError("Wind speed and direction must come from the same station")
    location = weather.locations[speed_key[0]]
    history = location.get("position_history", [])
    positions = {(p["longitude"], p["latitude"], p["height"]) for p in history}
    if len(positions) > 1:
        raise ValueError("Weather station relocated within the requested period")
    times = np.arange(np.datetime64(args.start, "ns"), np.datetime64(args.end, "ns"),
                      np.timedelta64(1, "h"))
    aligned, metadata, counts = [], {}, {}
    for key, unit in ((speed_key, "m/s"), (direction_key, "degrees")):
        series = weather[key]
        if series.unit != unit:
            raise ValueError(f"Historical {key[1]} must have unit {unit}")
        stamps = np.asarray(series.times, dtype="datetime64[ns]")
        if not len(stamps):
            raise ValueError("Historical weather contains no wind observations")
        values = np.asarray(series.values, dtype=float).reshape(len(stamps), -1)
        if values.shape[1] != 1 or np.isnat(stamps).any():
            raise ValueError("Expected scalar wind observations at finite timestamps")
        if len(stamps) > 1 and not np.all(stamps[1:] > stamps[:-1]):
            raise ValueError("Duplicate or unordered historical timestamps")
        if np.any(stamps.astype(np.int64) % 3_600_000_000_000):
            raise ValueError("Historical wind observations must lie on UTC hour boundaries")
        values = values[:, 0].copy()
        meta = weather.series_metadata[key]
        rejected = np.zeros(len(stamps), dtype=bool)
        if args.weather_source == "smhi":
            records = weather.observations.get(key, {})
            rejected = np.array([records.get(str(t), {}).get("quality") != "G" for t in stamps])
            values[rejected] = np.nan
        if key == speed_key:
            bad = (values < 0) | np.isinf(values)
        else:
            bad = (values < 0) | (values > 360) | np.isinf(values)
            values[values == 360] = 0.0
        values[bad] = np.nan
        selected = (stamps >= times[0]) & (stamps < np.datetime64(args.end))
        target = np.full(len(times), np.nan)
        target[np.searchsorted(times, stamps[selected])] = values[selected]
        aligned.append(target)
        metadata[key[1]] = meta
        counts[key[1]] = dict(quality_rejected=int((rejected & selected).sum()),
                              invalid_values=int((bad & selected).sum()),
                              returned=int(selected.sum()))
    speeds, directions = aligned
    valid = np.isfinite(speeds) & ((speeds == 0) | np.isfinite(directions))
    fraction = float(valid.mean())
    monthly = {}
    months = times.astype("datetime64[M]")
    for month in np.unique(months):
        mask = months == month
        monthly[str(month)] = float(valid[mask].mean())
    if fraction < 0.9 or any(value < 0.8 for value in monthly.values()):
        raise ValueError(f"Insufficient paired historical wind coverage: {fraction:.1%}; "
                         "require 90% overall and 80% in every requested month")
    if args.criterion == "city_of_london":
        month_numbers = months.astype(int) % 12 + 1
        for name, numbers in comfort.SEASONS.items():
            if not np.any(valid & np.isin(month_numbers, numbers)):
                raise ValueError(f"Historical weather has no valid {name} hours")
    warnings = ["QES comfort is screening output; model accuracy and planning compliance are unqualified.",
                "Historical hourly samples retain their native averaging semantics; they are not relabelled as hourly means.",
                "Station/model exposure is assumed open (z0=0.03 m); neutral log-law transfer ignores stability and displacement."]
    heights = [metadata[name].get("height_above_ground_m") for name in ("wind_speed", "wind_direction")]
    height = heights[0]
    if height is None:
        height = 10.0
        warnings.append("Wind measurement height is unknown; assumed 10 m above ground. Station elevation is never used as measurement height.")
    if not np.isfinite(height) or height <= 0.03 or (heights[1] is not None and heights[1] != height):
        raise ValueError("Wind measurement heights are invalid or inconsistent")
    raw_speeds = speeds.copy()
    # An invalid pair contributes to neither annual nor seasonal statistics.
    speeds[~valid] = np.nan
    speeds = comfort.log_law_transfer(speeds, height, .03, 10., EXPOSURES[args.exposure],
                                     from_law="standard", to_law="shifted")
    rose = np.zeros(16, dtype=int)
    noncalm = valid & (raw_speeds > 0)
    sectors = (np.floor((directions[noncalm] + 11.25) / 22.5).astype(int) % 16)
    np.add.at(rose, sectors, 1)
    identity = sha256()
    for array in (times.astype(np.int64), raw_speeds, directions, valid):
        identity.update(array.tobytes())
    identity.update(json.dumps(metadata, sort_keys=True).encode())
    record = dict(policy=WEATHER_POLICY, source=args.weather_source, location_id=speed_key[0],
        start=args.start, end_exclusive=args.end, expected_hours=len(times),
        valid_hours=int(valid.sum()), missing_hours=int((~valid).sum()),
        calm_hours=int((valid & (raw_speeds == 0)).sum()), coverage=fraction,
        monthly_coverage=monthly, quality_policy="SMHI G only; ERA5 has no quality flags",
        counts=counts, series=metadata, selection=_json_safe(location),
        retrieval_time=weather.attributes.get("retrieval_time"), identity=identity.hexdigest(),
        transfer=dict(from_height=height, from_roughness=.03, from_law="standard",
                      to_height=10., to_roughness=EXPOSURES[args.exposure], to_law="shifted",
                      blending_height=60., exposure=args.exposure, height_assumed=heights[0] is None),
        wind_rose=dict(directions=np.arange(0., 360., 22.5).tolist(), counts=rose.tolist(),
                       calm_hours=int((valid & (raw_speeds == 0)).sum()), unit="hours"))
    return WindClimate(speeds, directions, times, record, warnings, weather.dataset_context)


def _json_safe(value):
    """Keep station Points readable without depending on collection exchange."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "x") and hasattr(value, "y"):
        return dict(x=float(value.x), y=float(value.y), z=float(value.z), crs=value.transform.srs)
    return value
