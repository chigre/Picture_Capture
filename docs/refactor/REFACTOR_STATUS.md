# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4H is complete.

## Architecture checkpoint
- Last completed architecture PR: #196 — ExportController current-page text import/export action-entry seam
- Last completed architecture merge commit: `f0f630202345e55764e8175cf826e337503604f9`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Detection, Export, Page, Project, Review, Session.

`PictureCaptureApp.export_text()` and `PictureCaptureApp.import_text()` remain compatibility wrappers; `.OCRed` serialization stays in `processing` and project path policy stays in `project_storage`.

## Last verified tests
- Phase 4H pre-PR targeted suite: 186 passed
- Phase 4H pre-PR full suite: 1140 passed, 2 warnings
- PR #196 CI: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #196: Ubuntu / Windows / macOS all passed
- CodeQL after #196: Python and Actions analyses passed
- `app.py` architecture size baseline after #196: 876,797 bytes

## Current issue
No active architecture blocker.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into the next controller unit; it belongs with later runtime-patch cleanup.

## Next safe unit
Phase 4I candidate: extract only `PictureCaptureApp.split_lines_current()` action-entry orchestration into a narrow `CropController`, preserving the app compatibility wrapper, `_start_batch_task` routing, output semantics, status/error behavior, and all existing crop algorithms exactly.

Do **not** include `PictureCaptureApp.split_whole_current()` in the same safe unit, and do **not** touch the runtime-installed `split_single_lines_selected_scope` path.

Before acting, revalidate that `split_lines_current()` still exists on live `main`, is not replaced by a runtime installer, and can move without changing crop output, paths, worker/batch behavior, public API, or user-visible behavior. If any check fails, stop and record a blocker instead of choosing a broader task.

## Required validation for the next safe unit
- characterization/regression tests for `split_lines_current()` guard, batch-active, snapshot/worker/done, status, and compatibility-wrapper behavior
- reverse-dependency/boundary test for `CropController`
- explicit regression proving the runtime-owned `split_single_lines_selected_scope` path is untouched
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit per scheduled run and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
