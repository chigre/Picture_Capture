# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4M is complete.

## Architecture checkpoint
- Last completed architecture PR: #207 — illustration detection action-entry seam routed through `IllustrationController`
- Last completed architecture merge commit: `a70a7c373110da86e4165622ee3f6f48754b7d20`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, and `detect_illustrations_selected_scope()`.

`.OCRed` serialization and crop algorithms stay in `processing`; project path policy stays in `project_storage`.

## Last verified tests
- Phase 4M pre-PR targeted suite: 194 passed
- Phase 4M pre-PR full suite: 1179 passed, 2 warnings
- PR #207 fixed head: `b46b438c512e8d6b2b31404db4a0d8742e918542`
- PR #207 CI at the fixed head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #207: Ubuntu / Windows / macOS all passed
- CodeQL after #207: Python and Actions analyses passed
- `app.py` architecture size baseline after #207: 867,212 bytes

Phase 4M validation history worth preserving for recovery:
- the first temporary full-suite run reported 1 failure only because the old `tests/test_core.py::test_v2101_illustration_detection_button_uses_selected_scope_and_auto_ppp` source-shape assertion still required selected-range/PPP/batch text to appear directly inside the `app.py` method body
- the dedicated `IllustrationController` tests already covered the moved behavior; the legacy test was changed to verify that the UI still targets the app compatibility method while the selected-scope/AUTO-PPP behavior markers now live in `IllustrationController`
- no production implementation change was made to resolve that test-only boundary mismatch

## Completed Phase 4M seam
`PictureCaptureApp.detect_illustrations_selected_scope()` now delegates to `IllustrationController.detect_illustrations_selected_scope()` while preserving the historical app entry point.

The controller preserves:
- batch-active short-circuit/status text
- missing project/current-page/image `尚未打开` dialog
- selected-range parsing, `页面范围无效` forwarding, and empty-range no-op
- foreground PPP save before the confirmation dialog
- confirmation copy and first/last/count presentation
- `settings = replace(self.settings)` snapshot semantics
- worker call `detect_illustrations_job(str(page), settings, index)`
- error no-op, AUTO-region aggregation, stopped/completed status text
- current-page PPP reload, page-row update, polygon display enable, and redraw
- existing `_start_batch_task("插图识别", ...)`, item labels, `foreground_page_edit=True`, and integer page indexer

`split_illustrations_selected_scope()` and `_start_illustration_crop()` intentionally remain in `PictureCaptureApp` and were not changed by Phase 4M.

## Current issue
No active architecture blocker.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into controller decomposition; it belongs with later runtime-patch cleanup.

## Next safe unit
Phase 4N candidate: extract only `PictureCaptureApp.split_illustrations_selected_scope()` action-entry orchestration into the existing `IllustrationController`, preserving the historical app compatibility wrapper and exact live behavior.

Live-source revalidation after Phase 4M confirmed:
- `split_illustrations_selected_scope()` still lives directly in `PictureCaptureApp`
- no repository search result shows a runtime assignment replacing `split_illustrations_selected_scope()`
- the method is a narrow front-door seam: batch-active guard, open-project/current-page/image precondition, selected-range parsing, empty-range no-op, foreground polygon label sync, current-page PPP write, then `_start_illustration_crop(indices, self._load_crop_settings())`
- `_start_illustration_crop()` remains a separate orchestration/runner seam in `PictureCaptureApp` and must not be bundled into Phase 4N

Preserve the current action exactly:
- batch-active short-circuit and `已有批量任务正在运行，请结束后再执行插图切图。` status text
- missing project/current-page/image `尚未打开` info dialog
- selected-range parsing, `页面范围无效` forwarding, and empty-range return
- `_sync_polygon_label_texts()` before saving current foreground polygons
- `write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)` behavior
- one crop-settings snapshot/load at action entry via `_load_crop_settings()`
- call into the existing `_start_illustration_crop(indices, config)` boundary without moving or changing that helper
- existing UI button/tooltip contract for `("插图切图", self.split_illustrations_selected_scope)`

Do **not** include `_start_illustration_crop()`, `split_illustrations_job`, illustration crop-result logging/status internals, crop-settings UI/configuration methods, `_start_batch_task()` / `_start_parallel_batch_task()`, unrelated crop/export actions, or any runtime-installed method in the same safe unit.

Before acting, revalidate live `main`, open PRs, the exact method body, and absence of a runtime installer/competing change. If any check fails, record a blocker rather than broadening the unit.

## Required validation for the next safe unit
- characterization/regression tests for batch-active behavior, missing-project/current-page/image dialog, invalid/empty selected range, polygon-label synchronization, PPP write path/payload/order, crop-settings load timing, delegation arguments to `_start_illustration_crop()`, and app compatibility wrapper
- explicit regression proving `_start_illustration_crop()` remains in `PictureCaptureApp` and unchanged
- keep existing Phase 4M detection-controller tests green
- preserve the existing postproduction `插图切图` UI binding
- explicit regression proving runtime-owned `split_single_lines_selected_scope` and `run_normal_draw_action` remain untouched
- reverse-dependency/boundary checks for `IllustrationController`
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit at a time and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
