# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4O is complete.

## Architecture checkpoint
- Last completed architecture PR: #211 — illustration crop runner orchestration routed through `IllustrationController`
- Last completed architecture merge commit: `f1e601218daf0f8fe3b2550ad387792aca4beb6b`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, and `_start_illustration_crop()`.

`.OCRed` serialization and crop algorithms stay in `processing`; project path policy stays in `project_storage`.

## Last verified tests
- Phase 4O pre-PR targeted suite: 217 passed
- Phase 4O pre-PR full suite: 1191 passed, 2 existing Pillow deprecation warnings
- PR #211 fixed head: `ce883270b89df3591d7eeb79cf0d8ad4bd1d7162`
- PR #211 CI at the fixed head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #211: Ubuntu / Windows / macOS all passed
- CodeQL after #211: Python and Actions analyses passed
- `app.py` architecture size baseline after #211: 863,932 bytes

Phase 4O validation history worth preserving for recovery:
- the first focused validation run reported 2 failures and 215 passes; both were source-shape assumptions from the Phase 4N boundary, not production behavior regressions
- one dedicated test expected the compatibility delegate immediately after the method signature even though the historical docstring remained; it was changed to inspect the complete wrapper method block
- `tests/test_core.py::test_v295_illustration_crop_button_uses_shared_crop_settings_before_running_batch` still sliced the crop-entry controller method through `detect_illustrations_selected_scope()`, which unintentionally included the newly moved Phase 4O runner; its block endpoint was narrowed to `_start_illustration_crop()`
- no production implementation change was made to resolve either test-only failure
- temporary isolated-validation workflow/scripts were removed before PR creation; the final net diff contained only 5 expected production/test files

## Completed Phase 4O seam
`PictureCaptureApp._start_illustration_crop(indices, config)` now remains as a compatibility wrapper and delegates to `IllustrationController._start_illustration_crop(indices, config)`.

The controller preserves:
- no-project no-op and exact batch-active status `已有批量任务正在运行，未启动插图切图。`
- `project` capture and `settings = replace(app.settings)` snapshot timing
- output directory `qt_root(project.root) / "PIC"`
- all crop-config fallbacks and per-page `special_pages` top/bottom overrides
- exact per-page payload order, including the app-owned `_ppp_read_path(page)` compatibility/path-policy boundary and `pdic_path(page)`
- `append_crop_log` / `append_illustration_crop_log` result logging and record-count return value
- error no-op and exact stopped/completed status strings with count aggregation
- the existing app-owned `_start_parallel_batch_task(...)` boundary, `split_illustrations_job` processing worker, item labels, and worker-count semantics
- Phase 4M illustration detection and Phase 4N selected-scope crop-entry behavior/UI binding

Only the action-owned `append_crop_log`, `append_illustration_crop_log`, and `split_illustrations_job` imports moved out of `app.py`; the processing worker/algorithm itself was not changed.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

## Current issue / architecture choice required
There is no failing implementation blocker, but automatic continuation is paused because live-source review after Phase 4O exposes multiple materially different controller-decomposition choices rather than one mechanical next seam.

The immediately adjacent production actions include at least:
- `build_picdic()`: a bounded PicDic package-build orchestration action using `build_picdic_package`, batch cancellation/status, and a completion dialog. It could plausibly be added to the existing `ExportController`, but it is also semantically a production/package-build action and could justify a separate production-oriented controller.
- `export_picdic_index()`: a larger streaming export action that is clearly export-oriented and could plausibly migrate to the existing `ExportController`, but it has different state/temporary-file semantics from current-page `.OCRed` import/export.

Because choosing between “extend `ExportController`”, “introduce a production/package controller”, or selecting a different existing app seam would establish the next architecture direction rather than perform a mechanical migration, the resumable-execution protocol requires human confirmation before Phase 4P production changes.

## Revalidation facts for the next decision
After Phase 4O merge-push verification:
- live `main` is `f1e601218daf0f8fe3b2550ad387792aca4beb6b`
- no open competing PR exists at revalidation time
- `IllustrationController` now owns illustration detection, selected-scope illustration crop entry, and illustration crop runner orchestration, while preserving app runner/path boundaries
- neighboring `build_picdic()` remains directly in `PictureCaptureApp` and currently performs `guard()`, batch-active short-circuit, foreground `save_pdic(silent=True)`, `build_picdic_package(...)` with cooperative stop, completion status/dialog, and `_start_batch_task(...)`
- neighboring `export_picdic_index()` also remains directly in `PictureCaptureApp` and is a distinct project-wide streaming export workflow
- no Phase 5 runtime-patch cleanup has begun

## Required next action
Human architecture choice is required before writing Phase 4P production code. Whichever choice is selected, revalidate live `main`, open PRs, exact source body/callers, runtime ownership, and dependency boundaries again before modifying code; keep the next phase to one narrow safe unit and repeat targeted/full/three-platform/merge-push/CodeQL validation.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Paused pending the architecture choice above. After confirmation, automatic continuation may resume one safe unit at a time under `RESUMABLE_EXECUTION_PROTOCOL.md`.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
