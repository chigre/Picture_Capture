# PC-CQ B7b/R7.3 — overflowed polygon path lengths fail closed

Date: 2026-11-02. Sole [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663), main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged. Automated synthetic E2 only.

## Concrete failure-first evidence

The polygon boundary sampler's two `math.ceil(distance / 8)` paths could encounter infinity despite individually finite numeric X/Y coordinates: opposing finite ~1e308 input vertices overflow their difference, or individually finite stage coordinates produce a non-finite summed stage path length. The previous implementation raised an unclassified Python `OverflowError` instead of the mapper's explicit refusal contract. No real image or human PDIC was involved.

Test-only [`bf07d77f`](https://github.com/chigre/Picture_Capture/commit/bf07d77fc3736c400ca8fd844785083f2b056564) added four forward/reverse negative cases and a normal finite polygon positive control to `tests/test_r7_3_multiple_extrema_between_knots_20261102.py`. Exact-head [CI #41456523292](https://github.com/chigre/Picture_Capture/actions/runs/41456523292) completed **FAILURE in all six** Windows/macOS/Ubuntu × Python3.10/3.13 regression jobs, with the four intended `OverflowError: cannot convert float infinity to integer` assertions (Ubuntu3.13: 4 failed, 5422 passed, 3 skipped; macOS3.13: 4 failed, 5423 passed, 2 skipped; Windows3.13: 4 failed, 5423 passed, 2 skipped). This RED is not a release gate pass. Separate RED-head [OCR #41456523437](https://github.com/chigre/Picture_Capture/actions/runs/41456523437) succeeded 3/3; RED-head CodeQL [#41456516509](https://github.com/chigre/Picture_Capture/actions/runs/41456516509) Python/Actions succeeded 2/2.

## Minimal production correction

[`020931bb`](https://github.com/chigre/Picture_Capture/commit/020931bbedba4e8963c98cda39aef05a6287a58c) changes **only** `src/picture_capture/preprocess/coordinate_mapping.py`: two `math.isfinite` guards, eight inserted lines, no deletions. An overflowed input edge or stage-frame path length raises `CoordinateMappingUnavailable` before integer sample-grid sizing, rather than allowing `math.ceil(inf)` to escape. No change to normal finite geometry, saved knot coordinates, crop/half-open semantics, bound constants, inverse method, Pillow renderer or actual file writer. The ordinary finite polygon positive control stays green.

## Exact source/test HEAD gates

At `020931bbedba4e8963c98cda39aef05a6287a58c`:

| Platform | Python 3.13 | Python 3.10 |
| --- | --- | --- |
| Ubuntu | 5426 passed / 3 skipped | 5426 passed / 3 skipped |
| macOS | 5427 passed / 2 skipped | 5427 passed / 2 skipped |
| Windows | 5427 passed / 2 skipped | 5427 passed / 2 skipped |

- [CI #41457357693](https://github.com/chigre/Picture_Capture/actions/runs/41457357693): **COMPLETED SUCCESS**, matrix **6/6**, Risk-tier **SUCCESS** and Risk-tier CI gate **SUCCESS**.
- [OCR #41457357678](https://github.com/chigre/Picture_Capture/actions/runs/41457357678): **COMPLETED SUCCESS 3/3**.
- [CodeQL #41457351160](https://github.com/chigre/Picture_Capture/actions/runs/41457351160): **COMPLETED SUCCESS**, Analyze Python / Analyze Actions **2/2**.
- Documentation architecture check was **SKIPPED**, not counted as PASS.

This audit/STATE/RESUME documentation commit requires *its own* exact-head CI, OCR, Risk-tier and CodeQL verification. Do not attribute the source HEAD's green status to the later docs HEAD.

## Safety, limitations and recovery

This is read-only ephemeral geometry validation, not a change to PDIC/PPP/SECTION/Profile/OCR schema, actual atomic writer, original image pixels/XY, OCR selection, crop exporter or opt-in flags. No private project content was read or uploaded. Neither arbitrary oscillations/knot tangencies nor numerical inverse accuracy are mathematically certified; no real scan, benchmark, latency reduction, accuracy/F1 improvement or materialized-raster claim. Preserve R7.3 **in_progress**.

**NOT PERFORMED / DEFERRED:** Windows R3 E3, #483 W1–W11, #503 human manual Undo/Redo, real dictionary scan and PDIC/PPP/SECTION/Profile/OCR save/reopen. R6 verified-label learning and R8 real scanning are **DEFERRED**. E2 is not human E3.

**Next:** Independently verify final documentation HEAD; then examine R4.2 *before-first-terminal* same-key prefetch reassignment, epoch/SECTION/crop/save ownership, and bounded numerical fail-closed only with a material counterexample. Do not open a second production PR, merge, mark Ready, force-push or alter main.
