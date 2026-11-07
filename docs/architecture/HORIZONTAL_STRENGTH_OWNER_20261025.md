# Round 54 — horizontal perspective strength & composition owner

Issue #562 / Draft PR #663. Three complete numerical implementations moved from
`preprocess/geometry.py` into `preprocess/horizontal_strength.py`:

- `interpolate_perspective_estimate`: bounded identity-to-homography interpolation
  including singular-matrix and finite-Jacobian protections
- `optimize_horizontal_perspective_strength`: same 1D coarse→fine scan, fitted
  zero-crossing candidates, edge-pair safety weighting and minimum-strength tie
- `compose_perspective_estimates`: source-to-first and first-to-second matrix
  product and complete resulting metadata

The compatibility layer keeps the **exact** public function names and
signatures. The original frozen `PerspectiveEstimate` remains in
`geometry.py` to preserve class/pickle and consumers' import identities.
Each call explicitly injects the current coordinate/polygon transform hook,
current horizontal alignment audit and interpolation function, and all four
strength/range policy constants. Thus live monkeypatch points remain patchable
without importing the legacy geometry module from the new leaf owner.

Test coverage includes identity/clamped/partial strength behavior, singular
matrices, source-coordinate translation and independent composition, live
callback injection and optimizer rejection on insufficient polygons. The old
full-page N-column optimizer tests still run.

No change to integer/float rounding, thresholds, optimizer objective, model
identity, PDIC/PPP/SECTION/Project, Profile, OCR cache, image/pixel correction,
GUI startup, or crop/export. Full exact-head CI + OCR Platform Smoke required;
real scanned-page manual parity remains NOT DONE. Keep PR Draft, unmerged.
