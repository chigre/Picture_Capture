# R7.3 — Coordinate mapping versus homography raster-replay precondition (2026-11-01)

## Ownership and failure boundary

The ephemeral `preprocess/coordinate_mapping.py::PreprocessCoordinateMap` projects source/canonical points through deskew, homography, orthogonal transforms, half-open crop and optional no-rescale canvas. Pixel output is owned by `preprocess/replay.py`, using `preprocess/homography_ops.py::apply_homography_image`. Both consumers must agree on whether a matrix is replayable. This package changes only the read-only map constructor; it does **not** transform, write, or migrate PDIC/PPP/SECTION, crop plans, Project Profile, OCR, or stored analysis.

The image renderer normalizes `inverse(H)` by its `[2,2]` entry before passing inverse perspective coefficients to Pillow. Invertibility and finite inverse coefficients alone do not guarantee that denominator is nonzero. The synthetic, nonsingular `H=[[1,0,0],[0,0,1],[0,1,1]]` has `det(H)=-1` but `inverse(H)[2,2]=0`. Before the fix the coordinate-map constructor accepted this matrix, despite the raster replay precondition not being met.

## Test-first and minimal correction

- **RED-first test-only SHA:** `cdb3c4b817598d3b7a111922dced8cef36c31503`.
- **Observed failing evidence:** [CI #41304080041](https://github.com/chigre/Picture_Capture/actions/runs/41304080041), Ubuntu Python 3.13 `1 failed / 5,298 passed / 3 skipped`. The new `test_coordinate_map_fails_closed_if_homography_cannot_replay_into_pixels` failed because no `CoordinateMappingUnavailable` was raised. This is deliberately **RED, not accepted CI**.
- **Correction:** the mapping constructor refuses an inverse whose `[2,2]` magnitude is too small relative to the matrix norm, with a generic `CoordinateMappingUnavailable` diagnostic. This is a fail-closed read-only validation, not a change to the raster warper, source image, persisted geometry or pixel coordinates.
- **Positive counterexample:** a scalar-rescaled identity H at `1e-14`, `1`, and `1e14` still maps coordinates identically; projective scale alone must not trigger rejection.

## Acceptance and residual limitations

Exact-head Windows/macOS/Ubuntu Python 3.10/3.13 full CI, Risk-tier gate, OCR three-platform smoke, and CodeQL Python/Actions are required **after this code/docs change**. They are PENDING until GitHub returns terminal results; historical green gates do not certify this commit.

These are synthetic coordinate/raster contracts only (E2 when verified). No real source-image/PDIC/PPP/SECTION/Profile/OCR save-reopen, human R3 E3, #483 W1–W11, #503 manual Undo/Redo or dictionary accuracy/throughput measurements were performed. R6 human-label learning and R8 real scanning stay DEFERRED. PR #663 must remain Draft/Open/Unmerged; main unchanged.


## Intermediate exact-head regression and follow-up correction

At source/test/doc HEAD `72d795922cd561bf7e7554c1e9a4a5161b95fde9`, [CI #41304339978](https://github.com/chigre/Picture_Capture/actions/runs/41304339978) reported **one genuine positive-test failure** on Ubuntu Python 3.13 (1 failed / 5,299 passed / 3 skipped) and macOS Python 3.13 (1 failed / 5,300 passed / 2 skipped): the projectively identical `H=1e-14 I` was returned as `outside_crop`. This exposed an existing absolute `1e-9` denominator clamp in the general point-homography helper. The inverse direction for `H=1e14 I` has the same risk. These are real RED results and **do not count as passing gates**.

The map now strips arbitrary homogeneous scale before forwarding H or inverse(H) to that shared helper, choosing the `[2,2]` normalizer when safe and a maximum-coefficient fallback for forward matrices whose `[2,2]` is effectively zero. The test also round-trips output points to source across three H scales. This fix is restricted to the new read-only mapping contract; no global homography/image raster behavior, crop/PDIC/PPP/SECTION bytes or original XY storage is changed. **Final exact-head CI/OCR/CodeQL verification remains required after this follow-up.**

