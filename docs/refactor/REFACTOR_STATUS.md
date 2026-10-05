# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4W is complete.

## Architecture checkpoint
- Last completed architecture PR: #227 — `select_existing_headwords_file()` / `fill_existing_headwords()` routed through a dedicated `HeadwordController`
- Last completed architecture merge commit: `902e69a833059a1e9b1f47d7640d6c710f11e561`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

Historical `PictureCaptureApp` compatibility wrappers now include: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, `export_picdic_index()`, `backup_pdic()`, `restore_from_pdic_backup()`, `repair_pdic_order_selected_scope()`, `batch_auto_detect()`, `check_headword_order()`, `select_existing_headwords_file()`, and `fill_existing_headwords()`.

`restore_from_merged_pdic()` remains the historical compatibility alias and calls `restore_from_pdic_backup()`.

`ExportController` owns current-page `.OCRed` import/export orchestration, PicDic package build, PicDic index streaming export, PDIC backup streaming, selected-range PDIC restore, and selected-range PDIC order repair. The app still owns the generic batch runner and shared page/UI refresh helpers.

`DetectionController` owns the stable OCR/combined action-entry seams: current Paddle detection setup, selected-scope combined/OCR draw actions, scoped OCR draw routing, and full-project `batch_auto_detect()` routing. The app still owns `_detect_pages(...)`, `auto_detect_current(...)`, OCR/detection workers, batch execution, PDIC/`.OCRed` persistence, and the heavy detection pipeline.

`ReviewController` owns OCR review candidate lookup/matching, lightweight review highlight/navigation state, and current/all-page headword-order report orchestration. `PictureCaptureApp.check_headword_order(...)` remains as a compatibility wrapper. The app still owns the generic batch runner, generic UI-worker runner, text-report window helper, current-page sort-key helpers, durable candidate edits, PDIC/manual-override writes, and the detailed translucent proofreading highlight renderer.

`HeadwordController` owns page-aware headword-source selection and selected-range headword-fill orchestration. `PictureCaptureApp.select_existing_headwords_file()` and `PictureCaptureApp.fill_existing_headwords()` remain compatibility wrappers. The app still owns the durable source/cache fields, fill-status persistence, generic batch runner, page reload/refresh, PDIC format semantics, and the low-level `_parse_words_of_pages_text(...)` / `_fill_page_entries(...)` helpers; those helpers are injected into the controller to avoid a reverse dependency on `app.py`.

`pdic_restore.py` remains the deterministic low-level boundary for page-token lookup/resolution, merged-PDIC parsing, and one-page temporary-file + `os.replace(...)` atomic publication. PDIC field semantics and project path policy remain outside controllers.

## Last verified tests
- Phase 4W isolated focused suite: 183 passed
- Phase 4W isolated full suite: 1241 passed, 2 existing Pillow deprecation warnings
- `git diff --check`: passed
- compileall: passed
- Ruff F821: passed
- Phase 4W validated production code commit: `22c75b81593776f1b92e4f8888cc4df33369e8c6`
- Same-tree user-authored CI trigger commit: `b7632237e4fe01e97488aa43880d429f937f5e58`
- Final PR head after the Windows-only line-ending test normalization: `247d303e835211aae53cc456dbf885b09978fed3`
- PR #227 final-head CI: Ubuntu / Windows / macOS all passed, including pytest, GUI smoke, compatibility runner, compile, F821, and wheel build
- PR #227 CodeQL and Advanced Security checks passed
- Phase 4W architecture merge commit: `902e69a833059a1e9b1f47d7640d6c710f11e561`
- `main` merge-push CI after #227: Ubuntu / Windows / macOS all passed
- CodeQL after #227: Python and Actions analyses passed
- Previous `app.py` architecture size baseline after #223: 838,567 bytes; no new byte-size baseline was recorded for #227

