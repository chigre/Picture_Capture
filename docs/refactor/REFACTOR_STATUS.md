# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before new production writes, revalidate `main`, open PRs, relevant callers/import order, and tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5Q are complete.**

Phase 4 controller decomposition is complete. Phase 5 has progressively replaced dynamic installer/runtime ownership with explicit/static ownership while preserving current behavior.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5Q
- PR: **#264 — make long-band row recovery static**
- base before the production slice: `main@c5fef0574e1c937bb063afbfd444bb609c5ed7c6`
- validated production commit: `2fd49c542ff53c004b9211db35395dba4860c845`
- validated/merged production tree: `a5ca5b20e8b3f22b4115228314f39a7e2ef8d225`
- architecture merge: `b08e19be906ce86a9f40a350f9e5f90d6b08277b`
- previous Phase 5P PR #262 merge: `e3791afc88575ef3b5cd25731cff5aea0d6e6f9f`
- Phase 5A through Phase 5P remain complete in repository history and their earlier checkpoint commits.

### Static long-band row recovery ownership
The former `layout_row_recovery_runtime.py` installer is gone.

The established no-loss fallback now lives directly in `layout_physical_indent._logical_slots_for_oversized_run(...)`:
- ordinary/non-oversized runs are unchanged;
- when an unresolved projection band is tall enough to require logical splitting, slot count is no longer capped at four;
- enough slots are produced to satisfy the downstream `<= 1.90 * reference` acceptance contract;
- the existing 256-slot guard remains only as a pathological/corrupt-input bound;
- projection detection, successful valley splitting, physical-indent measurement, role semantics, and column geometry are otherwise unchanged.

Because that behavior is now always present statically, row-recovery installer imports/calls were removed from:
- GUI bootstrap;
- worker bootstrap;
- `spawn_layout_runtime.py`;
- `unlined_physical_rows_resolver.py`;
- `layout_rows_cache.py`.

`layout_column_drift_runtime.py`, spawn-layout parity, character-height fallback, ordinary-large-head authorization, entry classification, and unlined fast-path ownership were deliberately left intact.

The architecture guard no longer lists `layout_row_recovery_runtime.py` as allowed legacy runtime debt.

## Phase 5Q validation
Isolated fail-closed validation on the exact production tree:
- exact intended no-renames production/test path set: **12 files, passed**;
- architecture guard: passed;
- focused regressions: **34 passed**;
- full pytest suite: **1282 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication.

The focused gate covered:
- direct static long-band helper behavior;
- continuous oversized projection bands and ordinary runs;
- preservation of column-drift behavior;
- GUI/worker composition ownership after row-recovery installer removal;
- spawn worker parity while `spawn_layout_runtime.py` continues to own column-drift installation;
- runtime-entry guards;
- LayoutRows fast projection / physical-row resolution paths.

PR #264 fixed-head gate on `2fd49c542ff53c004b9211db35395dba4860c845`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility / compile / F821 / wheel: passed on all three platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security dynamic PR check: passed;
- no PR comments, review threads, review submissions, or objections.

Architecture merge `b08e19be906ce86a9f40a350f9e5f90d6b08277b` retained exactly the validated production tree `a5ca5b20e8b3f22b4115228314f39a7e2ef8d225`.

Post-merge verification on `main@b08e19be906ce86a9f40a350f9e5f90d6b08277b`:
- Ubuntu CI: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- Windows CI: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- macOS CI: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Previous completed Phase 5 ownership
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership backed by `unicode_nonbmp_input.py`.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native `AppSettings` + static settings/UI + direct non-runtime `overlay_opacity.py` rendering.
- Phase 5P: illustration fill opacity became native `AppSettings` + static settings/UI + direct non-runtime `illustration_fill_opacity.py` true-alpha rendering and refresh ownership.
- Phase 5Q: long-band row recovery is now static in `layout_physical_indent.py`.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper → `DetectionController`; OCR-independent quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper → `CropController` → app-owned shared parallel batch runner.
- Training package: app wrapper → `ExportController`; bootstrap no longer replaces the method.
- Layout visualization: LayoutRows capture, corrected indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are non-runtime/static ownership.
- Windows/Tk supplementary Unicode repair: explicit `PictureCaptureApp` lifecycle → non-runtime `unicode_nonbmp_input.py`.
- Overlay anchoring: non-runtime `overlay_line_anchor.py`.
- Guide/headword line opacity: native settings + direct non-runtime rendering/UI ownership.
- Illustration fill opacity: native settings + direct non-runtime rendering/UI ownership.
- Long-band logical row recovery: static `layout_physical_indent._logical_slots_for_oversized_run(...)`.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5R
**Retire `layout_character_height_runtime.py` by making the already-characterized fallback an explicit post-detection step in `layout_detection.detect_layout_parameters(...)`.**

