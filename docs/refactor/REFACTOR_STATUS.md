# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and relevant source/runtime/test paths before new production writes. Historical SHAs below are checkpoints, not assumptions about a future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5H are complete.**

Phase 4 controller decomposition is complete through Detection batch processing. Phase 5 has progressively removed runtime method/UI/worker ownership from ordinary drawing, selected-scope single-line crop, unlined-line export, training-package export, helper-only ordinary-action debt, and LayoutRows visualization capture.

## Architecture checkpoint
- Current architecture merge: **Phase 5H PR #246**
- Phase 5H merge commit: `d00df0bff2b3da947607310ea331b09b678f688d`
- Phase 5H validated production commit: `5c7fcb97df5381583f61bd6ea0d52c1358378dfa`
- Phase 5H validated/merged tree: `afd9a854090d91f62e25a70411979f38d981d823`
- Phase 5G PR #244 — retired helper-only `ordinary_action_runtime.py`
- Phase 5G merge: `de04953752d0294e838b3ac45ae9a0f5ee9a3548`
- Phase 5F PR #242 — routed training export through `ExportController`
- Phase 5F merge: `f62f056a51fddae4c05fbd7bc93261330dac2db6`
- Phase 5E PR #240 — retired unlined export runtime installer
- Phase 5D PR #238 — routed single-line export through shared parallel batch runner
- Phase 5C PR #236 — normal UI ownership for single-line action
- Phase 5B PR #234 — explicit selected-scope single-line method ownership
- Phase 5A PR #232 — retired ordinary-action method monkey patch
- Phase 4Y PR #230 — `auto_detect_current(...)` through `DetectionController`
- Phase 4X PR #229 — `batch_ocr()` through `DetectionController`
- Current production architecture PR: none after Phase 5H merge

## Current explicit ownership
Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection / ordinary drawing
`PictureCaptureApp.run_normal_draw_action()` is an explicit compatibility wrapper into `DetectionController.run_normal_draw_action()`.

OCR-independent quick-setting validation now lives in non-runtime `ordinary_quick_settings.py`. `ordinary_action_runtime.py` no longer exists. DetectionController and CropController share `_apply_quick_settings_for_ordinary(...)` without changing the all-OCR-off behavior.

### Crop / selected-scope single-line
Explicit path:

`PictureCaptureApp.split_single_lines_selected_scope()` → `CropController.split_single_lines_selected_scope()` → app-owned `_start_parallel_batch_task(...)` → `single_line_parallel.single_line_page_job(...)`.

The action no longer owns runtime method injection, runtime UI construction, or a private thread/queue/Tk-poll scheduler.

### Crop / unlined-line export
Explicit path:

`PictureCaptureApp.export_unlined_rows_selected_scope()` → `CropController.export_unlined_rows_selected_scope()` → app-owned `_start_parallel_batch_task(...)` → runtime-resolved `unlined_line_export.export_unlined_page_job(...)`.

`unlined_fast_path_runtime` remains intentionally separate because it is a real worker/performance import-order seam. Keep resolving `unlined_export.export_unlined_page_job` from the module at action time until that seam gets its own dedicated proof.

### Export / training-package export
Explicit path:

`PictureCaptureApp.export_training_package()` → `ExportController.export_training_package()` → app-owned `_start_batch_task(...)`, with stopped-export cleanup through app-owned `_start_ui_worker(...)`.

GUI bootstrap no longer replaces the app method dynamically. `training_export_ui.export_training_package_selected_range()` is only a compatibility shim. Archive/manifest semantics and training-v3/page-understanding wrappers are unchanged.

### Layout visualization / LayoutRows capture after Phase 5H
The LayoutRows capture wrapper is now explicit and static in `layout_visualization_shared.py`:

`shared_snapshot_for_app(app)` → `capture_layout_rows(project_root, current image, current index, app.settings)` → `_shared_snapshot_for_app_impl(app)`.

This preserves the former live runtime contract:
- missing project → call the snapshot implementation directly;
- malformed/current-page index lookup → direct fallback;
- out-of-range page → direct fallback;
- missing `app.settings` → direct fallback;
- valid context → capture uses persisted/project `app.settings` as the cache identity while the internal snapshot implementation remains free to derive page-effective settings.

`layout_visualization_rows_cache_runtime.py` has been removed. GUI bootstrap no longer imports or installs it. The later visualization decorator order remains:

`install_shared_layout_visualization_source()` → `install_local_indent_visualization()` → `install_layout_role_provenance()`.

