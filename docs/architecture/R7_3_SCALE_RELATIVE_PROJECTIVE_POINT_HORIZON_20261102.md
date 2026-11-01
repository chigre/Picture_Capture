# R7.3 — Scale-relative projective point-horizon contract (2026-11-02)

## Scope and ownership

This audit extends the read-only `PreprocessCoordinateMap` contract in
`src/picture_capture/preprocess/coordinate_mapping.py`. The map composes
source-image pixels → canonical layout → deskew/homography/orthogonal
transforms → half-open crop → optional no-rescale output canvas. It is not a
writer or a persisted coordinate migration.

The raster renderer remains owned by
`preprocess/homography_ops.py::apply_homography_image`; this change does not
modify that renderer or the shared general-purpose
`preprocess/geometry.py::transform_points_homography` helper. The mapping
contract now performs its own scale-relative point projection so a generic
absolute denominator clamp cannot fabricate a finite in-crop coordinate.

## Verified historical opt-out rescan result

The 2026-10-31 test commit
[`92afa633`](https://github.com/chigre/Picture_Capture/commit/92afa633b86d05158cab695bdb05dd14b2719d1e)
was **not green**: [CI #41098513706](https://github.com/chigre/Picture_Capture/actions/runs/41098513706)
completed FAILURE. Windows/macOS/Ubuntu Python 3.13 native Tk smoke timed out
after the test observed `status='已自动保存'`, `batch_active=False`, and
zero batch progress. Its separate [OCR run #41098513714](https://github.com/chigre/Picture_Capture/actions/runs/41098513714)
completed SUCCESS 3/3, and [CodeQL run #41098508919](https://github.com/chigre/Picture_Capture/actions/runs/41098508919)
completed SUCCESS 2/2. This historical test-only failure was superseded by the
native Tk interaction-sequence correction at
[`24e78710`](https://github.com/chigre/Picture_Capture/commit/24e78710589a5f2f4cd347300b200146bc386987),
whose exact-head [CI #41309027670](https://github.com/chigre/Picture_Capture/actions/runs/41309027670)
6/6, [OCR #41309027659](https://github.com/chigre/Picture_Capture/actions/runs/41309027659)
3/3, and [CodeQL #41309024720](https://github.com/chigre/Picture_Capture/actions/runs/41309024720)
2/2 all completed SUCCESS. The current PR HEAD is later than that correction.
The 92afa failure is retained as a real historical failure, not rewritten as
a successful run.

## New failure-first projective point counterexample

A homography can be nonsingular and pass the existing raster-replay
normalization check while an individual source point is numerically too close
to the projective horizon. For the synthetic matrix

`H = [[1,0,-50-1e-10],[0,1,-50-1e-10],[1,1,-100-1e-10]]`,

the source point (50,50) has a homogeneous denominator around 1e-12 after
normalization and an algebraic image near (1,1). The shared point utility
previously replaced that denominator with +1e-9, returning a different
coordinate around (0.001,0.001), which still appeared to be inside the crop.
In the reverse direction, output point (0,1) lies exactly on the inverse
homography horizon, but absolute clamping previously fabricated source
coordinates around (0,0.1).

- **RED-first test-only commit:**
  [`1d881ba0`](https://github.com/chigre/Picture_Capture/commit/1d881ba0a66692014fe646959120a5769655634f).
  [CI #41329969235](https://github.com/chigre/Picture_Capture/actions/runs/41329969235)
  completed FAILURE on all six Windows/macOS/Ubuntu × Python 3.10/3.13 test
  jobs. Each failed exactly the two new forward/reverse horizon assertions.
  Ubuntu Python 3.13: 2 failed / 5,304 passed / 3 skipped; Ubuntu Python 3.10:
  2 failed / 5,304 passed / 3 skipped; macOS and Windows each reproduced the
  same two failures (about 5,305 passed / 2 skipped). These are genuine
  intended REDs, not accepted release gates.

## Minimal source correction

Source fix:
[`17c4507b`](https://github.com/chigre/Picture_Capture/commit/17c4507be204a84660e76b76e07629612edcae6d).

- Adds a private projective-point mapper that evaluates the homogeneous
  denominator using `math.fsum` and rejects it when its magnitude is
  `<= 1e-12` of the sum of absolute denominator terms. This criterion is
  invariant to arbitrary nonzero homogeneous matrix scaling.
- Uses the same point guard in forward and inverse geometry, and the same
  relative denominator rule for polygon-horizon checks.
- Keeps the check local to the read-only coordinate-map contract; no global
  homography utility, Pillow raster writer, image pixel data, crop bytes or
  original source XY values are changed.
- Safe points remain mappable. Tests cover matrix scales 1e-14, 1 and 1e14,
  including the valid fallback where forward H[2,2] is zero but inverse
  H[2,2] is nonzero and raster replay remains normalizable.
- Tests also exercise point and ROI-polygon round trips through identity,
  mirror-X, rotate-CCW90 and rotate-CW90 canonical layouts.

## Exact source-head synthetic E2 gates

At source/test HEAD `17c4507be204a84660e76b76e07629612edcae6d`:

- [CI #41330338708](https://github.com/chigre/Picture_Capture/actions/runs/41330338708):
  **COMPLETED SUCCESS**, six Windows/macOS/Ubuntu × Python 3.10/3.13 jobs
  **6/6**, Risk-tier **SUCCESS**, Risk-tier CI gate **SUCCESS**.
- [OCR #41330338796](https://github.com/chigre/Picture_Capture/actions/runs/41330338796):
  **COMPLETED SUCCESS**, Windows/macOS/Ubuntu **3/3**.
- [CodeQL #41330336171](https://github.com/chigre/Picture_Capture/actions/runs/41330336171):
  **COMPLETED SUCCESS**, Analyze Python and Analyze Actions **2/2**.
- Documentation architecture check was **SKIPPED**, not counted as PASS.

The additional canonical-layout and zero-H[2,2] positive-control tests in this
checkpoint require their own final docs/test HEAD gate run. Do not infer that
future HEAD from the source-head runs above.

## Boundaries and remaining work

No PDIC, PPP, SECTION, Profile or OCR persistence schema, manual records,
actual file writer, source-image XY coordinates, preprocessing raster
algorithm or experimental default was changed. No real scanned page, real
save/reopen, benchmark, speedup or accuracy claim is made. The 1e-12 guard is
a conservative local numerical safety boundary, not a new persisted format
or a general claim that every ill-conditioned transform is valid.

**NOT PERFORMED:** Windows R3 E3 operator acceptance; #483 W1–W11; #503
human Undo/Redo; real dictionary scanning; real PDIC/PPP/SECTION/Profile/OCR
save/reopen. **DEFERRED:** R6 real-label learning and R8 real scanning.
Synthetic E2 does not constitute human acceptance.

PR #663 remains the sole Draft/Open/Unmerged production PR; main is untouched.
Next: continue B7b/R7.3 read-only source/canonical/transformed contracts for
SECTION/PDIC/PPP/ROI/crops; keep B7a profiling and all real-data-dependent
work blocked until authorized evidence exists.


## 2026-11-02 — B7b cross-owner source-XY preservation and multi-pass orthogonal raster parity

### PDIC / PPP / SECTION remain source-coordinate records

Test-only integration commit:
[`2e5cdbef`](https://github.com/chigre/Picture_Capture/commit/2e5cdbef44c06fff7b8d3370890966cbf03d812e),
in `tests/test_r7_3_source_annotation_projection_20261102.py`.

Across identity, mirror-X, rotate-CCW90 and rotate-CW90, the test creates
synthetic original-image pixels, a PDIC marker, a PPP polygon and a SECTION
v2 sidecar. It then projects the same source point/polygon through canonical
layout, perspective homography, crop and centered output canvas. The inverse
mapping restores the original source coordinates; the actual Pillow-rendered
pixel is located at the projected coordinate. Padding and the right/bottom
half-open content edge are rejected. Original image, PDIC, PPP and SECTION
bytes are snapshotted and verified unchanged after projection/rendering.

At exact test HEAD `2e5cdbef`: [CI #41332835127](https://github.com/chigre/Picture_Capture/actions/runs/41332835127)
6/6 plus Risk-tier and Risk-tier CI gate SUCCESS; [OCR #41332835149](https://github.com/chigre/Picture_Capture/actions/runs/41332835149)
3/3 SUCCESS; [CodeQL #41332832231](https://github.com/chigre/Picture_Capture/actions/runs/41332832231)
Analyze Python/Actions 2/2 SUCCESS.

### Applied orthogonal stage must have replayable geometry

Failure-first test commit:
[`3a4d4672`](https://github.com/chigre/Picture_Capture/commit/3a4d467297daef3ac3131ad431cac6230ac80850).
[CI #41333587702](https://github.com/chigre/Picture_Capture/actions/runs/41333587702)
completed FAILURE on all six Windows/macOS/Ubuntu × Python3.10/3.13 full-test
jobs. The same three intended assertions failed everywhere: missing modern
replay data, an empty modern step, and incomplete legacy row knots were all
silently accepted despite `orthogonal_applied=True`. Ubuntu3.13:
3 failed / 5,323 passed / 3 skipped. The failure was deterministic and
limited to the new fail-closed assertions.

Minimal source fix:
[`59edbb0b`](https://github.com/chigre/Picture_Capture/commit/59edbb0b6affff39dc6c1c2a9a7503a263c925ef),
local to `preprocess/coordinate_mapping.py`. It now rejects applied
orthogonal stages without usable geometry and validates finite/monotonic
legacy knots, paired separator arrays, row-grid dimensions and row-grid
lengths. Valid legacy row-knot replay and valid separator-only replay remain
supported. Malformed decoder inputs are normalized to
`CoordinateMappingUnavailable`; the general orthogonal transform and raster
renderer are not modified.

At exact source HEAD `59edbb0b`: [CI #41333905956](https://github.com/chigre/Picture_Capture/actions/runs/41333905956)
6/6 plus Risk-tier and Risk-tier CI gate SUCCESS; [OCR #41333906027](https://github.com/chigre/Picture_Capture/actions/runs/41333906027)
3/3 SUCCESS; [CodeQL #41333902165](https://github.com/chigre/Picture_Capture/actions/runs/41333902165)
Analyze Python/Actions 2/2 SUCCESS.

### Two-pass orthogonal transform agrees with the materialized raster

Test-only commit:
[`0b1aeff2`](https://github.com/chigre/Picture_Capture/commit/0b1aeff27e96f9753c4af786e2c3e19ae22a94dd).
The cross-owner fixture now includes two sequential separator shifts (2 px
then 1 px) after perspective correction, followed by crop and centered
canvas placement. For each of the four canonical layouts, the forward map,
inverse point/polygon mapping, and actual Pillow materialized pixel agree.
The source image and PDIC/PPP/SECTION files remain byte-identical.

**Final exact code/test HEAD `0b1aeff2`:**
- [CI #41334461268](https://github.com/chigre/Picture_Capture/actions/runs/41334461268):
  **COMPLETED SUCCESS**, six Windows/macOS/Ubuntu × Python3.10/3.13 jobs
  **6/6**; Risk-tier **SUCCESS**; Risk-tier CI gate **SUCCESS**.
- [OCR #41334461089](https://github.com/chigre/Picture_Capture/actions/runs/41334461089):
  **COMPLETED SUCCESS**, three operating systems **3/3**.
- [CodeQL #41334459114](https://github.com/chigre/Picture_Capture/actions/runs/41334459114):
  **COMPLETED SUCCESS**, Analyze Python and Analyze Actions **2/2**.
- Regression counts: Ubuntu Python3.13 and Python3.10 each 5,328 passed / 3 skipped; Windows and macOS Python3.13 and Python3.10 each 5,329 passed / 2 skipped. All six report `All checks passed!`.
- Documentation architecture check was **SKIPPED**, not counted as PASS.

### Scope boundaries

These are synthetic E2 checks only. No PDIC/PPP/SECTION persistence schema,
serializer, writer, source-image XY, OCR cache, image renderer, preprocessing
default or real project data was changed. The coordinate map remains a
read-only projection API; no new persistence consumer was wired. No real scan,
real save/reopen, benchmark, human Windows R3 E3, #483 W1–W11 or #503
Undo/Redo acceptance is claimed. R7.3 remains **in_progress**; B7a profiling
remains blocked pending authorized representative data, R6 remains blocked
pending verified human labels, and R8 remains user-deferred.

PR #663 remains the sole Draft/Open/Unmerged production PR; main remains
unchanged. Next: adversarial nonlinear orthogonal ROI/crop edge tests and
source-size/EXIF snapshot consistency, while keeping persistence writers and
schemas untouched.
