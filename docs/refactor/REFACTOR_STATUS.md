# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and the relevant source paths before writing production code. Historical SHAs below are checkpoints, not assumptions about a future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5D are complete.**

Phase 4 controller decomposition is complete through the approved Detection batch-processing boundary. Phase 5A retired the ordinary-drawing runtime method replacement. Phase 5B made selected-scope single-line method ownership explicit. Phase 5C retired the single-line UI/bootstrap monkey-patch. Phase 5D retired the main selected-scope single-line action's private thread/queue/Tk-poll scheduler by routing it through the existing app-owned parallel batch runner.

## Architecture checkpoint
- Last completed architecture PR: **#238 — Phase 5D: route single-line export through shared batch runner**
- Phase 5D architecture merge commit: `b648fd849f56463b61574b509a2665239bf8c5e3`
- Phase 5D validated production commit: `01b6ff6644c757209a4c1c3b8857b50165e6994a`
- Phase 5D same-tree PR trigger head: `42b12088ae08202303bd0cfa49da2ee907e0cc87`
- Phase 5D validated/merged production tree: `2caeb4e7a4803d33db048e7741a0e883ae1162cf`
- Previous Phase 5C PR: #236 — construct single-line action in normal UI
- Phase 5C architecture merge: `35c7a3a0bbfaa5332372f129948a313a374d3b5f`
- Previous Phase 5B PR: #234 — make selected-scope single-line action ownership explicit
- Phase 5B architecture merge: `44100e93ad148c1b30cc7a7ecf5bd514720ed89e`
- Previous Phase 5A PR: #232 — retire ordinary action runtime monkey patch
- Phase 5A architecture merge: `5f4bf0707fe32a52ab1af1f39a64652d8fcc9874`
- Previous Phase 4Y PR: #230 — `auto_detect_current(...)` routed through `DetectionController`
- Previous Phase 4X PR: #229 — `batch_ocr()` routed through `DetectionController`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none after the Phase 5D architecture merge
- Work in progress: false after this docs checkpoint is merged

## Current controller structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection
`DetectionController` owns the approved user-facing detection action-entry set plus ordinary OCR-independent drawing, Paddle setup, combined/OCR draw actions, scoped OCR routing, `batch_auto_detect()`, `batch_ocr()`, and `auto_detect_current(...)`.

`PictureCaptureApp.run_normal_draw_action()` is an explicit compatibility wrapper. GUI bootstrap no longer replaces it dynamically. `_apply_quick_settings_for_ordinary(...)` remains in `ordinary_action_runtime.py` as an OCR-independent quick-settings helper and is still reused by the selected-scope snapshot helper.

### Crop / selected-scope single-line action after Phase 5D
The explicit selected-scope path is now:

`PictureCaptureApp.split_single_lines_selected_scope()` → `CropController.split_single_lines_selected_scope()` → `PictureCaptureApp._start_parallel_batch_task(...)` → `single_line_parallel.single_line_page_job(...)`.

Ownership is intentionally split as follows:

`CropController` owns the action-specific orchestration:
- rejecting the action when the shared batch runner is already active;
- selected-page/range preflight through the retained `_snapshot_scope(...)` helper;
- project/image/index/settings snapshot;
- output directory creation;
- per-page merge-setting snapshot;
- effective single-line worker count;
- spawn-safe per-page job construction;
- coordinator-side crop-log publication;
- final page/line aggregation and user-facing success/stopped summary;
- temporary disable/restore of the `单行切图` button.

The app-owned shared parallel batch infrastructure owns:
- global `_batch_active` exclusivity;
- background coordinator thread;
- spawn `ProcessPoolExecutor` lifecycle;
- batch queue transport;
- Tk polling/finalization;
- pause/stop integration;
- process-pool shutdown and app-shutdown behavior;
- generic per-item progress/status while work is running.

The main single-line action no longer owns or creates a private thread/queue/Tk poll loop.

