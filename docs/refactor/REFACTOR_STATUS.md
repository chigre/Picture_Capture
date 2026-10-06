# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before new production writes, revalidate `main`, open PRs, relevant callers/import order, and tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5O are complete.**

Phase 4 controller decomposition is complete. Phase 5 has progressively replaced dynamic installer/runtime ownership with explicit/static ownership while preserving current behavior.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5O
- PR: **#260 — make line opacity explicit**
- validated production commit: `1f32b244d35e683dac4eff2d788358189fc352f9`
- validated/merged production tree: `830aeeed2fa65f55b2ce7c47f315107e99cf48e9`
- architecture merge: `a5e10ff348696f4ae8d755837e5e2a33dad68b08`
- previous Phase 5N PR #258 merge: `d1d63ea7d8d37efc78a7f90f1154cc10edab996d`
- previous Phase 5M PR #256 merge: `95bdb9b9d93df17922da2d5fbc43d4e9b5f781e5`
- previous Phase 5L PR #254 merge: `c78d1217fe8fa82ee85100a6409b58a09ee68d1a`
- previous Phase 5K PR #252 merge: `2bfedcb17e9058d1b4fd2f8749a6db9690f95592`
- Phase 5J #250, 5I #248, 5H #246, 5G #244, 5F #242, 5E #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.

### Explicit line-opacity ownership
The former `overlay_opacity_runtime.py` installer is gone.

Line opacity now has ordinary static ownership:
- `guide_opacity` and `headword_marker_opacity` are native `AppSettings` dataclass fields;
- both retain the established 40% default and immediate 0–100 assignment clamping;
- native settings JSON persistence carries the fields, while older projects that do not contain them fall back to 40%;
- Settings Center labels/help/units/spin metadata live in `ui/settings/schema.py`;
- guide/marker quick opacity controls are constructed directly during normal app UI build, with no `PictureCaptureApp.__init__` wrapper;
- non-runtime `overlay_opacity.py` owns true-alpha line rendering, opacity normalization, quick-control construction, and alpha-image lifetime helpers;
- the real guide and marker draw sites call `create_alpha_canvas_line(...)` directly instead of temporarily replacing `canvas.create_line`;
- redraw and per-entry removal explicitly clear/release retained Pillow images;
- Phase 5N one-sided line anchoring remains shared for 100%, 0%, and semi-transparent branches.

`illustration_fill_opacity_runtime.py` deliberately remains a separate seam. Phase 5O changed only its dependency on the retired line-opacity runtime: it now consumes ordinary helpers from `overlay_opacity.py`; its own property/JSON/UI/rendering installer behavior remains intact.

## Phase 5O validation
Isolated fail-closed validation on the exact production tree:
- exact intended no-renames path set: passed;
- architecture guard: passed;
- focused: **21 passed, 1 Pillow deprecation warning**;
- full: **1275 passed, 1 Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helpers/workflow removed before publication.

The first isolated characterization run intentionally blocked publication because a native field initially lost the former runtime property's immediate assignment-clamping behavior. Phase 5O therefore retained that compatibility contract through native `AppSettings` assignment normalization before the final validation run. No failed intermediate production tree was published.

Focused coverage proves:
- line opacity remains clamped to 0–100 at construction and later assignment;
- native JSON round-trip and old-project 40% fallback are preserved;
- 100% native Canvas, hidden 0%, and semi-transparent RGBA branches keep the same one-sided coordinates;
- alpha-photo lifetime cleanup remains explicit;
- Settings Center and quick controls have static ownership;
- GUI bootstrap no longer imports or installs `overlay_opacity_runtime.py`.

PR #260 fixed-head gate on `1f32b244d35e683dac4eff2d788358189fc352f9`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility / compile / F821 / wheel: passed on all three platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- no review threads or review objections.

Architecture merge `a5e10ff348696f4ae8d755837e5e2a33dad68b08` retained exactly the validated production tree `830aeeed2fa65f55b2ce7c47f315107e99cf48e9`.

Post-merge verification on `main@a5e10ff348696f4ae8d755837e5e2a33dad68b08`:
- Ubuntu CI: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- Windows CI: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- macOS CI: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous Phase 5N note
Phase 5N retired `overlay_line_anchor_runtime.py`. One-sided marker-down / guide-right geometry now lives in non-runtime `overlay_line_anchor.py` and is consumed directly by the static opacity renderer.

