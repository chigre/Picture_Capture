# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5U are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5U
- production PR: **#274 — make spawn detection worker static**
- base before the production slice: `main@7b6305136d4826bfcb3106b87b13874a74cdd95f`
- fixed production head: `2419240395e9648da9d0ff3da65d78b3d4923a5b`
- validated production tree: `a7577dec0768dd900f66498f761c050b705dc54d`
- merge commit / current architecture main: `c6af81df63f02eeac7906701468e0fb8f6d018d3`
- merge tree: `a7577dec0768dd900f66498f761c050b705dc54d`

### Static spawn-detection ownership
The former `spawn_detection_runtime.py` installer seam is gone.

Before Phase 5U, two ordinary-detection workers coexisted:
- `processing.detect_entries_job(...)`, an older static worker;
- `spawn_detection_runtime.detect_entries_job_with_runtime(...)`, the spawn-safe worker dynamically installed into `processing` before `app.py` imported `detect_entries_job` by value.

The runtime worker contained real behavior and therefore was not deleted directly. Phase 5U promoted its semantics into the normal top-level `processing.detect_entries_job(...)` function while preserving the same pickleable module identity expected by Windows/macOS spawn.

The static worker now directly preserves the former runtime contract:
1. lazily imports and calls `bootstrap.worker.build_worker_services()` inside the spawned process;
2. consumes the composed `processing` and `formats` services rather than recreating installer ownership inside the job;
3. opens and normalizes the page through the worker-composed processing facade;
4. copies `AppSettings` with `replace(settings)` before applying the worker-only `detection_method="left_edge"` override, so caller settings are not mutated;
5. wraps ordinary detection in `services.capture_layout_rows(...)` exactly once;
6. reads page sections through the worker processing core;
7. writes the automatic baseline through `services.save_automatic_baseline(...)`;
8. writes final PDIC through the classification-aware `formats.write_pdic(...)`;
9. returns the same entry count and closes the image in `finally`.

GUI composition still installs processing entry classification before importing `app`, but no longer replaces `processing.detect_entries_job`. `app.py` now imports the stable static processing worker directly. Worker composition remains the owner of PDIC classification, processing entry classification, LayoutRows persistence, and the `WorkerServices` bundle.

The architecture guard no longer permits `spawn_detection_runtime.py` as legacy runtime debt.

### Phase 5U anomaly caught before validation
One intermediate branch edit reconstructed `processing.py` from a segmented source read that stopped at line 560 and accidentally omitted the existing compatibility-facade tail below that point. The compare immediately exposed an implausibly large `processing.py` deletion (`36 additions / 93 deletions`).

Production work stopped before validation. The untouched tail was fetched from the fixed main base and restored exactly. A patch-level compare then confirmed the final `processing.py` change was limited to `detect_entries_job` (`36 additions / 18 deletions`). No validation result from the malformed intermediate tree was reused.

This is an explicit recovery lesson: segmented source reads must never be treated as EOF unless file completeness is independently established; compare/diff-shape review remains mandatory before expensive validation.

### Phase 5U isolated validation
The migration used a fail-closed temporary branch workflow and removed that workflow before production publication.

Final isolated validation on the corrected tree:
- exact intended production/test path set: **8 paths, passed**;
- no production `spawn_detection_runtime.py` file remained;
- no production `install_spawn_detection_runtime`, `_spawn_detection_runtime_installed`, or `spawn_detection_runtime` references remained;
- architecture guard: passed;
- focused regressions: **36 passed**;
- full pytest suite: **1289 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed.

Focused characterization included an actual fake-`WorkerServices` invocation of the static job, proving:
- original settings remain unchanged;
- the copied worker settings receive only the `left_edge` override;
- LayoutRows capture enters before detection and exits before persistence;
- baseline write occurs before final PDIC write;
- page index, page sections, image width, pages tuple, and returned entry count are preserved.

The temporary validation workflow was removed, and the exact validated tree `a7577dec0768dd900f66498f761c050b705dc54d` was re-anchored to the live main base as one clean production commit `2419240395e9648da9d0ff3da65d78b3d4923a5b`.

### Phase 5U PR gate
Fixed-head PR #274 on `2419240395e9648da9d0ff3da65d78b3d4923a5b`:
- Ubuntu CI run 2093: passed, including pytest, Linux GUI smoke, compatibility runner, compile, F821, and wheel build;
- Windows CI run 2093: passed, including pytest, Windows GUI smoke, compatibility runner, compile, F821, and wheel build;
- macOS CI run 2093: passed, including pytest, macOS GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL run 2074 Actions: passed;
- CodeQL run 2074 Python: passed;
- Advanced Security run 1839: passed;
- PR remained mergeable with one commit and eight changed files;
- no PR comments, review threads, review submissions, or objections.

