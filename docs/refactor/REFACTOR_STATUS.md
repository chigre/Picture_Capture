# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before new production writes, revalidate `main`, open PRs, relevant callers/import order, and tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5P are complete.**

Phase 4 controller decomposition is complete. Phase 5 has progressively replaced dynamic installer/runtime ownership with explicit/static ownership while preserving current behavior.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5P
- PR: **#262 — make illustration fill opacity explicit**
- validated production commit: `489c701b98ce5d8d65d0d3c5a28c4cde8a855e23`
- validated/merged production tree: `bdc971e75a65cbcf6df5746fb1a27edef4979b95`
- architecture merge: `e3791afc88575ef3b5cd25731cff5aea0d6e6f9f`
- previous Phase 5O PR #260 merge: `a5e10ff348696f4ae8d755837e5e2a33dad68b08`
- previous Phase 5N PR #258 merge: `d1d63ea7d8d37efc78a7f90f1154cc10edab996d`
- previous Phase 5M PR #256 merge: `95bdb9b9d93df17922da2d5fbc43d4e9b5f781e5`
- previous Phase 5L PR #254 merge: `c78d1217fe8fa82ee85100a6409b58a09ee68d1a`
- previous Phase 5K PR #252 merge: `2bfedcb17e9058d1b4fd2f8749a6db9690f95592`
- Phase 5J #250, 5I #248, 5H #246, 5G #244, 5F #242, 5E #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.

### Explicit illustration-fill opacity ownership
The former `illustration_fill_opacity_runtime.py` installer is gone.

Illustration fill opacity now has ordinary static ownership:
- `illustration_fill_opacity` is a native `AppSettings` dataclass field;
- it retains the established 40% default and immediate 0–100 assignment clamping used by the other display-opacity fields;
- native settings JSON persistence carries the field, while older projects that omit it fall back to 40%;
- Settings Center label/help/unit/spin metadata lives in `ui/settings/schema.py`;
- the quick `区域不透明度` control is constructed directly in the existing illustration-control row after the fill-color control;
- non-runtime `illustration_fill_opacity.py` owns true-alpha polygon rendering, static quick-control construction, alpha-image lifetime records, and geometry refresh;
- the real PPP illustration draw site calls `create_alpha_canvas_polygon(...)` directly instead of temporarily replacing `canvas.create_polygon` during redraw;
- redraw explicitly clears alpha-polygon records before rebuilding canvas overlays;
- `_update_polygon_canvas_geometry(...)` calls `refresh_alpha_polygon_fill(...)` after its existing `try/except`, matching the former wrapper timing even when the original method internally swallows `tk.TclError`;
- the editable Canvas polygon remains the authoritative outline/hit target while the RGBA fill image stays below it;
- 100% native fill, 0% transparent fill, semi-transparent RGBA fill, tags, z-order, and PPP coordinates remain behaviorally unchanged.

GUI bootstrap no longer imports, configures, or installs illustration-fill opacity runtime code. `illustration_fill_opacity_runtime.py` is also removed from the architecture-guard legacy runtime set.

## Phase 5P validation
Isolated fail-closed validation on the exact production tree:
- exact intended no-renames production/test path set: **10 files, passed**;
- architecture guard: passed;
- focused: **25 passed, 1 Pillow deprecation warning**;
- full: **1282 passed, 1 Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helpers/workflow removed before publication.

The isolated migration was intentionally fail-closed. Early runs stopped before production publication on source-shape/test-characterization mismatches, including the static schema formatting, actual PPP polygon call shape, and an over-broad generated `gray50` assertion. Those failures were confined to temporary migration validation; no failed intermediate production tree was published. The final run also preserved the former runtime wrapper's post-geometry-update fill-refresh timing rather than merely matching the normal path.

Focused coverage proves:
- native illustration opacity clamps at construction and later assignment;
- JSON round-trip and old-project 40% fallback are preserved;
- true 40% alpha rendering remains RGBA rather than Tk stipple approximation;
- 100%, 0%, and semi-transparent polygon paths keep the editable outline/hit target contract;
- redraw/geometry refresh retain alpha-image lifetime explicitly;
- Settings Center and quick controls have static ownership;
- GUI bootstrap no longer imports or installs `illustration_fill_opacity_runtime.py`;
- the old PPP `illustration_fill_color, stipple=` draw path is absent.

PR #262 fixed-head gate on `489c701b98ce5d8d65d0d3c5a28c4cde8a855e23`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility / compile / F821 / wheel: passed on all three platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security dynamic PR check: passed;
- no PR comments, review threads, review submissions, or objections.

