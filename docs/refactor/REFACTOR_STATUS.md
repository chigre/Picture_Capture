# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4K is complete.

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
- `app.py` architecture size baseline after #202: 871,742 bytes

## Current issue
No active architecture blocker.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into controller decomposition; it belongs with later runtime-patch cleanup.

## Next safe unit
Phase 4L candidate: extract only `PictureCaptureApp.split_entries_selected_scope()` action-entry orchestration into the existing `CropController`, preserving the historical app compatibility wrapper and all current behavior exactly.

This is the remaining selected-scope whole-entry crop action and stays in the same crop domain as the current-page and batch whole-entry actions already owned by `CropController`. Preserve `guard()`; selected-page parsing and its `页面范围无效` error forwarding; current-page PDIC save before export; transformed-geometry guard; settings and crop-settings snapshots; selected-page indices; `PWW` output path; per-page crop-setting overrides; spawn-safe `split_whole_entries_job` payload construction; `ppp_read_path_for_image(page)` path semantics; parallel worker-count resolution; result consumption/logging; `_start_parallel_batch_task` label/item labels; and error/stopped/completed status semantics.

Do **not** move or change `_start_parallel_batch_task()` itself, crop-settings UI/configuration methods, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, any unrelated batch/export action, or the runtime-installed `split_single_lines_selected_scope` path in the same safe unit. Illustration detection/export is a separate domain boundary and must remain outside Phase 4L.

Before acting, revalidate that `split_entries_selected_scope()` still exists on live `main`, is not runtime-replaced, and can move without changing crop output, paths, process-pool payloads, worker/batch behavior, public API, or user-visible behavior. If any check fails, stop and record a blocker instead of choosing a broader task.

## Required validation for the next safe unit
- characterization/regression tests for `split_entries_selected_scope()` guard, invalid range error, save-before-export behavior, transformed-geometry guard, settings/config snapshots, selected indices, per-page overrides, job-builder payload, PPP path, worker-count forwarding, result logging/count, done error/stopped/completed statuses, parallel batch label/item labels, and app compatibility wrapper
- keep `CropController.split_lines_current()`, `split_whole_current()`, and `batch_split_whole()` behavior tests green
- preserve the existing UI button/tooltip contract for `("词条切图", self.split_entries_selected_scope)`
- explicit regression proving `_start_parallel_batch_task()`, illustration detection/export actions, crop-settings UI/configuration, and runtime-owned `split_single_lines_selected_scope` remain untouched
- reverse-dependency/boundary checks for `CropController`
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit per scheduled run and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
