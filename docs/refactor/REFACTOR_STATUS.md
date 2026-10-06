# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5X are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5X
- production PR: **#280 — staticize entry classification and existing-marker OCR**
- base before the production slice: `main@f7593781e2b4c28f2936a039fc3ef0856f4fd93b`
- clean production head: `cdd19be392a2acd0355a636e9cdb30fc16ee2b39`
- validated production tree: `16619800e220e88b31bf200a5640546a69513658`
- merge commit / current architecture main: `541d871582a19778a955a4134ee2874cf5de842c`
- merge tree: `16619800e220e88b31bf200a5640546a69513658`

### Static entry-classification and marker-OCR ownership
The former `entry_classification_runtime.py` callable-mutation seam is gone.

Phase 5X promoted the runtime's three real behaviors into their normal static owners without changing PDIC format or the illustration-mask feature:
1. `processing._ordinary_entries_from_layout_roles(...)` now copies each final Layout entry row's canonical classification during materialization and preserves the existing oversized-CJK OCR hints;
2. `processing_core._ordinary_marker_local_crop(...)` now directly uses `entry_ocr_crop_box(...)` plus canonical entry classification;
3. `processing_core.ocr_existing_entry_words_from_markers(...)` now directly owns the shared multi-engine `OcrChannelSession` implementation, including one session per page, Paddle-record parsing, arbitration, replacement rules, provenance, stats, and the invariant that marker OCR must not move coordinates.

Core, GUI, and worker composition no longer import or call `install_processing_entry_classification(...)`. `entry_classification_runtime.py` was deleted, its three state markers are gone, and the architecture guard no longer permits that runtime file as legacy debt. The processing facade and core now expose the same static crop/OCR callables rather than relying on bootstrap order.

Phase 5X deliberately preserved one pre-existing classification semantic discovered while strengthening characterization: a materialized `Entry` whose concrete `ocr_source` says `page_understanding:ordinary_layout_role` can later be re-inferred as `indent` by `get_entry_classification(...)` even when large-head line classification previously drove oversized OCR hints during materialization. The old runtime behaved the same way. Phase 5X therefore did not change this semantic merely to satisfy a new test; the characterization was corrected to verify the existing observable contract. Any future change to that registry/source-precedence behavior should be a separate behavior slice.

### Phase 5X isolated validation
Temporary fail-closed branch workflows were used for targeted large-file migration and validation, then removed before publication.

Final isolated validation:
- exact intended production/test diff shape: **16 paths, passed**;
- `entry_classification_runtime.py` removed;
- zero production references to `entry_classification_runtime`, `install_processing_entry_classification`, `_entry_classification_runtime_installed`, `_entry_classification_crop_installed`, or `_entry_marker_ocr_dispatch_installed`;
- static facade/core callable identity: passed;
- architecture guard: passed;
- focused regressions: **243 passed**;
- full pytest suite: **1290 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed.

The first strengthened characterization exposed only a new-test expectation that exceeded the old runtime contract; production code was not changed. A subsequent full-suite run exposed two stale source contracts (`test_ocr_channel.py` and `test_worker_bootstrap.py`); those tests were migrated to the static owners. The final isolated run above was fully green.

The exact validated tree `16619800e220e88b31bf200a5640546a69513658` was re-anchored to the live main base as one clean production commit `cdd19be392a2acd0355a636e9cdb30fc16ee2b39`.

### Phase 5X PR gate
Fixed-head PR #280 on `cdd19be392a2acd0355a636e9cdb30fc16ee2b39`:
- CI run 2105 Ubuntu: passed;
- CI run 2105 Windows: passed;
- CI run 2105 macOS: passed;
- CodeQL run 2086 Actions: passed;
- CodeQL run 2086 Python: passed;
- Advanced Security run 1845: passed;
- PR remained mergeable with one commit and sixteen changed files;
- no PR comments, review threads, review submissions, or objections.

PR #280 was merged with fixed-head protection using `expected_head_sha=cdd19be392a2acd0355a636e9cdb30fc16ee2b39`.

### Phase 5X post-merge verification
On `main@541d871582a19778a955a4134ee2874cf5de842c`:
- merge tree exactly matched validated production tree `16619800e220e88b31bf200a5640546a69513658`;
- push CI run 2106 passed on Ubuntu, Windows, and macOS;
- GUI smoke passed on all applicable platforms;
- compatibility runner / compile / F821 / wheel passed on all three platforms;
- CodeQL run 2087 Actions: passed;
- CodeQL run 2087 Python: passed.

