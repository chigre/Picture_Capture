# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5Y are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5Y
- production PR: **#282 — make illustration settings and detector static**
- production base: `d3c9128f62e759c45f388f0f08af1dfb558274e8`
- clean production head: `1d3c03fa02c54c7d49372fd2ca68172fc10ceb33`
- validated production tree: `0c622b968ee4fc176ede6b36cf5ff56f6bb7f18d`
- production merge: `159ba4d30873797ac7d80c53b56146b6a07fd5e7`
- post-merge export-repair PR: **#283 — repair Phase 5Y runtime exports**
- repair head: `8c1d7efcdb60061e86151efeb47cea00055ccc62`
- final Phase 5Y main: `5d0a2ccfeb2a26e66246de5077342c5033097164`
- final tree: `7ab402eee95cc305bec2b9d5882f7c3d88489819`

### Native illustration-mask setting and static detector
Phase 5Y removed the first two import-order responsibilities from `layout_illustration_mask_runtime.py` while deliberately retaining the Page Understanding masking wrapper and GUI/cache mutation for later slices.

`AppSettings` now natively owns `layout_mask_illustrations: bool = False`. The dynamic AppSettings subclass/rebind path is gone, so backward defaults, JSON persistence, `dataclasses.replace`, and spawn/pickle identity all use the ordinary dataclass contract.

`processing_core` now statically owns the shared in-memory illustration detector. The historical path-based PPP detector and Layout masking consume the same implementation without bootstrap callable replacement. Core composition no longer installs an illustration setting or rebinds detector callables.

The remaining runtime file intentionally owns only:
1. fail-open preprocessing around `processing._understand_page_current(...)`, including disposable masked-image lifetime and `layout.reason` diagnostics;
2. `SettingsDialog` checkbox/help/label metadata;
3. Layout visualization cache-key invalidation when the switch changes.

Phase 5Y did **not** alter PPP format, illustration crop semantics, component thresholds, Layout mask thresholds, oversized-head protection, or the default-disabled behavior.

### Phase 5Y isolated validation
A temporary fail-closed branch workflow was removed before publication.

Final isolated validation:
- exact intended production/test diff shape: **6 paths, passed**;
- native `layout_mask_illustrations` setting without bootstrap: passed;
- `dataclasses.replace` and pickle identity/value: passed;
- static processing/core detector ownership before and after core composition: passed;
- retained Page Understanding wrapper state: passed;
- architecture guard: passed;
- focused regressions: **194 passed**;
- full pytest suite: **1291 passed, 1 existing Pillow deprecation warning**;
- compileall: passed;
- Ruff F821: passed.

The exact validated production tree `0c622b968ee4fc176ede6b36cf5ff56f6bb7f18d` was published as one clean commit `1d3c03fa02c54c7d49372fd2ca68172fc10ceb33`.

### Phase 5Y PR and post-merge gate
Fixed-head PR #282:
- CI run 2109 Ubuntu/Windows/macOS: passed, including platform GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL run 2090 Actions/Python: passed;
- Advanced Security run 1847: passed;
- no comments, review threads, review submissions, or objections.

PR #282 merged as `159ba4d30873797ac7d80c53b56146b6a07fd5e7`, retaining validated tree `0c622b968ee4fc176ede6b36cf5ff56f6bb7f18d`.

Post-merge production verification:
- push CI run 2110 Ubuntu/Windows/macOS: passed;
- CodeQL run 2091 Actions/Python: passed.

### Post-merge export-contract repair
Read-only post-merge review caught one narrow source-contract defect before checkpoint: `layout_illustration_mask_runtime.__all__` still advertised three symbols moved out by Phase 5Y:
- `detect_illustration_regions_from_image`;
- `detect_illustration_regions_from_path`;
- `install_layout_illustration_mask_settings`.

No current production consumer used star-import, but the advertised module export surface was internally invalid. This was treated as a real anomaly and repaired before checkpoint rather than deferred.

Repair PR #283 changed only two files:
- removed the three stale `__all__` names;
- added a regression proving every advertised runtime export resolves and `from ... import *` succeeds.

Repair validation/gates:
- exact repair diff: **2 files**;
- runtime export-contract test: passed;
- compileall/F821: passed;
- CI run 2111 Ubuntu/Windows/macOS: passed;
- CodeQL run 2092 Actions/Python: passed;
- Advanced Security run 1848: passed;
- no review/comment/thread objections.

PR #283 merged as `5d0a2ccfeb2a26e66246de5077342c5033097164` with final tree `7ab402eee95cc305bec2b9d5882f7c3d88489819`.

Post-repair main verification:
- push CI run 2112 Ubuntu/Windows/macOS: passed;
- CodeQL run 2093 Actions/Python: passed.

Phase 5Y is therefore closed only at `main@5d0a2ccfeb2a26e66246de5077342c5033097164`, not at the earlier production merge.

