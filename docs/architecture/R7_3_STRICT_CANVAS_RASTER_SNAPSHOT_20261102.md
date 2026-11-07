# R7.3 — Strict enabled-canvas raster snapshot and stable coordinate offsets

Date: 2026-11-02. Scope: B7b/R7.3, read-only preprocess coordinate mapping.
Implementation: the existing Draft/Open/Unmerged PR #663 only. No main write or merge.

## Defect and RED-first evidence

PreprocessCoordinateMap already rejected fractional/boolean crop_box values with
_validated_box, but accepted an enabled OutputCanvasInfo with fractional width
or height, fractional/boolean content_box coordinates, and some malformed
raster inputs. OutputCanvasInfo is a frozen dataclass, but its runtime
content_box argument could still be a mutable list. The map retained that
object, letting caller mutation change the output offset after construction.

Test-only commit f3cb33bce1980df6f57a25fccc4af038f034cc08:
tests/test_r7_3_canvas_raster_snapshot_20261102.py. It covers valid
integer canvas mapping roundtrips, NumPy integral scalar/array normalization,
invalid width/height (fractional, bool, string, zero, negative and inf),
malformed/boolean/fractional content_box, external mutable-list drift,
and the actual output_canvas_info factory as a positive control.

RED CI https://github.com/chigre/Picture_Capture/actions/runs/41407303817:
all six platform/Python regression jobs failed the new assertions as intended;
Ubuntu Python 3.13: 16 failed, 5355 passed, 3 skipped. In particular, changing
the original list's X offset from 10 to 20 changed a map result from
(15, 15) to (25, 15). This is a concrete before/after counterexample,
not a speed or accuracy measurement. The RED run is intentionally FAILURE,
not an acceptance gate pass.

## Smallest bounded correction

Code commit 1e7d054185dd76bad42475396941a6de7d0562d0 changes only
src/picture_capture/preprocess/coordinate_mapping.py.

- Require a valid OutputCanvasInfo object if canvas is supplied.
- Deep-copy canvas before storing it in the otherwise immutable mapping.
- For enabled canvas, validate strictly positive raster width/height with
  _validated_size_pair and validate half-open integer content_box with
  _validated_box (operator.index semantics, no lossy int() conversion).
- Canonicalize those fields to plain Python integer values and a tuple
  through dataclasses.replace, keeping all other canvas metadata unchanged.
- Preserve existing no-canvas and valid-canvas geometry, existing crop width
  and height equality checks, source-frame mapping, and writer isolation.

No preprocessing raster renderer, actual PDIC/PPP/SECTION/Profile/OCR
persistence writer/schema, original source XY, experiment default, or private
scan input was changed.

## Source-head automated evidence

Exact code/test HEAD: 1e7d054185dd76bad42475396941a6de7d0562d0.

- CI https://github.com/chigre/Picture_Capture/actions/runs/41407552831:
  Windows/macOS/Ubuntu times Python 3.10/3.13 6/6 SUCCESS; Risk-tier and
  Risk-tier CI gate SUCCESS. Ubuntu Python 3.13: 5371 passed, 3 skipped.
- OCR Platform Smoke https://github.com/chigre/Picture_Capture/actions/runs/41407552811:
  Windows/macOS/Ubuntu 3/3 SUCCESS.
- Documentation architecture check: SKIPPED, **not a pass**.
- A matching exact-code-HEAD CodeQL Python/Actions run had not been
  independently identified at documentation preparation. Do not infer
  its outcome from an earlier SHA or from the CI/OCR jobs.

The documentation/checkpoint HEAD will be newer than the source HEAD;
its own exact-head checks must be inspected independently.

## Remaining scope / operator boundaries

R7.3 remains in_progress. The strict raster snapshot does not prove coverage
of all non-monotonic or tangential knot preimages under bounded nonlinear
sampling. A read-only audit of selected preprocess/UI runtime modules did not
identify a production PreprocessCoordinateMap construction callsite, but this
is not a repository-wide proof; metadata delivery of raw size/EXIF at future
production callsites needs a separate reviewed integration. Any actual
preprocess renderer/persistence changes remain outside this increment.

NOT PERFORMED / DEFERRED: Windows R3 E3; #483 W1-W11; #503 human
Undo/Redo; real scanned-dictionary content and actual save/reopen
acceptance. R6 real-label learning and R8 real scans remain DEFERRED.
Synthetic E2 is not human approval. No performance/F1 claim.