### `postproduction_single_line_runtime.py` after Phase 5D
Despite its historical filename, this module is no longer the main single-line scheduler. It is intentionally retained as a temporary shared **preflight/UI-helper boundary** because `unlined_line_export_ui.py` still imports `_snapshot_scope(...)`.

It currently retains:
- `_snapshot_scope(app)` — guard, OCR-independent quick-settings validation, current-page save, selected-index validation, settings snapshot;
- `_status(app, text)`;
- `_set_job_button_state(app, active)`.

It no longer contains:
- `start_single_line_export(...)`;
- a dedicated `threading.Thread(...)` for the main single-line action;
- a dedicated `queue.Queue`;
- a private Tk `after(...)` poll loop;
- `_pc_single_line_crop_active`;
- `_pc_single_line_crop_token`;
- `_pc_single_line_crop_thread`.

Do not delete or rename this module automatically: the still-runtime-owned unlined export currently depends on `_snapshot_scope(...)` and needs a separate ownership decision first.

### Single-line UI ownership after Phase 5C
The `单行切图` control is created in the app's normal postproduction UI construction rather than by a runtime installer. The declared first row is:

`单行切图` → `词条切图` → `插图切图`

The concrete widget is stored as `_pc_single_line_crop_button`. `unlined_line_export_ui` currently uses that normal-app anchor and inserts `未画线行导出` immediately to the right, so the effective visible order remains:

`单行切图` → `未画线行导出` → `词条切图` → `插图切图`

`ExportController`, `HeadwordController`, `ReviewController`, `IllustrationController`, and the other established controllers retain the ownership recorded in earlier checkpoints. `pdic_restore.py` remains the deterministic low-level PDIC restore/publication boundary.

## Completed Phase 5A — ordinary drawing runtime patch
Phase 5A removed `ordinary_action_runtime.install_ordinary_action_runtime(...)` and made the action path explicit through `DetectionController.run_normal_draw_action()`. The OCR-independent quick-settings helper remains reusable.

Validation summary:
- first focused run: **205 passed / 1 source-shape failure**; no behavior failure and no production publication;
- corrected focused suite: **206 passed**;
- full suite: **1248 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- PR #232 Ubuntu / Windows / macOS CI, CodeQL, Advanced Security: passed;
- merge-push Ubuntu / Windows / macOS CI and CodeQL: passed.

## Completed Phase 5B — selected-scope single-line method ownership
Phase 5B removed only the dynamic `split_single_lines_selected_scope` method assignment and established the explicit app-wrapper/controller action entry. It deliberately retained the constructor/UI installer and worker/poll behavior for later slices.

Validation summary:
- first isolated run stopped before tests because `git diff --check` found an EOF blank-line formatting issue in a new test; no behavior failure and no production publication;
- final focused suite: **234 passed**;
- full suite: **1250 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- PR #234 and merge-push Ubuntu / Windows / macOS CI and CodeQL: passed.

## Completed Phase 5C — single-line UI/bootstrap ownership
Phase 5C moved `单行切图` into normal app UI construction and removed the single-line runtime's `PictureCaptureApp.__init__` wrapping, widget-tree search/insertion machinery, and GUI bootstrap installer. It deliberately left the worker/thread/queue/Tk-poll scheduler for Phase 5D.

Validation summary:
- first isolated focused suite: **258 passed**;
- first full suite: **1249 passed / 1 stale layout assertion**, with no production behavior failure and no publication;
- final focused suite: **259 passed**;
- final full suite: **1250 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- validated production tree: `2a5190bfa4720a9f6567f7c539fd732b8171c5b9`;
- PR #236 and merge-push Ubuntu / Windows / macOS CI, GUI smoke, CodeQL, and Advanced Security: passed.

## Completed Phase 5D — main single-line worker/poll ownership
### Live revalidation and architecture choice
Phase 5D started from the Phase 5C docs checkpoint `e81d55f6af752c2f2e246fc51e5e718459c7df61` with no open PR or competing architecture work.

