# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4T is complete.

## Architecture checkpoint
- Last completed architecture PR: #221 — `repair_pdic_order_selected_scope()` routed through the existing `ExportController`
- Last completed architecture merge commit: `11a49cb90906c692f3597df3de4e52d9a43b7f32`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, `export_picdic_index()`, `backup_pdic()`, `restore_from_pdic_backup()`, and `repair_pdic_order_selected_scope()`.

`restore_from_merged_pdic()` remains the historical compatibility alias and calls `restore_from_pdic_backup()`.

`ExportController` owns current-page `.OCRed` import/export orchestration, PicDic package build, PicDic index streaming export, PDIC backup streaming, selected-range PDIC restore, and selected-range PDIC order repair. The app still owns the generic batch runner and shared page/UI refresh helpers.

`pdic_restore.py` remains the deterministic low-level boundary for page-token lookup/resolution, merged-PDIC parsing, and one-page temporary-file + `os.replace(...)` atomic publication. Phase 4T reuses `write_pdic_atomic()` from that module and does not change PDIC field semantics or path policy.

## Last verified tests
- Phase 4T pre-PR focused suite: 632 passed
- Phase 4T pre-PR full suite: 1234 passed, 2 existing Pillow deprecation warnings
- Phase 4T PR #221 fixed head: `14b88839296894f98b0dcc4059612503a99d85e9`
- PR #221 fixed-head CI: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- Phase 4T architecture merge commit: `11a49cb90906c692f3597df3de4e52d9a43b7f32`
- `main` merge-push CI after #221: Ubuntu / Windows / macOS all passed
- CodeQL after #221: Python and Actions analyses passed
- `git diff --check`, compileall, and Ruff F821 passed before PR creation
- `app.py` architecture size baseline after #221: 838,705 bytes

Phase 4T validation history worth preserving for recovery:
- first focused run: 623 passed, 9 failed
- six failures were caused by the temporary migration script transforming the newly inserted `app = self.app` into `app = app.app`; this was a validation-script bug, not a pre-existing production failure
- the other three failures were stale source-shape checks: one hard-coded the previous `ExportController` formats import string and two still expected the repair implementation to be physically inside `app.py`
- after correcting the script and source-test boundaries, the next focused run was 631 passed, 1 failed
- that remaining test correctly exposed two bare `parent=self` references inside the moved repair action; unlike `self.` references they were not covered by the mechanical ownership transformation
- those two dialog parents were changed to `parent=app`, preserving the historical main-window parent semantics
- no repair algorithm, sort rule, PDIC format, settings-reference behavior, or batch-runner behavior was changed to resolve validation failures
- temporary isolated-validation workflow/scripts were removed before PR creation
- final net diff from the Phase 4S checkpoint contained exactly 5 expected files: `app.py`, `ui/controllers/export.py`, two existing test files, and new `test_ui_pdic_order_repair_controller.py`

## Completed Phase 4T seam
`PictureCaptureApp.repair_pdic_order_selected_scope()` now remains as a compatibility wrapper and delegates to `ExportController.repair_pdic_order_selected_scope()`.

The controller preserves:
- exact missing-project/current-page/image dialog and main-window parent
- exact batch-active status `已有批量任务正在运行，请结束后再修复排序。`
- `selected_page_indices()` as the authoritative scope and exact `页面范围错误` error title
- exact empty-selection status `没有选中需要修复的页面`
- filtering to selected pages with existing PDIC files and exact no-PDIC status `所选范围没有已有 PDIC 文件`
- foreground `_flush_deferred_page_save()`, `_sync_entry_editor_texts()`, and `save_pdic(silent=True, sync_editors=False)`
- exact preparation error title `修复排序准备失败`
- destructive confirmation text, including the requirement that word/X/Y tuples remain bound and the backup recommendation
- historical live settings-reference semantics: `settings = app.settings`; Phase 4T deliberately did not introduce `replace(...)`
- per-page `read_pdic(...)`, image-header-only width/height read, `derive_nominal_geometry(...)`, `read_page_sections(...)`, and `sort_entries_column_y(...)`
- the existing “column → Y” ordering rule with X excluded from sorting and stable handling of equal column/Y rows
- previous/current/following page metadata and atomic publication through `write_pdic_atomic(...)`
- empty PDIC pages return `(index, 0, False)` without publication
- worker result tuple `(index, record_count, changed_order)`
- unchanged completion aggregation, current-page reload, and exact stopped/completed status text
- app-owned `_start_batch_task("修复排序", ...)` boundary and page-name item labels
- existing UI `修复排序` binding

Phase 4T did not touch existing-headword selection/fill, order-review/report workflows, OCR workers, generic batch execution, runtime-installed actions, or Phase 5.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

Training package export is installed onto `PictureCaptureApp` during GUI bootstrap from `training_export_ui.export_training_package_selected_range`; do not treat that runtime-installed extension as an ordinary app-body controller seam during Phase 4.

## Revalidation after Phase 4T
After Phase 4T merge-push verification:
- live `main` is `11a49cb90906c692f3597df3de4e52d9a43b7f32`
- no open competing PR exists at revalidation time
- `ExportController` now owns the contiguous PicDic/PDIC build, index-export, backup, restore, and repair action boundaries while the app retains compatibility wrappers and the generic batch runner
- the next nearby app-owned actions are not equivalent in weight: existing-headword selection/fill owns source-file/cache and PDIC update state; `check_headword_order()` owns report/finalization UI work; `batch_ocr()` owns OCR processing plus `.OCRed`/PDIC persistence
- `batch_auto_detect(force_paddle_refresh=False)` is materially narrower than those paths: it only validates project presence, derives the full-project index list, and forwards the current detection method plus force-refresh flag into app-owned `_detect_pages(...)`
- `DetectionController` already owns the stable OCR/combined detection action-entry seams while intentionally leaving `_detect_pages(...)`, workers, persistence, and algorithms on the app
- no Phase 5 runtime-patch cleanup has begun

## Recommended next safe unit
The preferred Phase 4U candidate is a **single narrow migration of only `PictureCaptureApp.batch_auto_detect(force_paddle_refresh=False)` into the existing `DetectionController`**, retaining an app compatibility wrapper.

Phase 4U should preserve the current no-project no-op, full-project page-index construction, `self.settings.detection_method` lookup timing, `force_paddle_refresh` forwarding, and the app-owned `_detect_pages(...)` boundary exactly.

Do not move `_detect_pages(...)`, `batch_ocr()`, OCR processing/persistence, `check_headword_order()`, existing-headword select/fill workflows, runtime-installed methods, or Phase 5 work in the same unit.

Before any Phase 4U write, revalidate live `main`, open PRs, the exact `batch_auto_detect()` body/callers/UI binding, runtime ownership, and current `DetectionController` dependencies.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Phase 4T is complete and recoverable. No Phase 4U production code has started. The recommended Phase 4U unit above is narrow enough to resume when continuation is requested.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
