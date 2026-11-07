# G3 R4.2 — project / ReviewWindow session lifecycle guards

Date: 2026-11-03 (SGT). Sole development [PR #663](https://github.com/chigre/Picture_Capture/pull/663) remains Draft/Open/Unmerged. Live main baseline is `ec20989ea8c026cca5337293e67850b6b6df30f2`; source/test HEAD is `25d5cb46c38af10a831a31f7c8abc63eddc7bcb0`. Issues #503/#562/#483 remain Open; no unresolved inline review threads. Synthetic E2 only; no real scanned dictionary or operator acceptance.

## Scope and ownership contract

Two UI orderings could otherwise replace the project context while a non-modal proofreading window still holds callbacks against the previous `ProjectState`:

1. **ReviewWindow already open → user selects another project.** `project_session_workflow._load_project` now checks the existing `self.review_window` and its `winfo_exists()` state after the same-project no-op and before deferred page-save flush, timer cancellation, settings persistence, or `project-load` worker dispatch. A live window blocks the switch with a status prompt. It is not implicitly destroyed and no extra save is triggered. The existing `review_close_actions.close_review` / `review_page_lifecycle._finish_close_review` path remains the sole owner of save/uncertain-outcome coordination and clears the parent reference only as the window safely finishes closing.
2. **Project-load worker already active → user opens ReviewWindow.** `main_dialog_lifecycle.open_review` checks `_ui_worker_key_active("project-load")` before `guard()`, main-editor synchronization, review-setting mutation, or construction. It refuses the open until project loading completes.

The same-project reopen early return is retained. The new guards do not change PDIC/PPP/SECTION formats, source XY, OCR behavior, crop geometry, save semantics, or experimental defaults.

## RED-first evidence

- **Project switch guard:** test-only [`49d3401f`](https://github.com/chigre/Picture_Capture/commit/49d3401f73a49493e57ab0f40f322f3271ce6cfa) added `test_project_switch_is_refused_while_review_window_is_alive` and the same-project no-op control. [CI #41469931769](https://github.com/chigre/Picture_Capture/actions/runs/41469931769) completed failure on all six Windows/macOS/Ubuntu × Python3.10/3.13 matrix jobs, on the intended assertion that project loading started while a live ReviewWindow still owned the old session. Ubuntu Python3.13: 1 failed / 5432 passed / 3 skipped. Minimal production guard: [`9a608895`](https://github.com/chigre/Picture_Capture/commit/9a608895d61c64b352e63c8d189a913ac059cc97), in `src/picture_capture/ui/project_session_workflow.py`.
- **Reverse ordering:** test-only [`bfc2412d`](https://github.com/chigre/Picture_Capture/commit/bfc2412d9ad98ea45d40d13874ab2891d5729ab3) added `test_open_review_is_refused_while_project_load_worker_is_active`. [CI #41472574845](https://github.com/chigre/Picture_Capture/actions/runs/41472574845) completed failure on all six matrix jobs, on the intended assertion that ReviewWindow opened during project loading. Ubuntu Python3.13: 1 failed / 5434 passed / 3 skipped. Minimal production guard: [`5f2f5b00`](https://github.com/chigre/Picture_Capture/commit/5f2f5b008b6a9d89be927d6b134bfbb45cdd6139), in `src/picture_capture/ui/main_dialog_lifecycle.py`.
- A subsequent CI attempt [#41473173332](https://github.com/chigre/Picture_Capture/actions/runs/41473173332) caught a **test wording mismatch only**: the test expected `项目正在加载`, while the actual status string was `项目正在后台加载`. Test-only correction [`25d5cb46`](https://github.com/chigre/Picture_Capture/commit/25d5cb46c38af10a831a31f7c8abc63eddc7bcb0) aligned the assertion; no production behavior changed in that correction.

## Exact source/test HEAD verification

At `25d5cb46c38af10a831a31f7c8abc63eddc7bcb0`:

| Matrix job | Result |
| --- | --- |
| Ubuntu Python 3.13 | 5435 passed / 3 skipped |
| macOS Python 3.13 | 5436 passed / 2 skipped |
| Windows Python 3.13 | 5435 passed / 3 skipped |
| Ubuntu Python 3.10 | 5435 passed / 3 skipped |
| macOS Python 3.10 | 5436 passed / 2 skipped |
| Windows Python 3.10 | 5436 passed / 2 skipped |

- [CI #41473874028](https://github.com/chigre/Picture_Capture/actions/runs/41473874028): **COMPLETED SUCCESS**, all six matrix jobs; Risk tier and Risk-tier CI gate SUCCESS.
- [OCR #41473873904](https://github.com/chigre/Picture_Capture/actions/runs/41473873904): **COMPLETED SUCCESS 3/3** (Windows/macOS/Ubuntu).
- [CodeQL #41473865458](https://github.com/chigre/Picture_Capture/actions/runs/41473865458): Analyze Python and Analyze Actions **2/2 SUCCESS**.
- Native Tk smoke logs on all six regression jobs report actual synthetic thumbnail pixels and the scroll/sort identity check successful.
- Documentation architecture check in this source/test run was **SKIPPED**, not counted as PASS. This documentation checkpoint must receive its own exact-HEAD gate verification.

## Separate Windows thumbnail Tk-smoke intermittency audit

Historical [CI #41458526317](https://github.com/chigre/Picture_Capture/actions/runs/41458526317) attempt 1 failed only the Windows Python3.10 job after 5427 passed / 2 skipped. The native GUI smoke raised `RuntimeError: Real thumbnails never loaded into native first-column cells`. The unchanged-head attempt 2 Windows Python3.10 job (125324407177) succeeded with 5426 passed / 3 skipped. This remains a real recorded intermittent failure; the rerun does not prove its root cause was repaired.

The current smoke at `scripts/gui_smoke.py:159-165` waits 60 × 30 ms (1.8 seconds) for the first three native PhotoImage pixels. The controller polls worker results every 50 ms and retries an empty viewport at most 12 × 100 ms. Native Treeview mapping/layout timing or worker completion delay are plausible contributors, but no failure-state snapshot was captured; **root cause is unconfirmed**. At the latest exact source/test HEAD #41473874028, Windows Python3.13 and Python3.10 both passed the native thumbnail pixel/sort checks. No timeout widening, assertion weakening, skip, or production thumbnail behavior change was made. If the failure recurs, capture mapped state, widget height, visible iids, controller generation, pending tickets, worker failures, `ThumbnailTasks.active`, poll state and cache paths before deciding on a fix.

## Explicit non-claims and next work

- No real image/PDIC/PPP/SECTION/Profile/OCR data or human records were used or changed.
- No filesystem multi-file atomicity, OCR accuracy, performance improvement, or human acceptance is claimed.
- Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, and real dictionary scan/save-reopen remain **NOT PERFORMED**. R6/R8 remain **DEFERRED**.
- Next engineering packet: continue bounded G3 R4.2 SECTION/crop/source/save ownership with a concrete RED-first counterexample. Keep the Windows thumbnail intermittent failure unresolved unless reproduced.
