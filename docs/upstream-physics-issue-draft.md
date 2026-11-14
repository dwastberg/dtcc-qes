# Draft: cavity façade angles and contaminated incident wind references

Status: draft only; not submitted. Findings were checked against QES-Public
v2.3.1 (`dced7ec571487be7538eca17bfc25bb3262fb6d0`) and reproduced in the
dtcc-qes embedded derivative. The numbers below are from the derivative, with
its existing solver and other repairs, and are not claimed as upstream runs.

## Incorrect upwind-cavity façade angle

In `UpwindCavity.cpp`, `atan2(...) + pi/2` produces a normal in
(-pi/2, 3pi/2]. The existing `<= -pi` wrap cannot fire. Normals greater than
pi should instead subtract `2*pi`. The `effective_gamma` branch chain also
omits [-pi/4, pi/4), leaving zero instead of the face's actual normal.

Proposed correction:

```cpp
if (perpendicular_dir[id] > M_PI)
  perpendicular_dir[id] -= 2 * M_PI;
// After the existing effective_gamma branches:
else
  effective_gamma[id] = perpendicular_dir[id];
```

A 40 x 40 x 30 m building rotated 70 degrees, with wind from 200 degrees,
exposes the problem. Compare against geometry and wind rotated 180 degrees,
mapping staggered faces and negating horizontal components. Before the
pressure solve, maximum mirror error falls from 3.36468 to 1.29505 m/s,
the cavity-off control's error. Residual asymmetry has other causes; this
does not claim complete mirror invariance. Direct tests cover eight normal
angles and both previously incorrect sectors.

## Incident wind sampled after cavities have modified it

The building stages read `u0_h, v0_h` at each building's roof reference point.
When that point lies inside another building's upwind cavity, the reference
may already be reversed. This subsequently orients/scales another cavity or
wake using a locally modified value instead of the approach profile.

Reproduction: 300 x 200 x 140 m domain at 2 m spacing; a 90 m tower occupying
x=[100,130], y=[84,116], and an 8 m building at x=[84,94], y=[94,106]. Use a
5 m/s wind from 270 degrees at 10 m. Inspect the low building's roof reference
before and after the cavity stage and its upwind strip x=[60,84], y=[94,106].
In our fixed-500-sweep test, mean upwind u changes from -0.0821 to +0.2961 m/s
with the standard wake after correcting the reference capture.

Proposed correction: capture every building's incident roof vector before any
building parameterization writes. Use that vector for cavity and wake strength
and direction. Later canyon, sidewall and rooftop stages use its direction;
their strengths continue to read local velocities. For a zero incident vector,
use the condition direction only as a deterministic frame. Capture again for
each condition, respecting height-varying profile directions.

We compared frozen incident directions against directions captured after all
wakes, before later stages. Their pooled AIJ score difference was 0.000144;
the predeclared tie-break selected the incident frame. This is a model choice
for upstream discussion, separate from the contaminated-reference reproduction.

Tests include isolated-building controls, input-order reversal, calm/reused
conditions, turning profiles and asymmetric mirror layouts. The implementation
and measurement record are in `tests/native/check_symmetry.cpp`,
`check_incident_reference.cpp`, and `validation/PHYSICS_BUG_FIX_RESULTS.md`
in dtcc-qes. Public commit links can be added if this draft is submitted.
