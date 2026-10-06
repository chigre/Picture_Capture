# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5S are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5S
- production PR: **#269 — make column-drift remeasurement static**
- base before the production slice: `main@6553156cfa7b9448ad924f70474abfcfa53679eb`
- validated production head: `e786b4c2eddaba4eabf22545882ae8556e5b0721`
- validated production tree: `0571abc1d4bf85b1358c753705aee4978d274933`
- merge commit / current architecture main: `80280f693b9d93c0a8f8e6b4227f7471b4bdcf2e`
- merge tree: `0571abc1d4bf85b1358c753705aee4978d274933`

A client message timeout happened after the merge had already completed. Recovery briefly opened duplicate PR #270 from an equivalent validated tree. Live-state inspection showed that Phase 5S was already merged as #269, so #270 was closed without merge or any change to `main`.

### Static column-drift ownership
The former `layout_column_drift_runtime.py` monkey-patch seam is gone.

Deterministic drift helpers now live in ordinary non-runtime `layout_column_drift.py`:
- `_left_safety(...)` keeps the same bounded analysis-only margin;
- `_analysis_left_for_column(...)` still prevents later-column analysis from crossing into the previous text column;
- `remeasure_layout_indents_from_ink(...)` still permits negative semantic-column-local `first_x` values while leaving `column.left/right` unchanged;
- remeasurement still rebuilds indent modes and entry/body semantics from the unclipped first-X evidence.

`dictionary_page_layout_policy.infer_dictionary_page_layout(...)` now applies the remeasurement explicitly after the base `DictionaryPageLayout` has been assembled. Phase 5S deliberately preserved the former wrapper's second `_analysis_page(...)` / `analysis_ink_mask(...)` pass rather than combining ownership cleanup with a performance optimization. Display-head evidence, reliability, body bounds, and other base-policy products are not recomputed after the remeasurement, matching the historical runtime ordering.

`ordinary_large_head_runtime.py` still reuses the exact same `_analysis_left_for_column(...)` helper, now from the non-runtime module. Its large-head candidate extraction, observed line-height reference, row-front authorization, and evidence ownership were otherwise left unchanged.

Column-drift installer imports/calls were removed from GUI composition, worker composition, unlined physical-row escalation, and the spawn-layout compatibility adapter. The architecture guard no longer permits `layout_column_drift_runtime.py` as legacy runtime debt.

### Phase 5S isolated validation
The isolated migration used a fail-closed temporary branch workflow and removed all migration assets before production publication.

Final corrected validation:
- exact intended **no-renames** production/test path set: **13 paths, passed**;
- GitHub recognized `layout_column_drift_runtime.py -> layout_column_drift.py` as a rename, so the PR UI reports 12 changed files;
- no production `install_layout_column_drift_runtime` references remained;
- architecture guard: passed;
- focused regressions: **39 passed**;
- full pytest suite: **1287 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed.

The first isolated full-suite run had **1286 passed / 1 failed**. The sole failure was a stale source-contract test that still opened the retired filename `layout_column_drift_runtime.py`; it was updated to inspect `layout_column_drift.py` while preserving the same invariant that column drift must never replace or weaken the guarded large-head detector. The corrected full suite then passed completely.

### Phase 5S PR gate
Fixed-head PR #269 on `e786b4c2eddaba4eabf22545882ae8556e5b0721`:
- Ubuntu CI: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- Windows CI: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- macOS CI: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security dynamic PR check: passed;
- no PR comments, review threads, review submissions, or objections.

The merge retained exactly the validated production tree `0571abc1d4bf85b1358c753705aee4978d274933`.

