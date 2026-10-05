# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and the relevant source paths before writing production code. Historical SHAs below are checkpoints, not assumptions about a future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A, Phase 5B, and Phase 5C are complete.**

Phase 4 controller decomposition is complete through the approved Detection batch-processing boundary. Phase 5A retired the ordinary-drawing runtime method replacement. Phase 5B made selected-scope single-line method ownership explicit. Phase 5C retired the remaining single-line **UI/bootstrap** monkey-patch while deliberately leaving the single-line worker/thread/queue/Tk-poll scheduler as a separate runtime boundary.

## Architecture checkpoint
- Last completed architecture PR: **#236 — Phase 5C: construct single-line action in normal UI**
- Phase 5C architecture merge commit: `35c7a3a0bbfaa5332372f129948a313a374d3b5f`
- Phase 5C validated production commit: `c803522a272141df9b2d2f522426c01198fbcd2d`
- Phase 5C same-tree PR trigger head: `ab27be6d86779d89373d3c03701c74245ec02bb3`
- Phase 5C validated/merged production tree: `2a5190bfa4720a9f6567f7c539fd732b8171c5b9`
- Previous Phase 5B PR: #234 — make selected-scope single-line action ownership explicit
- Phase 5B architecture merge: `44100e93ad148c1b30cc7a7ecf5bd514720ed89e`
- Previous Phase 5A PR: #232 — retire ordinary action runtime monkey patch
- Phase 5A architecture merge: `5f4bf0707fe32a52ab1af1f39a64652d8fcc9874`
- Previous Phase 4Y PR: #230 — `auto_detect_current(...)` routed through `DetectionController`
- Previous Phase 4X PR: #229 — `batch_ocr()` routed through `DetectionController`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none after the Phase 5C architecture merge
- Work in progress: false after this docs checkpoint is merged

## Current controller structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection
`DetectionController` owns the approved user-facing detection action-entry set plus ordinary OCR-independent drawing, Paddle setup, combined/OCR draw actions, scoped OCR routing, `batch_auto_detect()`, `batch_ocr()`, and `auto_detect_current(...)`.

`PictureCaptureApp.run_normal_draw_action()` is an explicit compatibility wrapper. GUI bootstrap no longer replaces it dynamically. `_apply_quick_settings_for_ordinary(...)` remains in `ordinary_action_runtime.py` as a helper because the still-runtime-owned single-line export scheduler reuses its OCR-independent validation behavior.

### Crop / selected-scope single-line action
`PictureCaptureApp.split_single_lines_selected_scope()` is an explicit compatibility wrapper and delegates to `CropController.split_single_lines_selected_scope()`.

`CropController.split_single_lines_selected_scope()` is the explicit action owner and currently delegates to `postproduction_single_line_runtime.start_single_line_export(app)` as a temporary scheduler boundary. The controller intentionally does **not** yet own the thread/event-queue/Tk-poll implementation.

### Single-line UI ownership after Phase 5C
The `单行切图` control is now created by the app's normal postproduction UI construction rather than by a runtime installer.

The first row of `五、后期词典制作` is declared as:

`单行切图` → `词条切图` → `插图切图`

During normal button construction the concrete `单行切图` widget is stored as `self._pc_single_line_crop_button`.

`unlined_line_export_ui` remains a separate runtime seam. It already prefers `_pc_single_line_crop_button`, so after normal app construction it can still insert `未画线行导出` immediately to the right of `单行切图`. The effective visible ordering therefore remains:

`单行切图` → `未画线行导出` → `词条切图` → `插图切图`

Phase 5C deliberately did **not** change the unlined runtime's own method assignment, `__init__` wrapper, or worker/UI behavior.

`ExportController`, `HeadwordController`, `ReviewController`, `IllustrationController`, and the other established controllers retain the ownership recorded in earlier checkpoints. `pdic_restore.py` remains the deterministic low-level PDIC restore/publication boundary.

## Completed Phase 5A — ordinary drawing runtime patch
Phase 5A removed `ordinary_action_runtime.install_ordinary_action_runtime(...)` and made the action path explicit through `DetectionController.run_normal_draw_action()`. The OCR-independent quick-settings helper remains as a reusable helper and preserves the all-OCR-off validation behavior.

