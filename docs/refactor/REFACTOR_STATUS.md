# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and the relevant source paths before writing production code. Historical SHAs below are checkpoints, not assumptions about a future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5F are complete.**

Phase 4 controller decomposition is complete through the approved Detection batch-processing boundary. Phase 5 has progressively removed runtime method/UI/worker ownership from ordinary drawing, selected-scope single-line crop, unlined-line export, and training-package export.

## Architecture checkpoint
- Last completed architecture PR: **#242 — Phase 5F: route training export through ExportController**
- Phase 5F architecture merge: `f62f056a51fddae4c05fbd7bc93261330dac2db6`
- Phase 5F validated production commit: `42011c29fcce9112a11922a90049195609f31896`
- Phase 5F validated/merged production tree: `2a4eae1866d309365d50aa11196ac056ee740394`
- Previous Phase 5E PR: #240 — retire unlined export runtime installer
- Phase 5E architecture merge: `dcb916c352d9eb15c4866252698ee1abb3de9392`
- Phase 5D PR: #238 — route single-line export through shared batch runner
- Phase 5D architecture merge: `b648fd849f56463b61574b509a2665239bf8c5e3`
- Phase 5C PR: #236 — construct single-line action in normal UI
- Phase 5B PR: #234 — explicit selected-scope single-line method ownership
- Phase 5A PR: #232 — retire ordinary-action runtime monkey patch
- Phase 4Y PR: #230 — `auto_detect_current(...)` through `DetectionController`
- Phase 4X PR: #229 — `batch_ocr()` through `DetectionController`
- Current production architecture PR: none after the Phase 5F merge

## Current explicit controller structure
Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection
`DetectionController` owns ordinary OCR-independent drawing, Paddle setup, combined/OCR draw actions, scoped OCR routing, `batch_auto_detect()`, `batch_ocr()`, and `auto_detect_current(...)`.

`PictureCaptureApp.run_normal_draw_action()` is an explicit compatibility wrapper. `ordinary_action_runtime.py` no longer contains an installer; it currently exists only for the reusable OCR-independent quick-settings helper `_apply_quick_settings_for_ordinary(...)`, imported by DetectionController and CropController.

### Crop / single-line
Explicit path:

`PictureCaptureApp.split_single_lines_selected_scope()` → `CropController.split_single_lines_selected_scope()` → app-owned `_start_parallel_batch_task(...)` → `single_line_parallel.single_line_page_job(...)`.

The main single-line action no longer owns runtime method injection, runtime UI construction, or a private thread/queue/Tk-poll loop.

### Crop / unlined-line export
Explicit path:

`PictureCaptureApp.export_unlined_rows_selected_scope()` → `CropController.export_unlined_rows_selected_scope()` → app-owned `_start_parallel_batch_task(...)` → runtime-resolved `unlined_line_export.export_unlined_page_job(...)`.

Phase 5E removed `postproduction_single_line_runtime.py` and `unlined_line_export_ui.py`. The visible postproduction row is constructed normally as:

`单行切图` → `未画线行导出` → `词条切图` → `插图切图`

`unlined_fast_path_runtime` remains intentionally separate: bootstrap still installs the physical-row/LayoutRows/Profile worker optimization after app/controller import. `CropController` must continue resolving `unlined_export.export_unlined_page_job` from the module at action time; changing this to a by-value top-level worker import would bypass the installed fast path.

### Export / training-package export after Phase 5F
Explicit path:

`PictureCaptureApp.export_training_package()` → `ExportController.export_training_package()` → app-owned `_start_batch_task(...)`, with stopped-export cleanup through app-owned `_start_ui_worker(...)`.

Ownership after Phase 5F:
- `PictureCaptureApp.export_training_package()` is a compatibility wrapper only;
- GUI bootstrap no longer imports or assigns `training_export_ui.export_training_package_selected_range` onto the app class;
- `ExportController` owns main-window scope selection, PDIC filtering, confirmation, staging setup, project-context copy, per-page export coordination, manifest/ZIP finalization, cancellation cleanup, completion UI, and async stopped-export cleanup;
- `training_export_ui.export_training_package_selected_range()` remains only as a thin compatibility shim into the controller;
- `training_export.py`, training-v3/page-understanding wrappers, archive format, manifest semantics, and the generic batch/UI-worker APIs were not changed.

## Phase 5 validation summary
### Phase 5A
Ordinary runtime method replacement retired. Final focused **206 passed**; full **1248 passed**; three-platform PR/post-merge CI and CodeQL passed.

### Phase 5B
Selected-scope single-line method ownership made explicit. Final focused **234 passed**; full **1250 passed**; three-platform PR/post-merge CI and CodeQL passed.

