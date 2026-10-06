# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: always revalidate `main`, open PRs, relevant callers/import order, and tests before new production writes.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5J are complete.**

Phase 4 controller decomposition is complete through Detection batch processing. Phase 5 has retired runtime ownership from ordinary drawing, selected-scope single-line crop, unlined export, training export, helper-only ordinary-action debt, LayoutRows visualization capture, local-indent visualization replacement, and Layout role-provenance decoration.

## Latest architecture checkpoint
- Phase 5J PR: **#250 — make role provenance explicit**
- Phase 5J validated production commit: `734e91c378e3a5770bb21e935187383090b86d4d`
- Phase 5J validated/merged production tree: `df73ed8823ba21804fcf1c2b1c6d62f928b2eb15`
- Phase 5J architecture merge: `d56456047c51f97e2a2f929dfdab8c77df3db43c`
- Previous Phase 5I PR #248 merge: `78c956177ebf9b580f66b3593494d286eed4c9ff`
- Phase 5H PR #246 merge: `d00df0bff2b3da947607310ea331b09b678f688d`
- Phase 5G PR #244 merge: `de04953752d0294e838b3ac45ae9a0f5ee9a3548`
- Phase 5F PR #242 merge: `f62f056a51fddae4c05fbd7bc93261330dac2db6`
- Phase 5E PR #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.
- Current production architecture PR: none after Phase 5J merge.

## Current explicit ownership
Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

### Detection / ordinary drawing
`PictureCaptureApp.run_normal_draw_action()` delegates to `DetectionController.run_normal_draw_action()`. OCR-independent quick validation lives in non-runtime `ordinary_quick_settings.py`; `ordinary_action_runtime.py` is retired.

### Crop / single-line and unlined export
Selected-scope single-line and unlined actions are explicit app-wrapper → CropController → app-owned `_start_parallel_batch_task(...)` paths. Historical single-line/unlined UI/private-scheduler runtimes are retired.

`unlined_fast_path_runtime` remains intentionally because it is a real worker/performance import-order seam. CropController resolves `unlined_line_export.export_unlined_page_job` from the module at action time so the installed fast worker remains visible.

### Export / training package
`PictureCaptureApp.export_training_package()` delegates to `ExportController.export_training_package()` and reuses app-owned batch/UI-worker infrastructure. GUI bootstrap no longer replaces the method dynamically.

### Layout visualization after Phase 5H–5J
- LayoutRows capture is static in `layout_visualization_shared.shared_snapshot_for_app(...)`; `layout_visualization_rows_cache_runtime.py` is retired.
- Drift-corrected indent geometry lives in non-runtime `layout_local_indent_visualization.py`; `layout_local_indent_visualization_runtime.py` is retired.
- Entry-source provenance lives in non-runtime `layout_role_provenance.py`; `layout_role_provenance_runtime.py` is retired.
- `layout_visualization_shared._indent_blocks_from_understanding` is statically provenance-aware while still using the same drift-corrected block producer.
- Base `layout_visualization_summary._format_summary(...)` statically inserts the same `entry sources: ...` line before later summary decorators run.

Current later summary/display ordering remains:

`install_layout_role_theme()` → `install_layout_visualization(app_module)` → `install_physical_lane_summary()` → `install_layout_indent_visibility()`.

## Completed Phase 5J — role-provenance runtime retirement
### Production change
Phase 5J removed only the diagnostic provenance installer:
- created non-runtime `layout_role_provenance.py` with `indent_blocks_with_entry_sources(...)` and `add_entry_source_summary(...)`;
- preserved exact `(column, absolute y0, absolute y1)` line/block matching;
- preserved defaults: unmatched entry/headword → `indent`, non-entry → `body`;
- preserved summary source ordering: `indent`, `large_head`, `symbol_sample`, `ocr`, `manual`, `unknown`, then custom sources alphabetically;
- preserved insertion immediately after `line indents:` and no-count passthrough;
- statically made shared indent blocks provenance-aware;
- statically made the base summary provenance-aware;
- removed the GUI bootstrap provenance installer import/call;
- removed `layout_role_provenance_runtime.py` from `LEGACY_RUNTIME_FILES`;
- did not change later role-theme, lane-summary, indent-visibility, worker, classification, persistence, or public-action behavior.

