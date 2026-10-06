# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and the relevant source paths before writing production code. Historical SHAs below are checkpoints, not assumptions about a future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5E are complete.**

Phase 4 controller decomposition is complete through the approved Detection batch-processing boundary. Phase 5A retired the ordinary-drawing runtime method replacement. Phase 5B made selected-scope single-line method ownership explicit. Phase 5C retired the single-line UI/bootstrap monkey-patch. Phase 5D routed the main selected-scope single-line action through the shared app-owned parallel batch runner. Phase 5E retired the remaining unlined-line export UI/action/runtime installer and routed that action through the same explicit app/CropController/shared-batch architecture.

## Architecture checkpoint
- Last completed architecture PR: **#240 — Phase 5E: retire unlined export runtime installer**
- Phase 5E architecture merge commit: `dcb916c352d9eb15c4866252698ee1abb3de9392`
- Phase 5E validated production commit: `a37b08cc9ec3ca3bc31eb015bd97630108d4e21f`
- Phase 5E same-tree PR trigger head: `e9311cea3263c334b796f5a1f2933237d377ccbe`
- Phase 5E validated/merged production tree: `3ece5025453c8d9975cd430f2b4ab0421e8787d5`
- Previous Phase 5D PR: #238 — route single-line export through shared batch runner
- Phase 5D architecture merge: `b648fd849f56463b61574b509a2665239bf8c5e3`
- Previous Phase 5C PR: #236 — construct single-line action in normal UI
- Phase 5C architecture merge: `35c7a3a0bbfaa5332372f129948a313a374d3b5f`
- Previous Phase 5B PR: #234 — make selected-scope single-line action ownership explicit
- Phase 5B architecture merge: `44100e93ad148c1b30cc7a7ecf5bd514720ed89e`
- Previous Phase 5A PR: #232 — retire ordinary action runtime monkey patch
- Phase 5A architecture merge: `5f4bf0707fe32a52ab1af1f39a64652d8fcc9874`
- Previous Phase 4Y PR: #230 — `auto_detect_current(...)` routed through `DetectionController`
- Previous Phase 4X PR: #229 — `batch_ocr()` routed through `DetectionController`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none after the Phase 5E architecture merge
- Work in progress: false after this docs checkpoint is merged

## Current controller structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection
`DetectionController` owns the approved user-facing detection action-entry set plus ordinary OCR-independent drawing, Paddle setup, combined/OCR draw actions, scoped OCR routing, `batch_auto_detect()`, `batch_ocr()`, and `auto_detect_current(...)`.

`PictureCaptureApp.run_normal_draw_action()` is an explicit compatibility wrapper. GUI bootstrap no longer replaces it dynamically. `_apply_quick_settings_for_ordinary(...)` remains in `ordinary_action_runtime.py` as an OCR-independent quick-settings helper and is reused by selected-scope preflight.

### Crop / selected-scope single-line action
The explicit single-line path is:

`PictureCaptureApp.split_single_lines_selected_scope()` → `CropController.split_single_lines_selected_scope()` → `PictureCaptureApp._start_parallel_batch_task(...)` → `single_line_parallel.single_line_page_job(...)`.

`CropController` owns single-line-specific preflight, settings/index snapshots, per-page job construction, output/log publication, final aggregation, and temporary button disable/restore. The app-owned shared parallel batch infrastructure owns global batch exclusivity, coordinator thread, spawn process pool, queue/Tk polling, pause/stop, shutdown behavior, generic progress, and generic error finalization.

The main single-line action no longer owns a private thread/queue/Tk-poll loop.

### Crop / selected-scope unlined-line export after Phase 5E
The explicit unlined path is now:

`PictureCaptureApp.export_unlined_rows_selected_scope()` → `CropController.export_unlined_rows_selected_scope()` → `PictureCaptureApp._start_parallel_batch_task(...)` → runtime-resolved `unlined_line_export.export_unlined_page_job(...)`.

Ownership after Phase 5E:
- the `未画线行导出` button is constructed normally in the app postproduction row, immediately after `单行切图`;
- the concrete widget is retained as `_pc_unlined_export_button`;
- `PictureCaptureApp.export_unlined_rows_selected_scope()` is an explicit compatibility wrapper;
- `CropController` owns selected-scope snapshot/preflight, unlined per-page job payload construction, button-state handling, final aggregation, and user-facing completion/stopped summary;
- the existing app-owned parallel batch runner owns process-pool lifecycle, queue/Tk polling, pause/stop, global exclusivity, generic progress/error handling, and app-shutdown behavior;
- the main unlined action no longer owns its own thread, queue, Tk poll loop, or constructor/UI mutation seam.

The visible first-row order is now declared directly by normal UI construction:

`单行切图` → `未画线行导出` → `词条切图` → `插图切图`

### Retired Phase 5E runtime/helper modules
The following modules were removed in Phase 5E:
- `src/picture_capture/postproduction_single_line_runtime.py`
- `src/picture_capture/unlined_line_export_ui.py`