No post-merge behavior, packaging, or security regression was observed.

## Previous architecture checkpoint — Phase 5W
- production PR: **#278 — make unlined physical-row fast path static**
- base before the production slice: `main@73ad384329db8719f0636fb93b83254cf4596126`
- clean production head: `757a45fdbb70c527155a74e6a2ba0fca73cc148e`
- validated production tree: `a744deda0804e8c38da8119d861d9565f7e43493`
- merge commit / current architecture main: `94bf35b113e2b7bb3848047792597b47431df0de`
- merge tree: `a744deda0804e8c38da8119d861d9565f7e43493`

### Static unlined physical-row worker ownership
The former `unlined_fast_path_runtime.py` worker-replacement seam is gone.

Before Phase 5W, two top-level unlined page workers coexisted:
- `unlined_line_export.export_unlined_page_job(...)`, the older worker that built an analysis image and ran the complete Layout Core path;
- `unlined_fast_path_runtime.export_unlined_page_job_fast(...)`, dynamically installed by GUI bootstrap and used in normal GUI operation because CropController resolves `unlined_export.export_unlined_page_job` through the module at action time.

The runtime worker contained the intended performance behavior and therefore was not deleted directly. Phase 5W promoted its physical-row resolution semantics into the normal top-level `unlined_line_export.export_unlined_page_job(...)` while keeping the public/internal worker contract stable.

Current static worker behavior:
1. reads PDIC markers and page sections exactly as before;
2. opens and normalizes the source scan exactly once;
3. calls `resolve_unlined_physical_rows(...)` directly;
4. preserves the existing resolver order: persisted `data/LayoutRows/<page>.json` -> Profile-geometry physical-row projection -> reliable physical layout detection fallback;
5. does not require Page Understanding semantic enrichment, symbol evidence, or oversized-head evidence fusion;
6. returns `physical_reliable=False` with zero counters when no physical layout can be resolved;
7. reuses the unchanged `unlined_rows_from_layout(...)` Layout-minus-PDIC mapping;
8. reuses the unchanged `_save_unlined_rows(...)` filter/save path, including blankness measurement before white-border trimming, per-row/merged output naming, manifest replacement, stale-output cleanup, and image lifetime;
9. retains the same top-level function name, signature, module identity, and spawn-pickleable identity.

`CropController` still imports `unlined_line_export` as a module and resolves `unlined_export.export_unlined_page_job` at action time, but there is no longer any runtime replacement to discover. The legacy `run_unlined_export(...)` helper likewise resolves the same normal module-global worker.

GUI bootstrap no longer imports or calls `install_unlined_fast_path()`. `unlined_fast_path_runtime.py` was deleted, `_physical_rows_fast_path_installed` is gone, and the architecture guard no longer permits this runtime file as legacy debt.

Phase 5W deliberately did **not** change PDIC matching semantics, page-section filtering, blank-filter semantics, output format/manifests, CropController orchestration, worker-count policy, entry-classification ownership, or illustration-mask ownership. Full-Layout-only imports that are no longer called by the static worker were not made a separate cleanup objective; behavior/source ownership was the scope of this slice.

### Phase 5W isolated validation
A temporary fail-closed branch workflow was used and removed before publication.

Final isolated validation:
- exact intended production/test diff shape: **7 paths, passed**;
- `unlined_fast_path_runtime.py` removed;
- zero production references to `unlined_fast_path_runtime`, `install_unlined_fast_path`, `_physical_rows_fast_path_installed`, or `export_unlined_page_job_fast`;
- architecture guard: passed;
- focused regressions: **24 passed**;
- full pytest suite: **1289 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed.

Focused characterization proved:
- the normal `unlined_line_export.export_unlined_page_job` is still a top-level spawn-pickleable callable with module identity `picture_capture.unlined_line_export`;
- the static worker directly uses `resolve_unlined_physical_rows(...)` and does not call `understand_layout_core(...)` or `build_analysis_image(...)` in its worker body;
- the resolver remains independent of semantic symbol/large-head evidence and may escalate only through physical layout policy;
- LayoutRows cache and Profile physical-row recovery behavior remains intact;
- CropController still resolves the worker through the ordinary module;
- Layout-minus-PDIC semantics, blank-filter ordering, output/manifest behavior, and UI/batch contracts remain covered by their existing tests.

