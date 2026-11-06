# joined_v1: a bounded horizontal mixing hypothesis

Revision: `qes-canyon-join-v1`. This is a new QES adaptation, not an exact
reproduction of Singh. Its constants and neighborhood are frozen before any
joined_v1 measured score. It has no qualification or promotion claim.

Coordinates are those of the qualified horizontal reference: x from the trailing
wall, y centered across the matched rectangular span W, and z above flat ground.
Evaluate each component at its actual staggered face. Retain gamma=0.3, the
physical downstream gap S, and the reference's 4r(1-r), r=x/S, streamwise law.

The declared mixing assumption is that lateral momentum crosses a layer extending
one existing mixing width on each side of the old core/lateral boundary. With
b=W/2 and delta=0.2x, the old boundary is a=b-delta. The new layer is
[s,b]=[b-2delta,b]. Its width 2delta uses the existing growth law; it is not
chosen from residual locations. Retain the quarter-power core unchanged for
abs(y)<=s. Reject the entire building overlay before writes when s<=0 anywhere
in the gap (0.4S>=b). This deliberately restricts this hypothesis's support.

For a horizontal component let A be its retained cross-core amplitude, including
gamma and 4r(1-r), and B its along-canyon contribution. At the inner edge:

    F = (delta/a)^(1/4)
    q0 = B + A F
    m0 = -A F/(4delta)

The outer reference q1 is the incident horizontally uniform wind profile at the
same target height, captured before building parameterizations; its transverse
derivative is zero. This assumes the outer edge has returned to the incident
background. It does not model an edge inside another building's disturbed wake.
The retained preflight rejects intersecting, partial and ambiguous downstream
supports. A turning, reversed or calm incident sub-roof layer also causes a
whole-building fallback before writes. Applicability to more general urban
composition remains unassessed.

Assume an unresolved lateral mixing layer introduces no preferred sublayer or
extra extremum. Among profiles with these endpoint velocities and slopes, minimize
the squared curvature integral. Varying that functional gives q''''=0 and the
unique cubic Hermite bridge. With L=2delta and t=(abs(y)-s)/L:

    q = (2t^3-3t^2+1) q0 + (t^3-2t^2+t) L m0
        + (-2t^3+3t^2) q1

It matches the retained core value and derivative at s and the incident value
and zero transverse derivative at b. For the supported normal incident flow,
q0 is reverse-flow and q1 forward-flow in the wind direction; L m0=-A F/2.
The normalized inner slope lies in [0,1/2], so the cubic is monotone and stays
between its endpoint velocities. The signed transverse component follows rigid
rotation of this vector formula. Helper tests check these claims independently.
There is no forced zero at the old boundary a; the sign crossing is determined
by the endpoints, not the measured reversal rows.

At and beyond b in the reference traversal's edge stencil, set the component to
q1, replacing the old lateral overshoot. Outside that stencil the existing field
is untouched. Ambient matching is a property of this prescribed overlay and its
declared uniform-background assumption, not a claim about all composed urban
fields. x<=0 uses the finite retained core/edge limit without dividing by delta.
As delta tends to zero, the transition stays bounded and its support shrinks;
gradients are finite for each positive x, not uniformly bounded as x tends to 0.

Run the complete legacy canyon pass first, then this horizontal overlay before
sidewall, roof and solid-mask stages. Never write W. Skip every face in the
reference's protected roof wedge. Keep complete preprojection W, independent
changed-face roof and W audits, and the legacy roof-reference convention. No
new roof, cavity-height, turbulence or W law participates.

The two-sided layer and minimum-curvature closure are modeling assumptions.
Physical usefulness must be tested against the frozen legacy gates and the
archived horizontal-reference retention gate. No retuning, alternative join,
case-specific coefficient, or automatic default change is authorized here.
