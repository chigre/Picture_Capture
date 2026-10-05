# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4Q is complete.

## Architecture checkpoint
- Last completed architecture PR: #215 — `export_picdic_index()` action orchestration routed through the existing `ExportController`
- Last completed architecture merge commit: `b6e8bff9be2c1115a3e971f4b5386e59b72ed45f`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, and `export_picdic_index()`.

`ExportController` now owns current-page `.OCRed` import/export orchestration, PicDic package-build orchestration, and PicDic index streaming export orchestration. Persisted formats and path policy remain outside controllers: `.OCRed`/PDIC/PicDic-index formatting remains in the existing format/processing modules, PicDic package building remains in `picdic.py`, and project output paths remain in `project_storage`.

## Last verified tests
- Phase 4Q pre-PR focused suite: 605 passed
- Phase 4Q pre-PR full suite: 1207 passed, 2 existing Pillow deprecation warnings
- Phase 4Q PR #215 fixed head: `f4e40265de49e7299882bba107687b663ac22652`
- PR #215 CI at the fixed head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #215: Ubuntu / Windows / macOS all passed
- CodeQL after #215: Python and Actions analyses passed
- `app.py` architecture size baseline after #215: 858,116 bytes

Phase 4Q validation history worth preserving for recovery:
- the first isolated validation stopped at `git diff --check` because the temporary patch generator added one extra blank line at EOF in two files; tests had not run and production behavior was not changed
- the next focused run reported 604 passed and 1 failure because `tests/test_core.py::test_v21111_picdic_index_export_is_background_streaming_and_exact_format` still required the streaming body to be physically inside `PictureCaptureApp.export_picdic_index()`
- that legacy source-shape test was updated to follow the app compatibility wrapper into `ExportController.export_picdic_index()` while retaining its streaming/background/format assertions; production code was not changed to resolve this test-only failure
- a subsequent focused run again reported 604 passed and 1 failure because the same legacy test expected the historical exact-format documentation `WORD<TAB>xx.xx<TAB>yy.yy<TAB>page` to remain with the implementation; the original method documentation was preserved in the controller instead of weakening the contract
- temporary isolated-validation workflows/scripts were removed before PR creation; the final net diff contained only 4 expected production/test files

## Completed Phase 4Q seam
`PictureCaptureApp.export_picdic_index()` now remains as a compatibility wrapper and delegates to `ExportController.export_picdic_index()`.

The controller preserves:
- exact missing-project/current-page/image dialog behavior
- exact batch-active status `已有批量任务正在运行，请结束后再导出PicDic索引。`
- foreground `_flush_deferred_page_save()`, `_sync_entry_editor_texts()`, and `save_pdic(silent=True, sync_editors=False)` before export
- exact preparation/publish error title `导出PicDic索引失败`
- filtering to project pages with existing PDIC files and exact no-PDIC info dialog
- timestamp format `%Y%m%d_%H%M%S_%f`, target name `PicDic_index_{stamp}.txt`, and `exports_root(project.root)` path policy
- hidden temporary-file naming and lazy stream creation with UTF-8 / `newline="\n"`
- one-page-at-a-time conversion through `read_picdic_index_records(pdic_path(page), fallback_page=page.stem)`
- incremental row streaming and page/record counters without project-wide accumulation
- stream flush/close plus temporary-file cleanup on stopped/error paths
- exact stopped status `PicDic索引导出已停止：完成 {completed}/{total} 页，未生成不完整索引。`
- empty-success publication behavior and atomic `os.replace(temp, target)` publication
- exact completed status/dialog contents and parent ownership
- the historical documented four-column format `WORD<TAB>xx.xx<TAB>yy.yy<TAB>page`
- the existing app-owned `_start_batch_task(...)` boundary, item labels, and `refresh_page_quality=False`
- the existing UI `导出PicDic索引` binding

Only the action-level `read_picdic_index_records` dependency moved out of `app.py`. The helper implementation in `formats.py`, PDIC format semantics, saved coordinates, `exports_root(...)`, generic batch runner, and atomic-file behavior were not changed.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

## Revalidation after Phase 4Q
After Phase 4Q merge-push verification:
- live `main` is `b6e8bff9be2c1115a3e971f4b5386e59b72ed45f`
- no open competing PR exists at revalidation time
- `ExportController` now owns both PicDic package-build orchestration and PicDic index streaming-export orchestration while the app retains compatibility wrappers and the generic batch runner
- `backup_pdic()` remains directly in `PictureCaptureApp`
- `restore_from_pdic_backup()` remains directly in `PictureCaptureApp` and is materially more complex/destructive than the backup action; it should not be bundled with a backup migration
- no Phase 5 runtime-patch cleanup has begun

## Recommended next safe unit
The preferred Phase 4R candidate is a **single narrow migration of only `PictureCaptureApp.backup_pdic()` action orchestration into the existing `ExportController`**, retaining the historical app wrapper, app-owned `_start_batch_task(...)`, output path/format semantics, streaming temporary-file lifecycle, exact status/dialog/error contracts, and atomic `os.replace(...)` publication.

This is the closest mechanical continuation of Phase 4Q: `backup_pdic()` uses the same project-wide streaming temporary-file pattern, the same `exports_root(...)` output boundary, the same generic batch runner, the same stop/error cleanup model, and the same atomic publication concept. `restore_from_pdic_backup()` is explicitly out of scope for that unit.

Before any Phase 4R write, revalidate live `main`, open PRs, the exact `backup_pdic()` body/callers/import ownership, runtime ownership, and its complete stream/temp cleanup contract. Keep Phase 4R to `backup_pdic()` only and repeat focused/full/three-platform/merge-push/CodeQL validation.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Phase 4Q is complete and recoverable. No Phase 4R production code has started. The recommended Phase 4R unit above is sufficiently narrow to resume when continuation is requested; do not bundle restore behavior or other app seams into it.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
