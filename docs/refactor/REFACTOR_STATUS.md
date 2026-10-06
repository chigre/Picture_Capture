# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before new production writes, revalidate `main`, open PRs, relevant callers/import order, and tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5R are complete.**

Phase 4 controller decomposition is complete. Phase 5 has progressively replaced dynamic installer/runtime ownership with explicit/static ownership while preserving current behavior.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5R
- production PR: **#266 — make character-height fallback static**
- base before the production slice: `main@c6078c8b269b799524b7824ac85903d6a9df6a90`
- validated production commit: `c0c6f27a15fc8662631d31afaa54bcd2ca9eb34a`
- validated production tree: `c87f4bd6dbfc07a81dcecef6270d5a565e37689e`
- architecture merge: `c293ad60df899cb5f5f3426d1921be0d7a824aff`
- source-hygiene follow-up PR: **#267 — remove accidental leading backslash**
- follow-up head: `8bc4f47164ad22109974721c38873e8cfe2c2130`
- final merged `main`: `a1764057fafab9cc55201987c17307265fe8ec28`
- final tree: `79e19494e00d2545aab05f0b66bb5e105c63e129`

### Static character-height fallback ownership
The former `layout_character_height_runtime.py` installer seam is gone.

The established observation logic now lives in ordinary non-runtime `layout_character_height.py`:
- only estimates whose method already contains `fallback=character_height` are eligible;
- foreground physical-row runs are measured from the same original input image as before;
- sparse or ambiguous samples are rejected;
- ratios within `0.82–1.22` preserve the original estimate;
- otherwise only `character_height` plus the existing method provenance suffix are changed.

`layout_detection.detect_layout_parameters(...)` now applies this helper explicitly after obtaining the raw reliable estimate.

### Preserved raw-cache contract
Phase 5R deliberately preserved the historical two-layer cache behavior:
- `_LAYOUT_ESTIMATE_CACHE` still stores only the raw reliable detector estimate;
- cache key construction, raw detector execution, raw cache insertion, LRU movement/eviction, and cache clearing are unchanged;
- the character-height correction is applied after both cache-hit and cache-miss raw-estimate retrieval;
- the corrected copy is never inserted into `_LAYOUT_ESTIMATE_CACHE`.

A focused regression proves that across two identical calls the raw detector runs once while the character-height fallback is replayed twice.

Because the behavior is now static, character-height installer plumbing was removed from shared core composition, GUI composition, and unlined physical-row escalation. The architecture guard no longer lists `layout_character_height_runtime.py` as allowed legacy runtime debt.

## Phase 5R validation
Isolated fail-closed validation on the intended production tree:
- exact intended no-renames production/test path set: **9 paths, passed**;
- GitHub recognized the runtime/helper pair as a rename, so PR #266 displayed **8 changed files**;
- architecture guard: passed;
- focused regressions: **36 passed**;
- full pytest suite: **1285 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication.

PR #266 fixed-head gate on `c0c6f27a15fc8662631d31afaa54bcd2ca9eb34a`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility / compile / F821 / wheel: passed on all three platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security dynamic PR check: passed;
- no PR comments, review threads, review submissions, or objections.

Architecture merge `c293ad60df899cb5f5f3426d1921be0d7a824aff` retained exactly the validated production tree `c87f4bd6dbfc07a81dcecef6270d5a565e37689e`.

