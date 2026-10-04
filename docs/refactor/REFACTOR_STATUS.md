# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4J is complete.

## Architecture checkpoint
- Last completed architecture PR: #200 — CropController current-page whole-entry crop action-entry seam
- Last completed architecture merge commit: `5a5d857980e8116195aff19ef0e59df43290b48f`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Page, Project, Review, Session.

`PictureCaptureApp.export_text()`, `PictureCaptureApp.import_text()`, `PictureCaptureApp.split_lines_current()`, and `PictureCaptureApp.split_whole_current()` remain compatibility wrappers. `.OCRed` serialization and crop algorithms stay in `processing`; project path policy stays in `project_storage`.

## Last verified tests
- Phase 4J pre-PR targeted suite: 201 passed
- Phase 4J pre-PR full suite: 1153 passed, 2 warnings
- PR #200 CI: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #200: Ubuntu / Windows / macOS all passed
- CodeQL after #200: Python and Actions analyses passed
- `app.py` architecture size baseline after #200: 873,916 bytes

## Current issue
No active architecture blocker.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into controller decomposition; it belongs with later runtime-patch cleanup.

## Next safe unit
Phase 4K candidate: extract only `PictureCaptureApp.batch_split_whole()` action-entry orchestration into the existing `CropController`, preserving the historical app compatibility wrapper and all current behavior exactly.

Preserve the silent no-op when no project exists or another batch is active; transformed-geometry guard; settings snapshot; all-page index selection; `PWW` output path; crop-settings parsing including per-page overrides; per-page PDIC/PPP reads; `split_whole_entries()` arguments and profile page index; crop-log append; `_start_batch_task` label/item labels; error/stopped/completed status semantics.

Do **not** include crop-settings UI/configuration methods, selected-scope or parallel crop/export paths, illustration crop/detection paths, any other batch action, or the runtime-installed `split_single_lines_selected_scope` path in the same safe unit.

Before acting, revalidate that `batch_split_whole()` still exists on live `main`, is not runtime-replaced, and can move without changing crop output, paths, worker/batch behavior, public API, or user-visible behavior. If any check fails, stop and record a blocker instead of choosing a broader task.

## Required validation for the next safe unit
- characterization/regression tests for `batch_split_whole()` no-project/batch-active behavior, geometry guard, settings/config snapshots, all-page selection, worker PDIC/PPP reads and per-page overrides, logging/count return, done error/stopped/completed statuses, batch label/item labels, and app compatibility wrapper
- keep current-page `CropController.split_lines_current()` and `split_whole_current()` behavior tests green
- explicit regression proving crop-settings UI/configuration, other selected-scope/parallel crop paths, and runtime-owned `split_single_lines_selected_scope` remain untouched
- reverse-dependency/boundary checks for `CropController`
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit per scheduled run and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
