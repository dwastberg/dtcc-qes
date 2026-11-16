# Tall buildings: shelter rule and tall-building zone

`wind.Parameterizations(wake=3, tall_buildings=1)`. Experimental and opt-in; needs the spreading wake (`wake=3`). The default `0` keeps `wake=3` bit for bit. The option is outside `pedestrian-v1`.

**It is a model of the scalar speed** that an omnidirectional anemometer reads, `result.scalar_speed()`. The direction of the mean flow near a tall building is not reliable with it (see the limits below).

## What it changes

Two things that belong together and cannot be switched separately.

**1. Shelter rule.** `wake=3` takes the far-wake deficit at a point as the largest deficit of any building. With the option the deficits combine by the root sum of squares, D = min(1, √ΣG²). Weak wakes that overlap then add up, which lowers the speed in open areas and along streets of a dense fabric. Around one building nothing changes. The roof-speed shelter of downstream buildings and the wake turbulence keep the largest-deficit rule.

**2. Tall-building zone.** A building much taller than its neighbours brings faster air down: corner streams beside it and a standing vortex in front of it. The zone is written after every other building zone and before the projection.

| Part | Rule | Source |
|---|---|---|
| Eligibility | Weight 0 at a roof-height ratio H/h of 1.5, 1 at 2.5. h is the area-weighted mean roof height of the other buildings within 2 H. A building without neighbours is not eligible. | Chosen; agrees with Reiter's reduction factors (0.55 at H/h = 2, 0.85 at 3) |
| Target speed | The undisturbed inflow speed at the same height times a ratio that depends on H: beside the building 1.94 at 48 m, 2.38 at 72 m, 2.74 at 96 m; in front 0.58, 1.20, 1.36. | Reiter (2010), *Environment and Planning B* 37, 857–873, Fig. 5 and Fig. 7 |
| Reach | 0.75 H from the walls, cosine decay | Chosen; the measured effect in AIJ Case E ends between 0.5 and 0.75 H |
| Height | Full weight up to 0.25 H, none above 0.5 H | Chosen |
| Sector | The ratio runs from the front value on the upwind axis to the side value at 90°; the zone fades out between 90° and 150°, so the near wake is left alone. Faces a cavity wrote are skipped. | Chosen |
| Direction | Reversed on the upwind axis, tangential around the building beside it | Chosen |
| Mean flow and turbulence | The published ratios are scalar speeds. A share of 0.8 of the target is imposed on the mean flow; the rest is added as turbulence after the solve, k = W (1 − 0.8²) / (2 · 0.8²) · \|U\|², with W the zone weight. | Share from the split-fibre data of AIJ Case D: \|U\|² / (\|U\|² + 2k) = 0.65 |

The constants are in `TallBuildingModel` (`src/qes_core/dtcc/api/wake_model.h`); they are not user settings. The added turbulence is part of `result.wake.tke`; the deficit inside the zone is reduced by the zone weight.

## What it does

AIJ cases, `wake=3` scalar speed against thermistors, 2 m grid (Case C at 1 m):

| Measure | `wake=3` | With `tall_buildings=1` | Measured |
|---|---|---|---|
| Case E before construction, error within 30 m of the tower site | +0.176 | +0.093 | |
| Case E before, hit rate / MAE | 0.327 / 0.145 | 0.450 / 0.105 | |
| Case E, change within 30 m when the 60 m tower is built | +0.024 | +0.227 | +0.262 |
| Case E after, hit rate / R / MAE | 0.462 / 0.559 / 0.133 | 0.452 / 0.666 / 0.134 | |
| Case D (100 m tower), hit rate / bias / MAE | 0.414 / −0.120 / 0.152 | 0.515 / −0.033 / 0.131 | |
| Case C, change within 15 m when the central block doubles in height | +0.074 | +0.173 | +0.194 |

Cases A and B (isolated buildings) are bit-identical. The result is stable under ±25 % on every constant. Measurements, gates and sensitivities: [validation/ACCURACY_RESULTS.md](../validation/ACCURACY_RESULTS.md), sections 2 and 5 to 8.

## Limits

1. **Mean flow direction near towers.** At the 29 points of Case D where the direction is measured and resolved, sign errors of the streamwise component rise from 5 to 10, and the vector error rises by 0.086 U_H. Do not use the mean vector near a tall building with this option.
2. **No independent test.** Cases D and E were scored for three variants of the zone. The constants are from the literature and were not fitted, but the choice between variants was made on these cases. A default change needs towers that were not used here.
3. **Downwind of the tower** the rise is short: +0.09 against +0.25 measured in Case E.
4. **The nearest 15 m** (8 probes in Case E) are off by +0.14 before and +0.12 after construction.
5. **Heights must be full-scale metres.** The speed ratios are a function of the building height in metres. A model-scale geometry gives wrong ratios.
6. **Sectors use the building centroid.** For a long slab the corner position is approximate.
7. **The shelter rule saturates.** In dense arrays the deficit reaches 1.0 in places.
8. **Any eligible building gets a zone**, also an existing one. In Case E before construction one probe changes by 0.39 while the mean levels do not move.

## Test

`tests/test_tall_buildings.py`: the option off is `wake=3`; an isolated building is unchanged; an equal-height array gets the shelter rule and no zone; the deficit stays within 1 and does not fall with added upwind rows; the speed-up around a tower; mirror symmetry and mass balance; both precisions.