Validation summary:
- first focused run: **205 passed / 1 source-shape failure** exposing the pre-existing app method body; no behavior failure and no production publication;
- corrected focused suite: **206 passed**;
- full suite: **1248 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- PR #232 Ubuntu / Windows / macOS CI, CodeQL, Advanced Security: passed;
- merge-push Ubuntu / Windows / macOS CI and CodeQL: passed.

## Completed Phase 5B — selected-scope single-line method ownership
Before Phase 5B, `postproduction_single_line_runtime.install_postproduction_single_line_runtime(...)` mixed method injection, app-constructor wrapping, dynamic UI insertion, and worker/poll orchestration.

Phase 5B removed only the dynamic method assignment. The explicit action path became:

`PictureCaptureApp.split_single_lines_selected_scope()` → `CropController.split_single_lines_selected_scope()` → `postproduction_single_line_runtime.start_single_line_export(app)`.

It retained the constructor/UI installer and worker/poll behavior for later slices.

Validation summary:
- first isolated run stopped before tests because `git diff --check` found an EOF blank-line formatting issue in a new test; no behavior failure and no production publication;
- final focused suite: **234 passed**;
- full suite: **1250 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- PR #234 Ubuntu / Windows / macOS CI, GUI smoke, CodeQL, Advanced Security: passed;
- merge-push Ubuntu / Windows / macOS CI and CodeQL: passed.

## Completed Phase 5C — single-line UI/bootstrap ownership
### Live revalidation and scope
Phase 5C started from the Phase 5B checkpoint `c788bbedec50000f70519218068ff99d559f03bb` with no open PR or competing architecture work.

Live inspection confirmed that `PictureCaptureApp` already had a normal declarative construction point for the `五、后期词典制作` row. This made the UI seam separable from the worker/poll seam.

The approved scope was therefore limited to:
- normal construction of `单行切图` in `app.py`;
- removal of the single-line runtime's `PictureCaptureApp.__init__` monkey-patch and widget-tree insertion machinery;
- removal of the corresponding installer import/call from GUI composition;
- preserving the worker/thread/queue/Tk-poll scheduler unchanged in responsibility;
- preserving `unlined_line_export_ui`, training export, and all unrelated runtime installers.

### Production changes
`app.py` now:
- declares `单行切图` in the normal postproduction first row before `词条切图` / `插图切图`;
- supplies its normal tooltip through the same production tooltip table;
- stores the concrete widget as `_pc_single_line_crop_button` during normal sidebar button construction.

`postproduction_single_line_runtime.py` no longer contains the UI/bootstrap seam:
- no `install_postproduction_single_line_runtime(...)`;
- no `PictureCaptureApp.__init__` wrapping;
- no widget-tree walking/search for `词条切图`;
- no presentation-copy helper;
- no pack/grid-relative insertion helper;
- no dynamic `单行切图` widget creation.

It still intentionally owns:
- selected-scope snapshot/preflight;
- OCR-independent quick-setting validation;
- background thread creation;
- event queue transport;
- Tk `after(...)` polling/finalization;
- active-job token/thread/button state;
- success/error/stale-result handling and button restoration.

`bootstrap/gui.py` no longer imports or invokes a single-line postproduction installer. `install_unlined_line_export_ui(app_module)` remains and resolves the normally-created `_pc_single_line_crop_button` after app construction.

Training export and all unrelated runtime installers were unchanged.

### Phase 5C validation history
The first isolated run correctly failed closed during the full suite:
- focused suite: **258 passed**;
- full suite: **1249 passed / 1 failed, 2 existing Pillow warnings**;
- the sole failure was `tests/test_core.py::test_sidebar_defaults_fold_sections_two_through_five_and_keep_project_details`, whose source-shape assertion still hard-coded the old first row containing only `词条切图` / `插图切图`;
- this was exactly the approved UI-row ownership change, not a production behavior failure;
- the workflow stopped before compile/publish and no partially validated production tree was promoted.

After updating only that stale layout assertion and adding it to the focused set:
- focused suite: **259 passed**;
- full suite: **1250 passed, 2 existing Pillow deprecation warnings**;
- `git diff --check`: passed;
- compileall: passed;
- Ruff F821: passed;
- validated production commit: `c803522a272141df9b2d2f522426c01198fbcd2d`;
- same-tree user-authored PR CI trigger: `ab27be6d86779d89373d3c03701c74245ec02bb3`;
- validated production tree: `2a5190bfa4720a9f6567f7c539fd732b8171c5b9`;
- temporary migration scripts/workflow were removed before the validated production commit;
- final net diff contained exactly 8 expected files:
  - `src/picture_capture/app.py`
  - `src/picture_capture/bootstrap/gui.py`
  - `src/picture_capture/postproduction_single_line_runtime.py`
  - `tests/test_core.py`
  - `tests/test_postproduction_single_line_runtime.py`
  - `tests/test_ui_illustration_controller.py`
  - `tests/test_ui_illustration_crop_controller.py`
  - `tests/test_unlined_line_export.py`