Their remaining stable responsibilities were absorbed into explicit normal ownership rather than moved to another runtime installer. `scripts/architecture_guard.py` was ratcheted so `postproduction_single_line_runtime.py` is no longer permitted legacy debt.

### Unlined fast-path preservation
`bootstrap/gui.py` still installs the separate `unlined_fast_path_runtime` worker optimization after app/controller imports. This remains a performance-path seam, not the retired UI/action runtime seam.

To preserve that install order, `CropController` deliberately imports the `unlined_line_export` **module** and resolves `unlined_export.export_unlined_page_job` at action time. Do not replace this with a top-level by-value import of `export_unlined_page_job`; doing so would bypass the installed fast worker and silently fall back to the slower full-layout path.

The following were intentionally unchanged in Phase 5E:
- `unlined_line_export.py` algorithms;
- output/manifest semantics;
- filter and merge settings;
- `run_unlined_export(...)` compatibility coordinator;
- the physical-row/LayoutRows/Profile fast-worker behavior;
- training export behavior.

`ExportController`, `HeadwordController`, `ReviewController`, `IllustrationController`, and the other established controllers retain the ownership recorded in earlier checkpoints. `pdic_restore.py` remains the deterministic low-level PDIC restore/publication boundary.

## Completed Phase 5A — ordinary drawing runtime patch
Phase 5A removed `ordinary_action_runtime.install_ordinary_action_runtime(...)` and made the action path explicit through `DetectionController.run_normal_draw_action()`. The OCR-independent quick-settings helper remains reusable.

Validation summary:
- corrected focused suite: **206 passed**;
- full suite: **1248 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- PR #232 and merge-push Ubuntu / Windows / macOS CI and CodeQL: passed.

## Completed Phase 5B — selected-scope single-line method ownership
Phase 5B removed only the dynamic `split_single_lines_selected_scope` method assignment and established the explicit app-wrapper/controller action entry.

Validation summary:
- final focused suite: **234 passed**;
- full suite: **1250 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- PR #234 and merge-push Ubuntu / Windows / macOS CI and CodeQL: passed.

## Completed Phase 5C — single-line UI/bootstrap ownership
Phase 5C moved `单行切图` into normal app UI construction and removed the single-line runtime's `PictureCaptureApp.__init__` wrapping, widget-tree search/insertion machinery, and GUI bootstrap installer.

Validation summary:
- final focused suite: **259 passed**;
- final full suite: **1250 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- PR #236 and merge-push Ubuntu / Windows / macOS CI, GUI smoke, CodeQL, and Advanced Security: passed.

## Completed Phase 5D — main single-line worker/poll ownership
Phase 5D reused the existing app-owned `_start_parallel_batch_task(...)` and the spawn-safe `single_line_parallel.single_line_page_job(...)` rather than creating a new worker service or extending the generic batch-runner API.

Validation summary:
- final focused suite: **248 passed**;
- final full suite: **1252 passed, 2 existing Pillow deprecation warnings**;
- compileall / Ruff F821 / `git diff --check`: passed;
- validated production tree: `2caeb4e7a4803d33db048e7741a0e883ae1162cf`;
- PR #238 and merge-push Ubuntu / Windows / macOS CI, GUI smoke, CodeQL, and Advanced Security: passed.

## Completed Phase 5E — unlined-line UI/action/runtime decomposition
### Live revalidation and architecture choice
Phase 5E started from the Phase 5D docs checkpoint with no competing production PR. Live inspection confirmed that `unlined_line_export_ui.py` mixed four responsibilities:
- runtime `PictureCaptureApp.__init__` wrapping and dynamic button insertion;
- method/action installation;
- selected-scope/preflight/UI state;
- a private worker thread / queue / Tk-poll scheduler.

Inspection also confirmed that the low-level unlined module already exposed spawn-safe `export_unlined_page_job(...)`, and the app already owned the shared parallel batch runner established in Phase 5D.

The chosen narrow architecture was therefore:
- construct the unlined button in normal UI;
- expose an app compatibility wrapper;
- move action-specific preflight/job/finalization ownership to `CropController`;
- reuse `_start_parallel_batch_task(...)` unchanged;
- remove the now-empty historical runtime/helper modules;
- preserve the separate fast-worker installer through runtime module lookup;
- do not bundle training export cleanup.

### Production changes
Phase 5E changed exactly the intended UI/controller/runtime ownership surface:
- `src/picture_capture/app.py` — explicit unlined compatibility wrapper;
- `src/picture_capture/bootstrap/gui.py` — no unlined UI installer call; fast-path install remains;
- `src/picture_capture/ui/controllers/crop.py` — selected-scope preflight helpers plus unlined orchestration through the shared parallel runner;
- `src/picture_capture/postproduction_single_line_runtime.py` — removed;
- `src/picture_capture/unlined_line_export_ui.py` — removed;
- `scripts/architecture_guard.py` — legacy-runtime baseline ratcheted;
- focused regression/source-shape tests updated or added.