## Completed Phase 5 ownership milestones
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership backed by `unicode_nonbmp_input.py`.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native settings + static UI/rendering ownership.
- Phase 5P: illustration fill opacity became native settings + static UI/rendering ownership.
- Phase 5Q: long-band logical row recovery became static in `layout_physical_indent.py`.
- Phase 5R: character-height fallback became a static post-raw-cache step.
- Phase 5S: column-drift first-X remeasurement became explicit static policy finalization.
- Phase 5T: identity-only spawn-layout wrapper was removed.
- Phase 5U: spawn-safe ordinary worker became static `processing.detect_entries_job`.
- Phase 5V: guarded oversized-head detection and row/fusion authorization became static.
- Phase 5W: unlined physical-row fast worker became static `unlined_line_export.export_unlined_page_job`.
- Phase 5X: Layout-entry classification and existing-marker crop/OCR became static processing ownership.
- Phase 5Y: illustration-mask setting became native and the shared PPP/Layout detector became static `processing_core` ownership.

Earlier Phase 5A–5K details remain available in the repository's checkpoint history; they are complete and are not reopened by this checkpoint.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper -> `DetectionController`; quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper -> `CropController` -> app-owned shared parallel batch runner.
- Unlined page worker: static `unlined_line_export.export_unlined_page_job(...)` -> `resolve_unlined_physical_rows(...)`.
- Training package: app wrapper -> `ExportController`.
- Layout visualization: LayoutRows capture, indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are static/non-runtime ownership.
- Windows/Tk supplementary Unicode repair: explicit `PictureCaptureApp` lifecycle -> `unicode_nonbmp_input.py`.
- Overlay anchoring: `overlay_line_anchor.py`.
- Guide/headword line opacity: native settings + direct non-runtime rendering/UI ownership.
- Illustration fill opacity: native settings + direct non-runtime rendering/UI ownership.
- Long-band row recovery: static `layout_physical_indent._logical_slots_for_oversized_run(...)`.
- Character-height fallback: static `layout_detection.detect_layout_parameters(...)` -> `layout_character_height.apply_character_height_fallback(...)` after raw-cache retrieval.
- Column-drift remeasurement: static layout policy -> `layout_column_drift` helpers.
- Spawn layout preparation: direct `processing._ensure_layout_runtime()` ownership; no wrapper remains.
- Spawn ordinary detection: static top-level `processing.detect_entries_job(...)` consuming `build_worker_services()`.
- Oversized-head detection/authorization: static `ordinary_large_head_evidence` + pure policy + direct evidence-fusion strength gate.
- Entry classification / existing-marker OCR: static `processing._ordinary_entries_from_layout_roles(...)` + static `processing_core._ordinary_marker_local_crop(...)` / `ocr_existing_entry_words_from_markers(...)`.
- Illustration-mask setting/detector: native `AppSettings.layout_mask_illustrations` + static `processing_core.detect_illustration_regions_from_image(...)`.
- Illustration-mask compatibility wrapper: `layout_illustration_mask_runtime.py` remains only for Page Understanding masking/diagnostics and SettingsDialog/Layout-cache integration.

## Recommended next slice — Phase 5Z
**Staticize only the Page Understanding illustration-masking wrapper; keep SettingsDialog/cache-key mutation for the following slice.**

After Phase 5Y, the remaining runtime file no longer owns settings schema or detector selection. Its next separable responsibility is the wrapper around `processing._understand_page_current(...)`.

### Safest Phase 5Z architecture
- move the current optional preprocessing directly into static `processing._understand_page_current(...)` or a normal helper called by it;
- preserve disabled-mode passthrough exactly;
- when enabled, preserve `mask_large_illustrations_for_layout(...)` fail-open behavior: any masking/filter error falls back to the original analysis image rather than making Layout unavailable;
- preserve identical `IllustrationMaskStats` diagnostics appended to `layout.reason`;
- preserve disposable masked-image lifetime and close it only when a separate image copy was created;
- preserve both `layout_only=True` and full Page Understanding routes, page index, and page sections;
- remove `install_layout_illustration_mask_runtime(processing_module)` and `_pc_layout_illustration_mask_installed` only after static behavior is proven equivalent;
- keep `install_layout_illustration_mask_ui(app_module)` and the cache-key mutation unchanged for this phase;
- do **not** delete `layout_illustration_mask_runtime.py` until the UI/cache responsibility has independently migrated.

### Required Phase 5Z focused characterization
Before publication, prove at minimum:
- disabled masking calls the same underlying Layout/Page Understanding path with the original image object;
- enabled masking passes the disposable masked image into both layout-only and full Page Understanding routes;
- masking detector/filter exceptions fail open to the original image;
- the temporary image is closed exactly when it is a separate object, including underlying-understanding exceptions;
- mask diagnostics remain equivalent in `layout.reason`;
- no bootstrap callable replacement or `_pc_layout_illustration_mask_installed` dependency remains;
- GUI checkbox/help/cache invalidation remains unchanged because it is outside Phase 5Z;
- full cross-platform CI, GUI smoke, compatibility runner, compile, F821, wheel, CodeQL, and security gates remain green.

Any difference in fail-open behavior, image lifetime, diagnostics, or layout-only/full routing is a stop condition rather than a reason to broaden the slice.

## Remaining runtime seams after Phase 5Y
Treat the final illustration-mask runtime as real behavior until its two remaining responsibilities are independently proven:
- `layout_illustration_mask_runtime.py` — Phase 5Z should remove only Page Understanding wrapping/diagnostics; SettingsDialog/cache-key mutation remains the final later slice.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