PR #274 was merged with fixed-head protection using `expected_head_sha=2419240395e9648da9d0ff3da65d78b3d4923a5b`.

### Phase 5U post-merge verification
On `main@c6af81df63f02eeac7906701468e0fb8f6d018d3`:
- merge tree exactly matched validated production tree `a7577dec0768dd900f66498f761c050b705dc54d`;
- push CI run 2094 passed on Ubuntu, Windows, and macOS;
- GUI smoke passed on all applicable platforms;
- compatibility runner / compile / F821 / wheel passed on all three platforms;
- CodeQL run 2075 Actions: passed;
- CodeQL run 2075 Python: passed.

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
- Phase 5T: the identity-only spawn-layout wrapper was deleted; `processing._ensure_layout_runtime` is directly authoritative without core-composition wrapping.
- Phase 5U: the real spawn-safe ordinary worker became static `processing.detect_entries_job`; GUI-time worker replacement and `spawn_detection_runtime.py` were removed.

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
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves the worker at action time and the fast worker remains an import-order/performance seam.

## Recommended next slice — Phase 5V
**Staticize oversized-head detection and its strong row-front/fusion authorization as one cohesive ownership slice.**

Fresh read-only inspection after Phase 5U shows that `ordinary_large_head_runtime.py` is the smallest remaining runtime file, but it is **not independently removable**.

Current behavior spans two dynamic seams:
- `ordinary_large_head_runtime.py` replaces `ordinary_large_head_evidence.detect_ordinary_large_head_entries` before `layout_core_understanding.py` imports that detector by value. The guarded detector adds page-observed ordinary-row height, the shared column-drift analysis-left safety band, semantic-column coordinate correction, and row-front authorization.
- `ordinary_large_head_role_guard.py` then mutates `ordinary_large_head_runtime.candidate_starts_at_row_front` to the stricter row-front/strong-oversized rule and also wraps `ordinary_evidence_fusion._force_oversized_head_rows` so weak large-head evidence is consumed without manufacturing a new entry row.

Therefore deleting only `ordinary_large_head_runtime.py` would change behavior and/or import-order semantics. Phase 5V must remove both dynamic mutations together while preserving the exact detector/fusion policy.

### Safest Phase 5V architecture
- make the guarded detector the ordinary static implementation in `ordinary_large_head_evidence.py`, including:
  - `observed_body_line_reference(...)`;
  - the shared `layout_column_drift._analysis_left_for_column(...)` widened analysis band;
  - semantic-column-local coordinate correction before row-front checks;
  - stacked-head splitting and current deduplication semantics;
  - strict row-front authorization with the existing `HARD_ROLE_OVERRIDE_RATIO = 1.65` behavior for body-row role changes;
- make strong/weak large-head fusion handling explicit/static in `ordinary_evidence_fusion.py` rather than wrapping `_force_oversized_head_rows` at bootstrap time;
- remove `install_ordinary_large_head_runtime()` and `install_ordinary_large_head_role_guard()` from `bootstrap/core.py` only after static behavior is equivalent;
- delete `ordinary_large_head_runtime.py` once no production consumer remains;
- either retain `ordinary_large_head_role_guard.py` as a pure non-mutating policy/helper module or fold its small static policy into the normal evidence/fusion owners; do not leave an installer behind;
- ratchet architecture/source-contract tests so import order can no longer select a weaker detector;
- do **not** combine Phase 5V with entry-classification retirement, illustration-mask ownership, or unlined-fast-path work.

### Required Phase 5V focused characterization
Before publication, prove at minimum:
- `layout_core_understanding` receives the final guarded detector without bootstrap mutation;
- page-observed line-height reference remains identical on noisy/underestimated-layout cases;
- later-column analysis still uses the shared column-drift left safety band without altering semantic column bounds;
- semantic-local candidate coordinates are unchanged after widened-band analysis;
- weak oversized candidates on body rows are rejected/consumed and cannot fall through to generic nearest-row promotion;
- existing entry/headword rows retain the intended looser candidate allowance;
- body-row role override still requires the current strong ratio and width/aspect guards;
- consecutive stacked oversized heads remain separable and deduplicated correctly;
- static column drift cannot replace or weaken the guarded detector;
- `bootstrap/core.py` no longer mutates detector or fusion callables for this feature;
- no `install_ordinary_large_head_runtime` or installer-state dependency remains;
- full cross-platform CI, GUI smoke, compatibility runner, compile, F821, wheel, CodeQL, and security gates remain green.

Any behavior difference between the current two-stage runtime/role-guard chain and the proposed static ownership is a stop condition rather than a reason to weaken tests.

## Remaining runtime seams after Phase 5U
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `ordinary_large_head_runtime.py` — recommended Phase 5V, but only together with removal of the related dynamic role/fusion guard mutations;
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
