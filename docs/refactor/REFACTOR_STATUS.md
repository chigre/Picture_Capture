# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and the relevant source paths before writing production code. Historical SHAs below are checkpoints, not assumptions about the future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A and Phase 5B method-ownership slice are complete.**

Phase 4 controller decomposition is complete through the approved Detection batch-processing boundary. Phase 5A retired the ordinary-drawing runtime method replacement. Phase 5B retired only the dynamic `split_single_lines_selected_scope` method injection while deliberately leaving the wider single-line GUI/worker runtime in place.

## Architecture checkpoint
- Last completed architecture PR: **#234 — Phase 5B: make selected-scope single-line action ownership explicit**
- Phase 5B architecture merge commit: `44100e93ad148c1b30cc7a7ecf5bd514720ed89e`
- Phase 5B validated production commit: `d72151f45be0683b6942dc61d7542b6dd92aecfb`
- Phase 5B same-tree PR trigger head: `65cff08d67c448ddef0a72c52f5a68b7c05ebde3`
- Previous Phase 5A PR: #232 — retire ordinary action runtime monkey patch
- Phase 5A architecture merge commit: `5f4bf0707fe32a52ab1af1f39a64652d8fcc9874`
- Previous Phase 4Y architecture PR: #230 — `auto_detect_current(...)` routed through `DetectionController`
- Phase 4Y merge commit: `6b5af293232039102fddcf90bb51c6a2373023e7`
- Phase 4X PR: #229 — `batch_ocr()` routed through `DetectionController`
- Phase 4X merge commit: `704936dfe90c5132f130475a2ff199cd4bc3d9ab`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none after the Phase 5B checkpoint is merged
- Work in progress: false

## Current controller structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection
`DetectionController` owns the explicit user-facing detection action-entry set plus the approved batch/current-page orchestration, including ordinary OCR-independent drawing, Paddle setup, combined/OCR draw actions, scoped OCR routing, `batch_auto_detect()`, `batch_ocr()`, and `auto_detect_current(...)`.

`PictureCaptureApp.run_normal_draw_action()` is an explicit compatibility wrapper. GUI bootstrap no longer replaces it dynamically. The OCR-independent helper `_apply_quick_settings_for_ordinary(...)` remains in `ordinary_action_runtime.py` because the still-runtime-owned single-line export path reuses it.

The app still owns generic `_start_batch_task(...)`, `_detect_pages(...)`, transformed-geometry guarding, page tuple generation, shared page/review/quality refresh helpers, and broader UI/persistence infrastructure.

### Crop / single-line export after Phase 5B
`CropController` now explicitly owns both the established crop actions and the selected-scope single-line **action entry**:
- `split_lines_current()`
- `split_whole_current()`
- `batch_split_whole()`
- `split_entries_selected_scope()` and the previously completed crop-controller seams
- `split_single_lines_selected_scope()` — new explicit Phase 5B ownership

`PictureCaptureApp.split_single_lines_selected_scope()` is now a compatibility wrapper and delegates to `CropController.split_single_lines_selected_scope()`.

The controller intentionally does **not** own the temporary Tk thread/poll implementation yet. Its selected-scope method delegates to `postproduction_single_line_runtime.start_single_line_export(app)` as an explicit temporary scheduler boundary.

`ExportController`, `HeadwordController`, `ReviewController`, `IllustrationController`, and the remaining controllers retain the ownership recorded in earlier checkpoints. `pdic_restore.py` remains the deterministic low-level PDIC restore/publication boundary.

## Completed Phase 5A seam — ordinary drawing runtime patch
Before Phase 5A, `PictureCaptureApp` contained a legacy `run_normal_draw_action()` body while `ordinary_action_runtime.install_ordinary_action_runtime(...)` replaced it again at GUI bootstrap time. The runtime replacement also carried the important OCR-independent validation needed when all visible OCR engines were disabled.

Phase 5A made that action ownership explicit:
- app body reduced to a compatibility wrapper;
- action orchestration moved into `DetectionController.run_normal_draw_action()`;
- `install_ordinary_action_runtime(...)` was removed;
- GUI bootstrap no longer imports or invokes that installer;
- `ordinary_action_runtime.py` remains only as a helper module for `_apply_quick_settings_for_ordinary(...)`.

