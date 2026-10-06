# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: always revalidate `main`, open PRs, relevant callers/import order, and tests before new production writes.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5K are complete.**

Phase 4 controller decomposition is complete through Detection batch processing. Phase 5 has retired runtime ownership from ordinary drawing, selected-scope single-line crop, unlined export, training export, helper-only ordinary-action debt, LayoutRows visualization capture, local-indent visualization replacement, role-provenance decoration, and indent-visibility decoration.

## Latest architecture checkpoint
- Phase 5K PR: **#252 — make indent visibility explicit**
- Phase 5K validated production commit: `88e7d969a7014e3890088da34a45f8ceedcc83f3`
- Phase 5K validated/merged production tree: `19c32f34a2a8f4f6a47dbce20b0df8c3dae09a4b`
- Phase 5K architecture merge: `2bfedcb17e9058d1b4fd2f8749a6db9690f95592`
- Previous Phase 5J PR #250 merge: `d56456047c51f97e2a2f929dfdab8c77df3db43c`
- Phase 5I PR #248 merge: `78c956177ebf9b580f66b3593494d286eed4c9ff`
- Phase 5H PR #246 merge: `d00df0bff2b3da947607310ea331b09b678f688d`
- Phase 5G PR #244 merge: `de04953752d0294e838b3ac45ae9a0f5ee9a3548`
- Phase 5F PR #242 merge: `f62f056a51fddae4c05fbd7bc93261330dac2db6`
- Phase 5E PR #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.
- Current production architecture PR: none after Phase 5K merge.

## Current explicit ownership
Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection / ordinary drawing
`PictureCaptureApp.run_normal_draw_action()` delegates to `DetectionController.run_normal_draw_action()`. OCR-independent quick validation lives in non-runtime `ordinary_quick_settings.py`; `ordinary_action_runtime.py` is retired.

### Crop / single-line and unlined export
Selected-scope single-line and unlined actions are explicit app-wrapper → CropController → app-owned `_start_parallel_batch_task(...)` paths. Historical single-line/unlined UI/private-scheduler runtimes are retired.

`unlined_fast_path_runtime` remains intentionally because it is a real worker/performance import-order seam. CropController resolves `unlined_line_export.export_unlined_page_job` from the module at action time so the installed fast worker remains visible.

### Export / training package
`PictureCaptureApp.export_training_package()` delegates to `ExportController.export_training_package()` and reuses app-owned batch/UI-worker infrastructure. GUI bootstrap no longer replaces the method dynamically.

### Layout visualization after Phase 5H–5K
- LayoutRows capture is static in `layout_visualization_shared.shared_snapshot_for_app(...)`; `layout_visualization_rows_cache_runtime.py` is retired.
- Drift-corrected indent geometry lives in non-runtime `layout_local_indent_visualization.py`; `layout_local_indent_visualization_runtime.py` is retired.
- Entry-source provenance lives in non-runtime `layout_role_provenance.py`; `layout_role_provenance_runtime.py` is retired.
- Visible indent drawing and prepared-count diagnostics live in non-runtime `layout_indent_visibility.py`; `layout_indent_visibility_runtime.py` is retired.
- `layout_visualization_summary._draw_indent_blocks` is statically bound to the visible renderer.
- The physical-lane summary wrapper appends `add_prepared_indent_summary(...)` last, preserving the historical final text order: base/provenance/role theme → physical lanes → `indent blocks prepared:`.

Current bootstrap no longer installs local-indent, provenance, or indent-visibility runtime decorators. `install_physical_lane_summary()` remains the final summary composition point.

