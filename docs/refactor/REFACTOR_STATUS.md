# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before new production writes, revalidate `main`, open PRs, relevant callers/import order, and tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5N are complete.**

Phase 4 controller decomposition is complete. Phase 5 has retired runtime ownership from ordinary drawing, selected-scope single-line crop, unlined export, training export, helper-only ordinary-action debt, LayoutRows visualization capture, local-indent replacement, role-provenance decoration, indent-visibility decoration, the helper-only Windows GPU module name, the Windows/Tk non-BMP app lifecycle installer, and overlay line anchoring.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5N
- PR: **#258 — make overlay line anchoring explicit**
- validated production commit: `c0197db6c1ce12e0ab1239bb0ef9b75114753a13`
- validated/merged production tree: `bb977f4b41230ea8c7b64460a7d2158f16fb42fc`
- architecture merge: `d1d63ea7d8d37efc78a7f90f1154cc10edab996d`
- previous Phase 5M PR #256 merge: `95bdb9b9d93df17922da2d5fbc43d4e9b5f781e5`
- previous Phase 5L PR #254 merge: `c78d1217fe8fa82ee85100a6409b58a09ee68d1a`
- previous Phase 5K PR #252 merge: `2bfedcb17e9058d1b4fd2f8749a6db9690f95592`
- Phase 5J #250, 5I #248, 5H #246, 5G #244, 5F #242, 5E #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.

### Explicit overlay line anchoring
The former `overlay_line_anchor_runtime.py` installer is gone.

Pure one-sided geometry and idempotent Settings Center help augmentation now live in non-runtime `overlay_line_anchor.py`:
- headword-marker thickness grows downward from the stored top anchor;
- smooth guide thickness grows rightward from the stored left anchor;
- width 1 remains unchanged.

`overlay_opacity_runtime._alpha_canvas_line(...)` now applies this geometry directly before all opacity branches, so native 100% Canvas lines, hidden 0% lines, and semi-transparent Pillow overlays share the same coordinates.

Marker-opacity controls are created directly before `插图标签：外框`; the old second app-`__init__` wrapper that repacked them after construction is gone.

`overlay_opacity_runtime.py` deliberately remains for a separate slice because it still owns line-opacity persistence compatibility, Settings Center fields, quick controls, and alpha-rendering integration. Illustration-fill opacity ownership also remains unchanged.

## Phase 5N validation
Isolated fail-closed validation:
- exact intended no-renames path set: passed;
- architecture guard: passed;
- focused: **16 passed, 2 existing Pillow deprecation warnings**;
- full: **1277 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication.

Focused coverage proves:
- one-sided geometry is preserved for marker-down and guide-right growth;
- 100%, 0%, and semi-transparent opacity branches share the same anchored coordinates;
- Settings Center anchor help augmentation is idempotent;
- marker-opacity quick controls are constructed in their final order without a second app-init wrapper;
- GUI bootstrap no longer imports or installs `overlay_line_anchor_runtime.py`.

PR #258 validated production commit `c0197db6c1ce12e0ab1239bb0ef9b75114753a13` retained production tree `bb977f4b41230ea8c7b64460a7d2158f16fb42fc`.

Architecture merge `d1d63ea7d8d37efc78a7f90f1154cc10edab996d` retained exactly that validated tree `bb977f4b41230ea8c7b64460a7d2158f16fb42fc`.

Post-merge verification on `main@d1d63ea7d8d37efc78a7f90f1154cc10edab996d`:
- Ubuntu CI: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- Windows CI: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- macOS CI: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous Phase 5M note
Phase 5M moved Windows/Tk supplementary Unicode repair into explicit `PictureCaptureApp` lifecycle ownership backed by non-runtime `unicode_nonbmp_input.py`. Attach remains at the end of core `__init__`; close runs before `super().destroy()`. `unicode_nonbmp_input_runtime.py` is no longer legacy runtime debt.

## Previous Phase 5L note
`windows_gpu.py` is an ordinary non-runtime helper. `configure_windows_nvidia_dlls()` remains deliberately call-time immediately before Paddle/PaddleOCR imports in `ocr_channel.py`, `paddle_headwords_core.py`, `document_unwarping.py`, and `layout_detection_legacy.py`.

