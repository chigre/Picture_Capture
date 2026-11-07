# G3 R4.2 — image/PDIC/SECTION source drift vs asynchronous crop cache (2026-10-31)

## Problem, scope and physical ownership

`src/picture_capture/ui/focused_filter_workflow.py::_filter_batch_snapshot` originally keyed its crop preview solely by source page index/X/Y, original word, settings, viewport and zoom. An unchanged tuple thus reused a cached/prefetched crop after **original image pixels**, **PDIC contents**, or the actually read **SECTION sidecar** were replaced. Same-sized replacement bytes with the old modification timestamp still passed. Even `_apply_filter_batch_payload` accepted the stale payload and updated column/sequence metadata. This risks visually attributing a crop to a stale source; it does **not** by itself prove a bad persisted PDIC write or historic OCR accuracy.

## Real red-first evidence (no private images)

- Test-only `d53abc953f0e0d72531d05d091888620bb245747`; corrected test-only `0426f197e8890a648a3ae15565b4deb048487fc0` restores the **original** image mtime in the same-size image negative control.
- [Red-first CI #41168242309](https://github.com/chigre/Picture_Capture/actions/runs/41168242309): Ubuntu Python 3.13 runner logs show **7 expected failures, 4,997 passed, 3 skipped**; macOS Python 3.13 **7 expected failures, 4,998 passed, 2 skipped**. Four failures prove equal old/new cache keys after image/PDIC/SECTION mutation or SECTION removal. Three failures prove `_apply_filter_batch_payload` incorrectly returned True for stale image/PDIC/SECTION. Unchanged-source positive control passed. The intentionally RED commit is not an acceptance gate.
- Test `tests/test_g3_r4_crop_source_snapshot_20261031.py` creates disposable tiny BMP and synthetic PDIC/SECTION content; no real dictionary, profile, OCR cache, labels or scan pixels.

## Bounded source fix

- New physical owner `proofreading/focused_crop_source_fingerprint.py` (`7ac6fb024fb3fbb804a1da96acd40d1840cf13fe`) reads only selected batch pages, and SHA-256 hashes the image, active PDIC and active SECTION file. It uses the existing managed/legacy resolver `page_sections_read_path_for_image`, records resolved paths, and distinguishes absent SECTION. An image or selected PDIC missing/unreadable fails closed. All witnesses are **memory-only**; they are neither OCR-origin attestation nor human truth labels.
- Existing owner `ui/focused_filter_workflow.py` (`746ddef47298e18c608e54e231d967a8fea88e3f`) incorporates the resulting witness into the crop cache key. On subsequent async worker/cached-payload application, source drift changes the key; stale render is rejected without changing visible human editors, target column metadata or PDIC files. A source that cannot be snapshotted yields a generic message instead of a misleading crop or raw source path. No new schema, persistent setting, OCR/PDIC/PPP/SECTION writer, source XY or R3 transaction changed.

## Exact guarantees and remaining risks

This is content-byte readback at discrete snapshot/apply times, **not OS-level cross-file atomicity or continuous source locking**. Extremely large page images may add synchronous preview-hash I/O and need actual operator performance evaluation; no speed benchmark is claimed. The earlier focused-save callback privacy fix remains intact, but this batch **does not extend the new source witness to authorize the PDIC writer after a later image/SECTION change**. This separate R3/source-save ownership gate needs its own test-first package before claiming edit/save consistency. No source-time OCR witness may be retroactively manufactured.

At authoring the source [CI #41168312629](https://github.com/chigre/Picture_Capture/actions/runs/41168312629) Windows/macOS/Ubuntu × Python3.10/3.13 was still running (Risk-tier success); do **not** treat it as final until all jobs conclude. Source [OCR Smoke #41168312628](https://github.com/chigre/Picture_Capture/actions/runs/41168312628) passed all three OS. Source [CodeQL/PR #41168309968](https://github.com/chigre/Picture_Capture/actions/runs/41168309968) Python and Actions succeeded. The final docs commit creates a new HEAD and needs its **own** exact-head CI, OCR, Risk-tier and CodeQL verification.

Still **NOT PERFORMED:** real Windows R3 E3, #483 W1–W11, #503 complex Undo/Redo, G3 operator workflow and actual dictionary-page GUI/PDIC/PPP/SECTION/Profile save-reopen. R6 verified human labels and R8 real-scan evaluation remain **DEFERRED**. The sole PR #663 stays Draft/Open/Unmerged, main unchanged; no automatic merge, Ready or issue closure.