PR #236 final-head verification:
- Ubuntu CI: passed;
- Windows CI: passed, including Windows GUI construction smoke;
- macOS CI: passed, including macOS GUI construction smoke;
- pytest, compatibility runner, compile, F821, and wheel build passed on applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security AI findings: passed;
- no review threads or review objections were present before merge.

Architecture merge: `35c7a3a0bbfaa5332372f129948a313a374d3b5f`.
The merge commit tree remained exactly `2a5190bfa4720a9f6567f7c539fd732b8171c5b9`, matching the validated PR tree.

Post-merge verification on `35c7a3a0bbfaa5332372f129948a313a374d3b5f`:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI construction smoke;
- macOS CI: passed, including GUI construction smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Remaining runtime-owned seams after Phase 5C
Phase 5C does **not** remove `postproduction_single_line_runtime.py`; it reduces it to the remaining scheduler/worker boundary.

### Single-line worker/poll seam
Still runtime-owned:
- selected-page/range preflight and OCR-independent quick-setting validation;
- worker thread creation;
- event queue transport;
- Tk `after(...)` polling/finalization;
- active-job token/thread/private state;
- success/error/stale-result finalization and button restoration.

`CropController.split_single_lines_selected_scope()` still calls `start_single_line_export(app)`. A later slice must decide whether these responsibilities belong in CropController, a reusable UI-worker abstraction, or a dedicated service. Do not mechanically move the entire scheduler into the controller without fresh dependency/shutdown inspection.

### Unlined-line export runtime
`unlined_line_export_ui` remains a separate runtime seam. It has its own constructor/UI mutation and action/worker responsibilities. Phase 5C only established a stable normal-app button anchor for it; it did not authorize removing that runtime.

### Training export assignment
GUI bootstrap still assigns the training export action from `training_export_ui.export_training_package_selected_range`. It owns batch staging/finalization, cancellation cleanup, manifest/ZIP publication, and an auxiliary UI-worker cleanup path. Treat this as a separate export/batch ownership decision.

### Other installers
Other GUI/bootstrap runtime installers remain. Continue evaluating them by actual ownership, UI mutation, import-order constraints, worker behavior, compatibility surface, and shutdown semantics rather than mechanically deleting installers.

## Next architecture decision point
Phase 5C is complete and recoverable. The remaining highlighted directions are materially different:

1. **Phase 5D — single-line worker/poll decomposition (recommended next assessment).** Revalidate `start_single_line_export`, `_snapshot_scope`, `_single_line_worker`, thread/queue/Tk-poll lifecycle, private token/button state, shutdown/staleness semantics, and CropController dependency direction. If inspection confirms a narrow extractable boundary, prefer separating scheduler/service ownership before deleting the runtime module.
2. **Training export method-assignment cleanup.** Separate export/batch ownership problem; do not bundle with single-line scheduler cleanup.
3. **Unlined-line runtime decomposition.** Separate constructor/UI/action/worker seam; the new `_pc_single_line_crop_button` anchor makes its UI dependency clearer, but it still requires its own architecture decision.

Because these directions differ materially, **human confirmation is required before the next production-code write**. Completion of Phase 5C is not authorization to start Phase 5D automatically.

Before the next production write, revalidate:
- live `main` and open PRs;
- the complete remaining `postproduction_single_line_runtime.py` scheduler path and all callers;
- CropController import/dependency direction;
- button-state/private token/thread fields and application shutdown/stale-result behavior;
- any reusable batch/UI-worker abstractions already present before introducing a new one;
- `training_export_ui.py` only if selecting that separate route;
- `unlined_line_export_ui.py` only if selecting its separate route.

Do not rerun the full suite merely on wake-up with no code change.

## Auto continuation
Phase 5C is complete and recoverable. Automatic production-code continuation is paused at the next Phase 5 architecture decision point.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone/ownership transition not already explicitly approved.
