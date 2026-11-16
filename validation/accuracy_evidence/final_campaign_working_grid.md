Defaults, final build against 0.1.0b5 runs:
109 runs compared; 0 differ
tall_buildings=1, final build against the prototype (s-d3):
37 runs compared; 0 differ
both options against the prototype (all):
37 runs compared; 32 differ (largest probe difference 1.14e-05 m/s)
   E-after-NNE-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-after-NW-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-before-ESE-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-before-ENE-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-before-NNE-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-before-W-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-before-N-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-before-SSE-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-before-S-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03
   E-after-NNW-r2-measured-float32-it20000-angle_fade2.5-tall_buildings1-wake3-wgrid-velocity1e-03

| Variant | E before, error 0–30 m | E after, error 0–30 m | E change 0–30 m (measured +0.262) | E after, error ≥ 60 m | E before q / MAE | E after q / R / MAE | Case D q / bias / MAE | Case D vector RMSE against parent | Case D U sign errors of 29 |
|---|---|---|---|---|---|---|---|---|---|
| 0.1.0b5, wake=3 | +0.176 | -0.062 | +0.024 | +0.052 | 0.327 / 0.145 | 0.462 / 0.559 / 0.133 | 0.414 / -0.120 / 0.152 | +0.000 | 5 |
| angle_fade=2.5 | +0.176 | -0.062 | +0.024 | +0.052 | 0.327 / 0.145 | 0.463 / 0.559 / 0.133 | 0.414 / -0.120 / 0.152 | +0.000 | 5 |
| tall_buildings=1 | +0.093 | +0.058 | +0.227 | -0.016 | 0.450 / 0.105 | 0.452 / 0.666 / 0.134 | 0.515 / -0.033 / 0.131 | +0.086 | 10 |
| both options | +0.093 | +0.058 | +0.227 | -0.016 | 0.450 / 0.105 | 0.452 / 0.666 / 0.134 | 0.515 / -0.033 / 0.131 | +0.086 | 10 |
| prototype, tall | +0.093 | +0.058 | +0.227 | -0.016 | 0.450 / 0.105 | 0.452 / 0.666 / 0.134 | 0.515 / -0.033 / 0.131 | +0.086 | 10 |
| prototype, both | +0.093 | +0.058 | +0.227 | -0.016 | 0.450 / 0.105 | 0.452 / 0.666 / 0.134 | 0.515 / -0.033 / 0.131 | +0.086 | 10 |
