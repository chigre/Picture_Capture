# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5T are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5T
- production PR: **#272 — retire identity-only spawn layout runtime**
- base before the production slice: `main@8bb786cff5ac49098cdd4a6c68c5494d79a3364b`
- initially published clean head: `1d6c6be55b0bc9fe0d9389b20c28bc26d8d4de43`
- final fixed PR head: `20b2dab8a8a5d734be783c1f9ccf054d4b775a4a`
- validated production tree: `c3d9b11d1931be7bf4155611b6a28e3a50274b5f`
- merge commit / current architecture main: `61a96f1a5a80800ac06b48d3d5afb53a5c1ced83`
- merge tree: `c3d9b11d1931be7bf4155611b6a28e3a50274b5f`

### Static spawn-layout ownership
The former `spawn_layout_runtime.py` compatibility wrapper is gone.

Before Phase 5T, `install_spawn_layout_runtime(processing_module)` captured `processing_module._ensure_layout_runtime`, replaced it with a `@wraps` function that only called the captured function, and set `_pc_spawn_layout_runtime_installed = True`. It no longer added any behavior after Phase 5S.

The authoritative layout-preparation path remains directly in `processing._ensure_layout_runtime()` itself. That helper still:
1. binds `dictionary_page_design.detect_entries_from_page_design` to the refined implementation;
2. installs robust line-start handling;
3. installs physical-indent inference.

`processing._understand_page_current(...)` still calls `_ensure_layout_runtime()` before both layout-only and full Page Understanding paths. Core composition no longer mutates the `_ensure_layout_runtime` function object, and the architecture guard no longer permits `spawn_layout_runtime.py` as runtime debt.

Phase 5T deliberately did **not** change spawn detection, entry classification, large-head handling, illustration masking, or the unlined fast path.

### Phase 5T isolated validation
The migration used a temporary branch-only validation workflow and removed that workflow before production publication.

Final isolated validation:
- exact intended production/test diff shape: **7 paths, passed**;
- no production `install_spawn_layout_runtime` or `_pc_spawn_layout_runtime_installed` references remained;
- architecture guard: passed;
- focused regressions: passed;
- full pytest suite: passed;
- compileall: passed;
- Ruff F821: passed.

The final production tree was then re-anchored as one clean commit on `main@8bb786cff5ac49098cdd4a6c68c5494d79a3364b`.

### Phase 5T PR gate
The initially published clean head did not receive the repository's normal `pull_request` CI event. Because `ci.yml` is configured for every PR to `main`, absence of a CI run was treated as an incomplete gate rather than as success.

To trigger a fresh `synchronize` event without changing code, the PR head was regenerated with the **same parent and same validated tree**. The replacement head was `20b2dab8a8a5d734be783c1f9ccf054d4b775a4a`; tree content remained `c3d9b11d1931be7bf4155611b6a28e3a50274b5f`.

On that fixed head:
- CI run 2088: passed;
- CI run 2089: passed;
- Ubuntu: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- Windows: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- macOS: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security dynamic PR check: passed;
- no PR comments, review threads, review submissions, or objections.

PR #272 was merged with fixed-head protection using `expected_head_sha=20b2dab8a8a5d734be783c1f9ccf054d4b775a4a`.

### Phase 5T post-merge verification
On `main@61a96f1a5a80800ac06b48d3d5afb53a5c1ced83`:
- merge tree exactly matched the validated production tree `c3d9b11d1931be7bf4155611b6a28e3a50274b5f`;
- push CI run 2090 passed on Ubuntu, Windows, and macOS;
- GUI smoke passed on all applicable platforms;
- compatibility runner / compile / F821 / wheel passed on all three platforms;
- CodeQL run 2071 Actions: passed;
- CodeQL run 2071 Python: passed.

No post-merge behavior or security regression was observed.

## Previous completed Phase 5 ownership
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership backed by `unicode_nonbmp_input.py`.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native `AppSettings` + static settings/UI + direct non-runtime `overlay_opacity.py` rendering.
- Phase 5P: illustration fill opacity became native `AppSettings` + static settings/UI + direct non-runtime `illustration_fill_opacity.py` rendering and refresh ownership.
- Phase 5Q: long-band logical row recovery became static in `layout_physical_indent.py`.
- Phase 5R: character-height fallback became an explicit post-raw-cache step in `layout_detection.py`, backed by non-runtime `layout_character_height.py`.
- Phase 5S: column-drift first-X remeasurement became an explicit finalization step in `dictionary_page_layout_policy.py`, backed by non-runtime `layout_column_drift.py`.
- Phase 5T: the identity-only spawn-layout wrapper was deleted; `processing._ensure_layout_runtime` is now directly authoritative without core-composition wrapping.

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
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5U
**Retire the dynamic spawn-detection installer by promoting its existing worker semantics into static `processing.detect_entries_job` ownership.**

Fresh read-only inspection after Phase 5T shows that `spawn_detection_runtime.py` is **not** an identity wrapper and must not simply be deleted.

Two worker implementations currently coexist:
- `processing.detect_entries_job(...)` is the older top-level processing worker;
- `spawn_detection_runtime.detect_entries_job_with_runtime(...)` is the worker actually installed for the GUI before `app.py` imports `detect_entries_job` by value.

The installed runtime worker adds important behavior that the older static worker does not fully own: it builds worker services in the spawned interpreter, uses the worker composition's `processing` and `formats`, captures physical Layout rows through `services.capture_layout_rows(...)`, writes the automatic baseline, and emits PDIC through the classification-aware formats writer. It is also intentionally top-level/pickleable for Windows/macOS spawn.

### Safest Phase 5U architecture
- move the exact current `detect_entries_job_with_runtime(...)` behavior into the normal top-level `processing.detect_entries_job(...)` implementation, retaining its spawn-pickleable top-level identity;
- keep the lazy `build_worker_services()` call inside worker execution so a fresh spawned interpreter receives the same composition as today;
- preserve the existing LayoutRows capture, automatic-baseline write, classification-aware PDIC write, page-section handling, `detection_method="left_edge"` worker override, and image lifetime exactly;
- remove `install_spawn_detection_runtime(...)` and its bootstrap/gui import/call only after the static worker is behaviorally equivalent;
- delete `spawn_detection_runtime.py` only when no production consumer remains;
- ratchet architecture/source-contract tests to assert static processing ownership and absence of installer mutation;
- do **not** combine this slice with entry-classification retirement, large-head runtime changes, illustration-mask runtime changes, or unlined-fast-path work.

### Required Phase 5U focused characterization
Before publication, prove at minimum:
- `processing.detect_entries_job` is top-level and pickleable under spawn without a bootstrap-time function replacement;
- GUI/app import receives the same static processing worker without import-order mutation;
- a worker invocation still builds worker services in the spawned process;
- LayoutRows capture still occurs exactly once around ordinary detection;
- automatic-baseline and final PDIC writes remain equivalent to the current installed worker path;
- classification-aware formats ownership is preserved;
- physical page coordinates and entry counts are unchanged;
- GUI and worker composition continue to share the intended `processing` facade;
- no `install_spawn_detection_runtime` / `_spawn_detection_runtime_installed` production dependency remains;
- full cross-platform CI, GUI smoke, compatibility runner, compile, F821, wheel, CodeQL, and security gates remain green.

Any difference between the current runtime worker and the proposed static worker is a stop condition; do not paper over it by weakening tests or falling back to the older `processing.detect_entries_job` semantics.

## Remaining runtime seams after Phase 5T
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `spawn_detection_runtime.py` — recommended Phase 5U; real worker behavior, not identity plumbing;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
