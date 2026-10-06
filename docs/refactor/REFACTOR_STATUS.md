# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: always revalidate `main`, open PRs, relevant callers/import order, and tests before new production writes.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5I are complete.**

Phase 4 controller decomposition is complete through Detection batch processing. Phase 5 has retired runtime ownership from ordinary drawing, selected-scope single-line crop, unlined export, training export, helper-only ordinary-action debt, LayoutRows visualization capture, and local-indent visualization replacement.

## Latest architecture checkpoint
- Phase 5I PR: **#248 — make local-indent visualization explicit**
- Phase 5I validated production commit: `251ec8b31c238029feeb9beaa4ef1e0fb7934fbc`
- Phase 5I validated/merged tree: `bdb12ad9631b50e22d222138f29d4027907c3f0e`
- Phase 5I merge commit / current architecture merge: `78c956177ebf9b580f66b3593494d286eed4c9ff`
- Previous Phase 5H PR #246 merge: `d00df0bff2b3da947607310ea331b09b678f688d`
- Phase 5G PR #244 merge: `de04953752d0294e838b3ac45ae9a0f5ee9a3548`
- Phase 5F PR #242 merge: `f62f056a51fddae4c05fbd7bc93261330dac2db6`
- Phase 5E PR #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.
- Current production architecture PR: none after Phase 5I merge.

## Current ownership and preserved seams
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection / ordinary drawing
`PictureCaptureApp.run_normal_draw_action()` delegates to `DetectionController.run_normal_draw_action()`. OCR-independent quick validation lives in non-runtime `ordinary_quick_settings.py`; `ordinary_action_runtime.py` is retired.

### Crop / single-line and unlined export
Selected-scope single-line and unlined actions are explicit app-wrapper → CropController → app-owned `_start_parallel_batch_task(...)` paths. The historical single-line/unlined UI/private-scheduler runtimes are retired.

`unlined_fast_path_runtime` remains intentionally because it is a real worker/performance import-order seam. CropController resolves `unlined_line_export.export_unlined_page_job` from the module at action time so the installed fast worker remains visible.

### Export / training package
`PictureCaptureApp.export_training_package()` delegates to `ExportController.export_training_package()` and reuses app-owned batch/UI-worker infrastructure. GUI bootstrap no longer replaces the method dynamically.

### Layout visualization after Phase 5H/5I
LayoutRows capture is static in `layout_visualization_shared.shared_snapshot_for_app(...)`, wrapping `_shared_snapshot_for_app_impl(...)` in `capture_layout_rows(...)` only for valid project/page/settings context. `layout_visualization_rows_cache_runtime.py` is retired.

The local-indent corrected-block algorithm now lives in non-runtime `layout_local_indent_visualization.py` as `drift_corrected_indent_blocks(...)`. `layout_visualization_shared._indent_blocks_from_understanding` is statically bound to that exact function object. `layout_local_indent_visualization_runtime.py` and its GUI installer are retired.

Role provenance is still installed afterward and therefore continues to wrap the corrected-indent function. Bootstrap currently preserves:

`install_shared_layout_visualization_source()` → `install_layout_role_provenance()` → later role-theme / visualization-v3 / physical-lane-summary / indent-visibility decorators.

## Completed Phase 5I — local-indent visualization runtime retirement
### Production change
Phase 5I kept the corrected-indent algorithm unchanged while making ownership explicit:
- renamed `layout_local_indent_visualization_runtime.py` to non-runtime `layout_local_indent_visualization.py`;
- removed the installer function and GUI bootstrap import/call;
- statically bound shared `_indent_blocks_from_understanding` to `drift_corrected_indent_blocks`;
- preserved role-provenance as the later wrapper;
- removed the retired runtime filename from `LEGACY_RUNTIME_FILES`;
- migrated dedicated behavior/source-shape tests.

### Fail-closed validation
The first effective focused run produced **14 passed / 1 failed**. The only failure was a stale Phase 5H source-shape assertion still requiring `install_local_indent_visualization()` in bootstrap. Corrected-indent behavior tests were already green and no production tree was published from the failed run. Only that historical ownership assertion was migrated.

Final isolated validation:
- architecture guard: passed;
- focused: **15 passed**;
- full: **1263 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration/assertion helpers and validation workflow removed before publication;
- final net diff against the Phase 5H checkpoint: exactly 6 files, including a runtime→non-runtime rename.

PR #248 final-head verification:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility runner, compile, F821, and wheel passed on applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security: passed;
- no review threads or review objections before merge.

Architecture merge `78c956177ebf9b580f66b3593494d286eed4c9ff` retained exactly the validated tree `bdb12ad9631b50e22d222138f29d4027907c3f0e`.

Post-merge verification:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI smoke;
- macOS CI: passed, including GUI smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Recommended next slice — Phase 5J
**Retire `layout_role_provenance_runtime.py` as a pure diagnostic decorator installer.**

Fresh read-only inspection after Phase 5I shows the runtime owns only two diagnostic wrappers:
1. `shared._indent_blocks_from_understanding` → annotate entry/headword blocks with `entry_source` from `get_layout_line_classification(...)`;
2. `layout_visualization_summary._format_summary` → insert an `entry sources: ...` line based on those block annotations.

It owns no worker, thread, widget, persistence format, or public app action.

Important ordering constraint: provenance is currently the **innermost summary decorator**. Later GUI bootstrap installs `layout_visualization_role_theme`, `layout_lane_summary_extension`, and finally `layout_indent_visibility_runtime`, all of which may wrap `summary._format_summary`. Phase 5J must preserve this order exactly.

Recommended implementation:
- move provenance block/summary decorator functions to a non-runtime module or static module-level composition;
- make shared corrected-indent blocks statically provenance-aware without changing block matching/defaults;
- make the base summary statically include the exact provenance line before later summary wrappers run;
- remove only `install_layout_role_provenance()` and its bootstrap import/call;
- ratchet `layout_role_provenance_runtime.py` out of `LEGACY_RUNTIME_FILES`;
- preserve later role-theme / lane-summary / indent-visibility wrappers unchanged;
- add focused tests for entry-source annotation, ordering/insertion point, unknown/custom source ordering, no-count fallback, and later-wrapper compatibility.

Do not combine Phase 5J with `layout_indent_visibility_runtime`, `unlined_fast_path_runtime`, `ordinary_large_head_runtime`, spawn/detection runtimes, or other core import-order work.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint after fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