The all-OCR-off behavior remains preserved: the helper temporarily satisfies only the legacy OCR-presence validation when necessary, then restores the user's visible OCR selection/settings before ordinary drawing or the retained single-line path continues.

Phase 5A validation:
- first isolated focused run: **205 passed / 1 failed**; the only failure exposed the pre-existing legacy app method body and was ownership/source-shape only;
- no behavior test failed and no partially validated production tree was promoted;
- corrected focused suite: **206 passed**;
- full suite: **1248 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- final net diff: exactly 6 expected files;
- PR #232 Ubuntu / Windows / macOS CI, CodeQL Python/Actions, and Advanced Security passed;
- merge-push Ubuntu / Windows / macOS CI and CodeQL Python/Actions passed.

## Completed Phase 5B seam — selected-scope single-line method ownership
Before Phase 5B, `postproduction_single_line_runtime.install_postproduction_single_line_runtime(...)` mixed several distinct responsibilities:
1. dynamically assigned `split_single_lines_selected_scope` onto `PictureCaptureApp`;
2. wrapped `PictureCaptureApp.__init__`;
3. located the existing postproduction `词条切图` control and dynamically inserted the `单行切图` button;
4. owned a dedicated background thread, event queue, Tk polling/finalization loop, button state, token/state fields, and cancellation/staleness handling.

Phase 5B deliberately removed **only responsibility 1**. The resulting path is now explicit:

`单行切图 button command` → `PictureCaptureApp.split_single_lines_selected_scope()` → `CropController.split_single_lines_selected_scope()` → `postproduction_single_line_runtime.start_single_line_export(app)` → retained runtime worker/thread/poll implementation.

Production changes:
- added explicit `PictureCaptureApp.split_single_lines_selected_scope()` compatibility wrapper;
- added explicit `CropController.split_single_lines_selected_scope()` action entry;
- renamed the runtime scheduler boundary from private `_start_single_line_export(app)` to explicit `start_single_line_export(app)` and exported it;
- removed `app_class.split_single_lines_selected_scope = split_single_lines_selected_scope` from the installer;
- retained `install_postproduction_single_line_runtime(...)` because it still owns the `__init__` wrap and dynamic button insertion;
- retained the dedicated worker/thread/event-queue/poll implementation and its private runtime state;
- GUI bootstrap installer order was not changed;
- training export and all unrelated runtime installers were not touched.

### Phase 5B validation history
Live revalidation started from the Phase 5A docs checkpoint `8fcc7bfe259d85147d7f92bc212307328a11cf30`, with no open PR or competing architecture work.

The first isolated Phase 5B run failed closed **before tests**:
- the migration itself applied successfully;
- `git diff --check` reported one newly appended blank line at EOF in `tests/test_postproduction_single_line_runtime.py`;
- this was a migration-helper formatting issue only, not a production behavior or architecture failure;
- no production tree was published from that run.

After normalizing the test EOF, final isolated validation passed:
- focused single-line/runtime/controller suite: **234 passed**;
- full suite: **1250 passed, 2 existing Pillow deprecation warnings**;
- `git diff --check`: passed;
- compileall: passed;
- Ruff F821: passed;
- validated production commit: `d72151f45be0683b6942dc61d7542b6dd92aecfb`;
- same-tree user-authored PR CI trigger head: `65cff08d67c448ddef0a72c52f5a68b7c05ebde3`;
- final production tree: `584cf0f0a196012b39f844c9cdc41e6f223ce2f7`;
- temporary migration scripts/workflow were removed before the validated production commit;
- final net diff contained exactly 8 expected files:
  - `src/picture_capture/app.py`
  - `src/picture_capture/postproduction_single_line_runtime.py`
  - `src/picture_capture/ui/controllers/crop.py`
  - `tests/test_postproduction_single_line_runtime.py`
  - `tests/test_ui_crop_controller.py`
  - `tests/test_ui_crop_controller_selected_scope.py`
  - `tests/test_ui_illustration_controller.py`
  - `tests/test_ui_illustration_crop_controller.py`