### Phase 5C
Single-line UI/bootstrap monkey-patch retired. Final focused **259 passed**; full **1250 passed**; GUI smoke / CI / CodeQL passed.

### Phase 5D
Main single-line private scheduler retired in favor of `_start_parallel_batch_task(...)`. Final focused **248 passed**; full **1252 passed**; GUI smoke / CI / CodeQL passed.

### Phase 5E
Unlined UI/action/private scheduler retired; two historical modules deleted and architecture runtime debt ratcheted. Final focused **658 passed**; full **1256 passed**; architecture guard / CI / GUI smoke / CodeQL / Advanced Security passed. The first post-merge Windows job was cancelled before any step obtained a runner; rerunning only that job passed every Windows gate.

### Phase 5F — training export ownership
Live inspection found two simultaneous hidden implementations: a full legacy `PictureCaptureApp.export_training_package(...)` body plus the bootstrap replacement from `training_export_ui`. Both were replaced by one explicit controller-owned action.

Fail-closed validation history:
- first validation stopped at diff-shape because a new test was untracked and therefore absent from plain `git diff --name-only`;
- a second run referenced one nonexistent focused-test path and ran no tests;
- the next focused run produced **219 passed / 2 failed**, both stale ownership assertions still expecting training orchestration in `app.py`;
- after migrating those assertions, focused passed but the full suite found one over-broad source-shape assertion that scanned the entire `ExportController` for `replace(app.settings)` although the actual PDIC repair method remained unchanged; that assertion was scoped to the repair method body;
- the first fully valid isolated run passed **228 focused**, **1259 full** with only 2 existing Pillow deprecation warnings, compileall, and Ruff F821;
- its publication step then exposed a workflow staging bug: after temporary assets were removed, `git add src tests tools .github/workflows || true` failed because `tools` no longer existed, so only temporary-file deletions were committed and the validated production working tree was not promoted;
- no PR was opened from that incomplete publication;
- the exact same migration/fixes were rerun from the final pre-publication SHA on a clean republish branch with publication corrected to `git add src tests`;
- final republish validation again passed diff-shape, **228 focused**, **1259 full**, compileall, and Ruff F821;
- temporary migration assets were deleted before the production commit;
- final net diff was exactly 8 intended production/test files;
- validated production commit: `42011c29fcce9112a11922a90049195609f31896`;
- validated production tree: `2a4eae1866d309365d50aa11196ac056ee740394`.

PR #242 final-head verification:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI construction smoke;
- macOS CI: passed, including GUI construction smoke;
- compatibility runner, compile, F821, and wheel build passed on all applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security AI findings: passed;
- no review threads or review objections before merge.

Architecture merge `f62f056a51fddae4c05fbd7bc93261330dac2db6` retained exactly the validated tree `2a4eae1866d309365d50aa11196ac056ee740394`.

Post-merge verification on that merge:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI construction smoke;
- macOS CI: passed, including GUI construction smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Remaining Phase 5 runtime/bootstrap debt
`scripts/architecture_guard.py` still permits a ratcheted baseline of legacy `*_runtime.py` modules. Evaluate these by actual semantics and import-order requirements; do not mechanically remove installers.

Highlighted remaining seams:

1. **`ordinary_action_runtime.py` helper-only debt — recommended Phase 5G.** It no longer installs anything. Only DetectionController, CropController, and tests import `_apply_quick_settings_for_ordinary(...)`. The safest next slice is to move that stable helper into a non-runtime module, update callers/tests, delete the historical runtime file, and ratchet it out of `LEGACY_RUNTIME_FILES`. This should not alter any quick-setting behavior.
2. **`unlined_fast_path_runtime.py`.** This is a real performance/import-order seam, not just naming debt. Preserve module-level runtime worker lookup and physical-row/LayoutRows/Profile semantics until a dedicated replacement is proven.
3. **Other layout/overlay/runtime installers.** Many are import-order compatibility layers and should be handled individually only after live caller/wrapper inspection.

## Standing continuation authorization
The user has explicitly authorized continued Phase 5 work along the recommended architecture path without pausing for confirmation at each normal ownership decision point.

Therefore after a successful checkpoint, continue automatically with the recommended next Phase 5 slice after freshly revalidating live `main`, open PRs, callers, import-order/runtime ownership, and relevant tests.

Only stop production writes for a genuine anomaly such as:
- unexplained behavior/test/CI failure;
- file-format, archive/output, or public API change not already in the approved slice;
- merge conflict or concurrent architecture work;
- checkpoint/live-state mismatch;
- materially large cross-core-module redesign;
- a safety-critical or irreversible compatibility deletion whose impact cannot be established from tests/live inspection.

Source-shape assertions that are demonstrably stale after an intended ownership move may be migrated without pausing, provided behavior tests stay green and publication remains fail-closed.
