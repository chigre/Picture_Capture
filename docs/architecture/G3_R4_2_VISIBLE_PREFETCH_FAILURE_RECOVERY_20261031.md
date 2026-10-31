# G3 R4.2 — failed N+1 prefetch: selected-batch recovery without stale source promotion

Date: 2026-10-31. Single Draft PR #663 only. main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged.

## Observed test-first red

Based on verified-green `c9837923b0bcf5184ac16098688a4688600c68b6`, test-only commit `1166cd5e18c3bc13e67417b23ea8e3ca15db9491` added synthetic cases to `tests/test_g3_r4_prefetch_visible_failure_recovery_20261031.py`. In [CI #41204531136](https://github.com/chigre/Picture_Capture/actions/runs/41204531136), macOS Python3.13 had **5 targeted FAILED, 5,180 passed, 2 skipped**: a selected N+1 batch prefetch failure left the UI waiting indefinitely; source-byte changes to image, PDIC or SECTION did not give the user a refilter warning. Control tests for old epochs, non-selected batches, and outstanding human changes did not produce those target failures. This red-only SHA is **not** an accepted gate. Other CI job statuses must be inspected rather than inferred.

## Minimal fix and proof boundary

Modify only `ui/focused_filter_workflow.py::_schedule_filter_next_batch_preload`'s failure callback. It must first match both the current scan epoch and the *same active prefetch key*; otherwise leave newer state untouched. For a still-selected N+1 batch only, and only if no focused human edits or save worker are pending, recheck the exact current image/PDIC/SECTION content witness. If the witness is byte-identical, initiate the already-existing direct-render path **once**; failure of that direct worker uses its own terminal refusal, not an automatic retry loop. If witness changed or unreadable, explicitly request rescreening in generic terms and clear only the abandoned waiting placeholder. Never silently accept a different SECTION, discard an edited source XY, surface a private exception, or claim a multi-file OS-level CAS guarantee.

Test fixture PDIC now uses a real newline delimiter, rather than escaped backslash+n, while retaining the eight native fields. The tests use only temporary generated 8×8 BMP, PDIC and SECTION bytes, including equal-size/restored-mtime external changes. There is no real dictionary, OCR upload, learning, R6/R8 data, persistence writer/schema/XY modification, nor observed performance speedup.

## Exact-head requirements

The **final code+docs commit** must independently pass Windows/macOS/Ubuntu × Python3.10/3.13 **6/6**, Risk-tier CI gate, OCR three-OS Smoke **3/3** and CodeQL Python/Actions **2/2** before its E2 scope can be marked verified; conditional Documentation architecture SKIPPED is not a pass. At commit time these final checks were PENDING; report actual completed results in an immutable post-gate PR comment.

**NOT PERFORMED:** real Windows operator R3 E3, #483 W1–W11, #503 full compound Undo/Redo, scanned dictionary GUI/OCR/PDIC/PPP/SECTION/Profile/crop save-reopen and large-image latency. **DEFERRED:** R6 human truth, R8 scanned baseline. Retain #663 Draft/Open/Unmerged, main unchanged, blocker issues open.
