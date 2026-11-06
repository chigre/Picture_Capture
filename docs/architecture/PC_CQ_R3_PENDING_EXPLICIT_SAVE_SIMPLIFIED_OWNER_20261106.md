# PC-CQ R3 — pending-page explicit Save/Next must not acknowledge unowned simplified text (2026-11-06)

## Reachable source gap

The ordinary ReviewWindow autosave path already refused partially rebound simplified row owners, but the separate explicit save() path lacked the same check. When _foreground_batch_state returned pending, the "no dirty input" fast path checked _simplified_dirty_pages and _has_unreported_simplified_input. The latter deliberately returns False when _owned_rendered_simplified_rows cannot prove live ownership; this cannot mean a half-bound human Tk input is saved. Consequently explicit Save returned True, and change_page used that True to navigate and replace the editor.

## Failure-first evidence

- [Test-only RED 0d578454b91e9eb592388943f3a626067cd31bbd](https://github.com/chigre/PictureCapture/commit/0d578454b91e9eb592388943f3a626067cd31bbd), tests/test_r3_pending_explicit_save_partial_simplified_owner_20261106.py. Synthetic same-page row identity with an incomplete simplified flags/actual-values binding, plus a pending foreground batch; contains no user text/images or real disk writes.
- [CI #42181740573](https://github.com/chigre/PictureCapture/actions/runs/42181740573), Ubuntu Python3.13 **2 intended failed / 5747 passed / 3 skipped**, macOS Python3.13 **2 intended failed / 5748 passed / 2 skipped**. Explicit save wrongly returned True and Next-page wrongly called parent.change_page. Fully bound unchanged Save and legacy original-only positive controls passed.

## Minimal production change and verified HEAD

- [cbdb6de36874814c44b88c710faeed124e541d21](https://github.com/chigre/PictureCapture/commit/cbdb6de36874814c44b88c710faeed124e541d21) modifies ONLY src/picture_capture/ui/review_page_lifecycle.py. On pending pages with real simplified widgets and bound rows, require _owned_rendered_simplified_rows before bridge or no-op fast path; if incomplete, mark _r3_autosave_unconfirmed, show fixed safe warning, return False, keep human Tk words intact. Does not weaken normal guarded bundle, background claim, original-only compatibility or previously repaired autosave/PPP status guard.
- [CI #42182133098](https://github.com/chigre/PictureCapture/actions/runs/42182133098), Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, Risk-tier + CI gate SUCCESS, Ubuntu3.13 **5749 passed / 3 skipped**. All four focused tests pass.
- [OCR #42182133226](https://github.com/chigre/PictureCapture/actions/runs/42182133226) **3/3 SUCCESS**; [CodeQL #42182128094](https://github.com/chigre/PictureCapture/actions/runs/42182128094) Python/Actions **2/2 SUCCESS**. Documentation architecture SKIPPED, NOT PASS.

## Limits

No real user page Save/Next, actual PDIC/PPP/SECTION/Profile/OCR save/reopen, Windows human E3, #483 W1–W11, #503 human Undo/Redo, R6 labels or R8 scans. E2 cannot be described as real operator acceptance. No persistence format, XY, external/private data, OS-level atomicity or CAS changes. Next review must start from LIVE HEAD and new independent RED-first candidate.
