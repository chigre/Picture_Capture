# G3 R4.2 — exact page/XY identity at focused human edit queue

**Date:** 2026-11-03. **Repository:** chigre/Picture_Capture. **Source/test HEAD:** `00167584d552dbb58c5c341af3cf5661e1e55a1e`. **Development:** sole PR #663 Draft/Open/Unmerged; main `ec20989ea8c026cca5337293e67850b6b6df30f2`.

## Concrete failure mechanism

The downstream PDIC writer previously acquired exact-integer checks but its UI caller, `_queue_focused_change`, still applied `int(target["page_index"])`, `int(target["x"])` and `int(target["y"])`. For example, 3.9 or "3" could become pixel 3, and `True` could become 1. A malformed upstream target might therefore be queued under another real marker's coordinate and pass downstream exactness checks after the type was erased. This is a defensive synthetic hazard, not a claim that live OCR data actually contains such types.

## Executed RED-first evidence

The only test change in [`a40c7b7f`](https://github.com/chigre/Picture_Capture/commit/a40c7b7f5f1db6f5e9fd7869813c7b2bdf5c6e84) adds nine invalid page/XY cases (fractional, boolean, numeric text) and one normal integer control. The expectation is that malformed targets cannot modify `_filter_pending_changes`, schedule a writer or mutate `current_word`. [CI #41628494277](https://github.com/chigre/Picture_Capture/actions/runs/41628494277) completed all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs with exactly nine intended failures each. Ubuntu3.13: 9 failed/5502 passed/3 skipped; Windows3.10: 9 failed/5503 passed/2 skipped. Risk-tier CI gate FAILURE on RED is not accepted.

## Minimal fix and GREEN source-head gates

[`00167584`](https://github.com/chigre/Picture_Capture/commit/00167584d552dbb58c5c341af3cf5661e1e55a1e) changes one UI module (15 additions/2 deletions). It reuses `_source_page_index` from source fingerprinting and `_exact_page_coordinate` from the PDIC owner and returns before editing or queuing for a malformed page/XY. There is an optional visible status message; valid true-integer page/XY values retain existing behavior. No schema, crop image, OCR arbitration, canvas coordinate, PDIC serializer, or worker timing changed.

- [CI #41629160886](https://github.com/chigre/Picture_Capture/actions/runs/41629160886): all six matrix **SUCCESS**, Risk tier/gate **SUCCESS**.
- [OCR #41629160918](https://github.com/chigre/Picture_Capture/actions/runs/41629160918): three OS **SUCCESS**.
- [CodeQL #41629155015](https://github.com/chigre/Picture_Capture/actions/runs/41629155015): Python/Actions **SUCCESS**.
- Documentation architecture check **SKIPPED**, not a passing check. New documentation HEAD must be verified independently.

## Limits / resumption

This is automated synthetic E2, not Windows R3 E3 or a real save-reopen transaction. A post-publication PDIC error can still mean the write landed; no rollback or cross-file atomicity is promised. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo and real dictionary/OCR/PDIC/PPP/SECTION/Profile are **NOT PERFORMED/DEFERRED**. R6 real labels and R8 actual scan remain DEFERRED. Keep default-OFF evidence settings, sole Draft PR, unchanged main and issues. Next bounded audit: strict original-image XY through filter batch signature/crop render and asynchronous session provenance; only proceed on executable fail-first evidence.
