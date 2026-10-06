# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before new production writes, revalidate `main`, open PRs, relevant callers/import order, and tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5M are complete.**

Phase 4 controller decomposition is complete. Phase 5 has retired runtime ownership from ordinary drawing, selected-scope single-line crop, unlined export, training export, helper-only ordinary-action debt, LayoutRows visualization capture, local-indent replacement, role-provenance decoration, indent-visibility decoration, the helper-only Windows GPU module name, and the Windows/Tk non-BMP app lifecycle installer.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5M
- PR: **#256 — make non-BMP input lifecycle explicit**
- validated production commit: `0fe87d17a2065a46d5ad7362154acd3d3ccbdfb3`
- validated/merged production tree: `88edf72559bf446a4ac555d270f35e27883c48b9`
- architecture merge: `95bdb9b9d93df17922da2d5fbc43d4e9b5f781e5`
- previous Phase 5L PR #254 merge: `c78d1217fe8fa82ee85100a6409b58a09ee68d1a`
- previous Phase 5K PR #252 merge: `2bfedcb17e9058d1b4fd2f8749a6db9690f95592`
- Phase 5J #250, 5I #248, 5H #246, 5G #244, 5F #242, 5E #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.

### Explicit non-BMP Unicode lifecycle
The Windows/Tk 8 compatibility implementation now lives in non-runtime `unicode_nonbmp_input.py`. The native IMM32/message-hook logic and repair planner are behavior-identical; only ownership changed.

`PictureCaptureApp` now owns the lifecycle explicitly:
- its core `__init__` ends with `attach_nonbmp_unicode_input(self)`;
- its explicit `destroy()` calls `close_nonbmp_unicode_input(self)` before `super().destroy()`.

This preserves the historical timing. The old installer was the first app `__init__` wrapper installed after importing `app`, so its post-init attach already ran immediately after core `PictureCaptureApp.__init__` returned and before later wrapper post-hooks.

The old `install_nonbmp_unicode_input(app_module)` bootstrap call is gone and `unicode_nonbmp_input_runtime.py` is removed from `LEGACY_RUNTIME_FILES`.

## Phase 5M validation
Isolated fail-closed validation:
- exact no-renames path set: passed;
- architecture guard: passed;
- focused: **12 passed**;
- full: **1273 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication.

Focused lifecycle coverage proves:
- non-Windows is no-op;
- Windows/Tk 8 requires the bridge;
- Windows/Tk 9 is no-op;
- attach is idempotent;
- close is idempotent;
- app owns attach/destroy explicitly;
- GUI bootstrap no longer installs the lifecycle dynamically.

PR #256 fixed-head gate on `0fe87d17a2065a46d5ad7362154acd3d3ccbdfb3`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including **Windows GUI smoke**;
- macOS CI: passed, including macOS GUI smoke;
- compatibility / compile / F821 / wheel: passed;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- GitHub Advanced Security workflow: passed;
- no review threads or review objections.

Architecture merge `95bdb9b9d93df17922da2d5fbc43d4e9b5f781e5` retained exactly validated tree `88edf72559bf446a4ac555d270f35e27883c48b9`.

Post-merge verification on that same tree:
- Ubuntu / Windows / macOS CI: passed;
- GUI smoke: passed on all applicable platforms;
- compatibility / compile / F821 / wheel: passed;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous Phase 5L note
`windows_gpu.py` is an ordinary non-runtime helper. `configure_windows_nvidia_dlls()` remains deliberately call-time immediately before Paddle/PaddleOCR imports in `ocr_channel.py`, `paddle_headwords_core.py`, `document_unwarping.py`, and `layout_detection_legacy.py`.

PR #254's separate Copilot/agentic `github-advanced-security` review failed before reviewing code because GitHub returned HTTP 402 monthly quota exceeded. That was an external service-quota failure, not a code/security finding. CodeQL Actions/Python and three-platform OCR Platform Smoke passed.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper → `DetectionController`; OCR-independent quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper → `CropController` → app-owned shared parallel batch runner.
- Training package: app wrapper → `ExportController`; bootstrap no longer replaces the method.
- Layout visualization: LayoutRows capture, corrected indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are non-runtime/static ownership.
- Windows/Tk supplementary Unicode repair: explicit `PictureCaptureApp` lifecycle → non-runtime `unicode_nonbmp_input.py`.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5N
**Retire `overlay_line_anchor_runtime.py` while leaving `overlay_opacity_runtime.py` persistence/UI ownership intact.**

Fresh read-only inspection after Phase 5M shows `overlay_line_anchor_runtime.py` owns three narrow behaviors:
1. pure `one_sided_line_coordinates(...)` geometry, making guide thickness grow right and marker thickness grow down;
2. a wrapper around `overlay_opacity_runtime._alpha_canvas_line` so both native 100% Canvas lines and semi-transparent Pillow overlays use the same one-sided geometry;
3. display-only UI polish: two Settings Center help suffixes and moving the marker-opacity control group before `插图标签：外框` after app init.

It owns no persistence schema, OCR/PDIC/crop/detection semantics, worker, file format, or project data.

Safest Phase 5N architecture:
- move `one_sided_line_coordinates(...)` and the control-order/help helpers to non-runtime `overlay_line_anchor.py`;
- make `overlay_opacity_runtime._alpha_canvas_line(...)` call the one-sided coordinate helper directly before either the 100% native Canvas path or the RGBA path, preserving identical anchoring at all opacities;
- have the existing overlay-opacity installer apply the anchor help text and control-order adjustment as part of the opacity surface it already owns, rather than installing a second renderer/init wrapper;
- remove only `install_overlay_line_anchor_runtime(...)` and its GUI bootstrap import/call;
- ratchet `overlay_line_anchor_runtime.py` out of `LEGACY_RUNTIME_FILES`;
- preserve current installer order for opacity and illustration fill;
- migrate `test_overlay_line_anchor_runtime.py` / opacity source-shape tests and add direct integration tests for 100%, semi-transparent, guide-right and marker-down geometry plus marker-opacity control ordering.

Do **not** retire `overlay_opacity_runtime.py` in the same slice: it still owns persisted compatibility properties, JSON hooks, Settings Center fields, quick controls, and alpha-rendering integration and needs a separate design.

## Remaining runtime seams after Phase 5M
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `illustration_fill_opacity_runtime.py`;
- `layout_character_height_runtime.py`;
- `layout_column_drift_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `layout_row_recovery_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `overlay_line_anchor_runtime.py` (recommended Phase 5N);
- `overlay_opacity_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