A separate older compatibility function, `layout_rows_cache.install_layout_visualization_cache_context()`, remains untouched. It has no repository callers, is exported in `__all__`, and differs semantically by using effective settings plus broad exception fallback. Phase 5H deliberately did not bundle a compatibility API deletion.

## Completed Phase 5H — static LayoutRows visualization capture
### Live assessment
The active `layout_visualization_rows_cache_runtime` was only a one-layer wrapper around `layout_visualization_shared.shared_snapshot_for_app(...)`; it owned no app method, worker, thread, widget, file format, or scheduler.

Read-only inspection also found the older `layout_rows_cache.install_layout_visualization_cache_context()` compatibility function. Because it is exported and not exactly equivalent to the active runtime wrapper, it was left unchanged rather than silently deleted.

### Production change
Phase 5H changed exactly six production/test paths:
- `layout_visualization_shared.py` — current body split into `_shared_snapshot_for_app_impl(...)`; public `shared_snapshot_for_app(...)` statically owns the exact active capture routing;
- `bootstrap/gui.py` — removed only the rows-cache visualization runtime import/install call;
- `layout_visualization_rows_cache_runtime.py` — removed;
- `scripts/architecture_guard.py` — ratcheted the retired runtime filename out of `LEGACY_RUNTIME_FILES`;
- `tests/test_processing_layout_roles.py` — source-shape assertion migrated to inspect the implementation plus public capture wrapper;
- `tests/test_layout_visualization_rows_capture.py` — added focused valid-context/fallback/order tests.

No worker, output/file format, unlined fast path, ordinary-large-head path, local-indent behavior, or role-provenance behavior changed.

### Validation
Isolated validation:
- diff shape: exact six-file surface;
- architecture guard: passed;
- focused: **27 passed**;
- full: **1262 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication.

PR #246 final-head verification:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility runner / compile / F821 / wheel passed on all applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security: passed;
- no review threads or review objections before merge.

Architecture merge `d00df0bff2b3da947607310ea331b09b678f688d` retained exactly the validated tree `afd9a854090d91f62e25a70411979f38d981d823`.

Post-merge verification:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI smoke;
- macOS CI: passed, including GUI smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous Phase 5 validation summary
- 5A: ordinary runtime method replacement retired; focused 206 / full 1248.
- 5B: selected-scope single-line method ownership explicit; focused 234 / full 1250.
- 5C: single-line UI/bootstrap monkey-patch retired; focused 259 / full 1250.
- 5D: single-line private scheduler retired for `_start_parallel_batch_task(...)`; focused 248 / full 1252.
- 5E: unlined UI/action/private scheduler retired; focused 658 / full 1256.
- 5F: training export moved to ExportController; focused 228 / full 1259.
- 5G: helper-only ordinary runtime renamed to non-runtime helper and debt ratcheted; focused 226 / full 1259.

## Recommended next slice — Phase 5I
**Retire the local-indent visualization installer while preserving its pure corrected-indent function.**

Fresh read-only inspection after Phase 5H shows:
- `layout_local_indent_visualization_runtime.py` contains one pure function, `drift_corrected_indent_blocks(...)`, plus one installer that replaces `layout_visualization_shared._indent_blocks_from_understanding`;
- the installer is called only once from GUI bootstrap;
- the pure function has dedicated behavior coverage in `tests/test_layout_local_indent_visualization_runtime.py`;
- `layout_role_provenance_runtime` is installed afterward and deliberately captures/wraps whatever `_indent_blocks_from_understanding` exists at that point.

Recommended Phase 5I architecture:
1. preserve `drift_corrected_indent_blocks(...)` in a non-runtime module (rename rather than rewrite where possible);
2. make `layout_visualization_shared` statically use that corrected-indent function as `_indent_blocks_from_understanding`;
3. remove only the local-indent installer/import/call from GUI bootstrap;
4. ratchet `layout_local_indent_visualization_runtime.py` out of `LEGACY_RUNTIME_FILES`;
5. update its dedicated behavior test to the non-runtime module and add source/order assertions proving role-provenance still wraps the corrected helper afterward;
6. do not combine Phase 5I with role-provenance, unlined fast path, ordinary-large-head, or core detector import-order work.

## Standing continuation authorization
The user has explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at each normal ownership decision point.

Continue automatically after successful checkpoints after freshly revalidating live `main`, open PRs, callers/import order, and relevant tests.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or an irreversible compatibility deletion whose impact cannot be established.