PR #234 final-head verification:
- Ubuntu CI: passed;
- Windows CI: passed, including Windows GUI construction smoke;
- macOS CI: passed, including macOS GUI construction smoke;
- pytest, compatibility runner, compile, F821, and wheel build passed on applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security AI findings: passed;
- no review threads or review objections were present before merge.

Post-merge verification on architecture merge `44100e93ad148c1b30cc7a7ecf5bd514720ed89e`:
- Ubuntu CI: passed;
- Windows CI: passed;
- macOS CI: passed;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Remaining runtime-owned seams after Phase 5B
Phase 5B does **not** retire `postproduction_single_line_runtime` itself. The remaining responsibilities need separate ownership decisions.

### `postproduction_single_line_runtime` UI/bootstrap seam
Still runtime-owned:
- wraps `PictureCaptureApp.__init__`;
- after normal app construction, searches the main postproduction UI for `词条切图`;
- dynamically inserts the `单行切图` button relative to that widget;
- maintains button enabled/disabled state tied to its private job state.

Removing the `__init__` wrapper likely requires an explicit UI construction seam or a deliberate app/controller hook. Do not simply delete the installer or move the button code without first inspecting `_build_ui()` ordering, widget ownership, and tests that depend on the current placement.

### `postproduction_single_line_runtime` worker/poll seam
Still runtime-owned:
- selected-page/range preflight and OCR-independent quick-setting validation inside the retained scheduler path;
- worker thread creation;
- event queue transport;
- Tk `after(...)` polling/finalization;
- active-job token/thread/private state;
- success/error/stale-result finalization and button restoration.

`CropController.split_single_lines_selected_scope()` currently calls the explicit scheduler helper rather than duplicating or moving these semantics. This is intentional. A later migration should decide whether these belong in CropController, a reusable UI-worker abstraction, or a dedicated service; do not infer that moving them wholesale into the controller is automatically correct.

### Training export assignment
GUI bootstrap still assigns the training export action onto `PictureCaptureApp` from `training_export_ui.export_training_package_selected_range`. It owns batch staging/finalization, cancellation cleanup, manifest/ZIP publication, and an auxiliary UI-worker cleanup path. Treat it as a separate ownership problem from single-line runtime cleanup.

### Other installers
Other GUI/bootstrap runtime installers remain. Phase 5 is incremental: evaluate each by actual runtime ownership, UI mutation, import-order constraints, worker behavior, compatibility surface, and shutdown semantics rather than mechanically eliminating all installers.

## Next architecture decision point
Phase 5B method ownership is complete and recoverable. The next production change is **not automatic**, because at least three materially different directions remain:

1. **Single-line UI/bootstrap decomposition.** Remove the `PictureCaptureApp.__init__` monkey-patch and dynamic button insertion by establishing an explicit UI construction hook. This is the most direct continuation of Phase 5B, but it touches GUI construction ordering and therefore needs fresh live inspection.
2. **Single-line worker/poll decomposition.** Move or redesign the thread/event-queue/Tk polling ownership. This is behaviorally heavier than the method-ownership slice and should not be bundled with UI/bootstrap cleanup unless live inspection proves they cannot be separated safely.
3. **Training export method-assignment cleanup.** A separate export/batch ownership problem; do not bundle it with either single-line seam.

Recommended order for assessment is **single-line UI/bootstrap seam first**, then reassess the worker/poll seam, because the method entry is already explicit and the remaining installer exists primarily to mutate construction/UI. This is a recommendation, not authorization for another production write.

Before the next production write, revalidate:
- live `main` and open PRs;
- current `postproduction_single_line_runtime.py` installer and scheduler;
- `PictureCaptureApp.__init__`, `_build_ui()`, postproduction frame/button construction, and all UI bindings;
- current CropController import/dependency direction;
- runtime private state initialization and shutdown/stale-result behavior;
- tests asserting the relative placement and command target of `单行切图`;
- training-export assignment only if selecting that separate route.

Do not rerun the full suite merely on wake-up with no code change.

## Auto continuation
Phase 5B method-ownership cleanup is complete and recoverable. Automatic production-code continuation is paused at the next Phase 5 architecture decision point.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone/ownership transition not already explicitly approved.