Architecture merge `e3791afc88575ef3b5cd25731cff5aea0d6e6f9f` retained exactly the validated production tree `bdc971e75a65cbcf6df5746fb1a27edef4979b95`.

Post-merge verification on `main@e3791afc88575ef3b5cd25731cff5aea0d6e6f9f`:
- Ubuntu CI: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- Windows CI: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- macOS CI: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous Phase 5O note
Phase 5O retired `overlay_opacity_runtime.py`. Guide/headword opacity are native `AppSettings` fields with static Settings Center / quick-control ownership, and real guide/marker draw sites call non-runtime `overlay_opacity.py` true-alpha helpers directly.

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
- Illustration fill opacity: native `AppSettings` + static settings schema + direct non-runtime `illustration_fill_opacity.py` rendering/UI helpers.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5Q
**Retire `layout_row_recovery_runtime.py` as the next narrow runtime seam.**

Fresh read-only inspection after Phase 5P shows this runtime is substantially smaller and more deterministic than the remaining Layout wrappers:
1. it defines one pure fallback function, `logical_slots_without_loss(y0, y1, reference)`;
2. it replaces only `layout_physical_indent._logical_slots_for_oversized_run`;
3. the behavioral change is already narrowly specified: when valley splitting cannot separate a tall projection band, choose enough logical slots to keep each slot within the downstream `<= 1.90 * reference` acceptance window instead of capping at four slots;
4. it retains a hard cap of 256 solely for corrupt/pathological geometry and otherwise leaves normal runs / successful valley splits untouched;
5. existing focused tests already exercise both the pure helper and the installed physical-indent behavior.

The current static helper in `layout_physical_indent.py` still contains the pre-runtime four-slot cap, so Phase 5Q can remove dynamic ownership by making the already-established runtime implementation the ordinary static implementation at that exact helper site.

Safest Phase 5Q architecture:
- replace only the body of `layout_physical_indent._logical_slots_for_oversized_run(...)` with the already-characterized `logical_slots_without_loss(...)` behavior; do not redesign `projection_line_runs`, valley splitting, thresholds, row semantics, or physical-indent measurement;
- keep the function name and call site stable so downstream code continues using the same private helper contract;
- remove `install_layout_row_recovery_runtime()` imports/calls from GUI bootstrap, worker bootstrap, `spawn_layout_runtime.py`, `unlined_physical_rows_resolver.py`, and `layout_rows_cache.py` only because the behavior is now always present statically;
- remove `layout_row_recovery_runtime.py` and its architecture-guard legacy entry after focused characterization proves static/runtime equivalence;
- rewrite runtime-installation tests into direct static-behavior and entry-path tests rather than weakening them;
- preserve GUI / worker / spawn parity by proving all relevant paths call the same static `layout_physical_indent` helper without installer order dependence.

Do **not** combine Phase 5Q with `layout_column_drift_runtime.py`, `layout_character_height_runtime.py`, `ordinary_large_head_runtime.py`, entry classification, spawn-runtime retirement, or unlined fast-path work. In particular, removing the row-recovery installer references from `spawn_layout_runtime.py` is cleanup only; Phase 5Q must not otherwise alter spawn parity logic.

## Why Phase 5Q is next
After Phase 5P, every remaining runtime seam affects algorithm/import-order/performance behavior, so the next slice should be the smallest already-characterized algorithmic seam rather than a broader wrapper.

`layout_row_recovery_runtime.py` is the best next boundary because it is a pure deterministic helper replacement with one explicit fallback contract and existing focused coverage. The alternatives are broader:
- `layout_character_height_runtime.py` wraps `detect_layout_parameters(...)` and performs image-based fallback measurement before Page Design imports the callable by value;
- `layout_column_drift_runtime.py` wraps the whole page-layout policy, re-runs analysis, and is reused by oversized-head evidence;
- `ordinary_large_head_runtime.py` changes detection authorization and explicitly depends on the column-drift runtime helper/import order;
- `layout_illustration_mask_runtime.py` affects Page Understanding input, AppSettings class setup, PPP detector binding, and visualization cache invalidation;
- `entry_classification_runtime.py` changes processing/OCR classification semantics;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py` are multiprocessing parity seams;
- `unlined_fast_path_runtime.py` is an import-order/performance seam.

## Remaining runtime seams after Phase 5P
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `layout_character_height_runtime.py`;
- `layout_column_drift_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `layout_row_recovery_runtime.py` (recommended Phase 5Q);
- `ordinary_large_head_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
