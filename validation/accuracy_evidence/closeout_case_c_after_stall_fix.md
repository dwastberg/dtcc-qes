# Case C at 1 m after the stall fix (2026-11-16, build df09ee9d)

Checks B1 and B2 of ACCURACY_CLOSEOUT_PLAN.md. Runs: validation/output/accuracy/runs-close-{parent,tall,both}.

B1: tall_buildings alone against both options, Case C 1 m:
9 runs compared; 0 differ
B2: new against stalled runs, probe velocity:
  close-both vs final-both
9 runs compared; 9 differ (largest probe difference 2.96e-05 m/s)

Scores, both options against the wake=3 parent, Case C 1 m — stalled runs (0.1.0b6):
| C 0H | 360 | +22 / −9 | +0.036 | -0.0093 [-0.0142, -0.0041] | 0.0103 [-0.0097, 0.0278] | -0.0356 [-0.0396, -0.0098] | 0.189 | better |
| C 1H | 360 | +17 / −9 | +0.022 | -0.0046 [-0.0111, 0.0020] | 0.0040 [-0.0236, 0.0294] | 0.0425 [-0.0144, 0.0481] | 0.219 | no resolved change |
| C 2H | 360 | +21 / −15 | +0.017 | -0.0013 [-0.0074, 0.0045] | 0.0175 [-0.0217, 0.0595] | -0.0247 [-0.0344, -0.0144] | 0.257 | no resolved change |
— same on the committed build:
| C 0H | 360 | +22 / −9 | +0.036 | -0.0093 [-0.0142, -0.0041] | 0.0103 [-0.0097, 0.0278] | -0.0356 [-0.0396, -0.0098] | 0.189 | better |
| C 1H | 360 | +17 / −9 | +0.022 | -0.0046 [-0.0111, 0.0020] | 0.0040 [-0.0236, 0.0294] | 0.0425 [-0.0144, 0.0481] | 0.219 | no resolved change |
| C 2H | 360 | +21 / −15 | +0.017 | -0.0013 [-0.0074, 0.0045] | 0.0175 [-0.0217, 0.0595] | -0.0247 [-0.0344, -0.0144] | 0.257 | no resolved change |
  close-parent vs 0.1.0b6 runs (wake=3 parent):
9 runs compared; 9 differ (largest probe difference 6.01e-05 m/s)
