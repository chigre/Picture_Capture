# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4U is complete.

## Architecture checkpoint
- Last completed architecture PR: #223 — `batch_auto_detect(force_paddle_refresh=False)` routed through the existing `DetectionController`
- Last completed architecture merge commit: `d30eae9e4a7290dce8038a84b9972b77b1e138ac`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

Historical `PictureCaptureApp` compatibility wrappers now include: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, `export_picdic_index()`, `backup_pdic()`, `restore_from_pdic_backup()`, `repair_pdic_order_selected_scope()`, and `batch_auto_detect()`.

`restore_from_merged_pdic()` remains the historical compatibility alias and calls `restore_from_pdic_backup()`.

`ExportController` owns current-page `.OCRed` import/export orchestration, PicDic package build, PicDic index streaming export, PDIC backup streaming, selected-range PDIC restore, and selected-range PDIC order repair. The app still owns the generic batch runner and shared page/UI refresh helpers.

`DetectionController` owns the stable OCR/combined action-entry seams: current Paddle detection setup, selected-scope combined/OCR draw actions, scoped OCR draw routing, and now full-project `batch_auto_detect()` routing. The app still owns `_detect_pages(...)`, `auto_detect_current(...)`, OCR/detection workers, batch execution, PDIC/`.OCRed` persistence, and the heavy detection pipeline.

`pdic_restore.py` remains the deterministic low-level boundary for page-token lookup/resolution, merged-PDIC parsing, and one-page temporary-file + `os.replace(...)` atomic publication. PDIC field semantics and project path policy remain outside controllers.

## Last verified tests
- Phase 4U pre-PR focused suite: 592 passed
- Phase 4U pre-PR full suite: 1236 passed, 2 existing Pillow deprecation warnings
- `git diff --check`: passed
- compileall: passed
- Ruff F821: passed
- Phase 4U PR #223 fixed head: `32dd47eb439758d2388de6a4b2c93132cfcb513e`
- PR #223 fixed-head CI: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- Phase 4U architecture merge commit: `d30eae9e4a7290dce8038a84b9972b77b1e138ac`
- `main` merge-push CI after #223: Ubuntu / Windows / macOS all passed
- CodeQL after #223: Python and Actions analyses passed
- `app.py` architecture size baseline after #223: 838,567 bytes

Phase 4U validation history worth preserving for recovery:
- live revalidation started from the Phase 4T checkpoint `173b4f4f60d535255d1a0e353f4d26d76e9add36`
- no competing open PR existed and the live `batch_auto_detect()` body matched the checkpoint description
- no runtime replacement for `batch_auto_detect()` was found; the runtime-owned detection exclusion remains `run_normal_draw_action`
- the first and only isolated validation run passed without stale source-shape or production failures
- focused suite: 592 passed
- full suite: 1236 passed, 2 existing Pillow deprecation warnings
- temporary isolated-validation workflow/script were removed before PR creation
- final net diff from the Phase 4T checkpoint contained exactly 3 expected files: `src/picture_capture/app.py`, `src/picture_capture/ui/controllers/detection.py`, and `tests/test_ui_detection_controller.py`

## Completed Phase 4U seam
`PictureCaptureApp.batch_auto_detect(force_paddle_refresh=False)` remains as a compatibility wrapper and delegates to `DetectionController.batch_auto_detect(...)`.

The controller preserves exactly:
- missing-project behavior as a silent no-op
- full-project scope through `list(range(len(app.project.images)))`
- lookup of the current `app.settings.detection_method` at call time
- direct forwarding of `force_paddle_refresh` into `_detect_pages(..., force_refresh=...)`
- no additional settings mutation or `save_settings()` call
- no selected-range parsing and no use of `selected_page_indices()`
- app-owned `_detect_pages(...)` processing boundary

Phase 4U did not move `_detect_pages(...)`, `auto_detect_current(...)`, `batch_ocr()`, OCR/detection workers, `.OCRed`/PDIC persistence, runtime-installed methods, or Phase 5 work.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

Training package export is installed onto `PictureCaptureApp` during GUI bootstrap from `training_export_ui.export_training_package_selected_range`; do not treat that runtime-installed extension as an ordinary app-body controller seam during Phase 4.

## Revalidation after Phase 4U
After Phase 4U merge-push verification:
- live `main` is `d30eae9e4a7290dce8038a84b9972b77b1e138ac`
- no open competing PR exists at revalidation time
- the narrow detection action-entry seams are now routed through `DetectionController`
- the remaining adjacent detection methods are materially heavier than Phase 4U:
  - `auto_detect_current(...)` is the app-owned single-page worker/batch bridge and ends in app-owned `_start_batch_task(...)`
  - `batch_ocr()` owns transformed-geometry guarding, project-wide PDIC filtering, destructive confirmation, OCR worker logic, `.OCRed` export, PDIC writes, done aggregation, and the app-owned batch runner
- `check_headword_order()` is a different domain choice: it owns current/all-page order reporting plus background finalization/UI work and could plausibly extend `ReviewController` or justify a separate reporting boundary
- `select_existing_headwords_file()` / `fill_existing_headwords()` form another domain: source-file selection, parsed-source caching/signature invalidation, repeated range fills, PDIC updates, and persisted fill-status state; choosing an existing controller versus a dedicated headword-fill controller is a material architecture decision
- entering Phase 5 to remove runtime installers is a milestone transition and always requires explicit human confirmation

## Next-step decision point
Automatic controller decomposition is paused after Phase 4U because the live repository now exposes multiple materially different architecture choices rather than one uniquely narrow mechanical seam.

Reasonable next directions are:
1. **Headword-fill domain** — decide controller ownership for `select_existing_headwords_file()` / `fill_existing_headwords()` before moving code. A dedicated controller is plausible, but adding one is an architecture choice.
2. **Detection batch-processing boundary** — move `batch_ocr()` and/or later `auto_detect_current()` toward `DetectionController`. This would deliberately expand that controller beyond action-entry routing into worker/persistence orchestration, so it is not an ownership-only continuation.
3. **Review/order-report domain** — move `check_headword_order()` toward `ReviewController` or a separate reporting controller; this carries report/finalization UI state.
4. **Phase 5 runtime-patch cleanup** — remove runtime-installed ownership seams such as `ordinary_action_runtime`; this is a milestone transition, not Phase 4 auto-continuation.

Do not select among these directions automatically. Human confirmation is required before the next production-code write.

Before the next write, revalidate live `main`, open PRs, the selected method bodies/callers/UI bindings, runtime ownership, and dependency ownership.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Phase 4U is complete and recoverable. Automatic production-code continuation is paused at the architecture decision point above.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