Fresh read-only inspection after Phase 5Q makes this the narrowest reasonable remaining algorithm/import-order seam:
1. `observed_character_height(...)` is already a deterministic helper with direct focused tests;
2. the runtime wrapper only changes estimates whose method already contains `fallback=character_height`;
3. it measures physical foreground-run heights, requires at least eight well-supported samples and a compact height family, and otherwise returns the original estimate unchanged;
4. it only replaces `character_height`; geometry, column starts/widths, OCR, and entry semantics are untouched;
5. explicit installer references are concentrated in shared core, GUI ordering, the unlined physical-row escalation path, and their source-contract tests.

### Critical cache contract for Phase 5R
Current ownership is two-layered:
- the original `layout_detection.detect_layout_parameters(...)` builds/looks up the existing `_LAYOUT_ESTIMATE_CACHE` and therefore caches the **raw reliable detector result**;
- `install_character_height_fallback_runtime()` wraps that callable from the outside, so the observed-height correction is applied after every raw cache lookup and the corrected copy itself is **not** inserted into `_LAYOUT_ESTIMATE_CACHE`.

Phase 5R must preserve that contract. Do **not** simply move the correction before the cache write or cache the corrected estimate.

Safest Phase 5R architecture:
- keep `observed_character_height(...)` as ordinary non-runtime helper ownership (move/rename the module only if doing so does not widen the slice; deleting the `_runtime` filename is the goal);
- add a small explicit helper that receives `(image, settings, raw_estimate, backend)` and reproduces the current wrapper conditions exactly: require `fallback=character_height`, measure, preserve the estimate on no result or ratio 0.82–1.22, otherwise `dataclasses.replace(..., character_height=observed)` and append the existing method provenance text;
- in `layout_detection.detect_layout_parameters(...)`, preserve the current raw cache key, raw cache lookup, raw detector call, raw cache insertion, LRU behavior, and cache-clear semantics exactly; only after obtaining the raw estimate should the function apply the explicit character-height fallback and return the corrected copy;
- apply the fallback on both cache-hit and cache-miss paths so behavior matches the current outer wrapper;
- pass the same original input image used by the current runtime wrapper to the observation helper rather than silently substituting a different analysis image;
- remove `install_character_height_fallback_runtime()` from `bootstrap/core.py`, GUI bootstrap, and `unlined_physical_rows_resolver.py` only after direct static behavior/order tests prove equivalence;
- remove `layout_character_height_runtime.py` and ratchet the architecture guard only after focused/full validation;
- rewrite installer-order tests into explicit ownership/cache/entry-path assertions rather than weakening them.

Do **not** combine Phase 5R with column-drift, ordinary-large-head, illustration-mask, entry-classification, spawn-runtime, or unlined-fast-path retirement.

## Why not the other remaining seams yet
- `layout_column_drift_runtime.py` wraps the page-layout policy, re-runs analysis, and provides analysis-left helpers consumed by oversized-head evidence.
- `ordinary_large_head_runtime.py` changes detection authorization and explicitly depends on column-drift analysis helpers.
- `layout_illustration_mask_runtime.py` is broad: it participates in AppSettings class setup, shared PPP illustration detection, Page Understanding input masking, and cache/visualization behavior.
- `entry_classification_runtime.py` changes processing materialization plus marker OCR crop/engine dispatch.
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py` are multiprocessing parity seams.
- `unlined_fast_path_runtime.py` is an action-time import-order/performance seam.

Character-height fallback is therefore the next best candidate, but it is materially broader than Phase 5Q and must be isolated with explicit cache-contract characterization before production publication.

## Remaining runtime seams after Phase 5Q
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `layout_character_height_runtime.py` — recommended Phase 5R;
- `layout_column_drift_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
