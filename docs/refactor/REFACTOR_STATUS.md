# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5W are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5W
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

## Recommended next slice — Phase 5X
**Retire `entry_classification_runtime.py` by promoting its three real behaviors into their existing static processing owners as one cohesive classification/OCR slice.**

Fresh read-only inspection after Phase 5W shows this is safer than taking the remaining illustration-mask runtime next. `layout_illustration_mask_runtime.py` still combines dynamic `AppSettings` extension, shared illustration-detector redirection, a fail-open Page Understanding image-mask wrapper, diagnostics, and GUI settings/cache integration. Entry classification is also real behavior, but its mutation targets are already explicit and separately identifiable.

Current entry-classification runtime behavior spans three mutations:
1. it wraps `processing._ordinary_entries_from_layout_roles(...)` so each final Layout entry row copies canonical line classification metadata to the materialized `Entry`, including oversized-CJK OCR hints and observed head/ordinary-row heights;
2. it replaces `processing_core._ordinary_marker_local_crop(...)` (and the facade alias) with the canonical classification-aware `entry_ocr_crop_box(...)` path and derives the oversized flag from `get_entry_classification(entry)`;
3. it replaces `processing_core.ocr_existing_entry_words_from_markers(...)` (and the facade alias) with the shared multi-engine `OcrChannelSession` implementation, preserving one session per page, Paddle candidate parsing, ordinary/oversized handling, replacement rules, provenance fields, stats, and the hard invariant that marker OCR cannot move line coordinates.

Bootstrap currently installs this runtime from core composition and redundantly/idempotently from GUI/worker composition. CLI deliberately calls `build_core_services()` before importing processing callables by value, while `DetectionController` imports the processing facade callable by value during GUI app import. Static ownership can remove this import-order dependency rather than emulate it.

### Safest Phase 5X architecture
- fold classification metadata attachment directly into the normal `processing._ordinary_entries_from_layout_roles(...)` materializer after each entry is created, preserving refined separator Y and exact line-to-entry correspondence;
- make the current classification-aware crop the normal `processing_core._ordinary_marker_local_crop(...)` implementation, backed by `entry_ocr_crop_box(...)` and `get_entry_classification(...)`;
- promote the current multi-engine marker OCR implementation into the normal top-level `processing_core.ocr_existing_entry_words_from_markers(...)` function;
- let the existing `processing` facade copy the final static core crop/OCR callables at import time; do not add a new proxy or second installer;
- remove `install_processing_entry_classification(...)` from core, GUI, and worker bootstrap only after static behavior is equivalent;
- delete `entry_classification_runtime.py` once no production consumer remains;
- ratchet architecture/source-contract tests so classification/OCR behavior can no longer depend on bootstrap mutation order;
- preserve the separate PDIC classification/persistence owner in `entry_classification.py`; do **not** combine this slice with PDIC-format changes, review UI changes, or illustration-mask runtime retirement.

### Required Phase 5X focused characterization
Before publication, prove at minimum:
- every final Layout entry row receives the same `EntryClassification` metadata as the current runtime path;
- oversized rows still set `ocr_oversized_cjk`, `ocr_single_cjk`, `ocr_visual_run_height`, and `ocr_line_height_reference` under the same conditions;
- refined separator Y/materialized coordinates remain unchanged by classification attachment;
- existing-marker OCR uses the same `entry_ocr_crop_box(...)` geometry and returns the same oversized flag;
- ordinary and oversized marker crops remain covered across transformed/Profile geometry cases;
- one `OcrChannelSession` is reused per page, with the same engine-plan arbitration and Paddle record parsing;
- OCR replacement/lowercase rules, confidence, `ocr_source`, `final_engine`, issue type, and fill/fail/skip stats remain equivalent;
- marker OCR still raises if any entry coordinate changes;
- CLI, GUI `DetectionController`, and worker/bootstrap paths all resolve the final static callable without installer order;
- no `install_processing_entry_classification`, `_entry_classification_runtime_installed`, `_entry_classification_crop_installed`, or `_entry_marker_ocr_dispatch_installed` production dependency remains;
- full cross-platform CI, GUI smoke, compatibility runner, compile, F821, wheel, CodeQL, and security gates remain green.

Any behavior difference between the current installed classification/OCR path and the proposed static owners is a stop condition rather than a reason to weaken tests.

## Remaining runtime seams after Phase 5W
Treat these as real compatibility/algorithm seams until individually proven:
- `entry_classification_runtime.py` — recommended Phase 5X; three explicit classification/marker-OCR mutations with natural static owners already present;
- `layout_illustration_mask_runtime.py` — keep for a later dedicated slice because it still couples settings schema, detector ownership, Page Understanding masking, diagnostics, and GUI integration.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
