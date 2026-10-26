"""Run a steady wind simulation for a 200 m city area (requires network)."""

from dtcc_core import datasets, Bounds
import dtcc_qes

import time

h = 1000
x_min = 319720
y_min = 6397660
bounds = Bounds(x_min, y_min, x_min + h, y_min + h)

start_time = time.time()
result = datasets.qes_wind(bounds=bounds, wind_speed=5.0, wind_direction=270.0, resolution=1.5, product="slice", slice_height=2)
print(f"{time.time() - start_time} seconds")
result.plot(presentation=False)
