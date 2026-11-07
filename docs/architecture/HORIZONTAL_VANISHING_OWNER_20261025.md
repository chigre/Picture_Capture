# Round 56 — N-column robust horizontal vanishing-point owner (2026-10-25)

Issue #562, Draft PR #663. Moved the real numerical implementations of
`_fit_horizontal_vanishing_point`,
`_horizontal_vp_column_spread_deg`, and
`estimate_horizontal_perspective_from_polygons` out of
`preprocess/geometry.py` into `preprocess/horizontal_vanishing.py`.

The new math owner preserves the original five-iteration weighted least-squares
robust common-VP fit (with equal influence per populated column), residual MAD
gates, degenerate and low-angle rejection, columnwise residual P90 and the one
homography constructed in original source XY space. The near-VP rejection,
thresholds and correction matrix sign/orientation are unchanged.

`geometry.py` retains all three original public/private callable names and
signatures; the original `PerspectiveEstimate` frozen class and pickle identity;
and authoritative `HORIZONTAL_VP_MIN_ROWS` and
`HORIZONTAL_VP_MIN_TREND_DEG` constants. A frozen
`HorizontalVanishingOps` supplies original current row reconstruction,
row statistics, region angles, fit/spread hooks, coordinate mapping,
class constructor and both thresholds **on every call**. The math owner only
imports numpy/math/dataclasses/typing, never geometry, app, Tk or OCR.

Focused tests cover exact mathematical recovery of a simulated far
vanishing point, multi-column agreement, degenerate sample/range handling,
live threshold and callback substitution, result/class/pickle identity,
near-VP safety rejection, legacy function signature and leaf-first imports.
All preexisting perspective/correction/orthogonal full-suite tests remain.

No PDIC/PPP/SECTION schema, stored Profile/settings, scanner source-coordinate,
OCR/cache, crop/export, or Tk callback changes. Exact-head full CI and 3-OS OCR
smoke required. Manual real scanned-page acceptance is NOT DONE; keep Draft.
