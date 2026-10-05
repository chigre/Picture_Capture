# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the live repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4W, 4X, and 4Y are complete. Automatic Phase 4 production-code continuation is paused at the Phase 5 milestone boundary.

## Architecture checkpoint
- Last completed architecture PR: #230 — `auto_detect_current(...)` routed through `DetectionController`
- Last completed architecture merge commit: `6b5af293232039102fddcf90bb51c6a2373023e7`
- Previous detection batch-processing PR: #229 — `batch_ocr()` routed through `DetectionController`
- Phase 4X merge commit: `704936dfe90c5132f130475a2ff199cd4bc3d9ab`
- Previous headword-fill PR: #227 — `select_existing_headwords_file()` / `fill_existing_headwords()` routed through `HeadwordController`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

Historical `PictureCaptureApp` compatibility wrappers now include: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, `export_picdic_index()`, `backup_pdic()`, `restore_from_pdic_backup()`, `repair_pdic_order_selected_scope()`, `batch_auto_detect()`, `batch_ocr()`, `auto_detect_current(...)`, `check_headword_order()`, `select_existing_headwords_file()`, and `fill_existing_headwords()`.

`restore_from_merged_pdic()` remains the historical compatibility alias and calls `restore_from_pdic_backup()`.

`ExportController` owns current-page `.OCRed` import/export orchestration, PicDic package build, PicDic index streaming export, PDIC backup streaming, selected-range PDIC restore, and selected-range PDIC order repair. The app still owns the generic batch runner and shared page/UI refresh helpers.

`DetectionController` now owns:
- current Paddle detection setup (`paddle_detect_current`)
- selected-scope combined/OCR draw entry actions
- scoped OCR draw routing
- full-project `batch_auto_detect()` routing
- full-project `batch_ocr()` worker/persistence orchestration
- current-page `auto_detect_current(...)` worker/batch bridge, including clicked-column replacement and combined-mode blank-text rescue

The app still owns the generic `_start_batch_task(...)` runner, `_detect_pages(...)` multi-page detection pipeline, transformed-geometry guard, page tuple generation, shared page/review/quality refresh helpers, and broader UI/persistence infrastructure.

`ReviewController` owns OCR review candidate lookup/matching, lightweight review highlight/navigation state, and current/all-page headword-order report orchestration. `PictureCaptureApp.check_headword_order(...)` remains a compatibility wrapper. The app still owns generic batch/UI-worker runners, text-report window construction, current-page sort-key helpers, durable candidate edits, PDIC/manual-override writes, and detailed proofreading rendering.

`HeadwordController` owns page-aware headword-source selection and selected-range headword-fill orchestration. `PictureCaptureApp.select_existing_headwords_file()` and `PictureCaptureApp.fill_existing_headwords()` remain compatibility wrappers. The app still owns durable source/cache fields, fill-status persistence, generic batch runner, page reload/refresh, PDIC format semantics, and low-level parser/fill helpers injected into the controller.

`pdic_restore.py` remains the deterministic low-level boundary for page-token lookup/resolution, merged-PDIC parsing, and one-page temporary-file + `os.replace(...)` atomic publication. PDIC field semantics and project path policy remain outside controllers.

## Last verified tests
### Phase 4X — batch OCR routing
- isolated focused suite: 190 passed
- isolated full suite: 1243 passed, 2 existing Pillow deprecation warnings
- `git diff --check`: passed
- compileall: passed
- Ruff F821: passed
- validated production commit: `6d1f8456cc9c62ea096a428aabc2a0ae099923ea`
- final same-tree PR head used to trigger standard CI: `28b499ac07290ffee3b91ac58fbc53f2607f5bff`
- PR #229 Ubuntu / Windows / macOS CI passed, including pytest, GUI smoke, compatibility runner, compile, F821, and wheel build
- PR #229 CodeQL / Advanced Security passed
- Phase 4X merge commit: `704936dfe90c5132f130475a2ff199cd4bc3d9ab`
- merge-push CI on `main` passed on Ubuntu / Windows / macOS
- merge-push CodeQL Python and Actions analyses passed

### Phase 4Y — current-page detection routing
- first isolated focused run: 192 passed / 2 failed; both failures were stale source-shape assertions still requiring the implementation body in `app.py`
- those assertions were migrated to verify the compatibility wrapper plus `DetectionController` ownership; no production behavior was changed by that test-only correction
- final isolated focused suite: 194 passed
- final isolated full suite: 1247 passed, 2 existing Pillow deprecation warnings
- `git diff --check`: passed
- compileall: passed
- Ruff F821: passed
- validated production commit: `09c75f2aae5fff299b3a04feda11f7a7ef750813`
- final PR head after same-tree user-authored CI trigger: `6f40b5d611f0aa10169f1915412bc546b7b25961`
- final net diff contained exactly 4 expected files: `src/picture_capture/app.py`, `src/picture_capture/ui/controllers/detection.py`, `tests/test_next_stage_regressions.py`, and `tests/test_ui_detection_controller.py`
- PR #230 Ubuntu / Windows / macOS CI passed, including pytest, GUI smoke, compatibility runner, compile, F821, and wheel build
- PR #230 CodeQL Python / Actions and Advanced Security passed
- no PR review threads, review objections, or PR comments were present before merge
- Phase 4Y merge commit: `6b5af293232039102fddcf90bb51c6a2373023e7`
- merge-push CI on `main`: Ubuntu / Windows / macOS all passed
- merge-push CodeQL on `main`: Python and Actions analyses passed