PR #254's separate Copilot/agentic `github-advanced-security` review failed before reviewing code because GitHub returned HTTP 402 monthly quota exceeded. That was an external service-quota failure, not a code/security finding. CodeQL Actions/Python and three-platform OCR Platform Smoke passed.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper → `DetectionController`; OCR-independent quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper → `CropController` → app-owned shared parallel batch runner.
- Training package: app wrapper → `ExportController`; bootstrap no longer replaces the method.
- Layout visualization: LayoutRows capture, corrected indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are non-runtime/static ownership.
- Windows/Tk supplementary Unicode repair: explicit `PictureCaptureApp` lifecycle → non-runtime `unicode_nonbmp_input.py`.
- Overlay line anchoring: non-runtime `overlay_line_anchor.py` geometry/help → `overlay_opacity_runtime._alpha_canvas_line(...)`; no separate renderer/app-init installer remains.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5O
**Retire `overlay_opacity_runtime.py` while leaving `illustration_fill_opacity_runtime.py` intact.**

Fresh read-only inspection on `main@d1d63ea` shows the line-opacity runtime now has a bounded ownership surface:
1. compatibility storage for `guide_opacity` and `headword_marker_opacity` plus JSON hooks;
2. Settings Center metadata for those two fields;
3. quick opacity controls in the guide/marker rows;
4. true-alpha rendering hooks for guide redraw and entry overlays, including `_pc_alpha_line_photos` cleanup;
5. the Phase 5N one-sided anchor helper call, which is already non-runtime.

It does **not** own OCR, PDIC, crop, detection, worker, Layout analysis, or stored geometry semantics.

Safest Phase 5O architecture:
- make `guide_opacity` and `headword_marker_opacity` native `AppSettings` dataclass fields with the current effective default of 40%, relying on the existing `asdict()` JSON contract instead of runtime properties/read-write wrappers;
- keep backward loading behavior for projects without those keys through dataclass defaults;
- move Settings Center field metadata and quick-control construction to ordinary static UI ownership instead of wrapping `PictureCaptureApp.__init__`;
- move guide/marker alpha rendering into an explicit non-runtime display helper called by the existing draw/redraw paths, rather than temporarily replacing `canvas.create_line` through an installer;
- preserve 100% native Canvas, 0% hidden, semi-transparent RGBA, z-order/photo lifetime, and Phase 5N one-sided geometry exactly;
- remove only `install_overlay_opacity_runtime(...)`, its GUI bootstrap import/call, and `overlay_opacity_runtime.py` from `LEGACY_RUNTIME_FILES` after characterization passes;
- keep `illustration_fill_opacity_runtime.py` and its current 40% shared default behavior out of this slice except for the minimum import/default adjustment required by removing line-opacity runtime ownership.

Do **not** combine Phase 5O with illustration-fill opacity, Layout runtime, spawn runtime, or crop fast-path cleanup. Those remain separate seams with different persistence/rendering/algorithm/process risk.

## Why Phase 5O is next
The remaining alternatives are materially riskier:
- `ordinary_large_head_runtime.py` contains real detection authorization and depends on the column-drift analysis band/import order;
- `layout_character_height_runtime.py`, `layout_column_drift_runtime.py`, and `layout_row_recovery_runtime.py` alter Layout fallback algorithms;
- `layout_illustration_mask_runtime.py` changes AppSettings class identity, Page Understanding input, PPP detector binding, and visualization cache behavior;
- `entry_classification_runtime.py` affects processing semantics;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py` are multiprocessing parity seams;
- `unlined_fast_path_runtime.py` is a performance/import-order seam.

Line opacity is therefore the narrowest remaining seam whose behavior is display-only and whose persistence surface can be characterized directly before migration.

## Remaining runtime seams after Phase 5N
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `illustration_fill_opacity_runtime.py`;
- `layout_character_height_runtime.py`;
- `layout_column_drift_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `layout_row_recovery_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `overlay_opacity_runtime.py` (recommended Phase 5O);
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
