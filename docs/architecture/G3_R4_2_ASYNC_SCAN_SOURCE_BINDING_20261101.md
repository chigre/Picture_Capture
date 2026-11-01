# G3 R4.2 — asynchronous filter scan source binding and crop-cache consistency

**Date:** 2026-11-01  
**Repository:** `chigre/Picture_Capture`  
**Production branch:** `refactor/562-retire-root-image-utils-20261024`  
**Source/test HEAD:** `4458faa953fccc1bb247e3209dba400139c10a68`  
**PR:** [#663 — Draft / Open / Unmerged](https://github.com/chigre/Picture_Capture/pull/663)

## Scope

Close a concrete source-provenance gap in the asynchronous focused-filter path. The scan worker reads PDIC entries and optional OCR JSON; crop generation subsequently reads the page image, PDIC and SECTION. Before this change, a PDIC/OCR/SECTION mutation during scan could leave a target list whose source revision was not bound to the later crop cache key.

This packet changes only volatile in-memory source attestation and synthetic regression coverage. It does not change real user files, persistence schema, crop coordinates, save publication semantics, or experimental defaults.

## Failure-first evidence

Test-only commit [`36e917d`](https://github.com/chigre/Picture_Capture/commit/36e917d27e98615413ad770c138cdba2f294ede4) added `tests/test_g3_r4_scan_source_consistency_20261101.py`.

The exact test-first run [CI #41286614069](https://github.com/chigre/Picture_Capture/actions/runs/41286614069) completed FAILURE. All six platform/Python regression jobs exposed the four intended assertions:
- PDIC changes during page scan were not rejected.
- OCR-cache changes during page scan were not rejected.
- SECTION changes during page scan were not rejected.
- Returned targets did not carry a source witness, so a later same-length OCR-cache replacement with restored mtime could still reach the crop snapshot.

The Ubuntu Python 3.13 log recorded 4 failed / 5,276 passed / 3 skipped; macOS Python 3.13 recorded 4 failed / 5,277 passed / 2 skipped. This is genuine RED evidence, not a passing gate.

## Minimal implementation

Source commit `035b50631b46a1ec1b6474736cc354c9a2214d77` added two helpers to `proofreading/focused_crop_source_fingerprint.py`:

- `focused_scan_source_witness`: records the required PDIC and optional OCR-cache and active SECTION sidecar, including resolved path, presence and SHA-256 content witness.
- `verify_focused_scan_source`: fails closed when the source cannot be read or no longer matches.

`ui/focused_filter_workflow.py` now:

1. Captures the page scan witness before PDIC/OCR candidate reads and verifies it after candidate/risk ordering.
2. Attaches the witness to each returned target as in-memory `_focused_scan_source_witness`; no disk field or persisted schema was added.
3. Revalidates the witness in `_filter_batch_snapshot` and includes it in the render cache key.
4. Rechecks scan provenance after both N+1 prefetch and direct crop generation; Tk completion and payload application re-snapshot before cache publication or repaint.
5. Preserves legacy synthetic helper callers without a witness while real `scan_page` results always carry one.

The intermediate source HEAD exposed a fixture/compatibility issue: older streaming tests did not create the now-required synthetic PDIC files, and older crop mocks lacked `parent.project`. The new four tests were passing, but Ubuntu Python 3.13 reported 25 full-suite failures in those existing fixtures. Follow-up commit `4458faa953fccc1bb247e3209dba400139c10a68` created synthetic PDIC files in the old fixture and made project-root capture safe for legacy mocks. The production source checks were not weakened.

## Exact source-head E2 evidence

At source/test HEAD `4458faa953fccc1bb247e3209dba400139c10a68`:

- [CI #41287049195](https://github.com/chigre/Picture_Capture/actions/runs/41287049195): **SUCCESS, 6/6** Windows/macOS/Ubuntu × Python 3.10/3.13.
- Risk-tier: **SUCCESS**; Risk-tier CI gate job `124791254146`: **SUCCESS**.
- [OCR Platform Smoke #41287049231](https://github.com/chigre/Picture_Capture/actions/runs/41287049231): **SUCCESS, 3/3**.
- [CodeQL #41287046391](https://github.com/chigre/Picture_Capture/actions/runs/41287046391): Analyze Python and Actions **2/2 SUCCESS**.
- Python 3.13: Ubuntu **5,280 passed / 3 skipped**; macOS **5,281 / 2**; Windows **5,281 / 2**.
- Python 3.10: Ubuntu **5,280 / 3**; macOS **5,281 / 2**; Windows **5,281 / 2**.
- Documentation architecture check: **SKIPPED**, not counted as PASS. The docs checkpoint must receive its own exact-HEAD gate run.

These are automated synthetic E2 results only.

## Code audit and boundaries

- The scan witness intentionally excludes page pixels because the scan path does not read them. The crop witness continues to bind image/PDIC/SECTION bytes.
- Missing OCR cache and missing SECTION are represented as optional source states; a later appearance, disappearance, path change or byte change invalidates the witness.
- SHA-256 readback detects same-size replacements even when mtime is restored.
- The checks are volatile readbacks, **not** an OS-level multi-file CAS, lock, or atomic filesystem snapshot. A file can theoretically change and be restored between observations.
- A no-hit page's witness is currently checked around its own `scan_page` call but is not retained in an epoch-wide page map after the function returns. Mutation of a previously scanned no-hit page before the scan terminal remains a concrete next audit target.
- Save publication code, cross-page transaction semantics, PDIC/PPP/SECTION/Profile formats, image coordinates and actual human records were not modified.
- No real-data benchmark, speedup, precision, recall or accuracy claim is made.

## Repository and operator state

- `main` remains `ec20989ea8c026cca5337293e67850b6b6df30f2`.
- #663 remains the sole development PR and stays Draft/Open/Unmerged.
- #503, #562 and #483 remain Open.
- No inline review comments or submitted reviews were present at this audit.
- **NOT PERFORMED:** Windows R3 E3; #483 W1–W11; #503 manual Undo/Redo; real dictionary scanning; real PDIC/PPP/SECTION/Profile/OCR save/reopen; operator acceptance.
- **DEFERRED:** R6 real-label learning and R8 real scan.

## Next recovery point

1. Commit this audit with synchronized `CORE_QUALITY_STATE.json`, `CORE_QUALITY_RESUME.md` and the corrected plan status.
2. Re-run six-platform CI, Risk-tier + gate, OCR 3OS and CodeQL on the documentation checkpoint HEAD. Do not count a skipped architecture job as pass.
3. Add a fail-first epoch-wide witness test for a previously scanned no-hit page changing before scan terminal; then continue the remaining save/publication consistency audit.