## Completed Phase 4X seam — `batch_ocr()`
`PictureCaptureApp.batch_ocr()` remains a compatibility wrapper and delegates to `DetectionController.batch_ocr()`.

The controller preserves:
- project-open and batch-active no-op behavior
- transformed-geometry guard
- project-wide filtering to pages that already contain PDIC entries
- destructive-operation confirmation and original user-facing wording
- copied settings snapshot and replace-rule snapshot before the worker runs
- page tuple metadata generated through the app-owned helper
- page-image normalization, effective page settings, page-template analysis image, page sections, reading-order sort, and OCR behavior
- `.OCRed` export and PDIC writes on each worker page
- existing generic batch identity and page labels
- stop/completion aggregation and current-page reload behavior

Phase 4X deliberately did not move generic batch infrastructure, page tuple semantics, page reload/status UI, `_detect_pages(...)`, or Phase 5 runtime installers.

## Completed Phase 4Y seam — `auto_detect_current(...)`
`PictureCaptureApp.auto_detect_current(clicked_x=None, force_paddle_refresh=False)` remains a compatibility wrapper and delegates to `DetectionController.auto_detect_current(...)`.

The controller preserves:
- batch-active foreground-detection guard and exact status text
- normal project guard and transformed-geometry guard
- immutable snapshots of project/page identity, current index, settings, page sections, and existing entries
- compact OCR cache and headword-filter-rule path semantics for Paddle/combined modes
- current-page detection worker behavior and `force_paddle_refresh` propagation
- combined-mode local blank-text rescue through `ocr_existing_entry_words_from_markers(..., only_blank=True)`
- the hard guard that combined-mode text rescue must not modify detected marker coordinates
- clicked-column semantics: replace only the clicked column while preserving entries from the other columns
- project/page identity check before publishing worker results back into the live UI
- reading-order sort, OCR review-candidate reload, page-quality refresh, redraw, and original completion wording
- app-owned generic `_start_batch_task(...)` and current-page item label / quality-refresh flags

Phase 4Y deliberately did not move `_detect_pages(...)`, the generic batch runner, the heavy multi-page detection pipeline, runtime-installed ordinary drawing, or any Phase 5 runtime patch.

## Runtime-owned exclusions after Phase 4Y
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime.install_ordinary_action_runtime(...)` replaces that app method at GUI bootstrap time. The runtime adapter also contains the special OCR-independent quick-setting validation used when all OCR engines are disabled.

`postproduction_single_line_runtime` remains a substantially wider runtime patch: it installs `split_single_lines_selected_scope`, wraps `PictureCaptureApp.__init__`, locates/inserts the `单行切图` button dynamically, owns a dedicated background thread/poll loop, and tracks private runtime state fields.

Training package export remains assigned onto `PictureCaptureApp` during GUI bootstrap from `training_export_ui.export_training_package_selected_range`; it owns batch staging/finalization, cancellation cleanup, manifest/ZIP publication, and an auxiliary UI-worker cleanup path.

Other GUI bootstrap runtime installers still exist and are not implied to be removable merely because the three seams above are highlighted. Phase 5 should remain incremental rather than attempting to eliminate the entire installer chain in one change.

## Phase 5 read-only assessment after Phase 4Y
The recommended first Phase 5 seam is **`ordinary_action_runtime`**, for these reasons:
- it replaces one method whose semantic home is already the Detection domain;
- its core action is small: guard → OCR-independent quick-setting validation → selected-page resolution → set `left_edge` → save settings → `_detect_pages(...)`;
- moving it first would let `DetectionController` own the ordinary/combined/OCR action-entry trio consistently;
- unlike the single-line runtime, it does not wrap `__init__` or dynamically mutate widget layout;
- unlike training export, it does not own staging/ZIP/cancellation cleanup semantics.

A safe first Phase 5 slice should therefore be limited to retiring the `run_normal_draw_action` monkey patch while preserving the OCR-independent validator behavior exactly. The likely shape is an explicit app compatibility method routed to `DetectionController`, with the ordinary quick-setting helper retained or moved to a non-monkey-patching helper module. Do not combine this with `_detect_pages(...)` extraction or another runtime installer in the same first Phase 5 PR.

Recommended Phase 5 order after that first slice:
1. retire `ordinary_action_runtime` method replacement only;
2. reassess `postproduction_single_line_runtime` separately, because its method patch and `__init__`/button injection should probably be decomposed into separate ownership changes;
3. reassess training-export method assignment separately after the batch/export ownership boundary is explicit.

This is a recommendation only. No Phase 5 production code has been written at this checkpoint.

## Next-step decision point
Detection batch-processing decomposition requested after Phase 4W is complete: both `batch_ocr()` and `auto_detect_current(...)` now belong to `DetectionController` while generic batch infrastructure and `_detect_pages(...)` remain app-owned.

The next production-code change would cross into **Phase 5 runtime-patch cleanup**, which is an explicit milestone transition. Human confirmation is required before that write.

If Phase 5 is approved, revalidate before writing:
- live `main` and open PRs
- `ordinary_action_runtime.py`
- the current app-body `run_normal_draw_action` compatibility/default implementation
- DetectionController wiring/tests
- GUI bootstrap installer order and all tests that assert runtime ownership
- the all-OCR-engines-disabled ordinary-drawing behavior

Do not start by deleting the runtime helper or bootstrap call until the explicit replacement path is present and covered by regression tests.

## Auto continuation
Phase 4Y is complete and recoverable. Automatic production-code continuation is paused before Phase 5.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
