# G3 R4.2 — exact Tk save callbacks and page-owned risk evidence

**2026-11-04 JST** · main `ec20989ea8c026cca5337293e67850b6b6df30f2` · sole active [Draft PR #663](https://github.com/chigre/PictureCapture/pull/663) · source `252808dc724e243938f63df7d9fcc858d42e607d`.

## Two source-identity defects, independently observed RED

1. A completed or failed focused save called `int()` on live `filtered_targets` to associate prior PDIC source coordinates with Tk rows. A string, integral/fractional float or bool could be associated with another edit or cause a callback exception. This could suppress recovery of a valid uncommitted correction when a malformed visible row happened to appear reverted. The same risk existed for the second main-canvas view's `Entry.x/y`. Test-only [`559c3a6b`](https://github.com/chigre/PictureCapture/commit/559c3a6b435f49090c491e00cdd6e149324d1745) yielded **22 intended failures / 5572 pass / 3 skip** on Ubuntu Python 3.13.
2. Provenance-validated risk triage read an attested page, then attached priority to view rows without checking their `page_index` type, `page_name`, and optional `page_stem`. One forged/mixed view row could receive another page's priority or produce partially annotated rows. Test-only [`723d4d76`](https://github.com/chigre/PictureCapture/commit/723d4d768c8244f3d5bac0748bb601bec0576fcc) produced **31 intended failures total (22+9) / 5573 pass / 3 skip** on Ubuntu Python 3.13.

No private dictionary input, user data, real pixel, model, cache or schema were added. These are hardening cases, not confirmed incidents in a normal scan where target page/XY are generated as integers.

## Minimal fix and architecture ratchet

- `proofreading/review_risk_snapshot.py` checks each view row's genuine integer page key, consistent page index, actual page filename and (when present) stem **before** running provenance I/O. Any mismatch returns the original order and references without new risk annotations. The setting remains opt-in OFF by default.
- `proofreading/focused_visible_owner.py` is a new pure/read-only identity owner. It accepts only genuine integral source page/XY; duplicate coordinates are ambiguous and excluded, not resolved by last row or nearest neighbor.
- `ui/focused_filter_workflow.py` uses those unique map keys both when restoring an unwritten snapshot after callback failure and when reconciling committed rows to live targets, preserving newer queued writes and in-flight revert precedence.
- `proofreading/main_editor_sync.py` now owns precise source-page/main-canvas Entry reconciliation after a verified save. A malformed or duplicated main Entry can never inherit someone else's committed word.
- Initial [`b89b43b1`](https://github.com/chigre/PictureCapture/commit/b89b43b12bdd92588eaa9034d5e0ee3258bc83ab) failed the unchanged architecture size guard at **100,988 > 100,000** bytes. The subsequent structural extraction [`252808dc`](https://github.com/chigre/PictureCapture/commit/252808dc724e243938f63df7d9fcc858d42e607d) brought `ui/focused_filter_workflow.py` down to **98,271 bytes** without weakening the guard. Additional seven synthetic cases in [`074d8354`](https://github.com/chigre/PictureCapture/commit/074d835438eec9721205b74d02a7d3ead96c1a6c) cover duplicate display/canvas owners and invalid current page indices.

## Gates, limits and rollback

- [Source CI](https://github.com/chigre/PictureCapture/actions/runs/41688399205) six Windows/macOS/Ubuntu × Python 3.10/3.13 + Risk tier/gate: **PENDING at creation**.
- [Source OCR smoke](https://github.com/chigre/PictureCapture/actions/runs/41688399189) three OS: **PENDING**. [CodeQL](https://github.com/chigre/PictureCapture/actions/runs/41688392097) Python+Actions: **SUCCESS**. Architecture documentation check SKIPPED is not a pass; docs HEAD requires separate CI.
- No changes to public signatures, model/pickle paths, monkeypatch seams, actual writer, ND/PNG pixels, OCR priority defaults, or PDIC/PPP/SECTION schema. Source guards are optimistic; do not claim filesystem CAS, multi-file atomicity or rollback of foreign writes.
- Rollback: if eventual GREEN CI proves a regression, revert `252808dc`, `074d8354`, and `b89b43b1` together with the two RED tests only after preserving observed failing evidence; never reset/force-push an active PR.
- Known distinct native macOS Tk in-flight reversion intermittent conflict: root cause **UNVERIFIED**; no claim that these identity checks resolve it. Windows operator E3, W1-W11, #503 manual undo/redo, real dictionary OCR save/reopen and R6/R8 are NOT PERFORMED/DEFERRED.