Phase 4W validation history worth preserving for recovery:
- live revalidation started from the Phase 4V checkpoint `f0654f84449e79bdd0d3860d72d52d3ae9852416`; no competing open PR existed
- the user explicitly confirmed continuation from the post-4V decision point
- a dedicated `HeadwordController` was chosen instead of extending `ReviewController` because the domain includes file selection, signature/cache invalidation, PDIC writes, repeated batch fills, and persisted fill-status state rather than read-side review/reporting alone
- the controller was deliberately kept narrow: app-owned cache/status/batch/PDIC infrastructure remained in place, and existing parser/fill helpers were dependency-injected instead of importing `app.py`
- the first isolated focused suite passed 183 tests; the first isolated full run reported 1238 passed / 3 failed, and all three failures were stale source-shape assertions in `tests/test_core.py` still assuming the implementation lived in `app.py`
- those three assertions were updated to verify the compatibility wrappers plus the new controller ownership without changing production behavior
- two temporary validation runs overlapped because the temporary workflow was triggered by both branch push and the draft PR event; one fully validated sibling run published the production tree while the other was rejected only at its final non-fast-forward push. No force overwrite was used, and the remote validated tree was preserved
- final isolated validation passed: focused suite 183 passed; full suite 1241 passed with the same 2 existing Pillow deprecation warnings; compileall and Ruff F821 passed
- temporary validation workflow/script were removed from the final production tree
- the initial standard PR CI then found one Windows-only test failure: the new test compared `"\n"` exactly while the Windows temporary text file was read as `"\r\n"`; 1240 other tests passed and production behavior was unaffected
- that test alone was made cross-platform by comparing `splitlines()` content; no production code changed in that final commit
- the final PR head passed all standard CI and security checks on all supported platforms
- final net diff from the Phase 4V checkpoint contained exactly 6 expected files: `src/picture_capture/app.py`, `src/picture_capture/ui/controllers/__init__.py`, `src/picture_capture/ui/controllers/headword.py`, `tests/test_core.py`, `tests/test_next_stage_regressions.py`, and `tests/test_ui_headword_controller.py`
- no PR review threads or review objections were present before merge

## Completed Phase 4W seam
`PictureCaptureApp.select_existing_headwords_file()` and `PictureCaptureApp.fill_existing_headwords()` remain compatibility wrappers and delegate to `HeadwordController`.

The controller preserves exactly:
- the existing project-open and batch-active guards
- source-file selection dialog defaults and status text
- source signature semantics using resolved path, nanosecond mtime, and file size
- unchanged-source cache reuse and changed-source cache invalidation
- repeated fill batches from a previously selected source without reopening the file picker
- selected-page scope through the existing app-owned `selected_page_indices()` path
- flushing/synchronizing/saving live foreground edits before background PDIC reads begin
- a copied `settings_snapshot` for worker geometry rather than reading mutable live settings inside the worker
- source TXT parsing on the batch-worker path for cache misses rather than blocking Tk's event thread
- a batch-local mapping holder so worker execution does not publish app-level parse cache state mid-run
- header-size image access only; no full page-image decode was introduced
- existing reading-order sorting using nominal geometry and page sections
- existing `_fill_page_entries(...)` semantics through dependency injection
- one-page-at-a-time PDIC commit behavior and the existing rule against fabricating a PDIC solely because TXT words exist
- the existing `"填充词条"` generic batch runner identity, page item labels, and `foreground_page_edit=False` protection
- publication of parsed cache to app state only in `done(...)` and only when project, source path, and source signature still match
- existing fill-status recording/persistence and current-page reload behavior
- existing stop/completion status summaries and mismatch/no-data counts

Phase 4W did not move `import_legacy_words()`, old/new headword comparison workflows, fill-status persistence helpers, generic batch infrastructure, detection/OCR batch processing, runtime-installed methods, or Phase 5 work.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

Training package export is installed onto `PictureCaptureApp` during GUI bootstrap from `training_export_ui.export_training_package_selected_range`; do not treat that runtime-installed extension as an ordinary app-body controller seam during Phase 4.

## Revalidation after Phase 4W
After Phase 4W merge-push verification:
- live architecture merge on `main` is `902e69a833059a1e9b1f47d7640d6c710f11e561`
- the headword-fill domain selected after Phase 4V is complete and routed through the dedicated `HeadwordController`
- the remaining adjacent detection methods are materially heavier than the completed action-entry seams:
  - `auto_detect_current(...)` is the app-owned single-page worker/batch bridge and ends in app-owned `_start_batch_task(...)`
  - `batch_ocr()` owns transformed-geometry guarding, project-wide PDIC filtering, destructive confirmation, OCR worker logic, `.OCRed` export, PDIC writes, done aggregation, and the app-owned batch runner
- entering Phase 5 to remove runtime installers remains a milestone transition and always requires explicit human confirmation

## Next-step decision point
Automatic controller decomposition is paused after Phase 4W because the remaining routes require materially different ownership/milestone decisions rather than a uniquely narrow mechanical continuation.

Reasonable next directions are:
1. **Detection batch-processing boundary** — move `batch_ocr()` and/or later `auto_detect_current()` toward `DetectionController`. This would deliberately expand that controller beyond action-entry routing into worker/persistence orchestration, so it is not an ownership-only continuation.
2. **Phase 5 runtime-patch cleanup** — remove runtime-installed ownership seams such as `ordinary_action_runtime`; this is a milestone transition, not Phase 4 auto-continuation.

Do not select between these directions automatically. Human confirmation is required before the next production-code write.

Before the next write, revalidate live `main`, open PRs, the selected method bodies/callers/UI bindings, runtime ownership, and dependency ownership.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Phase 4W is complete and recoverable. Automatic production-code continuation is paused at the architecture decision point above.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
