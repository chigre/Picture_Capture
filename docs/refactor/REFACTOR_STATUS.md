# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5V are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5V
- production PR: **#276 — make large-head detection and authorization static**
- base before the production slice: `main@e5e4ab588bd37893bb5eaa2af683c771614d44f7`
- clean production head: `6e10e631a39a75f898378f7257e72e2f5df24926`
- validated production tree: `1b643a5fb1c41402a0e36cb9e048bbea0394dd50`
- merge commit / current architecture main: `9ae55e6d368a8e57b3dfd627b00aa90d227e4ded`
- merge tree: `1b643a5fb1c41402a0e36cb9e048bbea0394dd50`

### Static oversized-head ownership
The former `ordinary_large_head_runtime.py` installer seam is gone.

Before Phase 5V, large-head behavior was split across two dynamic mutations:
1. `ordinary_large_head_runtime.py` replaced `ordinary_large_head_evidence.detect_ordinary_large_head_entries` before Layout Core imported the detector by value. The installed detector added page-observed row scale, the shared column-drift left analysis band, semantic-column coordinate correction, and row-front authorization.
2. `ordinary_large_head_role_guard.py` then replaced the runtime module's row-front helper with the stricter policy and wrapped `ordinary_evidence_fusion._force_oversized_head_rows` so weak large-head evidence was consumed instead of falling through to generic nearest-row promotion.

Phase 5V moved both responsibilities into ordinary static owners rather than deleting only one installer.

Current ownership:
- `ordinary_large_head_evidence.py` is the final detector imported by Layout Core. It statically owns:
  - existing component/group/split candidate logic;
  - `observed_body_line_reference(...)` for page-observed ordinary-row scale;
  - `layout_column_drift._analysis_left_for_column(...)` widened analysis safety for later columns;
  - conversion from widened-band local X back to semantic-column-local coordinates before authorization;
  - strict row-front authorization;
  - the same source-coordinate emission, metadata, sorting, deduplication, and image lifetime.
- `ordinary_large_head_role_guard.py` is now a pure mutation-free policy/helper module. It retains `HARD_ROLE_OVERRIDE_RATIO = 1.65`, strict first-ink/full-height-anchor row-front geometry, and body-row width/aspect guards. Its `strong_ordinary_large_head(...)` helper is called directly by fusion.
- `ordinary_evidence_fusion.py` now consumes weak ordinary-large-head evidence directly. Weak observations cannot fall through to generic nearest-row promotion; strong observations retain the existing `_force_oversized_head_rows(...)` behavior.
- `bootstrap/core.py` no longer imports or calls either large-head installer.
- the architecture guard no longer permits `ordinary_large_head_runtime.py` as runtime debt.

Phase 5V deliberately did **not** change entry-classification runtime ownership, illustration-mask runtime ownership, unlined export output/filter semantics, or the remaining GUI/runtime contracts.

### Phase 5V isolated validation
A temporary fail-closed branch workflow was used and removed before publication.

Final isolated validation:
- exact intended production/test diff shape: **9 paths, passed**;
- `ordinary_large_head_runtime.py` removed;
- zero production references to `ordinary_large_head_runtime`, `install_ordinary_large_head_runtime`, `install_ordinary_large_head_role_guard`, `_row_front_runtime_installed`, `_large_head_role_guard_installed`, or `detect_ordinary_large_head_entries_guarded`;
- architecture guard: passed;
- focused regressions: **35 passed**;
- full pytest suite: **1289 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed.

Focused characterization retained the behavioral cases that matter for the migration:
- an underestimated Layout scale is corrected by observed body-row height;
- a tall object in the middle of definition text cannot become a headword;
- a true oversized head after a small prefix remains eligible through the full-height anchor;
- later-column large-head analysis still uses the shared left safety band without changing semantic column bounds;
- semantic-local X correction remains in place after widened-band analysis;
- weak large-head evidence cannot manufacture a new entry through fallback;
- the strong `1.65` role-override threshold and width/aspect authorization remain intact;
- stacked oversized heads remain supported by the existing split/dedup logic;
- static column drift cannot replace the large-head detector.

The temporary validation workflow was deleted before publication. The exact validated tree `1b643a5fb1c41402a0e36cb9e048bbea0394dd50` was then re-anchored to the live main base as one clean production commit `6e10e631a39a75f898378f7257e72e2f5df24926`.

### Phase 5V PR gate
Fixed-head PR #276 on `6e10e631a39a75f898378f7257e72e2f5df24926`:
- CI run 2097 Ubuntu: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- CI run 2097 Windows: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- CI run 2097 macOS: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL run 2078 Actions: passed;
- CodeQL run 2078 Python: passed;
- Advanced Security run 1841: passed;
- PR remained mergeable with one commit and nine changed files;
- no PR comments, review threads, review submissions, or objections.

PR #276 was merged with fixed-head protection using `expected_head_sha=6e10e631a39a75f898378f7257e72e2f5df24926`.

