# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4S is complete.

## Architecture checkpoint
- Last completed architecture PR: #219 — `restore_from_pdic_backup()` routed through the existing `ExportController`, with shared restore primitives extracted to `pdic_restore.py`
- Last completed architecture merge commit: `eadfb3bb55f15d6971a507e1d8d412b4cdb3492b`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, `export_picdic_index()`, `backup_pdic()`, and `restore_from_pdic_backup()`.

`restore_from_merged_pdic()` remains the historical compatibility alias and calls `restore_from_pdic_backup()`.

`ExportController` now owns current-page `.OCRed` import/export orchestration, PicDic package-build orchestration, PicDic index streaming export orchestration, project-wide PDIC backup streaming orchestration, and selected-range PDIC restore orchestration. The app still owns the generic batch runner and the page/UI refresh helpers used by these actions.

`pdic_restore.py` now owns only deterministic low-level restore primitives:
- exact/numeric/suffix page-token lookup and resolution
- merged-PDIC parsing into per-page `Entry` collections plus source match statistics
- one-page temporary-file + `os.replace(...)` atomic publication

The existing page-aware TXT/headword importer continues to use the same page-token lookup/resolution rules through aliases imported from `pdic_restore.py`; Phase 4S did not duplicate or fork page-token semantics.

Persisted PDIC field semantics remain in the existing format/model layer, project path policy remains outside controllers, and the generic batch runner remains in `PictureCaptureApp`.

## Last verified tests
- Phase 4S pre-PR focused suite: 625 passed
- Phase 4S pre-PR full suite: 1227 passed, 2 existing Pillow deprecation warnings
- Phase 4S PR #219 fixed head: `a8ba1b57e3b230e5950ab5bf0fbd27fef2161511`
- PR #219 CI at the fixed head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #219: Ubuntu / Windows / macOS all passed
- CodeQL after #219: Python and Actions analyses passed
- `git diff --check`, compileall, and Ruff F821 passed before PR creation
- `app.py` architecture size baseline after #219: 842,331 bytes

Phase 4S validation history worth preserving for recovery:
- the first focused run completed with 621 passed and 4 failures
- all four failures were stale source-shape checks, not behavioral regressions
- two tests still expected restore settings-snapshot / nominal-geometry code to be physically inside `PictureCaptureApp.restore_from_pdic_backup()` after that method became a wrapper
- two tests sliced `ExportController.export_picdic_index()` / `backup_pdic()` from the target method to end-of-file, so the newly appended restore method's `Image.open()` was incorrectly treated as part of the earlier methods
- those tests were narrowed to the correct controller method boundaries; production behavior was not changed to resolve the failures
- temporary isolated-validation workflows/scripts were removed before PR creation
- final Phase 4S net diff from the Phase 4R checkpoint contained exactly 7 expected files: `app.py`, new `pdic_restore.py`, `ui/controllers/export.py`, three existing test files, and new `test_ui_pdic_restore_controller.py`

## Completed Phase 4S seam
`PictureCaptureApp.restore_from_pdic_backup()` now remains as a compatibility wrapper and delegates to `ExportController.restore_from_pdic_backup()`.

The controller preserves the historical restore contract:
- exact missing-project/current-page/image dialog
- exact batch-active dialog
- main-window `selected_page_indices()` as the authoritative destructive scope; exact range-error and empty-range behavior
- exact file picker title, initial directory, file types, parent, and cancel behavior
- exact destructive confirmation explaining selected-page overwrite, empty-page reconstruction, per-page atomic commits, stop behavior, and no rollback of completed pages
- foreground `_flush_deferred_page_save()`, `_sync_entry_editor_texts()`, and `save_pdic(silent=True, sync_editors=False)` before starting restore
- exact preparation error title `PDIC 备份 恢复准备失败`
- settings snapshot timing through `replace(app.settings)` before background work
- project page/stem snapshot and selected-index `pages_tuple(...)` metadata snapshot
- one-time merged-source parse under a lock for the batch
- page image header-only size read through `Image.open(page).size`; no full-image normalization/decoding for restore geometry
- reading-order reconstruction with `derive_nominal_geometry(...)`, `read_page_sections(page)`, and `sort_entries_reading_order(...)`
- every selected page is atomically rewritten, including pages with zero matched source records
- result dictionaries retain page index, record count, empty flag, and source record/match/unmatched statistics
- error completion remains a no-op for success/status refresh handling
- completed pages clear persisted stale word-fill checks, refresh page rows/overlays, and reload the current page when applicable
- exact stopped/completed status aggregation, including unmatched-source-record suffix
- app-owned `_start_batch_task("恢复PDIC", ..., foreground_page_edit=False)` boundary and page-name item labels
- exact started batch-text/status messages only when the batch runner actually starts
- historical `restore_from_merged_pdic()` alias and UI `恢复PDIC` binding