### Phase 5S post-merge verification
On `main@80280f693b9d93c0a8f8e6b4227f7471b4bdcf2e`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility / compile / F821 / wheel: passed on all three platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous completed Phase 5 ownership
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership backed by `unicode_nonbmp_input.py`.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native `AppSettings` + static settings/UI + direct non-runtime `overlay_opacity.py` rendering.
- Phase 5P: illustration fill opacity became native `AppSettings` + static settings/UI + direct non-runtime `illustration_fill_opacity.py` rendering and refresh ownership.
- Phase 5Q: long-band logical row recovery became static in `layout_physical_indent.py`.
- Phase 5R: character-height fallback became an explicit post-raw-cache step in `layout_detection.py`, backed by non-runtime `layout_character_height.py`.
- Phase 5S: column-drift first-X remeasurement became an explicit finalization step in `dictionary_page_layout_policy.py`, backed by non-runtime `layout_column_drift.py`.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper -> `DetectionController`; OCR-independent quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper -> `CropController` -> app-owned shared parallel batch runner.
- Training package: app wrapper -> `ExportController`; bootstrap no longer replaces the method.
- Layout visualization: LayoutRows capture, corrected indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are non-runtime/static ownership.
- Windows/Tk supplementary Unicode repair: explicit `PictureCaptureApp` lifecycle -> non-runtime `unicode_nonbmp_input.py`.
- Overlay anchoring: non-runtime `overlay_line_anchor.py`.
- Guide/headword line opacity: native settings + direct non-runtime rendering/UI ownership.
- Illustration fill opacity: native settings + direct non-runtime rendering/UI ownership.
- Long-band logical row recovery: static `layout_physical_indent._logical_slots_for_oversized_run(...)`.
- Character-height fallback: static `layout_detection.detect_layout_parameters(...)` -> `layout_character_height.apply_character_height_fallback(...)` after raw-cache retrieval.
- Column-drift remeasurement: static `dictionary_page_layout_policy.infer_dictionary_page_layout(...)` -> non-runtime `layout_column_drift` helpers.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5T
**Retire `spawn_layout_runtime.py` as an identity-only compatibility wrapper.**

Fresh read-only inspection after Phase 5S shows that `spawn_layout_runtime.py` now has no behavior of its own. `install_spawn_layout_runtime(processing_module)` captures `processing_module._ensure_layout_runtime`, replaces it with a `@wraps` function that does nothing except call `original()`, and sets `_pc_spawn_layout_runtime_installed = True`.

The real layout preparation already remains in `processing._ensure_layout_runtime()` itself. That function directly:
1. binds `dictionary_page_design.detect_entries_from_page_design` to the refined implementation;
2. calls `install_robust_line_starts()`;
3. calls `install_physical_indent_inference()`.

`processing._understand_page_current(...)` calls `_ensure_layout_runtime()` before both layout-only and full Page Understanding paths. Therefore the Phase 5S result leaves the spawn wrapper as pure identity plumbing rather than a behavior seam.

### Safest Phase 5T architecture
- delete `spawn_layout_runtime.py`;
- remove its import and `install_spawn_layout_runtime(processing_module)` call from `bootstrap/core.py`;
- remove `_pc_spawn_layout_runtime_installed` expectations from tests;
- rewrite the existing spawn-layout tests to assert direct ownership instead: `processing._ensure_layout_runtime` remains stable across calls, still prepares the same line-start/physical-indent chain, and GUI/worker composition reaches the same `processing` entry point without a wrapper;
- remove `spawn_layout_runtime.py` from the architecture-guard legacy runtime allowance;
- do **not** combine Phase 5T with `spawn_detection_runtime.py`, entry classification, large-head runtime, illustration-mask runtime, or unlined-fast-path retirement.

### Required Phase 5T focused characterization
Before publication, prove at minimum:
- `processing._ensure_layout_runtime` object identity is no longer changed by core composition;
- repeated `_ensure_layout_runtime()` calls remain idempotent in observable behavior;
- refined page-design binding, robust line-start installation, and physical-indent installation are still performed by the existing processing helper;
- GUI and spawn-worker composition continue to share the same core `processing` module;
- layout-only Page Understanding and ordinary worker paths still execute successfully without `_pc_spawn_layout_runtime_installed`;
- source/architecture guards contain no `spawn_layout_runtime` production dependency after deletion.

Because the wrapper is already behaviorally identity-only, Phase 5T should be a very small ownership cleanup. Any unexpected behavior failure is a stop condition rather than a reason to broaden the slice.

## Remaining runtime seams after Phase 5S
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `spawn_detection_runtime.py`;
- `spawn_layout_runtime.py` — recommended Phase 5T; currently identity-only after Phase 5S;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