## Completed Phase 5K — indent-visibility runtime retirement
### Production change
Phase 5K removed only the display-only indent-visibility installer while preserving behavior:
- renamed `layout_indent_visibility_runtime.py` to non-runtime `layout_indent_visibility.py`;
- preserved `prepared_indent_counts(...)` and `_draw_indent_blocks_visible(...)`;
- added pure `add_prepared_indent_summary(base_text, app)`;
- statically bound the visible renderer into `layout_visualization_summary`;
- removed the historical base renderer that lowered pale-yellow blocks beneath the base Layout tag;
- changed the existing physical-lane summary wrapper to append prepared-count diagnostics after lane diagnostics, matching the previous outermost runtime wrapper order;
- removed only the GUI bootstrap indent-visibility installer import/call;
- removed `layout_indent_visibility_runtime.py` from `LEGACY_RUNTIME_FILES`;
- migrated prior source-shape ordering assertions and added a direct integration regression proving `physical indent lanes:` precedes `indent blocks prepared:`.

No corrected-indent geometry, role provenance, lane clustering, detection/crop semantics, persistence format, worker/thread behavior, or public app action changed.

### Validation
Final isolated fail-closed validation:
- exact expected no-renames path set passed; GitHub rendered the runtime→non-runtime move as a rename, so the final PR displayed 8 changed files;
- architecture guard: passed;
- focused: **24 passed**;
- full: **1269 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication;
- validated production commit: `88e7d969a7014e3890088da34a45f8ceedcc83f3`;
- validated production tree: `19c32f34a2a8f4f6a47dbce20b0df8c3dae09a4b`.

PR #252 final-head verification:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility runner, compile, F821, and wheel passed on all applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- GitHub Advanced Security aggregate CodeQL: passed with no new alerts;
- Advanced Security AI findings: passed;
- no review threads or review objections before merge.

Architecture merge `2bfedcb17e9058d1b4fd2f8749a6db9690f95592` retained exactly the validated tree `19c32f34a2a8f4f6a47dbce20b0df8c3dae09a4b`.

Post-merge verification on that merge:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI smoke;
- macOS CI: passed, including GUI smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Recommended next slice — Phase 5L
**Retire helper-only `windows_gpu_runtime.py` naming debt without changing Paddle import timing.**

Fresh read-only inspection after Phase 5K shows `windows_gpu_runtime.py` contains no installer, monkey patch, UI mutation, worker replacement, persistence format, or dynamic app ownership. It is a call-time environment helper:
- `_site_package_roots()` enumerates site-package roots;
- `configure_windows_nvidia_dlls()` is a no-op off Windows;
- on Windows it discovers `site-packages/nvidia/*/bin`, prepends discovered paths to `PATH`, and retains `os.add_dll_directory(...)` handles so NVIDIA wheel DLLs remain visible to native consumers.

Current production callers explicitly invoke `configure_windows_nvidia_dlls()` immediately before Paddle/PaddleOCR import paths in:
- `ocr_channel.py`;
- `document_unwarping.py`;
- `layout_detection_legacy.py`.

`scripts/verify_ocr_environment.py` also imports/calls the helper, and OCR runner tests mock the current module path to assert configuration happens before OCR import.

The safest Phase 5L scope is therefore a behavior-neutral runtime→non-runtime module rename, e.g. `windows_gpu_runtime.py` → `windows_gpu.py`, with all callers/scripts/tests updated to the new path and the retired runtime filename removed from `LEGACY_RUNTIME_FILES`. Keep every `configure_windows_nvidia_dlls()` call at the exact same call site immediately before Paddle/PaddleOCR import; do not centralize or move it earlier/later.

Phase 5L validation must include Windows-specific CI and focused OCR runner/import-order tests in addition to the normal full suite/compile/F821/architecture guard. Do not combine it with Paddle dependency changes, OCR profile changes, spawn worker changes, `ordinary_large_head_runtime`, or `unlined_fast_path_runtime`.

## Remaining high-risk runtime seams after Phase 5K
Treat these as real compatibility/performance seams rather than mechanical naming debt until individually proven:
- `entry_classification_runtime.py`;
- `illustration_fill_opacity_runtime.py`;
- `layout_character_height_runtime.py`;
- `layout_column_drift_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `layout_row_recovery_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `overlay_line_anchor_runtime.py`;
- `overlay_opacity_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unicode_nonbmp_input_runtime.py`;
- `unlined_fast_path_runtime.py`;
- `windows_gpu_runtime.py` (helper-only candidate for Phase 5L).

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint after fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