Phase 4S did not change PDIC record fields, output path policy, generic batch execution, runtime-installed actions, or Phase 5 behavior.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

Training package export is installed onto `PictureCaptureApp` during GUI bootstrap from `training_export_ui.export_training_package_selected_range`; do not treat that runtime-installed extension as an ordinary app-body controller seam during Phase 4.

## Revalidation after Phase 4S
After Phase 4S merge-push verification:
- live `main` is `eadfb3bb55f15d6971a507e1d8d412b4cdb3492b`
- no open competing PR exists at revalidation time
- `ExportController` owns the adjacent PicDic/PDIC build, index-export, backup, and restore action boundaries while the app retains compatibility wrappers and the generic batch runner
- `repair_pdic_order_selected_scope()` remains directly in `PictureCaptureApp`
- live inspection found no runtime replacement for `repair_pdic_order_selected_scope()`
- its worker already uses image-header-only dimensions, `derive_nominal_geometry(...)`, `sort_entries_column_y(...)`, page sections, and the same atomic PDIC writer now provided by `pdic_restore.py`
- `select_existing_headwords_file()` / fill-existing-headwords workflows remain separate and are not part of the recommended next unit
- no Phase 5 runtime-patch cleanup has begun

## Recommended next safe unit
The preferred Phase 4T candidate is a **single narrow migration of only `PictureCaptureApp.repair_pdic_order_selected_scope()` into the existing `ExportController`**, retaining a historical app compatibility wrapper.

This is now the closest mechanical continuation because it is another selected-range PDIC rewrite action adjacent to backup/restore, and it can reuse the Phase 4S low-level atomic PDIC publication boundary without creating a new format or controller domain.

Phase 4T must preserve:
- exact missing-project/current-page/image dialog
- exact batch-active status `已有批量任务正在运行，请结束后再修复排序。`
- `selected_page_indices()` scope and exact `页面范围错误` error title
- exact empty-selection and no-existing-PDIC status messages
- foreground flush/sync/save and exact `修复排序准备失败` error title
- destructive confirmation text and the requirement that word/X/Y tuples remain bound
- filtering to selected pages whose PDIC file exists
- current settings reference semantics as they exist at the Phase 4S checkpoint; do not silently change snapshot/concurrency behavior inside an ownership-only migration
- `read_pdic(...)`, image-header-only width/height read, `derive_nominal_geometry(...)`, `sort_entries_column_y(...)`, and `read_page_sections(...)`
- previous/current/following page metadata and atomic rewrite through the existing low-level PDIC writer
- worker result tuple `(index, record_count, changed_order)` and unchanged handling of empty PDIC pages
- done callback aggregation, current-page reload, exact stopped/completed status text
- app-owned `_start_batch_task("修复排序", ...)` boundary and page-name item labels
- existing UI `修复排序` binding

Do not bundle `select_existing_headwords_file()`, `fill_existing_headwords()`, review/order-report actions, runtime-installed methods, generic batch-runner changes, or Phase 5 work into Phase 4T.

Before any Phase 4T write, revalidate live `main`, open PRs, exact method body/callers/import ownership, runtime ownership, and whether any dependency moved since this checkpoint.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Phase 4S is complete and recoverable. No Phase 4T production code has started. The recommended Phase 4T unit above is sufficiently narrow to resume when continuation is requested.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
