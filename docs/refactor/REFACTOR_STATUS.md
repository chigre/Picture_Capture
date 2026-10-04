# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4K is complete. Phase 4L is blocked pending human confirmation.

## Architecture checkpoint
- Last completed architecture PR: #202 — CropController batch whole-entry crop action-entry seam
- Last completed architecture merge commit: `b1aab8b210a516a202ef35ecb5da2f5c54166de5`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Page, Project, Review, Session.

`PictureCaptureApp.export_text()`, `PictureCaptureApp.import_text()`, `PictureCaptureApp.split_lines_current()`, `PictureCaptureApp.split_whole_current()`, and `PictureCaptureApp.batch_split_whole()` remain compatibility wrappers. `.OCRed` serialization and crop algorithms stay in `processing`; project path policy stays in `project_storage`.

## Last verified tests
- Phase 4K pre-PR targeted suite: 211 passed
- Phase 4K pre-PR full suite: 1159 passed, 2 warnings
- PR #202 CI: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #202: Ubuntu / Windows / macOS all passed
- CodeQL after #202: Python and Actions analyses passed
- Phase 4K checkpoint PR #203 merged at `7ef93d2298356842a7209623754f6ab9c97a8442`; its merge-push Ubuntu / Windows / macOS CI and Python / Actions CodeQL all passed
- `app.py` architecture size baseline after #202: 871,742 bytes

## Current issue
Active architecture blocker: the Phase 4L candidate recorded by PR #203 contained two assumptions that do not match live `main`.

Live `PictureCaptureApp.split_entries_selected_scope()` currently:
- calls `guard()` and parses `selected_page_indices()`, forwarding exceptions as `页面范围无效`;
- saves the current PDIC with `save_pdic(silent=True)` before snapshotting the crop task;
- does **not** call `_guard_transformed_geometry()`;
- builds the spawn-safe `split_whole_entries_job` payload with `str(self._ppp_read_path(page))`, not `ppp_read_path_for_image(page)`;
- otherwise snapshots settings/crop configuration, applies special-page bounds, forwards the configured parallel-worker count, appends crop logs in the result consumer, and preserves existing stopped/completed status text.

PR #203 incorrectly said Phase 4L should preserve a transformed-geometry guard and `ppp_read_path_for_image(page)` semantics. Those behaviors are not present in the live method. No Phase 4L production code has been changed.

Two materially different paths therefore exist:
1. **Strict mechanical refactor:** move the existing action seam into `CropController` exactly as it behaves today, including no transformed-geometry guard and the existing `_ppp_read_path(page)` resolution path (accessed through the app compatibility boundary if needed).
2. **Behavior correction:** add a transformed-geometry guard and/or switch PPP path resolution to `ppp_read_path_for_image(page)`. This is a behavior/path-semantics change and must be a separately approved task with dedicated regression evidence; it must not be silently bundled into the controller refactor.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into controller decomposition; it belongs with later runtime-patch cleanup.

## Next safe unit
Blocked pending human confirmation of which Phase 4L path to take. Do not modify `split_entries_selected_scope()` until that confirmation is recorded.

If strict mechanical refactor is approved, Phase 4L should extract only `PictureCaptureApp.split_entries_selected_scope()` into the existing `CropController`, preserving its exact live behavior and the historical app compatibility wrapper. Do not move or change `_start_parallel_batch_task()` itself, crop-settings UI/configuration methods, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, unrelated batch/export actions, or the runtime-installed `split_single_lines_selected_scope` path.

## Required validation if strict mechanical Phase 4L is approved
- characterize exact current behavior before moving it: guard, invalid-range error, `save_pdic(silent=True)`, absence of transformed-geometry guard, settings/config snapshots, selected indices, special-page overrides, exact `split_whole_entries_job` payload including `_ppp_read_path(page)`, worker-count forwarding, result logging/count, done error/stopped/completed statuses, parallel-batch label/item labels, and app compatibility wrapper
- keep `CropController.split_lines_current()`, `split_whole_current()`, and `batch_split_whole()` behavior tests green
- preserve the existing UI button/tooltip contract for `("词条切图", self.split_entries_selected_scope)`
- explicit regression proving `_start_parallel_batch_task()`, illustration detection/export actions, crop-settings UI/configuration, and runtime-owned `split_single_lines_selected_scope` remain untouched
- reverse-dependency/boundary checks for `CropController`
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Blocked for Phase 4L until human confirmation resolves the checkpoint mismatch. After confirmation, resume one safe unit at a time under `RESUMABLE_EXECUTION_PROTOCOL.md`.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