The temporary validation workflow was deleted before publication. The exact validated tree `a744deda0804e8c38da8119d861d9565f7e43493` was then re-anchored to the live main base as one clean production commit `757a45fdbb70c527155a74e6a2ba0fca73cc148e`.

### Phase 5W PR gate
Fixed-head PR #278 on `757a45fdbb70c527155a74e6a2ba0fca73cc148e`:
- CI run 2101 Ubuntu: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- CI run 2101 Windows: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- CI run 2101 macOS: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL run 2082 Actions: passed;
- CodeQL run 2082 Python: passed;
- Advanced Security run 1843: passed;
- PR remained mergeable with one commit and seven changed files;
- no PR comments, review threads, review submissions, or objections.

PR #278 was merged with fixed-head protection using `expected_head_sha=757a45fdbb70c527155a74e6a2ba0fca73cc148e`.

### Phase 5W post-merge verification
On `main@94bf35b113e2b7bb3848047792597b47431df0de`:
- merge tree exactly matched validated production tree `a744deda0804e8c38da8119d861d9565f7e43493`;
- push CI run 2102 passed on Ubuntu, Windows, and macOS;
- GUI smoke passed on all applicable platforms;
- compatibility runner / compile / F821 / wheel passed on all three platforms;
- CodeQL run 2083 Actions: passed;
- CodeQL run 2083 Python: passed.

No post-merge behavior, packaging, or security regression was observed.

## Previous completed Phase 5 ownership
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership backed by `unicode_nonbmp_input.py`.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native `AppSettings` + static settings/UI + direct non-runtime `overlay_opacity.py` rendering.
- Phase 5P: illustration fill opacity became native `AppSettings` + static settings/UI + direct non-runtime `illustration_fill_opacity.py` rendering and refresh ownership.
- Phase 5Q: long-band logical row recovery became static in `layout_physical_indent.py`.
- Phase 5R: character-height fallback became an explicit post-raw-cache step in `layout_detection.py`, backed by non-runtime `layout_character_height.py`.
- Phase 5S: column-drift first-X remeasurement became an explicit finalization step in `dictionary_page_layout_policy.py`, backed by non-runtime `layout_column_drift.py`.
- Phase 5T: the identity-only spawn-layout wrapper was deleted; `processing._ensure_layout_runtime` became directly authoritative.
- Phase 5U: the real spawn-safe ordinary worker became static `processing.detect_entries_job`; GUI-time worker replacement and `spawn_detection_runtime.py` were removed.
- Phase 5V: guarded oversized-head detection plus strict row/fusion authorization became static; `ordinary_large_head_runtime.py` and both large-head bootstrap mutations were removed.
- Phase 5W: the unlined physical-row fast worker became the normal static `unlined_line_export.export_unlined_page_job`; `unlined_fast_path_runtime.py` and GUI-time worker replacement were removed.
- Phase 5X: Layout-entry classification attachment plus classification-aware existing-marker crop/OCR became static processing ownership; `entry_classification_runtime.py` and its bootstrap mutation chain were removed.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper -> `DetectionController`; OCR-independent quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper -> `CropController` -> app-owned shared parallel batch runner.
- Unlined page worker: static top-level `unlined_line_export.export_unlined_page_job(...)` -> `resolve_unlined_physical_rows(...)`; no worker installer remains.
- Training package: app wrapper -> `ExportController`; bootstrap no longer replaces the method.
- Layout visualization: LayoutRows capture, corrected indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are non-runtime/static ownership.
- Windows/Tk supplementary Unicode repair: explicit `PictureCaptureApp` lifecycle -> non-runtime `unicode_nonbmp_input.py`.
- Overlay anchoring: non-runtime `overlay_line_anchor.py`.
- Guide/headword line opacity: native settings + direct non-runtime rendering/UI ownership.
- Illustration fill opacity: native settings + direct non-runtime rendering/UI ownership.
- Long-band logical row recovery: static `layout_physical_indent._logical_slots_for_oversized_run(...)`.
- Character-height fallback: static `layout_detection.detect_layout_parameters(...)` -> `layout_character_height.apply_character_height_fallback(...)` after raw-cache retrieval.
- Column-drift remeasurement: static `dictionary_page_layout_policy.infer_dictionary_page_layout(...)` -> non-runtime `layout_column_drift` helpers.
- Spawn layout preparation: direct `processing._ensure_layout_runtime()` ownership; no compatibility wrapper remains.
- Spawn ordinary detection: static top-level `processing.detect_entries_job(...)` -> lazy `build_worker_services()` consumption; no GUI-time replacement remains.
- Oversized-head detection/authorization: static `ordinary_large_head_evidence` + pure `ordinary_large_head_role_guard` policy + direct `ordinary_evidence_fusion` strength gate.
- Entry classification / existing-marker OCR: static `processing._ordinary_entries_from_layout_roles(...)` + static `processing_core._ordinary_marker_local_crop(...)` / `ocr_existing_entry_words_from_markers(...)`; no classification callable installer remains.

