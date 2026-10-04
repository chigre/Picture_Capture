# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4I is complete.

## Architecture checkpoint
- Last completed architecture PR: #198 — CropController current-page single-line crop action-entry seam
- Last completed architecture merge commit: `b6cc2a9d6be2f0078b6d17ca07b71b097271d7e6`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Page, Project, Review, Session.

`PictureCaptureApp.export_text()`, `PictureCaptureApp.import_text()`, and `PictureCaptureApp.split_lines_current()` remain compatibility wrappers. `.OCRed` serialization and crop algorithms stay in `processing`; project path policy stays in `project_storage`.

## Last verified tests
- Phase 4I pre-PR targeted suite: 190 passed
- Phase 4I pre-PR full suite: 1148 passed, 2 warnings
- PR #198 CI: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #198: Ubuntu / Windows / macOS all passed
- CodeQL after #198: Python and Actions analyses passed
- `app.py` architecture size baseline after #198: 875,916 bytes

## Current issue
No active architecture blocker.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into controller decomposition; it belongs with later runtime-patch cleanup.

## Next safe unit
Phase 4J candidate: extract only `PictureCaptureApp.split_whole_current()` action-entry orchestration into the existing `CropController`, preserving the app compatibility wrapper, `_start_batch_task` routing, crop-settings lookup, current-page entry/settings/polygon snapshots, output semantics, status/error behavior, and all existing crop algorithms exactly.

Do **not** include `batch_split_whole()`, crop-settings UI/configuration methods, any other batch crop/export path, or the runtime-installed `split_single_lines_selected_scope` path in the same safe unit.

Before acting, revalidate that `split_whole_current()` still exists on live `main`, is not replaced by a runtime installer, and can move without changing crop output, paths, worker/batch behavior, public API, or user-visible behavior. If any check fails, stop and record a blocker instead of choosing a broader task.

## Required validation for the next safe unit
- characterization/regression tests for `split_whole_current()` batch-active, guard/geometry, crop-settings lookup, entry/settings/polygon snapshots, worker/logging, done/status, and compatibility-wrapper behavior
- keep the existing `CropController.split_lines_current()` behavior tests green
- explicit regression proving `batch_split_whole()` and runtime-owned `split_single_lines_selected_scope` remain untouched
- reverse-dependency/boundary checks for `CropController`
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit per scheduled run and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
