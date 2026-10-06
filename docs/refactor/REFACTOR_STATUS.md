# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and the relevant source paths before writing production code. Historical SHAs below are checkpoints, not assumptions about a future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5G are complete.**

Phase 4 controller decomposition is complete through Detection batch processing. Phase 5 has progressively removed runtime method/UI/worker ownership from ordinary drawing, selected-scope single-line crop, unlined-line export, training-package export, and the now-helper-only ordinary-action runtime module.

## Architecture checkpoint
- Current `main` after Phase 5G architecture merge: `de04953752d0294e838b3ac45ae9a0f5ee9a3548`
- Last completed architecture PR: **#244 — Phase 5G: retire ordinary action runtime helper module**
- Phase 5G validated production commit: `854cb026d108887aceec2d5a3a59ffdebcc16cbf`
- Phase 5G validated/merged production tree: `055565f0d81f376636f1d8753308007c7eefe6d4`
- Previous Phase 5F PR: #242 — route training export through `ExportController`
- Phase 5F architecture merge: `f62f056a51fddae4c05fbd7bc93261330dac2db6`
- Phase 5E PR: #240 — retire unlined export runtime installer
- Phase 5D PR: #238 — route single-line export through shared batch runner
- Phase 5C PR: #236 — construct single-line action in normal UI
- Phase 5B PR: #234 — explicit selected-scope single-line method ownership
- Phase 5A PR: #232 — retire ordinary-action runtime monkey patch
- Phase 4Y PR: #230 — `auto_detect_current(...)` through `DetectionController`
- Phase 4X PR: #229 — `batch_ocr()` through `DetectionController`
- Current production architecture PR: none after Phase 5G merge

## Current explicit ownership
Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection / ordinary drawing
`PictureCaptureApp.run_normal_draw_action()` is an explicit compatibility wrapper into `DetectionController.run_normal_draw_action()`.

The OCR-independent quick-settings helper is now in `ordinary_quick_settings.py`. The historical `ordinary_action_runtime.py` file no longer exists. DetectionController and CropController import `_apply_quick_settings_for_ordinary(...)` from the non-runtime helper module.

The helper semantics remain unchanged: when all visible OCR engines are off, it temporarily satisfies the legacy quick-settings validator, then restores the user's exact all-off OCR selection before settings persistence or worker start.

### Crop / selected-scope single-line
Explicit path:

`PictureCaptureApp.split_single_lines_selected_scope()` → `CropController.split_single_lines_selected_scope()` → app-owned `_start_parallel_batch_task(...)` → `single_line_parallel.single_line_page_job(...)`.

The main action no longer owns runtime method injection, runtime UI construction, or a private thread/queue/Tk-poll loop.

### Crop / unlined-line export
Explicit path:

`PictureCaptureApp.export_unlined_rows_selected_scope()` → `CropController.export_unlined_rows_selected_scope()` → app-owned `_start_parallel_batch_task(...)` → runtime-resolved `unlined_line_export.export_unlined_page_job(...)`.

The visible postproduction row is constructed normally as:

`单行切图` → `未画线行导出` → `词条切图` → `插图切图`

`unlined_fast_path_runtime` remains intentionally separate because it is a real worker/performance import-order seam. `CropController` must continue resolving `unlined_export.export_unlined_page_job` from the module at action time so the installed fast worker remains visible.

### Export / training-package export
Explicit path:

`PictureCaptureApp.export_training_package()` → `ExportController.export_training_package()` → app-owned `_start_batch_task(...)`, with stopped-export cleanup through app-owned `_start_ui_worker(...)`.

GUI bootstrap no longer replaces the app method dynamically. `training_export_ui.export_training_package_selected_range()` remains only as a compatibility shim. Training archive/manifest format and the training-v3/page-understanding wrapper chain were unchanged in Phase 5F.

## Completed Phase 5G — ordinary helper runtime debt
### Live assessment
After Phase 5F, `ordinary_action_runtime.py` no longer contained any installer. Its production callers were only DetectionController and CropController, both consuming `_apply_quick_settings_for_ordinary(...)`. The file therefore represented naming/architecture debt rather than a runtime-patch seam.

### Production change
Phase 5G was deliberately narrow:
- 100% rename `src/picture_capture/ordinary_action_runtime.py` → `src/picture_capture/ordinary_quick_settings.py`;
- DetectionController and CropController imports updated to the new helper module;
- source-shape tests updated to require the old runtime path to be absent while preserving the helper contract;
- `ordinary_action_runtime.py` removed from `scripts/architecture_guard.py::LEGACY_RUNTIME_FILES`.

No bootstrap installer, worker behavior, quick-setting semantics, output format, public action path, or controller ownership changed.

