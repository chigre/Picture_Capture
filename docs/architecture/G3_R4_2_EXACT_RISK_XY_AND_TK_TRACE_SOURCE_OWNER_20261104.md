# G3 R4.2 — strict risk-queue source XY and Tk edit trace ordering

**Date:** 2026-11-04 (SGT). **Main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Sole development PR:** #663, Draft/Open/Unmerged. **Source HEAD:** `61d29a23a12c5bee56a7a3ded3e3544a88fe2e97`.

## Two distinct synthetic source-boundary counterexamples

1. Read-only, default-OFF opt-in risk priority view previously coerced `row["x"]` and `row["y"]` with `int()`. A source target with textual `"30"`, float `30.0` or `30.7`, or boolean `True` was allowed to inherit an attested integer PDIC source point or trigger ranking of other rows even though this page queue contained an unowned target. Test-only `6ac6eff0` added ten malformed X/Y cases and a real-integer positive control against independently synthetic OCR/PDIC/PNG and origin witness. [RED CI](https://github.com/chigre/PictureCapture/actions/runs/41680157583) Ubuntu Python3.13 had exactly ten intended failures, 5550 passed, 3 skipped.
2. The UI's live `_commit_filter_editor_value` set `target["current_word"]` *before* calling the already strict `_queue_focused_change`. For malformed page index or original-image X/Y, the guarded queue refused to schedule a writer, but the target had already been changed. Test-only `796f61ee` added nine malformed source owner cases plus a valid control on a minimal synthetic Tk StringVar adapter. [RED CI](https://github.com/chigre/PictureCapture/actions/runs/41680462020) Ubuntu Python3.13 had exactly 19 intended failures total (ten prior + nine new), 5551 passed, 3 skipped.

## Narrow fix and assurance boundaries

[Source `61d29a23`](https://github.com/chigre/PictureCapture/commit/61d29a23a12c5bee56a7a3ded3e3544a88fe2e97) changes exactly two production modules:

- `proofreading/review_risk_snapshot.py`: when priority mode is explicitly enabled, require `type(x) is int` and `type(y) is int` **before** constructing a source tuple. Invalid targets cause unchanged original ordering and no risk annotation. The default OFF path still performs no extra I/O.
- `ui/focused_filter_workflow.py`: remove the early `target["current_word"] = value` assignment in the StringVar commit handler. The existing guarded queue updates it only after exact page/XY validation. Positive integer path still queues normal human edits with identical debounce.

Exact source GREEN: [CI](https://github.com/chigre/PictureCapture/actions/runs/41680839943), [OCR](https://github.com/chigre/PictureCapture/actions/runs/41680839652), [CodeQL](https://github.com/chigre/PictureCapture/actions/runs/41680831854) **PENDING at authoring**. Documentation architecture job SKIPPED (not PASS). Verify this audit/documentation HEAD separately; do not inherit source check results.

Prior macOS Python3.13 native Tk in-flight reversion failure at source `4642f6cb` remains root-cause **UNVERIFIED** despite prior docs `da229d2e` passing six-matrix CI. Do not represent these new boundary fixes as a concurrency-race repair. No OCR accuracy, clinical/real-world operator evidence, machine learning, images, new PDIC/schema format, OS multi-file atomicity or rollback claim. Windows E3, #483 W1–W11, #503 complex manual Undo/Redo, real dictionary scan-save-reopen, R6/R8 remain NOT PERFORMED/DEFERRED.
