# G3 R4.2 — direct crop render: exact-source return and Tk callback ownership

Date: 2026-10-31. Sole Draft PR #663. main at `ec20989ea8c026cca5337293e67850b6b6df30f2`. This is automated synthetic E2 only.

## Observed failing counterexamples

Green starting point `6376d1a058bb634b8f09e18955cb80a9f4a67339` had independent [CI #41212007134](https://github.com/chigre/Picture_Capture/actions/runs/41212007134) 6/6 + Risk, [OCR #41212007119](https://github.com/chigre/Picture_Capture/actions/runs/41212007119) 3/3 and [CodeQL #41212004168](https://github.com/chigre/Picture_Capture/actions/runs/41212004168) Python/Actions 2/2 success. Those results do not validate new code.

Test-only commit `13f4abbbb54f787ca0357ebde161f443ae105dda` added deterministic temporary 8×8 RGB BMP, native 8-field PDIC and SECTION sidecars and isolated callback fixtures in `tests/test_g3_r4_prefetch_visible_failure_recovery_20261031.py`. [CI #41213043690](https://github.com/chigre/Picture_Capture/actions/runs/41213043690) Ubuntu Python3.13 actually reported **9 targeted FAILED / 5,192 passed / 3 skipped**. Failures: same-size/restored-mtime image, PDIC or SECTION changes after direct crop but before successful UI callback still inserted stale cache; direct worker read while a source changed; success/error callback or cached hit could redraw/clear a workspace with pending human correction or unconfirmed save. Stable-source and old serial positive controls were not among failures. **The RED test commit is intentionally not a passed release gate.**

## Minimal implementation

`cc1d2d44289eb6b81f9f80adfaa2081567c5d40a` modifies only `src/picture_capture/ui/focused_filter_workflow.py::_request_filter_batch_render`:

1. The background worker rechecks the byte/path-aware image/PDIC/SECTION `focused_crop_source_witness` against the original crop key **after** rendering, before returning payload. Undecidable/missing source fails rather than relabeling a newly changed source.
2. On Tk success, require matching render serial, scan epoch, active selected batch, no pending human edits, no active save, and a fresh batch snapshot exactly matching the original key **before** cache insertion or row repaint. For changed/unreadable source and no pending work, replace an abandoned waiting placeholder with generic explicit refilter notice. The existing apply-time check remains intact as a final additional readback.
3. On Tk failure, preserve current editors when human changes or save are outstanding. A cached-hit render request likewise refuses to repaint those editors, while still invalidating older render callbacks by incrementing the render serial.

## Contract and scope

All source check hashes are volatile evidence; **not** a transactional OS multi-file CAS, and external mutation between last hash and Tk display can remain a race. No change to PDIC/PPP/SECTION/Profile/manual-selection persisted schema, actual PDIC writer, page geometry/source XY, public entrypoints, OCR engine, opt-in defaults or actual operator evidence. No real dictionary, image or private OCR/SECTION/Profile content is used/uploaded. No claims of faster crop, improved OCR accuracy or reliable human workflow performance.

The **final code+docs SHA** requires independent completed CI Windows/macOS/Ubuntu × Python 3.10 and 3.13 six jobs, Risk-tier gate, OCR three-platform Smoke and CodeQL Python/Actions. At this document commit, these gates are **PENDING**, not assumed green. Preserve intermediate red failures; post verified exact-head conclusion in PR #663, without another unverified documentation-only commit.

**NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 manual compound Undo/Redo, actual dictionary-page OCR/crop/PDIC/PPP/SECTION/Profile save-reopen, original-image XY human comparison, real latency measurements. Automated E2 != human E3. **DEFERRED:** R6 verified-label learning, R8 real scans. #663 Draft/Open/Unmerged, main unchanged, blocker Issues Open.

Next resume: review callback duplicate terminal delivery and the direct vs prefetch source handoff under SECTION changes, plus any newly failed CI regression; use test-first incremental guard only if independently reproducible.
