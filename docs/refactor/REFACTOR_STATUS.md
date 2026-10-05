# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4N is complete.

## Architecture checkpoint
- Last completed architecture PR: #209 — illustration crop action-entry seam routed through `IllustrationController`
- Last completed architecture merge commit: `a1b9b44270ded56d80fcc85b15b27c34d4ff3ccc`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, and `split_illustrations_selected_scope()`.

`.OCRed` serialization and crop algorithms stay in `processing`; project path policy stays in `project_storage`.

## Last verified tests
- Phase 4N pre-PR targeted suite: 206 passed
- Phase 4N pre-PR full suite: 1186 passed, 2 warnings
- PR #209 fixed head: `f70aa3ebdcd60b75dd202cdb8f46d6fa9804cb23`
- PR #209 CI at the fixed head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #209: Ubuntu / Windows / macOS all passed
- CodeQL after #209: Python and Actions analyses passed
- `app.py` architecture size baseline after #209: 866,451 bytes

Phase 4N validation history worth preserving for recovery:
- the first real full-suite run after the narrow migration reported 1 failure and 1185 passes because `tests/test_core.py::test_v295_illustration_crop_button_uses_shared_crop_settings_before_running_batch` still required the shared crop-settings call to appear physically inside the `app.py` method body
- dedicated Phase 4N controller tests already covered the moved behavior; the legacy test was updated to verify the app compatibility wrapper plus the same shared crop-settings/delegation contract in `IllustrationController`
- no production implementation change was made to resolve that test-only source-shape mismatch
- temporary isolated-validation workflow/scripts were removed before the PR; the final PR net diff contained only the app wrapper, `IllustrationController`, and behavior/boundary tests

## Completed Phase 4N seam
`PictureCaptureApp.split_illustrations_selected_scope()` now delegates to `IllustrationController.split_illustrations_selected_scope()` while preserving the historical app entry point and the existing `("插图切图", self.split_illustrations_selected_scope)` UI binding.

The controller preserves:
- batch-active short-circuit and exact `已有批量任务正在运行，请结束后再执行插图切图。` status text
- missing project/current-page/image `尚未打开` dialog
- selected-range parsing, `页面范围无效` forwarding, and empty-range no-op
- `_sync_polygon_label_texts()` before committing foreground PPP state
- exact current-page PPP write through the app-owned path boundary: `write_ppp(app._ppp_write_path(app.current_page), app.polygons, app.current_page.stem)`
- one crop-settings load at action entry via `app._load_crop_settings()`
- delegation to the existing app-owned `_start_illustration_crop(indices, config)` runner seam without changing that helper

`_start_illustration_crop()` and `split_illustrations_job` intentionally remain outside `IllustrationController` after Phase 4N.

## Current issue
No active architecture blocker.

`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold that runtime-owned path into controller decomposition; it belongs with later runtime-patch cleanup.

## Next safe unit
Phase 4O candidate: extract only the orchestration body of `PictureCaptureApp._start_illustration_crop(indices, config)` into the existing `IllustrationController`, while retaining `PictureCaptureApp._start_illustration_crop()` as a compatibility wrapper and retaining the app-owned parallel-runner boundary.

Live-source revalidation after Phase 4N confirmed:
- live `main` is exactly the Phase 4N architecture merge `a1b9b44270ded56d80fcc85b15b27c34d4ff3ccc` before this checkpoint PR
- there are no open competing PRs at revalidation time
- `_start_illustration_crop()` still lives directly in `PictureCaptureApp`
- no repository search result shows a runtime assignment replacing `_start_illustration_crop()`
- the helper is a bounded illustration-export orchestration seam: project/batch guard, settings snapshot, output/config snapshot, per-page job payload construction, result logging/counting, completion status, then `_start_parallel_batch_task(...)`
- `split_illustrations_job` remains the processing worker/algorithm and must not be moved or changed as part of the same safe unit

Preserve the current runner exactly:
- `not self.project` no-op and batch-active short-circuit with exact `已有批量任务正在运行，未启动插图切图。` status text
- `project = self.project` and `settings = replace(self.settings)` snapshot timing
- output root `qt_root(project.root) / "PIC"`
- config extraction/fallbacks for `general_top_y`, `general_bottom_y`, `polygon_margin`, `entry_left_padding_x`, `entry_right_padding_x`, `integrate_illustrations`, `special_pages`, and `parallel_workers` with fallback to `settings.crop_parallel_workers`
- per-page special-bound override semantics
- exact worker payload order: `(str(page), str(app._ppp_read_path(page)), str(out_dir), settings, top_y, bottom_y, margin, str(pdic_path(page)), entry_left, entry_right, integrate_illustrations, index)`; keep the app-owned `_ppp_read_path(page)` boundary unless a separate live proof and explicit scoped decision establishes an equivalent replacement
- result consumer semantics: copy `result.records` / `result.events`, call `append_crop_log(project.root, records)` and `append_illustration_crop_log(project.root, events)`, then return `len(records)`
- completion callback error no-op; stopped status `插图切图已停止：完成 {completed}/{total_pages} 页，共导出 {count} 张`; completed status `插图切图完成：{completed} 页，共 {count} 张`
- existing `_start_parallel_batch_task("插图切图", indices, split_illustrations_job, job_builder, consume_result, done, item_label=..., max_workers=workers)` boundary and item labels
- the Phase 4N `split_illustrations_selected_scope()` behavior and UI binding unchanged

Do **not** change or move `_start_parallel_batch_task()`, `split_illustrations_job`, crop algorithms, illustration log formats, crop-settings UI/configuration methods, project-storage policy, unrelated crop/export actions, or any runtime-installed method in the same safe unit. Dependency-import cleanup is allowed only where live search proves an import became action-only; do not broaden scope merely to remove imports.

Before acting, revalidate live `main`, open PRs, the exact helper body, its callers, processing/storage dependencies, and absence of a runtime installer/competing change. If any check fails, record a blocker rather than broadening the unit.

## Required validation for the next safe unit
- characterization/regression tests for no-project and batch-active behavior
- settings snapshot immutability and timing
- output `PIC` directory and every crop-config fallback/override listed above
- exact per-page worker payload order, including app-owned PPP read path, PDIC path, special-page bounds, settings snapshot, and page index
- result consumer logging semantics and returned record count
- done-callback error no-op and exact stopped/completed status strings/count aggregation
- `_start_parallel_batch_task` title/items/worker/job builder/result consumer/done/item label/max-worker contract
- app `_start_illustration_crop()` compatibility wrapper after migration
- existing Phase 4M detection and Phase 4N crop-entry controller tests remain green
- preserve postproduction `插图切图` UI binding
- explicit regression proving runtime-owned `split_single_lines_selected_scope` and `run_normal_draw_action` remain untouched
- reverse-dependency/boundary checks for `IllustrationController`
- targeted tests while iterating
- full suite and normal three-platform PR CI before merge, followed by merge-push CI and CodeQL

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit at a time and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