## Recommended next slice — Phase 5Y
**Staticize only the illustration-mask settings schema and shared illustration detector; keep the Page Understanding wrapper and GUI/cache mutation for later slices.**

Fresh read-only inspection after Phase 5X confirms that `layout_illustration_mask_runtime.py` is now the remaining file explicitly tracked as runtime debt, but it still combines four distinct responsibilities:
1. dynamically subclasses/rebinds `models.AppSettings` to add `layout_mask_illustrations`;
2. owns an in-memory illustration component detector and mutates `processing_core.detect_illustration_regions` plus the processing facade so PPP and Layout masking share it;
3. wraps `processing._understand_page_current(...)` with fail-open white-fill preprocessing and diagnostics;
4. mutates `SettingsDialog` metadata plus `layout_visualization_ui._layout_cache_key`.

Taking all four at once would mix settings serialization/pickle identity, detector semantics, Page Understanding image lifetime/error fallback, and GUI cache behavior in one slice. Phase 5Y should therefore remove only the first two import-order dependencies.

### Safest Phase 5Y architecture
- add `layout_mask_illustrations: bool = False` directly to the native `AppSettings` dataclass and preserve JSON/backward-default behavior, `dataclasses.replace`, and spawn pickle identity without dynamic subclassing;
- remove `install_layout_illustration_mask_settings()` from core bootstrap once the native field is proven equivalent;
- promote the current in-memory illustration detector into a static non-runtime owner, preferably the existing `processing_core` detector surface so the historical path API and the Layout mask consume one implementation without a new proxy;
- make `processing_core.detect_illustration_regions(...)` statically delegate to/share that implementation rather than being replaced at composition time;
- let `mask_large_illustrations_for_layout(...)` consume the static detector directly; remove only the detector-rebinding portion of `install_layout_illustration_mask_runtime(...)`;
- keep the current fail-open `_understand_page_current(...)` wrapper, mask diagnostics, `SettingsDialog` integration, and Layout visualization cache-key mutation unchanged for this phase;
- do **not** delete `layout_illustration_mask_runtime.py` in Phase 5Y unless the remaining wrapper/UI responsibilities have independently migrated too;
- do not change PPP file format, illustration crop semantics, mask thresholds, headlike protection thresholds, or default-disabled behavior.

### Required Phase 5Y focused characterization
Before publication, prove at minimum:
- `AppSettings()` exposes `layout_mask_illustrations=False` without any bootstrap call;
- JSON round-trip, old settings without the key, `dataclasses.replace`, and spawn/pickle identity preserve the field exactly;
- bare package import remains runtime-inert;
- the path-based PPP detector and in-memory Layout detector return equivalent regions for the same image/settings and still share one algorithm;
- detector geometry/transform handling, component thresholds, padding, merging, and resource cleanup remain equivalent;
- `mask_large_illustrations_for_layout(...)` still uses the shared static detector by default and retains the same size/headlike guards;
- core/GUI/worker composition no longer needs the settings installer or detector callable rebinding;
- the Page Understanding wrapper still fails open on masking errors, closes disposable masked images, and appends identical diagnostics when enabled;
- GUI setting visibility/help/cache invalidation remains unchanged because UI mutation is explicitly outside Phase 5Y;
- full cross-platform CI, GUI smoke, compatibility runner, compile, F821, wheel, CodeQL, and security gates remain green.

Any detector-output, settings-persistence, Page Understanding, or GUI-cache behavior difference is a stop condition rather than a reason to broaden the slice.

## Remaining runtime seams after Phase 5X
Treat the remaining illustration-mask runtime as real behavior until its responsibilities are individually proven:
- `layout_illustration_mask_runtime.py` — Phase 5Y should remove only dynamic settings schema + detector rebinding; Page Understanding wrapping/diagnostics and GUI/cache mutation remain later work.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