## Previous Phase 5M note
Phase 5M moved Windows/Tk supplementary Unicode repair into explicit `PictureCaptureApp` lifecycle ownership backed by non-runtime `unicode_nonbmp_input.py`.

## Previous Phase 5L note
`windows_gpu.py` is an ordinary non-runtime helper. `configure_windows_nvidia_dlls()` remains deliberately call-time immediately before Paddle/PaddleOCR imports where required.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper → `DetectionController`; OCR-independent quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper → `CropController` → app-owned shared parallel batch runner.
- Training package: app wrapper → `ExportController`; bootstrap no longer replaces the method.
- Layout visualization: LayoutRows capture, corrected indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are non-runtime/static ownership.
- Windows/Tk supplementary Unicode repair: explicit `PictureCaptureApp` lifecycle → non-runtime `unicode_nonbmp_input.py`.
- Overlay anchoring: non-runtime `overlay_line_anchor.py`.
- Guide/headword line opacity: native `AppSettings` + static settings schema + direct non-runtime `overlay_opacity.py` rendering/UI helpers.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5P
**Retire `illustration_fill_opacity_runtime.py` as the next narrow display-only seam.**

Fresh read-only inspection after Phase 5O shows it now owns a bounded surface:
1. compatibility storage for `illustration_fill_opacity` plus JSON wrappers, defaulting to 40%;
2. pure `render_alpha_polygon_overlay(...)` true-alpha rendering;
3. `_alpha_canvas_polygon(...)`, which keeps the editable Canvas polygon as the authoritative outline/hit target and places an RGBA fill image underneath for opacity below 100%;
4. `_refresh_polygon_fill(...)` when polygon geometry moves;
5. Settings Center metadata for illustration fill opacity;
6. one quick `区域不透明度` control installed by wrapping app initialization;
7. redraw interception by temporarily replacing `canvas.create_polygon`, plus a wrapper around `_update_polygon_canvas_geometry`.

It owns no OCR, PDIC, crop, Layout analysis, worker behavior, PPP coordinates, or illustration-detection semantics.

Safest Phase 5P architecture:
- make `illustration_fill_opacity` a native `AppSettings` field with the existing 40% default and the same immediate 0–100 clamping contract as the two line-opacity fields;
- move its Settings Center metadata into the static settings schema;
- construct the quick `区域不透明度` control directly in the existing illustration-control row at the same final visual position;
- move polygon alpha rendering into ordinary non-runtime `illustration_fill_opacity.py` helpers;
- call the alpha-polygon helper directly at the real PPP illustration polygon draw site rather than overriding `canvas.create_polygon` during redraw;
- reset `_pc_alpha_polygon_records` directly at redraw start and refresh the stored fill image directly after `_update_polygon_canvas_geometry`;
- preserve 100% native fill, 0% transparent fill, semi-transparent RGBA rendering, polygon outline/hit target, z-order, tags, image lifetime, and live geometry refresh exactly;
- remove the no-longer-needed `configure_overlay_opacity_defaults()` compatibility shim, installer import/call, runtime module, and architecture-guard entry only after characterization passes.

Do **not** combine Phase 5P with Layout masking, ordinary-large-head logic, entry classification, spawn parity, or unlined fast-path work.

## Why Phase 5P is next
After Phase 5O, illustration-fill opacity is the narrowest remaining runtime seam and is almost entirely presentation/persistence plumbing. The alternatives are materially riskier:
- `ordinary_large_head_runtime.py` changes detection authorization and depends on column-drift/import-order behavior;
- `layout_character_height_runtime.py`, `layout_column_drift_runtime.py`, and `layout_row_recovery_runtime.py` modify Layout fallback algorithms;
- `layout_illustration_mask_runtime.py` affects Page Understanding input, AppSettings class setup, PPP detector binding, and visualization cache invalidation;
- `entry_classification_runtime.py` changes processing/OCR classification semantics;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py` are multiprocessing parity seams;
- `unlined_fast_path_runtime.py` is an import-order/performance seam.

## Remaining runtime seams after Phase 5O
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `illustration_fill_opacity_runtime.py` (recommended Phase 5P);
- `layout_character_height_runtime.py`;
- `layout_column_drift_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `layout_row_recovery_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
