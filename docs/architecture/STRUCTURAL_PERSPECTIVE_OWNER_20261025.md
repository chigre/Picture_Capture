# Round 57 — source-canvas structural and manual perspective math (2026-10-25)

Issue #562 / Draft PR #663. Extracted six complete numerical implementations
to a new canonical `preprocess/structural_perspective.py`:

- column-layout analysis constraints (minimum eight valid OCR boxes / two columns);
- structural-column edge pitch and in-body anchor sample filtering;
- robust three-pass least-squares fit for column-left trajectories;
- automatic source-polygon four-corner geometry with parallel-drift,
  weak-perspective, and keystone classification;
- manually selected four-corner correction including original bounds clipping,
  convex/noncrossing order checks, minimum size checks and same-size canvas.

All original public/private function names and signatures remain in
`preprocess/geometry.py`. `PerspectiveEstimate` class/pickle identity stays
where it was. A frozen `StructuralPerspectiveOps` injects live
`_layout`, sample, fit and 3×3 quad-homography callbacks into the automatic
math owner at call time; the manual path receives its current homography
function and historical result constructor explicitly. The new math module
imports only numpy, dataclasses and typing; never imports back from layout,
geometry, Profile, GUI, OCR or app.

Characterization tests: line fit with an outlier and insufficient data,
single/multi-column pitch, invalid layout fallback/rejection, source ROI
anchor box sampling, auto-keystone and callback wiring, manual correct
matrix/polygon mapping, source coordinate preservation, invalid cross/canvas
boundaries, public signatures and pickling plus leaf-import isolation.

No PDIC/PPP/SECTION, Profile, saved settings, OCR caches, Tk callback,
source-pixel transform/interpolation or crop/export contract change. Exact-head
six-matrix CI and 3-OS OCR smoke required; real scanned page manual validation
still outstanding. Keep original PR #663 Draft, not merged.
