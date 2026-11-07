# PC-CQ R4.2 — async ReviewWindow crop uses frozen human Tk text (2026-11-07)

## Reachable source gap

`_request_render_rows` snapshots each visible original-word Tk value in `editor_texts`, and the background worker computes crop height from those text values. The delivery callback previously compared only Entry ID, XY and **Entry.word**, which stays at the last committed word while an unsaved Tk edit occurs. Thus an older worker could paint crops sized for a previous text buffer even though newer human text must be preserved. This is a crop/UI snapshot mismatch, not proof of an incorrect PDIC save.

## RED → source GREEN

- Test-only [`3b3485245d2352551a64275446a684cb2798b5c3`](https://github.com/chigre/PictureCapture/commit/3b3485245d2352551a64275446a684cb2798b5c3), `tests/test_r42_review_async_visible_text_witness_20261107.py`: traps real worker/done callback registration in a synthetic Tk-like view, changes the editor value before callback, and asserts no stale repaint + renewed worker. Unchanged input control must render normally; no worker/image/OCR/project disk interaction.
- [RED CI #42257858949](https://github.com/chigre/PictureCapture/actions/runs/42257858949) Ubuntu Python3.13 and 3.10: **1 intended stale-Tk assertion failure / 5757 passed / 3 skipped**, unchanged control passed.
- Minimal [source `db786f1b4cb7583c611b3f85c524daa0099dbc64`](https://github.com/chigre/PictureCapture/commit/db786f1b4cb7583c611b3f85c524daa0099dbc64): only `src/picture_capture/ui/review_workspace_workflow.py`. On UI callback, after model-source signature verification, recompute exact current bound Tk text tuple and compare to worker-launch snapshot. Refuse obsolete crop, trigger owner-safe rerender; no clearing/saving user text in this check.
- [Exact source CI #42258437428](https://github.com/chigre/PictureCapture/actions/runs/42258437428): Python 3.10 / ubuntu-latest:success, Python 3.10 / macos-latest:success, test (macos-latest):success, Python 3.10 / windows-latest:success, test (windows-latest):success, test (ubuntu-latest):success; Risk tier and Risk-tier CI gate SUCCESS (six matrix SUCCESS 6/6 at checkpoint). [OCR #42258437502](https://github.com/chigre/PictureCapture/actions/runs/42258437502) 3/3 SUCCESS; [CodeQL #42258431303](https://github.com/chigre/PictureCapture/actions/runs/42258431303) Python/Actions 2/2 SUCCESS. Architecture documentation check SKIPPED, not PASS.

## Limits

Only synthetic E2, not an actual Windows GUI/user text, real OCR fidelity, crop latency benchmark, on-disk source transaction guarantee, or real save/reopen acceptance. No schema, original coordinates, persistence roles, or actual editor data changed.