### Fail-closed validation history
- isolated run 1 stopped at diff-shape because Git represented the identical-content delete/add as a rename; no behavior tests or publication ran;
- diff-shape was corrected to use `git diff --no-renames --name-only`;
- isolated run 2 passed diff-shape and architecture guard, then produced **225 passed / 1 failed** in focused tests; the only failure was a stale source-shape test that still opened the intentionally deleted `ordinary_action_runtime.py` path; no publication ran;
- only that ownership assertion was migrated;
- isolated run 3 passed completely.

Final isolated validation:
- architecture guard: passed;
- focused: **226 passed**;
- full: **1259 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication;
- validated production commit: `854cb026d108887aceec2d5a3a59ffdebcc16cbf`;
- net diff against the Phase 5F checkpoint was exactly 6 files: one 100% rename, two controller import edits, two test ownership edits, and one architecture-baseline deletion.

PR #244 final-head verification:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility runner, compile, F821, and wheel build passed on all applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security: passed;
- no review threads or review objections before merge.

Architecture merge: `de04953752d0294e838b3ac45ae9a0f5ee9a3548`.
The merge tree remained exactly `055565f0d81f376636f1d8753308007c7eefe6d4`, matching the validated production tree.

Post-merge verification on `de04953752d0294e838b3ac45ae9a0f5ee9a3548`:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI smoke;
- macOS CI: passed, including GUI smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous Phase 5 validation summary
- Phase 5A: ordinary runtime method replacement retired; focused 206, full 1248.
- Phase 5B: selected-scope single-line method ownership explicit; focused 234, full 1250.
- Phase 5C: single-line UI/bootstrap monkey-patch retired; focused 259, full 1250.
- Phase 5D: single-line private scheduler retired in favor of `_start_parallel_batch_task(...)`; focused 248, full 1252.
- Phase 5E: unlined UI/action/private scheduler retired, historical modules removed and runtime debt ratcheted; focused 658, full 1256.
- Phase 5F: training-package method assignment removed and orchestration moved to ExportController; focused 228, full 1259. Its first fully validated publication exposed a staging-command bug and was not promoted; the same tree was rerun and published cleanly before PR #242.

## Recommended next slice — Phase 5H
**Static LayoutRows capture for Layout visualization.**

Fresh read-only inspection after Phase 5G shows `layout_visualization_rows_cache_runtime.py` is a narrow single-function wrapper around `layout_visualization_shared.shared_snapshot_for_app(...)`:
- it does not patch an app method;
- it does not own a thread, worker, file format, or widget;
- it wraps the shared snapshot call in `capture_layout_rows(project_root, image_path, page_index, settings)` when project/page/settings are available;
- bootstrap currently installs this wrapper immediately before `install_shared_layout_visualization_source()` publishes the shared snapshot into the UI.

Recommended Phase 5H architecture:
1. preserve the exact outer-wrapper semantics inside `layout_visualization_shared.py` itself, ideally by separating the current body into an internal implementation and keeping `shared_snapshot_for_app(...)` as the capture-aware public entry;
2. remove `layout_visualization_rows_cache_runtime.py` and its GUI bootstrap installer/import;
3. ratchet that runtime filename out of `LEGACY_RUNTIME_FILES`;
4. add focused behavior tests proving the capture context receives project root, selected image, current index, and persisted app settings, while invalid project/page/settings cases still fall back safely;
5. preserve the current later visualization ordering: shared source publication, local-indent replacement, and role-provenance decoration must behave identically;
6. do not combine this with `layout_local_indent_visualization_runtime.py`, `layout_role_provenance_runtime.py`, `unlined_fast_path_runtime.py`, or ordinary-large-head/core import-order cleanup.

`ordinary_large_head_runtime.py` is explicitly not the next target: it is installed in core before Layout Core imports detector callables by value and therefore has a materially stronger import-order constraint.

## Standing continuation authorization
The user has explicitly authorized continued Phase 5 work along the recommended architecture path without pausing for confirmation at each normal ownership decision point.

Continue automatically after each successful checkpoint after freshly revalidating live `main`, open PRs, callers, import-order/runtime ownership, and relevant tests.

Stop production writes only for a genuine anomaly such as:
- unexplained behavior/test/CI failure;
- file-format, archive/output, or public API change outside the approved slice;
- merge conflict or concurrent architecture work;
- checkpoint/live-state mismatch;
- materially large cross-core-module redesign;
- a safety-critical or irreversible compatibility deletion whose impact cannot be established from tests/live inspection.

Source-shape assertions that are demonstrably stale after an intended ownership move may be migrated without pausing, provided behavior tests remain green and publication stays fail-closed.
