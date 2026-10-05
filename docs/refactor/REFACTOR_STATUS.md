# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4R is complete.

## Architecture checkpoint
- Last completed architecture PR: #217 — `backup_pdic()` action orchestration routed through the existing `ExportController`
- Last completed architecture merge commit: `d9e40fa12ec209da985000f70cf4968690ed0e7b`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, `export_picdic_index()`, and `backup_pdic()`.

`ExportController` now owns current-page `.OCRed` import/export orchestration, PicDic package-build orchestration, PicDic index streaming export orchestration, and project-wide PDIC backup streaming orchestration. Persisted formats and path policy remain outside controllers: `.OCRed`/PDIC/PicDic-index formatting remains in the existing format/processing modules, PicDic package building remains in `picdic.py`, and project output paths remain in `project_storage`.

## Last verified tests
- Phase 4R pre-PR focused suite: 613 passed
- Phase 4R pre-PR full suite: 1215 passed, 2 existing Pillow deprecation warnings
- Phase 4R PR #217 fixed head: `9c1da778b8726951339b195839ddedb887c2f070`
- PR #217 CI at the fixed head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #217: Ubuntu / Windows / macOS all passed
- CodeQL after #217: Python and Actions analyses passed
- `app.py` architecture size baseline after #217: 853,579 bytes

Phase 4R validation history worth preserving for recovery:
- the first isolated validation stopped at `git diff --check` because the temporary patch generator added one extra blank line at EOF in `export.py` and `test_ui_export_controller.py`; pytest had not run and production behavior was not changed
- the next focused run reported 611 passed and 2 failures because two legacy `tests/test_core.py` checks still required `_start_batch_task(...)` and `refresh_page_quality=False` to be physically inside `PictureCaptureApp.backup_pdic()`
- those source-shape checks were updated to follow the app compatibility wrapper into `ExportController.backup_pdic()` while retaining the original background-streaming and no-unrelated-refresh contracts; the adjacent no-image-read source check was updated at the same time so it continues to inspect the implementation rather than the wrapper
- production code was not changed to resolve those test-only failures
- temporary isolated-validation workflows/scripts were removed before PR creation; the final net diff contained only 4 expected production/test files

## Completed Phase 4R seam
`PictureCaptureApp.backup_pdic()` now remains as a compatibility wrapper and delegates to `ExportController.backup_pdic()`.

The controller preserves:
- exact missing-project/current-page/image dialog behavior
- exact batch-active status `已有批量任务正在运行，请结束后再备份PDIC。`
- foreground `_flush_deferred_page_save()`, `_sync_entry_editor_texts()`, and `save_pdic(silent=True, sync_editors=False)` before backup
- exact preparation/publish error title `备份PDIC失败`
- filtering to project pages with existing PDIC files and exact no-PDIC info dialog
- timestamp format `%Y%m%d_%H%M%S_%f`, target name `all_pdic_backup_{stamp}.txt`, and `exports_root(project.root)` path policy
- hidden temporary-file naming and lazy stream creation with UTF-8 / `newline="\n"`
- one-page-at-a-time source reads with `encoding="utf-8-sig"`, `splitlines()`, and blank-line filtering while preserving each nonblank raw record
- page/record counters without project-wide accumulation and without opening page images
- stream flush/close plus temporary-file cleanup on stopped/error paths
- exact stopped status `PDIC备份已停止：完成 {completed}/{total} 页，未生成不完整备份。`
- empty-success publication behavior and atomic `os.replace(temp, target)` publication
- exact completed status/dialog contents and parent ownership
- the existing app-owned `_start_batch_task(...)` boundary, page-name labels, and `refresh_page_quality=False`
- the existing UI `备份PDIC` binding

`restore_from_pdic_backup()` was explicitly not moved in Phase 4R. No restore parsing, destructive page rewrite, format semantics, generic batch runner, runtime-installed method, or Phase 5 behavior was changed.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

Training package export is also installed onto `PictureCaptureApp` during GUI bootstrap from `training_export_ui.export_training_package_selected_range`; do not treat that runtime-installed extension as an ordinary app-body controller seam during Phase 4.

## Revalidation after Phase 4R
After Phase 4R merge-push verification:
- live `main` is `d9e40fa12ec209da985000f70cf4968690ed0e7b`
- no open competing PR exists at revalidation time
- `ExportController` owns PicDic package build, PicDic index streaming export, and PDIC backup streaming orchestration while the app retains compatibility wrappers and the generic batch runner
- `restore_from_pdic_backup()` remains directly in `PictureCaptureApp`
- that restore path is materially more complex and destructive than the completed export/backup seams: it owns selected-range validation, confirmation, foreground save, one-time parsed backup mapping/cache, settings snapshots, image-size reads, reading-order reconstruction, per-page atomic PDIC writes, persisted warning cleanup, page-row/overlay refresh, current-page reload, and stopped/completed status aggregation
- training-package export is bootstrap-installed rather than a normal `PictureCaptureApp` method body
- remaining review/order/storage actions are semantically different controller domains rather than mechanical continuations of Phase 4R
- no Phase 5 runtime-patch cleanup has begun

## Current issue / architecture choice required
There is no failing implementation blocker. Automatic production-code continuation is paused because post-Phase-4R live review no longer exposes one mandatory mechanical next move.

The nearest adjacent candidate, `restore_from_pdic_backup()`, is not a symmetric inverse of the completed backup migration. Moving it would establish ownership for destructive PDIC restoration and its UI/storage refresh side effects. It may belong in `ExportController`, a future PDIC/storage-oriented controller, or remain at the app boundary until a broader storage ownership decision is made. Those are materially different architecture choices and must not be selected implicitly.

Other apparent export-like work is not a safe substitute: training-package export is installed dynamically during GUI bootstrap and belongs with later runtime-extension cleanup/ownership work, while remaining review/order actions belong to different controller domains.

## Recommended next action
Before any Phase 4S production write, obtain human confirmation of the next ownership direction. A focused review of `restore_from_pdic_backup()` versus the remaining PDIC/review/storage seams should decide whether Phase 4 continues with a new narrow PDIC-restoration unit, introduces a more appropriate controller boundary, or stops controller decomposition before runtime-patch cleanup.

Do not automatically migrate `restore_from_pdic_backup()` into `ExportController`. Do not fold training export or runtime-installed actions into Phase 4. Do not enter Phase 5 without an explicit milestone decision.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Phase 4R is complete and recoverable. No Phase 4S production code has started. Automatic production continuation is paused pending human confirmation of the next architecture seam.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
