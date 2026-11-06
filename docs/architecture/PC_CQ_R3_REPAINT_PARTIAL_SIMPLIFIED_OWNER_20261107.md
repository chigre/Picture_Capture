# PC-CQ R3 — partial simplified ReviewWindow rebind must block destructive redraw (2026-11-07)

## Reachable source gap

`review_workspace_workflow.render_rows` already calls `capture_pending_review_words` to protect unsaved original Tk text before destroying old widgets. But its separate `_capture_simplified_edits` returns silently when `_owned_rendered_simplified_rows` cannot prove the current simplified editor's owner (partial row rebind, missing flags/actual fields, stale page, duplicate source). The old code still reached `vars.clear(); ... simplified_vars.clear()` and child.destroy, potentially discarding visible unsaved human simplified input.

## RED → source proof and scope

- Test-only [`5751c2f4b32f6b22b7435608d513413b582b81a8`](https://github.com/chigre/PictureCapture/commit/5751c2f4b32f6b22b7435608d513413b582b81a8) `tests/test_r3_review_redraw_partial_simplified_owner_20261107.py`: synthetic live current Entry and fully rendered original word but partial simplified actual/manual-owner arrays containing visible human text. A deliberate `ReachedPostClear` sentinel at the next materialization stage proves the unsafe clear had already been crossed. Initial truly empty view positive control must be allowed through the same materialization boundary. No private files or real Tk.
- [RED CI #42258690755](https://github.com/chigre/PictureCapture/actions/runs/42258690755) Ubuntu Python3.13: **1 intended post-clear failure / 5759 passed / 3 skipped**; empty initial-view positive control passed. This is reached actual production render_rows after destructive clear, not a random missing dependency fixture.
- [Minimal source `4b8dff8a221fed53493d0d8ba08cab8bc27d7a32`](https://github.com/chigre/PictureCapture/commit/4b8dff8a221fed53493d0d8ba08cab8bc27d7a32), only `src/picture_capture/ui/review_workspace_workflow.py`. Before destructive same-page repaint, if existing simplified widgets have no provable row owner, preserve widgets and original/simplified text, show fixed safe warning, and refuse repaint. An initial empty view continues normally. This preserves strict owner checks; no schema or file writer changed.
- [Exact source CI #42259170860](https://github.com/chigre/PictureCapture/actions/runs/42259170860): **4/6 matrix SUCCESS, pending/non-success Python 3.10 / windows-latest=in_progress/none, test (macos-latest)=queued/none; Risk tier success, Risk-tier gate PENDING** at checkpoint; Ubuntu3.13 **5760 passed/3 skipped**. [OCR #42259170995](https://github.com/chigre/PictureCapture/actions/runs/42259170995): cpu-ocr (ubuntu-latest): success; cpu-ocr (windows-latest): success; cpu-ocr (macos-latest): success. [CodeQL #42259159683](https://github.com/chigre/PictureCapture/actions/runs/42259159683): Analyze (actions): success; Analyze (python): success. Documentation architecture SKIPPED ≠ PASS.

## Limits

Preservation is a fail-closed refusal, not proof that partial rebinding can always auto-heal. Operator must reconcile and retry; no claim that close/discard actions have undergone manual acceptance. Windows E3, #483 W1–W11, #503 human Undo/Redo, actual PDIC/PPP/SECTION/Profile/OCR save/reopen, R6/R8 remain NOT PERFORMED/DEFERRED.
