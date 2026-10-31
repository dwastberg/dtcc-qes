"""Run a steady wind simulation for a 500 m city area (requires network)."""

from dtcc_core import datasets, Bounds
import dtcc_qes

import time

h = 1000
x_min = 319720
y_min = 6397660
bounds = Bounds(x_min, y_min, x_min + h, y_min + h)

# Height steps survive cleaning; source/region courtyards are filled.
# Inspect result.dataset_context for cleaning provenance and fallback warnings.
start_time = time.time()
result = datasets.qes_wind(bounds=bounds, wind_speed=5.0, wind_direction=225, resolution=1.0, product="slice", slice_height=1.75)
print(f"{time.time() - start_time} seconds")
print(result)
result.plot(field_name="speedup", presentation=False)
