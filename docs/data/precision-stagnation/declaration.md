# Precision stagnation change declaration

Baseline: 7008159. Fresh builds identify it as
e130c2fbf47179923862c037a9a370ec17b91788a01f6719cd282506ba43471a.
The production qualification header instead names
31f6d956fecfa24654a34b7ed43941c38876f38b26d0800ca5868e7b54396f87;
The baseline changelog explicitly documents this build as unqualified for
`pedestrian-v1`. This work does not waive that existing qualification boundary.

Intentional change: velocity-rule solves may stop at precision_floor after
8 counted checks within twice the rounding floor and 8 checks without a new
minimum block change. Existing estimate and consecutive-floor tests retain
precedence. Fixed work, multiplier-change and adaptive decisions are unchanged.
Estimate metadata gains stagnation constants and a floor trigger; raw histories
are preserved. Only fields whose stopping iteration changes may differ.

Acceptance: replay native stopping decisions; reproduce the 67.5-degree case;
compare all 16 demo directions at 1 m and 2 m with tight float64 references;
check known Case C wake=3 stalls and the existing stop-rule study. At default
tolerance, maximum velocity error on assessed fluid faces must be <=0.001 Uref.
References must demonstrate stability with additional iterations. Preserve
existing probe gates. Require fixed-work and adaptive parity, serial/OpenMP
and thread parity, native/sanitizer tests, full isolated Python suites, and
sdist/wheel audits. Production qualification identity is promoted only after
these gates pass. Any unresolved failures are reported, not waived.