Inspection found that the repository already had an app-owned `_start_parallel_batch_task(...)` abstraction providing spawn-process execution, batch queue/Tk polling, pause/stop handling, and shutdown integration. `single_line_parallel.py` already exposed the spawn-safe `single_line_page_job(...)` needed by that runner.

Inspection also confirmed that `unlined_line_export_ui.py` still imports `_snapshot_scope(...)` from `postproduction_single_line_runtime.py`. Therefore deleting the entire runtime module in Phase 5D would have accidentally bundled the separate unlined runtime seam.

The chosen narrow architecture was therefore:
- do **not** add a new worker service;
- do **not** expand or change the app generic batch-runner API;
- do **not** change `app.py` production code;
- route only the main selected-scope single-line action through the existing app-owned parallel batch runner;
- keep `_snapshot_scope(...)` and its small UI helpers in the historical runtime module until the separate unlined runtime is decomposed;
- leave training export and unlined worker/UI ownership unchanged.

### Production changes
`CropController.split_single_lines_selected_scope()` now:
- exits with the existing busy message when `_batch_active` is true;
- obtains the project/images/indices/settings snapshot from `_snapshot_scope(app)`;
- creates `QT/PSW` through the existing `qt_root(...)` path policy;
- snapshots `load_merge_by_page(project_root)`;
- computes `max(1, min(configured_single_line_workers(project_root), len(indices)))`;
- publishes the preparation status showing serial/parallel mode;
- disables `_pc_single_line_crop_button` while the batch is active;
- builds spawn-safe payloads for `single_line_page_job`;
- appends returned crop records through coordinator-side `append_crop_log(...)`;
- uses `_start_parallel_batch_task(...)` for execution/polling/pause/stop/shutdown;
- restores the button on completion or runner refusal;
- preserves final completed/stopped page and line totals, merge mode, worker mode, and output directory.

The common batch runner now supplies the in-progress per-item status text. This intentionally replaces the former private single-line polling wording; crop/file semantics and final result reporting are unchanged.

`postproduction_single_line_runtime.py` was reduced to the preflight/UI-helper boundary described above.

`single_line_parallel.run_single_line_pages(...)` remains available as a compatibility/test coordinator, but the main selected-scope action no longer calls it; the controller submits `single_line_page_job(...)` directly through the app batch runner.

No production changes were made to:
- `src/picture_capture/app.py`;
- the generic `_start_parallel_batch_task(...)` API;
- `unlined_line_export_ui.py`;
- `training_export_ui.py`;
- single-line crop algorithms, output format, merge algorithm, or path policy.

### Phase 5D validation history
The first isolated validation correctly failed closed in the focused suite:
- patch application and `git diff --check`: passed;
- focused suite: **246 passed / 2 failed**;
- both failures were old Phase 4O source-shape assertions in `tests/test_ui_illustration_controller.py` and `tests/test_ui_illustration_crop_controller.py` that still required `def start_single_line_export(app: Any)` to exist in the runtime;
- no production behavior test failed;
- full suite / compile / F821 / publish steps were skipped;
- no partially validated production tree was promoted.

After updating only those stale ownership assertions:
- final focused suite: **248 passed**;
- final full suite: **1252 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- `git diff --check`: passed;
- temporary `tools/phase5d_apply.py`, `tools/phase5d_fix_assertions.py`, and `.github/workflows/phase5d-validate.yml` were removed before publication;
- validated production commit: `01b6ff6644c757209a4c1c3b8857b50165e6994a`;
- validated production tree: `2caeb4e7a4803d33db048e7741a0e883ae1162cf`;
- same-tree user-authored PR trigger head: `42b12088ae08202303bd0cfa49da2ee907e0cc87`;
- final net diff contained exactly 7 expected files:
  - `src/picture_capture/postproduction_single_line_runtime.py`
  - `src/picture_capture/ui/controllers/crop.py`
  - `tests/test_postproduction_single_line_runtime.py`
  - `tests/test_single_line_parallel.py`
  - `tests/test_ui_crop_controller.py`
  - `tests/test_ui_illustration_controller.py`
  - `tests/test_ui_illustration_crop_controller.py`