During post-merge source inspection, an accidental standalone leading `\` was found at the first line of `layout_character_height.py`. It did not break compile/tests because Python treated it as line continuation, but it was not an acceptable source shape. PR #267 removed exactly that one character:
- exact diff: **1 file, 1 deletion, 0 additions**;
- fixed head: `8bc4f47164ad22109974721c38873e8cfe2c2130`;
- Ubuntu / Windows / macOS CI: passed;
- CodeQL Actions / Python: passed;
- Advanced Security: passed;
- no review/comment/thread objections.

Final merge `a1764057fafab9cc55201987c17307265fe8ec28` has tree `79e19494e00d2545aab05f0b66bb5e105c63e129` and the file begins normally with `from __future__ import annotations`.

Final post-merge verification on `main@a1764057fafab9cc55201987c17307265fe8ec28`:
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
- Phase 5Q: long-band row recovery became static in `layout_physical_indent.py`.
- Phase 5R: character-height fallback became an explicit post-raw-cache step in `layout_detection.py`, backed by non-runtime `layout_character_height.py`.

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
- Character-height fallback: static `layout_detection.detect_layout_parameters(...)` → non-runtime `layout_character_height.apply_character_height_fallback(...)` after raw-cache retrieval.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5S
**Retire `layout_column_drift_runtime.py` by making unclipped indent remeasurement a static finalization step of `dictionary_page_layout_policy.infer_dictionary_page_layout(...)`.**

Fresh read-only inspection after Phase 5R makes column-drift the narrowest reasonable next seam, but it has one important shared-helper dependency with oversized-head evidence.

Current runtime behavior is:
1. call the existing policy inference first;
2. rebuild the same page-analysis domain from the returned `page_settings`;
3. remeasure each recovered row in a wider analysis band extending left of the semantic column boundary;
4. preserve semantic column geometry while allowing negative local `first_x` values;
5. rebuild indent modes/roles from those unclipped first-X values;
6. append `unclipped_first_x=...` provenance to `layout.reason`;
7. return the same `(layout, page_settings, applied)` tuple.

The runtime file also exposes `_left_safety(...)` and `_analysis_left_for_column(...)`. `ordinary_large_head_runtime.py` deliberately imports `_analysis_left_for_column(...)` so its guarded oversized-head detector uses exactly the same analysis-only left safety band. That helper dependency must survive Phase 5S unchanged even though the installer disappears.

### Safest Phase 5S architecture
- move the deterministic column-drift helpers into an ordinary non-runtime module such as `layout_column_drift.py`; retain `_left_safety(...)`, `_analysis_left_for_column(...)`, and `remeasure_layout_indents_from_ink(...)` semantics exactly;
- update `ordinary_large_head_runtime.py` to import `_analysis_left_for_column(...)` from the non-runtime helper module only; do not otherwise change large-head authorization, row-front checks, size reference, candidate extraction, or evidence ownership;
- in `dictionary_page_layout_policy.infer_dictionary_page_layout(...)`, keep the current policy inference, geometry, line extraction, display-head calculation, reliability calculation, and reason construction unchanged;
- after the `DictionaryPageLayout` object has been assembled, run the static unclipped-indent remeasurement and append the same `unclipped_first_x=...` provenance before returning;
- where safe and proven equivalent, reuse the already-computed policy `page_ink` rather than re-running the entire page-analysis pipeline; focused tests must prove that this does not change first-X / role results relative to the current outer wrapper;
- do not recompute display-head evidence, reliability, body bounds, or other policy products after remeasurement, because the current runtime wrapper also applies only after the base policy result exists;
- remove direct column-drift installer imports/calls from GUI bootstrap, worker bootstrap, and `unlined_physical_rows_resolver.py` only after static behavior is characterized;
- remove the column-drift extension from `spawn_layout_runtime.py`, but do **not** combine Phase 5S with broader spawn-runtime retirement; if the spawn adapter becomes behaviorally identity-only, leave its actual deletion to a spawn-specific later slice;
- delete `layout_column_drift_runtime.py` and ratchet the architecture guard only after focused/full validation;
- rewrite installer-presence tests into direct static ownership, shared-helper, and GUI/worker/spawn parity assertions rather than weakening coverage.

### Required Phase 5S focused characterization
Before publication, prove at minimum:
- widened analysis-left boundaries remain identical for first and later columns, including previous-column clipping protection;
- semantic column geometry does not move;
- negative local `first_x` remains possible and is normalized by the same downstream indent logic;
- indent modes/roles after static finalization match the current runtime wrapper on representative drifted layouts;
- `layout.reason` provenance is unchanged when rows are remeasured;
- `ordinary_large_head_runtime.py` uses the exact same left-safety helper after module relocation;
- GUI, worker, spawn, and unlined physical-row entry paths no longer require the column-drift installer to obtain the same policy result.

Do **not** combine Phase 5S with `ordinary_large_head_runtime.py`, illustration-mask ownership, entry classification, spawn-runtime retirement, or unlined-fast-path retirement.

## Remaining runtime seams after Phase 5R
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `layout_column_drift_runtime.py` — recommended Phase 5S;
- `layout_illustration_mask_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
