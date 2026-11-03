# G3 / R4.2 — final image/SECTION witness after focused PDIC readback

**Date:** 2026-11-03 (SGT)
**Repository:** `chigre/Picture_Capture`
**Branch:** `refactor/562-retire-root-image-utils-20261024` (sole Draft/Open/Unmerged PR #663)
**Source/test HEAD:** `8a0259b9a5175b8f760838862963530e01f2b1db`
**Main HEAD:** `ec20989ea8c026cca5337293e67850b6b6df30f2` (unchanged)

## Concrete failure and RED-first proof

The focused save helper `apply_focused_review_page_updates()` checked the image/SECTION source immediately after `_write_pdic_atomic()`. It subsequently called `read_pdic()`, verified complete ordered words and X/Y, compared all eight serialized PDIC fields and confirmed edited coordinates, but returned success without checking the source again. External image/SECTION drift *during* PDIC readback could thus be silently accepted.

Test-only commit [`636351b1`](https://github.com/chigre/Picture_Capture/commit/636351b14e805d4f05ac347b054e64ad413687a8) adds `tests/test_g3_r4_focused_save_postreadback_source_20261103.py`, using only disposable 8×8 BMP, synthetic PDIC and SECTION. Four interleavings modify/replace SECTION bytes, remove SECTION, create a previously absent SECTION, or replace image pixels during the *second* `read_pdic()` call, after the existing post-publication source verification. Both attested and legacy no-witness stable-source saves are positive controls.

[RED CI #41602730257](https://github.com/chigre/Picture_Capture/actions/runs/41602730257) completed **FAILURE on all six** Windows/macOS/Ubuntu × Python 3.10/3.13 matrix jobs, with exactly four intended `DID NOT RAISE RuntimeError` failures on this test per job. Ubuntu 3.13: 4 failed, 5442 passed, 3 skipped; Windows 3.10: 4 failed, 5443 passed, 2 skipped. RED Risk-tier CI gate **FAILED**, as expected; documentation architecture check **SKIPPED**, not PASS. This RED is evidence of the gap, not a release acceptance.

## Minimal correction and GREEN evidence

Source commit [`8a0259b9`](https://github.com/chigre/Picture_Capture/commit/8a0259b9a5175b8f760838862963530e01f2b1db) changes **only** `src/picture_capture/proofreading/focused_pdic_updates.py` (+6 lines): before the final successful return, when a caller provided the accepted focused image/SECTION witness, invoke `verify_focused_save_source(page, expected_source)` *after* PDIC readback, ordered-row comparison, eight-field comparison and edited-coordinate validation.

**Exact source/test HEAD checks:**
- [CI #41603256021](https://github.com/chigre/Picture_Capture/actions/runs/41603256021): **SUCCESS**, six OS/Python jobs, Risk tier and Risk-tier CI gate **SUCCESS**; Ubuntu Python 3.13 reports **5,446 passed / 3 skipped**. Documentation architecture check **SKIPPED**, not PASS.
- [OCR #41603256004](https://github.com/chigre/Picture_Capture/actions/runs/41603256004): **SUCCESS, 3/3**.
- [CodeQL #41603250733](https://github.com/chigre/Picture_Capture/actions/runs/41603250733): **SUCCESS, Analyze (python) and Analyze (actions) 2/2**.

This documentation commit has its own later HEAD and requires independently checked exact-head gates; the source-head results above cannot prove those gates.

## Safety, scope and limitations

- The accepted source witness retains image and active SECTION file/path/absence byte identity. The live focused UI requires it; optional legacy direct helper calls keep their previous ABI.
- A post-publication source drift raises instead of reporting confirmed success. **The PDIC may already have been written**; do not restore earlier bytes, overwrite a foreign publication, auto-retry an uncertain batch, or imply an atomic multi-file transaction.
- The final byte hash comparison is an optimistic check, **not** a cross-file OS lock/CAS. Mutations after the last comparison remain outside this discrete-check guarantee.
- No persisted PDIC/PPP/SECTION/Profile schema, original X/Y, raster geometry, OCR cache, actual user record, safe writer implementation or experimental default is changed. No real benchmark, acceleration or quality estimate was made.
- **NOT PERFORMED/DEFERRED:** Windows R3 E3; #483 W1–W11; #503 human Undo/Redo; real dictionary scan and actual PDIC/PPP/SECTION/Profile/OCR save/reopen; human acceptance. R6 real-label learning and R8 real scans remain DEFERRED. Synthetic E2 is never human E3.

## Recovery point

Verify the exact documentation HEAD's CI six OS/Python jobs, OCR three OS, Risk-tier/gate and CodeQL Python/Actions. Continue bounded async epoch/SECTION/crop-prefetch/save ownership and safe retry audits only with new concrete RED-first counterexamples. Preserve the historical Windows thumbnail intermittent-root-cause status **UNCONFIRMED**. Keep main unchanged and PR #663 Draft/Open/Unmerged.
