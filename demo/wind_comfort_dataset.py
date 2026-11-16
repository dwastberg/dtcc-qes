"""Historical wind comfort from bounds; uses this environment's dtcc-core."""

from pathlib import Path

from dtcc_core import datasets
import dtcc_qes  # Registers qes_wind_comfort.
from time import time


BOUNDS =  (319845, 6397785, 320095, 6398035)
RESOLUTION =2.0  # Horizontal cell spacing in metres.
MAX_CELLS = 50_000_000  # Cell limit for the full buffered simulation domain.
CRITERION = "lawson_2019"  # Also "NEN8100"
SOURCE = "LM"  # Also "OSM".
WEATHER_SOURCE = "open_meteo"  # Also "SMHI"
START = None  # Default: twelve calendar months before END.
END = None  # Default: first of the previous month, exclusive, in UTC.
SAVE_RESULT = True
OUTPUT_DIR = Path("wind-comfort-results")


def main():
    start_time = time()
    result = datasets.qes_wind_comfort(bounds=BOUNDS, resolution=RESOLUTION,
        max_cells=MAX_CELLS,
        source=SOURCE, criterion=CRITERION, weather_source=WEATHER_SOURCE,
        start=START, end=END, strict_live=True)
    weather = result.metadata_payload["weather"]
    sim_time = time() - start_time
    # print(f"{weather['location_id']}: {weather['start']} to {weather['end_exclusive']} (exclusive)")
    # print(f"Paired weather coverage: {weather['coverage']:.3%}; {weather['valid_hours']} valid hours")
    print(f"Simulation time: {sim_time:.3f} seconds")
    print(result)
    if SAVE_RESULT:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        result.write_artifact(OUTPUT_DIR / "comfort.png")
        result.write_artifact(OUTPUT_DIR / "comfort.geojson", format="geojson")
        (OUTPUT_DIR / "context.json").write_text(result.dataset_context.model_dump_json(indent=2)+"\n")
    result.plot()
    result.plot_wind_rose()
    return result


if __name__ == "__main__":
    main()