PR #238 final-head verification:
- Ubuntu CI: passed;
- Windows CI: passed, including Windows GUI construction smoke;
- macOS CI: passed, including macOS GUI construction smoke;
- pytest, compatibility runner, compile, F821, and wheel build passed on all applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security AI findings: passed;
- no review threads or review objections were present before merge.

Architecture merge: `b648fd849f56463b61574b509a2665239bf8c5e3`.
The merge commit tree remained exactly `2caeb4e7a4803d33db048e7741a0e883ae1162cf`, matching the validated PR tree.

Post-merge verification on `b648fd849f56463b61574b509a2665239bf8c5e3`:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI construction smoke;
- macOS CI: passed, including GUI construction smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Remaining runtime-owned seams after Phase 5D
### Unlined-line export runtime
`unlined_line_export_ui.py` is now the main reason `postproduction_single_line_runtime.py` still exists under that historical name. The unlined path still owns a separate runtime seam including constructor/UI mutation and its own worker/queue/Tk-poll behavior, and it reuses `_snapshot_scope(...)`.

A future unlined cleanup should freshly inspect:
- its `PictureCaptureApp.__init__` wrapping / dynamic UI insertion;
- its method/action assignment behavior;
- its direct use of `_pc_single_line_crop_button` as the insertion anchor;
- its dependency on `_snapshot_scope(...)`;
- worker thread / queue / polling / cancellation / shutdown semantics;
- whether it can use an existing app batch/UI-worker abstraction without changing visible behavior or output semantics.

Do not delete `postproduction_single_line_runtime.py` before this dependency is resolved.

### Training export assignment
GUI bootstrap still assigns the training export action from `training_export_ui.export_training_package_selected_range`. It owns batch staging/finalization, cancellation cleanup, manifest/ZIP publication, and an auxiliary UI-worker cleanup path. Treat this as a separate export/batch ownership decision and do not bundle it with unlined cleanup unless live inspection proves the boundaries inseparable.

### Other installers
Other GUI/bootstrap runtime installers remain. Continue evaluating them by actual ownership, UI mutation, import-order constraints, worker behavior, compatibility surface, and shutdown semantics rather than mechanically deleting installers.

## Next architecture decision point
Phase 5D is complete and recoverable. Two highlighted directions remain materially different:

1. **Unlined-line export UI/runtime decomposition — recommended next assessment.** This is the natural continuation because the main single-line runtime scheduler is gone and the retained `_snapshot_scope(...)` helper exists primarily because the unlined runtime still imports it. Fresh inspection should determine whether the unlined UI seam and worker seam are separable and whether the existing app batch/UI-worker abstractions can be reused safely.
2. **Training export method-assignment cleanup.** Separate export/batch ownership problem. Do not bundle it with unlined cleanup without a new architecture decision.

Because these are materially different ownership directions, **human confirmation is required before the next production-code write**. Completion of Phase 5D is not authorization to start the unlined or training-export migration automatically.

Before the next production write, revalidate:
- live `main` and open PRs;
- complete `unlined_line_export_ui.py` installer/UI/action/worker path and all callers;
- current use of `_pc_single_line_crop_button` and `_snapshot_scope(...)`;
- any app-owned batch/UI-worker abstraction that might replace private unlined thread/polling;
- shutdown/cancellation/stale-result semantics;
- `training_export_ui.py` only if selecting that separate route;
- tests asserting button placement, method ownership, output semantics, and worker behavior.

Do not rerun the full suite merely on wake-up with no code change.

## Auto continuation
Phase 5D is complete and recoverable. Automatic production-code continuation is paused at the next Phase 5 architecture decision point.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone/ownership transition not already explicitly approved.
