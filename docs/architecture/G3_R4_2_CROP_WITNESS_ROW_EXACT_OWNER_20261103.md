# G3 R4.2 — exact integer page owner in crop-to-save witness handoff

**Date:** 2026-11-03 (Asia/Singapore). **Sole development PR:** #663 (Draft/Open/Unmerged). **main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Source/test:** `4642f6cb481c9de78b30458b19fa55c496279e38`.

## Independent source-grounded counterexample

The earlier post-write image/SECTION and PDIC final readback protections are present and stay unchanged. A separate internal handoff remained in `proofreading/focused_crop_source_fingerprint.py`: the caller's `page_index` passed strict `operator.index` validation, while each internal crop `row[0]` used ordinary Python equality. `False == 0`, `True == 1`, `0.0 == 0`, and `1.0 == 1`. A forged/malformed volatile crop witness row carrying correct image/SECTION bytes could therefore yield an accepted `focused-save-source-v1` for a page despite invalid owner type. The normal witness constructor produces true integers; this proves a defensive input-boundary defect, not a normal live user incident.

Test-only commit [`db71a8f3`](https://github.com/chigre/PictureCapture/commit/db71a8f3617d65ee74f54050e682a580d7fef6d5) adds four purely synthetic malformed row cases, valid page 0/1 controls and wrong-page negative control. [RED CI #41665644553](https://github.com/chigre/PictureCapture/actions/runs/41665644553) already demonstrated four intended new pytest failures in Ubuntu Python3.13 and Python3.10 (5,545 other tests passing, 3 pre-existing skips per job). At writing, other RED matrix jobs were still pending; failures must not be counted as passing gates.

## Minimal code change and assurance boundary

[Source commit `4642f6cb`](https://github.com/chigre/PictureCapture/commit/4642f6cb481c9de78b30458b19fa55c496279e38) changes only `focused_crop_source_fingerprint.py` (+3/−1 lines): validate the internal row key with the existing strict `_source_page_index` helper before matching the requested owner. Malformed type raises within the established catch and returns `None`; legal integer rows retain the same accepted source witness. No persistent schema, original raster XY, write protocol, rollback, OCR model, experiment default, or private data is touched.

Source-matched isolated local logic returned RED before the fix and GREEN after the fix; this was **not a full local repository test** because the container lacks a GitHub-resolvable checkout. True repository evidence comes from exact-HEAD GitHub Actions.

## Pending exact-HEAD acceptance

- [Source CI #41666027710](https://github.com/chigre/PictureCapture/actions/runs/41666027710): six Windows/macOS/Ubuntu × Python3.10/3.13, Risk-tier/gate — **PENDING** at authoring.
- [OCR #41666027649](https://github.com/chigre/PictureCapture/actions/runs/41666027649): Windows/macOS/Ubuntu — **PENDING**.
- [CodeQL #41666019492](https://github.com/chigre/PictureCapture/actions/runs/41666019492): Python + Actions **SUCCESS 2/2**, tied to source SHA.
- Documentation architecture check: **SKIPPED**, not PASS. This docs SHA has separate gates.

The optional low-level save witness remains distinct from the mandatory live UI attestation. No cross-file compare-and-swap, atomic multi-file snapshot, rollback of already-published PDIC data, real OCR quality or operator acceptance is asserted.

**Human DEFERRED:** Windows R3 E3; #483 W1–W11; #503 manual Undo/Redo; real dictionary/PDIC/PPP/SECTION/Profile/OCR scan, save and reopen. R6 real-label training and R8 real scanning stay OFF/DEFERRED.

**Resume:** Re-fetch the live branch SHA and check all exact-source and exact-documentation gates. Then begin a genuinely new scoped review of scan epoch owner or save uncertainty only with executable synthetic RED evidence. Never merge, mark Ready, close issues or overwrite main.
