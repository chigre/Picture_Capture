# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4V is complete.

## Architecture checkpoint
- Last completed architecture PR: #225 — `check_headword_order(all_pages=False)` routed through the existing `ReviewController`
- Last completed architecture merge commit: `77c6e4a5a056e59381fde4fcc7516f2f4c137aba`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

Historical `PictureCaptureApp` compatibility wrappers now include: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, `build_picdic()`, `export_picdic_index()`, `backup_pdic()`, `restore_from_pdic_backup()`, `repair_pdic_order_selected_scope()`, `batch_auto_detect()`, and `check_headword_order()`.

`restore_from_merged_pdic()` remains the historical compatibility alias and calls `restore_from_pdic_backup()`.

`ExportController` owns current-page `.OCRed` import/export orchestration, PicDic package build, PicDic index streaming export, PDIC backup streaming, selected-range PDIC restore, and selected-range PDIC order repair. The app still owns the generic batch runner and shared page/UI refresh helpers.

`DetectionController` owns the stable OCR/combined action-entry seams: current Paddle detection setup, selected-scope combined/OCR draw actions, scoped OCR draw routing, and full-project `batch_auto_detect()` routing. The app still owns `_detect_pages(...)`, `auto_detect_current(...)`, OCR/detection workers, batch execution, PDIC/`.OCRed` persistence, and the heavy detection pipeline.

`ReviewController` owns OCR review candidate lookup/matching, lightweight review highlight/navigation state, and current/all-page headword-order report orchestration. `PictureCaptureApp.check_headword_order(...)` remains as a compatibility wrapper. The app still owns the generic batch runner, generic UI-worker runner, text-report window helper, current-page sort-key helpers, durable candidate edits, PDIC/manual-override writes, and the detailed translucent proofreading highlight renderer.

`pdic_restore.py` remains the deterministic low-level boundary for page-token lookup/resolution, merged-PDIC parsing, and one-page temporary-file + `os.replace(...)` atomic publication. PDIC field semantics and project path policy remain outside controllers.

## Last verified tests
- Phase 4V isolated focused suite: 184 passed
- Phase 4V isolated full suite: 1236 passed, 2 existing Pillow deprecation warnings
- `git diff --check`: passed
- compileall: passed
- Ruff F821: passed
- Phase 4V production code commit: `6d1f8456cc9c62ea096a428aabc2a0ae099923ea`
- Phase 4V fixed PR head: `292d99f0b5b86d9900651d676e3a7b8f2c1373af` (same production tree; empty user-authored commit used only to retrigger standard PR CI after the validated production commit had been pushed by `github-actions[bot]`)
- PR #225 fixed-head CI: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- PR #225 fixed-head CodeQL / Advanced Security checks passed
- Phase 4V architecture merge commit: `77c6e4a5a056e59381fde4fcc7516f2f4c137aba`
- `main` merge-push CI after #225: Ubuntu / Windows / macOS all passed
- CodeQL after #225: Python and Actions analyses passed
- Previous `app.py` architecture size baseline after #223: 838,567 bytes; no new byte-size baseline was recorded for #225

Phase 4V validation history worth preserving for recovery:
- live revalidation started from the Phase 4U checkpoint `bf88f940eafd0a567370ab3e24f1c0e2c03bb02b`
- Phase 4U was already complete when work resumed; the user explicitly confirmed continuation from the post-4U architecture decision point
- the selected direction was the review/order-report domain because it was the narrowest remaining seam already matching an existing controller without expanding detection worker/persistence ownership or entering Phase 5
- the existing regression suite required all-page order checking to remain serialized through the app-owned generic batch runner and to keep the batch busy state until `headword-order-finalize` completes
- the first isolated validation attempt stopped at `git diff --check` because the temporary patch helper emitted one trailing blank line in `review.py`; production semantics were not implicated
- the next isolated attempt reached the focused suite and reported 183 passed / 1 failed; the sole failure was a stale source-shape assertion still looking for `self._start_batch_task(...)` after ownership moved to `ReviewController`
- the ownership assertions were corrected to the new controller shape without changing production behavior
- final isolated validation passed: focused suite 184 passed; full suite 1236 passed with the same 2 existing Pillow deprecation warnings; compileall and Ruff F821 passed
- temporary isolated-validation workflow/script were removed before final PR review
- final net diff from the Phase 4U checkpoint contained exactly 4 expected files: `src/picture_capture/app.py`, `src/picture_capture/ui/controllers/review.py`, `tests/test_next_stage_regressions.py`, and `tests/test_ui_review_controller.py`
- no PR review threads or review objections were present before merge

