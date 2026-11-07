# PC-CQ R3 / #503 — candidate replay after durable commit: Tk refresh failure quarantine

Date: 2026-10-31. Only the open unmerged Draft PR #663 is modified. Main remains `ec20989ea8c026cca5337293e67850b6b6df30f2`.

## Genuine failure observed before the source fix

On the exact previously green baseline `683b06bed6fe0750ec94f6b4f65f2b89adda075a`, a *test-only* commit `8f528a4f4c991682833e85dda84840be5951f5ab` added eight real synthetic bundle-replay cases: Undo/Redo × derived word-count/page-row refresh × RuntimeError/TclError. CI [#41197223626](https://github.com/chigre/Picture_Capture/actions/runs/41197223626) independently showed eight targeted failures on Ubuntu Python3.13 (5168 other tests passed, 3 skipped) and eight on macOS Python3.13 (5169 other passed, 2 skipped). The failure occurred **after** the original `publish_owned_review_bundle` had durably published authoritative PDIC/manual/simplified bytes, while `CandidateReviewHistory._apply` had not yet moved its replay frame.

A late Tk-destroyed row refresh could propagate a private-looking RuntimeError/TclError to the UI and leave the Undo/Redo stack pointing at the old step even though files already changed. This is a confirmed *synthetic automated E2* failure, not a real Windows operator E3 observation. The intentionally red SHA is NOT an accepted gate.

## Narrow repair

In `src/picture_capture/proofreading/candidate_history.py`, after the existing successful bundle publication and Entry/candidate state reconciliation:
1. Move the completed replay frame to its destination stack **before** any derived word-count/page-row callback.
2. Contain exceptions exclusively around the post-commit `_refresh_word_fill_check_from_line_count(..., persist=True)` and `_update_page_row` best-effort updates, including destroyed Tk TclError/RuntimeError. Do not report a false disk failure, publish a rollback, expose the injected error/path, or replay a committed frame.
3. Keep the original precommit exact source checks, three-file recovery/publishing writer, original XY, human manual-selection/OCR ownership, serialized formats, default OFF settings and no auto-learning entirely unchanged.

The eight synthetic tests assert exact resulting PDIC bytes, optional manual override bytes, original Entry objects/words, candidate checkbox source, correctly advanced replay stacks and no private exception leakage. These tests do not claim that derived word-count metadata was successfully refreshed after an injected exception; later UI refresh may be necessary. No new persistent undo log or cross-file atomic CAS is claimed.

## Exact-head gates and outstanding acceptance

At documentation creation the final code+docs SHA and complete CI were **PENDING**. Verify Windows/macOS/Ubuntu × Python3.10/3.13 all 6/6, Risk-tier gate, OCR 3/3, CodeQL Python/Actions 2/2 and Tk synthetic smoke against the final HEAD, then record immutable results in a PR comment; a skipped documentation job does not count as a pass.

**NOT PERFORMED:** real Windows R3 E3, #483 W1–W11, full #503 composite and cross-session Undo/Redo acceptance, real dictionary source/OCR/PDIC/PPP/SECTION/Profile save-reopen and large-image benchmark. **DEFERRED:** R6 human-labelled truth, R8 real-scan evaluation. Keep #663 Draft/Open/Unmerged, main unchanged, blocker Issues open. Do not upload private data.
