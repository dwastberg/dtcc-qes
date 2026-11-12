# The spreading far wake (`Parameterizations(wake=3)`)

Experimental and opt-in. The default stays `wake=2` (see the validation status
below). The design, its evidence and every implementation step are in
[`WAKE_UPDATE_V2.md`](../WAKE_UPDATE_V2.md); the validation is in
[`validation/WAKE_UPDATE_V2_RESULTS.md`](../validation/WAKE_UPDATE_V2_RESULTS.md).

## What it changes

Code 3 keeps the code-2 cavity (the modified Röckle ellipsoid behind the lee
wall) and replaces the code-2 far wake, which ends abruptly where x = 3 d_n and
never spreads. Instead, each building's shadow is diffused across the wind and
in height by a mixing layer that grows linearly downstream:

- σ(x) = max(0.2 (x − x₁), Δ/2), with x₁ the upwind extent of the footprint;
- G = min(1, T(x) F_y F_z): F_y and F_z are the shadow (the footprint's
  cross-wind extent and its height, both widened by the separation-bubble
  thickness δ) convolved with a Gaussian of width σ, F_z with its image in the
  ground; T is a smooth taper to zero at the end of the reach;
- the deficit D = max over buildings of G multiplies the background u and v on
  every face that no cavity wrote; w is untouched and no far-wake flag (5) is set;
- each building's roof-level speed is sheltered by 1 − D at its roof point, so a
  building in another's wake gets a weaker cavity and wake turbulence;
- the wake turbulence is k_w = 0.08 max over buildings of U_H² G, with U_H the
  sheltered roof-level speed.

The geometry depends only on the footprint, its height, the roof-level wind
direction at its reference point and the grid. Nothing upstream of x₁, nothing
inside the footprint's own shadow upstream of its lee wall (notches and
courtyards), and no value is carried across the downstream end of the reach.
The constants are fixed (`metadata["wake"]["constants"]`); none is a user
setting.

## Outputs

```python
from dtcc_qes import wind

spec = wind.Parameterizations(wake=3)
result = wind.run(city, profile, bounds=bounds, parameterizations=spec)
result.wake.deficit        # D on (z, y, x) cells, float32, in [0, 1]
result.wake.tke            # k_w in m²/s²
result.scalar_speed()      # √(|u|² + 2k), float64, NaN in solid cells
plane = result.sample(1.75, "linear")  # plane.scalar_speed, plane.wake_deficit, plane.wake_tke
```

The scalar speed uses k = k_inflow(z) (1 − D)² + k_w: the inflow turbulence,
reduced inside far wakes, plus the wake turbulence. It is what an
omnidirectional (thermistor or hot-sphere) anemometer reads, and it is always at
least the magnitude of the mean vector. By default k_inflow = 5.5 u*² (the
neutral surface-layer σ_u, σ_v, σ_w = 2.4, 1.9, 1.25 u*), with u* = 0.4 a and a
the slope of a least-squares fit U = a ln(1 + z/z₀) to the profile speed at 32
log-spaced heights from 1 m to the domain top; a `UniformProfile` uses its
declared roughness instead. `metadata["wake"]["inflow_tke"]` records u*, the fit
window and the source. Pass `inflow_tke=` (a number in m²/s², a callable of
height or a `(heights, values)` pair interpolated in log height) to
`scalar_speed`, `sample` or `sample_points` to use a measured inflow k.

`to_dtcc()` adds `wake_deficit` and `wake_tke`. `comfort.assess_results(...,
speed="scalar")` assesses the scalar speed; it scales with the reference speed
like the mean velocity. No comfort criterion is defined on it.

The wake turbulence is separate from QES-Turb, which still runs on the final
field when `turbulence=Turbulence()` is requested.

## Limits

- It is an empirical shadow model. Its constants come from Cases A and B; the
  district cases (D and E) were not used to tune it.
- Adaptive solver runs report `unqualified_model_settings`, as for any
  non-default parameterization.
- Raised buildings (nonzero base height) are handled by the kernel but cannot
  be run through the public API, which assumes flat ground.
- The inflow k rule rests on the surface-layer constants; the fit window is its
  weak point (halving or doubling the top changes k by a factor 0.4–1.7 on the
  AIJ tunnel profiles). The AIJ scores barely depend on it.
- Cost: about +0.2 s per Case E direction at 2 m (1.8 M cells, 510 buildings,
  8 threads).