## Completed Phase 4V seam
`PictureCaptureApp.check_headword_order(all_pages=False)` remains as a compatibility wrapper and delegates to `ReviewController.check_headword_order(...)`.

The controller preserves exactly:
- the existing `guard()` and `save_pdic(silent=True)` entry behavior
- separate current-page and all-page report paths
- all-page snapshots of sort mode, OCR language, custom order, and accent-folding settings before worker execution
- PDIC reads through `read_pdic(pdic_path(page))`
- the app-owned generic batch runner and the existing `"所有词头顺序核对"` batch identity
- background finalization through the app-owned generic UI-worker runner and the existing `"headword-order-finalize"` identity
- the existing batch-busy protection until report finalization finishes
- adjacent-inversion detection, sorted-position mismatch counting, and the 200-item report display cap
- early-stop reporting and completed/total-page suffixes
- project-identity checking before publishing all-page results
- current-page ordering through the existing app-owned `_order_key(...)` / `_order_display_key(...)` helpers
- the existing message/report/status/error presentation behavior

Phase 4V did not move headword-fill workflows, `batch_ocr()`, `auto_detect_current(...)`, `_detect_pages(...)`, OCR/detection workers, `.OCRed`/PDIC persistence, generic batch/UI-worker infrastructure, runtime-installed methods, or Phase 5 work.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

Training package export is installed onto `PictureCaptureApp` during GUI bootstrap from `training_export_ui.export_training_package_selected_range`; do not treat that runtime-installed extension as an ordinary app-body controller seam during Phase 4.

## Revalidation after Phase 4V
After Phase 4V merge-push verification:
- live architecture merge on `main` is `77c6e4a5a056e59381fde4fcc7516f2f4c137aba`
- `check_headword_order()` is now routed through `ReviewController`, while the generic batch/UI-worker/report infrastructure remains app-owned
- the review/order-report direction selected after Phase 4U is therefore complete
- the remaining adjacent detection methods are materially heavier than the completed action-entry seams:
  - `auto_detect_current(...)` is the app-owned single-page worker/batch bridge and ends in app-owned `_start_batch_task(...)`
  - `batch_ocr()` owns transformed-geometry guarding, project-wide PDIC filtering, destructive confirmation, OCR worker logic, `.OCRed` export, PDIC writes, done aggregation, and the app-owned batch runner
- `select_existing_headwords_file()` / `fill_existing_headwords()` remain a separate headword-fill domain involving source-file selection, parsed-source caching/signature invalidation, repeated range fills, PDIC updates, and persisted fill-status state; choosing an existing controller versus a dedicated headword-fill controller remains a material architecture decision
- entering Phase 5 to remove runtime installers remains a milestone transition and always requires explicit human confirmation

## Next-step decision point
Automatic controller decomposition is paused after Phase 4V because the remaining routes again require materially different ownership decisions rather than a uniquely narrow mechanical continuation.

Reasonable next directions are:
1. **Headword-fill domain** — decide controller ownership for `select_existing_headwords_file()` / `fill_existing_headwords()` before moving code. A dedicated controller is plausible, but adding one is an architecture choice.
2. **Detection batch-processing boundary** — move `batch_ocr()` and/or later `auto_detect_current()` toward `DetectionController`. This would deliberately expand that controller beyond action-entry routing into worker/persistence orchestration, so it is not an ownership-only continuation.
3. **Phase 5 runtime-patch cleanup** — remove runtime-installed ownership seams such as `ordinary_action_runtime`; this is a milestone transition, not Phase 4 auto-continuation.

Do not select among these directions automatically. Human confirmation is required before the next production-code write.

Before the next write, revalidate live `main`, open PRs, the selected method bodies/callers/UI bindings, runtime ownership, and dependency ownership.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Phase 4V is complete and recoverable. Automatic production-code continuation is paused at the architecture decision point above.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
