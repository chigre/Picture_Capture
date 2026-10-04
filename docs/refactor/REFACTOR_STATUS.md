# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4L is complete.

## Architecture checkpoint
- Last completed architecture PR: #205 — selected-scope whole-entry crop action-entry seam routed through `CropController`, with the approved transformed-geometry safety correction
- Last completed architecture merge commit: `4cc021b53cf6b745649ce9068d5fd4db5784e18e`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, and `split_entries_selected_scope()`.

`.OCRed` serialization and crop algorithms stay in `processing`; project path policy stays in `project_storage`.

## Last verified tests
- Phase 4L pre-PR targeted suite: 210 passed
- Phase 4L pre-PR full suite: 1168 passed, 2 warnings
- PR #205 final fixed head: `e3e58f56c8dbc23c1ec1bf8ed6644e8dc21ad99b`
- PR #205 CI at the final head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #205: Ubuntu / Windows / macOS all passed
- CodeQL after #205: Python and Actions analyses passed
- `app.py` architecture size baseline after #205: 869,531 bytes

Phase 4L validation history worth preserving for recovery:
- the first temporary validation failure was a test-only assumption that `special_pages` was deep-snapshotted; live behavior never provided that deep snapshot, so the test was corrected without changing implementation
- the first formal PR head exposed a Windows-only test portability issue because expected spawn-payload paths were hard-coded with POSIX separators; the test now uses platform-native `str(Path(...))`, with no production-code change

## Completed Phase 4L behavior correction
Human confirmation explicitly selected the behavior-correction path rather than a purely mechanical move.

`PictureCaptureApp.split_entries_selected_scope()` now delegates to `CropController.split_entries_selected_scope()` and:
- keeps `guard()` first
- keeps selected-range parsing and `页面范围无效` error forwarding before the new safety gate
- adds `_guard_transformed_geometry("词条切图")` before saving or launching crop work
- keeps `save_pdic(silent=True)` before task snapshot/launch when the safety gate passes
- keeps the existing `AppSettings` snapshot via `replace()` and existing crop-settings / `special_pages` reference semantics
- keeps the same selected indices, `PWW` output path, per-page bounds, padding/integration options, configured worker count, result logging, and stopped/completed status text
- resolves the PPP input directly with `ppp_read_path_for_image(page)` at the controller/storage boundary; this is path-equivalent to the former `PictureCaptureApp._ppp_read_path(page)` wrapper, which only returned that same storage helper
- keeps `_start_parallel_batch_task()` in `PictureCaptureApp`; the controller only orchestrates the action through the existing runner

## Current issue
No active architecture blocker.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into controller decomposition; it belongs with later runtime-patch cleanup.

## Next safe unit
Phase 4M candidate: extract only `PictureCaptureApp.detect_illustrations_selected_scope()` action-entry orchestration into a new narrow `IllustrationController`, preserving the historical app compatibility wrapper and all current behavior exactly.

Live-source revalidation after Phase 4L confirmed:
- `detect_illustrations_selected_scope()` still lives directly in `PictureCaptureApp`
- no repository search result shows a runtime assignment replacing `detect_illustrations_selected_scope()`
- no existing `IllustrationController` is present
- the neighboring `split_illustrations_selected_scope()` / `_start_illustration_crop()` export path is a separate seam and must not be bundled into the first illustration-controller unit

Preserve the current detection action exactly:
- batch-active short-circuit and status text
- project/current-page/image precondition and `尚未打开` info dialog
- selected-range parsing, `页面范围无效` forwarding, and empty-range return
- saving current foreground polygons to PPP before confirmation
- confirmation dialog text and first/last page/count presentation
- `settings = replace(self.settings)` snapshot
- worker call `detect_illustrations_job(str(page), settings, index)`
- done behavior: error no-op; AUTO-region count aggregation; stopped/completed status text; reload current-page PPP when the current index is in the selected range; update page row; enable polygon display; redraw
- existing `_start_batch_task()` label, item labels, `foreground_page_edit=True`, and `page_indexer=lambda i: int(i)`

Do **not** include `split_illustrations_selected_scope()`, `_start_illustration_crop()`, illustration export/crop result logging, crop-settings UI/configuration, `_start_batch_task()` itself, `_start_parallel_batch_task()`, unrelated crop/export actions, or any runtime-installed method in the same safe unit.

Before acting, revalidate live `main`, open PRs, the exact detection method body, and absence of a runtime installer/competing controller. If any check fails, record a blocker rather than broadening the unit.

## Required validation for the next safe unit
- characterization/regression tests for batch-active behavior, missing-project/current-page/image dialog, invalid and empty selected ranges, foreground PPP save before confirmation, cancel-confirmation no-op, settings snapshot, worker arguments, AUTO-count/status semantics, current-page reload/update/polygon-toggle/redraw behavior, batch label/item labels, foreground-page-edit/page-indexer flags, and app compatibility wrapper
- reverse-dependency/boundary test for the new `IllustrationController`
- explicit regression proving `split_illustrations_selected_scope()` and `_start_illustration_crop()` remain in `PictureCaptureApp` and unchanged
- explicit regression proving runtime-owned `split_single_lines_selected_scope` and `run_normal_draw_action` remain untouched
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit per scheduled run and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
