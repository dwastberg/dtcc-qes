# Angle fade of the sidewall and upwind-cavity zones

`wind.Parameterizations(angle_fade=2.5)`. Experimental and opt-in; the default `0.0` keeps the released behaviour bit for bit. A non-zero value is outside `pedestrian-v1`.

## What it changes

QES applies two zones to a wall only when the wall is close to one alignment with the wind:

| Zone | Applied when | Source |
|---|---|---|
| Sidewall | the wall is within 10° of parallel to the wind, and its upwind neighbour within 10° of facing it | `Sidewall.cpp` |
| Upwind cavity | the wall is within 10° of facing the wind | `UpwindCavity.cpp` |

At 10° the whole zone, at full strength, appears or disappears between two wind directions. For a rectangular building that is a step in the field at ±10° from each wall direction.

With `angle_fade = h` degrees the test becomes a weight:

- 1 up to 10 − h degrees from alignment,
- a smoothstep down to 0 at 10 + h degrees.

The zone's change of the velocity is multiplied by the weight. For the sidewall the weights of the wall and of its upwind neighbour are multiplied. A wall exactly aligned with the wind gives the same field as before.

**Cell flags keep the 10° switch.** Later zones and QES-Turb read the flags, so they see the same cells with and without the fade.

## What it does

One 20 × 30 × 20 m building, `wake=3`, wind from 225° to 315° in 1° steps; RMS change of K over the 2 m plane per degree:

| Sweep | Largest step, switch | Largest step, `angle_fade=2.5` | Median step |
|---|---|---|---|
| 2 m grid | 0.032 (5.4 × the median) | 0.015 (2.5 ×) | 0.006 |
| 2 m grid, building turned 30° | 0.027 | 0.011 | 0.006 |
| 1 m grid | 0.033 | 0.014 | 0.006 |

On the AIJ cases the scores do not move: A, B, C and D are identical (no wall falls inside the ramp), and in Case E the MAE changes by 0.0001. Measurements and gate: [validation/ACCURACY_RESULTS.md](../validation/ACCURACY_RESULTS.md), section 1.

## What it does not do

- A point probe beside a building can still see a step of about 0.07 in K per degree. That step is a sharp spatial edge of the near-wake cavity passing over the probe, not an angle switch.
- Other angle tests in the building models (the 45° sector choice inside the upwind cavity, the wake geometry) are unchanged.
- `2.5` is the only validated value. The range is 0 to 10 degrees.

## Test

`tests/test_angle_fade.py` covers the identity at 0, the aligned wall, the extent of the ramp, the flags, and the direction step as a regression test.