### Phase 5V post-merge verification
On `main@9ae55e6d368a8e57b3dfd627b00aa90d227e4ded`:
- merge tree exactly matched validated production tree `1b643a5fb1c41402a0e36cb9e048bbea0394dd50`;
- push CI run 2098 passed on Ubuntu, Windows, and macOS;
- GUI smoke passed on all applicable platforms;
- compatibility runner / compile / F821 / wheel passed on all three platforms;
- CodeQL run 2079 Actions: passed;
- CodeQL run 2079 Python: passed.

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
- Spawn layout preparation: direct `processing._ensure_layout_runtime()` ownership; no compatibility wrapper remains.
- Spawn ordinary detection: static top-level `processing.detect_entries_job(...)` -> lazy `build_worker_services()` consumption; no GUI-time replacement remains.
- Oversized-head detection/authorization: static `ordinary_large_head_evidence` + pure `ordinary_large_head_role_guard` policy + direct `ordinary_evidence_fusion` strength gate.

## Recommended next slice — Phase 5W
**Retire `unlined_fast_path_runtime.py` by making its existing spawn-safe physical-row worker the normal static `unlined_line_export.export_unlined_page_job`.**

Fresh read-only inspection after Phase 5V shows this is the narrowest remaining runtime seam.

Current state:
- `unlined_line_export.export_unlined_page_job(...)` is an older top-level spawn-safe worker that builds an analysis image and runs the complete `understand_layout_core(...)` path for every selected page.
- `unlined_fast_path_runtime.export_unlined_page_job_fast(...)` is the worker installed by GUI bootstrap. It preserves the same PDIC matching, page sections, filtering, saving, result shape, and image lifetime, but resolves only the physical rows required by this QA export through `resolve_unlined_physical_rows(...)`.
- `resolve_unlined_physical_rows(...)` already owns the intended recovery order: persisted LayoutRows cache -> Profile-geometry physical projection -> reliable physical layout detection fallback. It stops before symbol/large-head semantic evidence.
- `CropController` intentionally imports `unlined_line_export` as a module and resolves `unlined_export.export_unlined_page_job` at action time. The legacy `run_unlined_export(...)` helper also calls the module-global top-level worker. Therefore no import-by-value compatibility layer is required once the normal worker itself becomes the fast implementation.

### Safest Phase 5W architecture
- replace the body of the existing top-level `unlined_line_export.export_unlined_page_job(...)` with the exact current fast-worker semantics;
- import/use `resolve_unlined_physical_rows(...)` directly from the ordinary module;
- keep the existing function name, module identity, signature, return type, and spawn-pickleable top-level identity;
- preserve PDIC reads, page-section reads, `unlined_rows_from_layout(...)`, `_save_unlined_rows(...)`, blank-filter ordering, merge-by-page behavior, result counters, and image lifetime exactly;
- preserve `physical_reliable=False` result behavior when no physical layout can be resolved;
- remove `install_unlined_fast_path()` from GUI composition only after the static worker is behaviorally equivalent;
- delete `unlined_fast_path_runtime.py` once no production consumer remains;
- remove now-unused full-Layout-only imports from `unlined_line_export.py` if source contracts permit;
- ratchet architecture/source-contract tests to assert direct static physical-row ownership;
- do **not** combine this slice with entry-classification runtime retirement or illustration-mask ownership.

### Required Phase 5W focused characterization
Before publication, prove at minimum:
- `unlined_line_export.export_unlined_page_job` remains top-level and spawn-pickleable;
- no GUI/bootstrap mutation is needed to obtain the fast worker;
- CropController continues to resolve the ordinary module worker at action time;
- cache/Profile/reliable-physical fallback order remains owned by `resolve_unlined_physical_rows(...)`;
- full Layout Core semantic enrichment is not called by the static worker;
- PDIC-to-Layout row matching and page-section filtering remain unchanged;
- blankness is still measured before white-border trimming;
- merge-by-page and per-row output naming/manifests remain unchanged;
- all `UnlinedPageResult` counters and the `physical_reliable` flag are equivalent to the current installed fast path;
- no `install_unlined_fast_path` / `_physical_rows_fast_path_installed` production dependency remains;
- full cross-platform CI, GUI smoke, compatibility runner, compile, F821, wheel, CodeQL, and security gates remain green.

Any behavioral difference between the currently installed fast worker and the proposed static worker is a stop condition; do not fall back to the older full-Layout worker merely to satisfy tests.

## Remaining runtime seams after Phase 5V
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py` — multiple real behaviors: final Layout classification materialization, canonical marker OCR crop, and multi-engine marker OCR dispatch;
- `layout_illustration_mask_runtime.py` — multiple real behaviors: native setting extension, shared PPP detector redirection, Page Understanding pre-mask wrapper, and GUI settings/cache integration;
- `unlined_fast_path_runtime.py` — recommended Phase 5W; a narrow worker-replacement/performance seam whose behavior can be promoted directly to the existing top-level exporter worker.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