No production changes were made to training export, low-level unlined output semantics, filter/merge algorithms, or the shared batch-runner API.

### Phase 5E validation history
The first isolated focused run failed closed with **653 passed / 5 failed**. All five failures were stale source-shape assertions: four still opened the retired runtime module, and one hard-coded the old three-button postproduction row. No production behavior test failed, and no production tree was published.

A subsequent fail-fast run stopped before tests because the temporary assertion-fix helper used an incorrect indentation match for `test_core.py`. Again, no production tree was published.

After changing only those stale assertions:
- final focused suite: **658 passed**;
- architecture guard: passed (`no debt added beyond the ratcheted baseline`);
- final full suite: **1256 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- `git diff --check`: passed;
- temporary migration scripts/workflow were removed before publication;
- validated production commit: `a37b08cc9ec3ca3bc31eb015bd97630108d4e21f`;
- validated production tree: `3ece5025453c8d9975cd430f2b4ab0421e8787d5`;
- same-tree user-authored PR trigger head: `e9311cea3263c334b796f5a1f2933237d377ccbe`;
- final net production/test diff contained exactly 15 expected files and no training-export production changes.

PR #240 final-head verification:
- Ubuntu CI: passed;
- Windows CI: passed, including Windows GUI construction smoke;
- macOS CI: passed, including macOS GUI construction smoke;
- pytest, compatibility runner, compile, F821, and wheel build passed on all applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security AI findings: passed;
- no review threads or review objections were present before merge.

Architecture merge: `dcb916c352d9eb15c4866252698ee1abb3de9392`.
The merge commit tree remained exactly `3ece5025453c8d9975cd430f2b4ab0421e8787d5`, matching the validated PR tree.

Post-merge verification on `dcb916c352d9eb15c4866252698ee1abb3de9392`:
- Ubuntu CI: passed, including Linux GUI smoke, compatibility, compile/F821, and wheel;
- macOS CI: passed, including GUI smoke, compatibility, compile/F821, and wheel;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- the initial Windows matrix job was cancelled **before any workflow step ran** after waiting for a runner; its step list was empty, so this was not treated as a code/test failure;
- only that cancelled Windows job was rerun; the rerun obtained a runner and passed pytest, Windows GUI construction smoke, compatibility runner, compile, F821, and wheel build;
- therefore the final post-merge three-platform gate is fully green without any production-code change after merge.

## Remaining runtime-owned / bootstrap seams after Phase 5E
### Training export assignment
GUI bootstrap still assigns the training export action from `training_export_ui.export_training_package_selected_range`. It owns batch staging/finalization, cancellation cleanup, manifest/ZIP publication, and an auxiliary UI-worker cleanup path. Treat this as a separate export/batch ownership decision.

### Unlined fast-path installer
`unlined_fast_path_runtime` still installs a performance worker override after app/controller import. This is intentionally separate from the now-retired unlined UI/action runtime. Any future cleanup must preserve the physical-row/LayoutRows/Profile fast path and must account for import-order semantics before replacing runtime installation with static ownership.

### Ordinary-action helper
`ordinary_action_runtime.py` remains only for the OCR-independent quick-settings helper used by ordinary/selected-scope preflight. Do not mechanically delete it without checking all current callers and deciding where that helper belongs.

### Other installers
Other GUI/bootstrap runtime installers may remain. Continue evaluating them by actual ownership, UI mutation, import-order constraints, worker behavior, compatibility surface, and shutdown semantics rather than mechanically deleting installers.

## Next architecture decision point
Phase 5E is complete and recoverable. The highlighted remaining directions are materially different:

1. **Training export method-assignment cleanup — recommended next assessment.** Freshly inspect `training_export_ui.export_training_package_selected_range`, its GUI bootstrap assignment, batch staging/finalization, cancellation cleanup, manifest/ZIP publication, UI-worker cleanup, and whether existing `ExportController` / app batch abstractions can own the action without changing archive semantics.
2. **Unlined fast-path installer cleanup.** Separate performance/import-order problem. Do not combine this with training export unless live inspection proves the ownership inseparable.
3. **Residual helper/installer cleanup.** Includes the remaining `ordinary_action_runtime` helper and any other bootstrap installers; evaluate individually after the higher-value seams above.

Because these are materially different ownership directions, **human confirmation is required before the next production-code write**. Completion of Phase 5E is not authorization to start Phase 5F automatically.

Before the next production write, revalidate:
- live `main` and open PRs;
- the complete selected next seam and all callers/UI bindings;
- import-order/runtime patch ownership;
- batch/cancellation/shutdown/stale-result semantics;
- file-format or archive/output compatibility;
- source-shape and behavior tests for the selected seam.

Do not rerun the full suite merely on wake-up with no code change.

## Auto continuation
Phase 5E is complete and recoverable. Automatic production-code continuation is paused at the next Phase 5 architecture decision point.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone/ownership transition not already explicitly approved.