### Validation
Isolated fail-closed validation completed without production failure:
- exact intended net diff: 9 production/test files;
- architecture guard: passed;
- focused: **25 passed**;
- full: **1267 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration helper/workflow removed before publication.

PR #250 final-head verification on `734e91c378e3a5770bb21e935187383090b86d4d`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility runner, compile, F821, and wheel passed on all applicable platforms;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- Advanced Security: passed;
- no review threads or review objections before merge.

A separate GitHub Advanced Security aggregate `CodeQL` check was neutral because the PR comparison could not find one default-setup configuration; the actual `Analyze (actions)` and `Analyze (python)` jobs both passed and were used as the CodeQL merge gate.

Architecture merge `d56456047c51f97e2a2f929dfdab8c77df3db43c` retained exactly the validated tree `df73ed8823ba21804fcf1c2b1c6d62f928b2eb15`.

Post-merge verification on that merge:
- Ubuntu CI: passed;
- Windows CI: passed, including GUI smoke;
- macOS CI: passed, including GUI smoke;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Recommended next slice — Phase 5K
**Retire `layout_indent_visibility_runtime.py` without changing its current outermost summary semantics.**

Fresh read-only inspection after Phase 5J shows this runtime owns two display-only behaviors:
1. replacement of `layout_visualization_summary._draw_indent_blocks` with `_draw_indent_blocks_visible(...)`, which draws the same prepared blank spans above the base scan and adds a solid first-ink edge;
2. the current **outermost** summary wrapper, which appends `indent blocks prepared: ...` after all earlier summary content, including physical lane diagnostics.

It owns no worker, persistence format, detection rule, crop geometry, or public app action. Dedicated behavior tests already cover per-column prepared counts, two-column rendering, first-ink edges, and the requirement not to lower indent blocks beneath the base layout.

### Critical ordering constraint for Phase 5K
Do **not** simply move the prepared-count line into base `_format_summary()`: that would place it before the later physical-lane summary and change the current text ordering.

The safest narrow architecture is:
- move `prepared_indent_counts(...)`, visible indent drawing, and a small `add_prepared_indent_summary(base_text, app)` helper to a non-runtime module;
- statically bind `layout_visualization_summary._draw_indent_blocks` to the visible renderer;
- preserve the final summary order by composing `add_prepared_indent_summary(...)` at the outside of the existing `install_physical_lane_summary()` wrapper, so the effective chain remains base/provenance → role theme → physical lanes → prepared-indent counts;
- remove only `install_layout_indent_visibility()` and its GUI bootstrap import/call;
- ratchet `layout_indent_visibility_runtime.py` out of `LEGACY_RUNTIME_FILES`;
- migrate the dedicated runtime/source-shape tests and add a direct summary-order regression proving `physical indent lanes:` appears before `indent blocks prepared:`.

`layout_visualization_ui_v3` imports `draw_layout_visualization_detailed` by value, but that function resolves summary-module `_draw_indent_blocks` at call time; static binding in the summary module therefore preserves rendering behavior without changing the UI-v3 app-method installer.

Do not combine Phase 5K with `unlined_fast_path_runtime`, `ordinary_large_head_runtime`, spawn runtimes, overlay opacity/anchor runtimes, or other import-order/core work.

## Remaining high-risk runtime seams
Treat these as real compatibility/performance seams rather than mechanical naming debt until individually proven:
- `unlined_fast_path_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- Windows/GPU/runtime initialization paths;
- entry-classification and overlay/UI runtimes with persistent/import-order effects.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint after fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
