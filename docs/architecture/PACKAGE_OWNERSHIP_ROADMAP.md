# Package ownership and staged migration roadmap

Status: **Phase 1 merged; staged package migrations ongoing (Issue #562)**. This is an implementation map, not a declaration that all root modules have been migrated.

## Why

At the verified baseline `main@2f041a9`, `src/picture_capture/` directly contained **253 Python files** (including package entry points). A flat directory obscures ownership; moving everything in one commit would also break imports, monkeypatch tests, Windows-spawn workers and persisted interfaces. Move small, cohesive dependency groups only after their call graphs and test consumers are known.

## Target directory ownership

| Package | Responsibility | Phase |
| --- | --- | --- |
| `bootstrap/`, `ui/` | Composition root, widgets, controllers, dialogs and view settings | Already structured |
| `crop/` | Crop-specific options and export support | Already structured |
| `quality/` | Quality metrics, matched-marker evaluation, provenance, timing, structured diagnostics and observational monitoring | **13-file Phase 1 subset** |
| `geometry/` | Geometry-only primitives, page-percentage transforms, gutter and boundary evidence | **13-file Phase 1 subset** |
| `layout/` | Page detection, columns, roles, Layout composition and physical-row inference | Next independent cohort |
| `ocr/` | OCR engines, cache, recognition, lexical evidence and arbitration | Later after injection/parity audit |
| `refinement/` | Existing-marker Y refinement, verification, parallel compute and guarded parent publish | Next bounded cohort |
| `illustration/` | PPP/illustration detection, editor and association | Next bounded cohort |
| `proofreading/` | Review operations, immutable transactions and event evidence | After R3 compatibility audit |
| `project/` | Project startup and recents, Profile and templates | Later, profile callbacks must retain contracts |
| `persistence/` | PDIC/PPP/SECTION formats, atomic writers and storage adapters | Last; high-risk compatibility gate |
| `training/` | Training export, baseline, holdout metadata and data provenance | Independent cohort |
| `ref/` | REF annotation, detection and OCR | Independent cohort |

The directory name describes **ownership**, not a blanket permission to import into the GUI shell. Domain services must not import `app.py` or UI modules; Profile/PDIC schemas and entry identities stay unchanged.

## Phase 1 implementation: physically moved, no root-level duplicate shims

- `quality/`: `benchmark_provenance`, `detection_quality_metrics`, `performance_metrics`, `ordered_marker_matching`, `ordinary_verified_evaluation`, `ordinary_unified_diff`, `draw_performance_profile`, `inference_monitor`, `paddle_diagnostic_formatting`.
- `geometry/`: `visual_boundary_locator`, `layout_gutter_rule`, `layout_percent_helpers`, `boundary_evidence`.
- Adjust production, benchmarks/CLI, and test imports as a coherent unit; all moved modules retain their functions and computational behavior, with package-relative dependencies updated to the canonical owner. Existing GUI entry points, PDIC formats, user settings and dependencies are unchanged.
- Do not introduce one root-level shim per moved module; that would preserve the original directory clutter. These helpers are internal implementation modules. External scripts using their former *internal* dotted paths must migrate imports, while documented GUI/CLI entry points remain stable.
- Phase 1 reduces root Python files from **253 to 240**; further reductions are separately gated. Do not claim full reorganization from this stage.

## Phase 7 first bounded REF cohort (Issue #562)

- Physically relocate `ref_box_geometry.py` to `ref/box_geometry.py` and `ref_text_label_layout.py` to `ref/text_label_layout.py`, without retaining root shim modules.
- Update the REF editor, illustrated-dictionary text-label consumer, and focused REF tests to canonical imports. The REF box data model, `.rbox` persistence, OCR worker and template detection remain at their existing paths for separate risk-gated migrations.
- The package `ref/__init__.py` does not eagerly import domain modules, avoiding circular imports and preserving Windows spawn behavior. Geometry and label placement algorithms are unchanged; the only code edit inside the moved modules is the `RefBox` relative import adjustment.
- This is a **partial P7 step**, not a claim that the entire `ref/` migration or final acceptance is complete. Root Python file count after merge: **242 → 240** (main@37756ff; two refinement modules were added after the Issue #562 baseline) (including `__init__.py` and entry points).

## Illustration helper cohort

Ten illustrated dictionary and overlay modules now reside in `illustration/`. Remaining illustration detection and association modules will migrate in a later PR. Root Python count: 240 to 230 after merge, pending verification.

## Illustration detection geometry follow-up (PR #572; pending acceptance)

- Move `illustration_candidate_size.py` to `illustration/candidate_size.py` and `illustration_cross_column.py` to `illustration/cross_column.py`; no root-level compatibility shims. Update production and focused tests to canonical paths.
- Preserve percentage/pixel threshold semantics and the full-page ink component reconciliation algorithm. Keep the `_rle_components` dependency late-imported from the still-root-owned `illustration_detection` module to avoid import cycles; do not relocate the detection pipeline until its callers and monkeypatch contracts are audited.
- Extend the ownership guard to reject both former root module paths. Expected root Python file count **230 → 228**, subject to independent tree enumeration. CI, CodeQL, reviews, and postmerge main CI remain separate acceptance gates; this section does not claim they passed.

## Migration gate for each following cohort

1. Capture the exact GitHub `main` SHA and open PR inventory; never overlap production PRs.
2. Classify by ownership and enumerate consumers, dynamic imports, monkeypatch points, test file paths and Windows-spawn entry points.
3. Prefer true physical moves and updated relative imports; preserve documented public API entry points. If public imports genuinely need a shim, justify it explicitly rather than mass-creating placeholders.
4. Check `scripts/architecture_guard.py`, `scripts/change_architecture_guard.py`, import/compile and focused regression tests. Never increase the existing oversized-module baselines.
5. Check full Python 3.10 + macOS + Windows + Ubuntu CI, Tk smoke, CodeQL and postmerge `main` CI.
6. Keep independent PRs for high-risk dependencies such as Layout hook composition, OCR monkeypatch/facades, shared PDIC writer and persistence migrations.

## Non-goals

This organization change is *not* a source-code compression project. An expanded tree can improve discoverability without shrinking compressed releases or installed OCR/ML dependencies. Do not delete tests, alter pixel coordinates, bypass manual acceptance or claim performance improvements on the basis of moves.

## Training package cohort (Issue #562)

- Physically move three training services to `training/`: `export_page_understanding.py`, `export_unified_layout.py`, `export_v3.py`. No root shims for these three.
- Retain `training_baseline.py` (PDIC baseline interface), `training_export.py` (stable v2 export), `training_export_composed.py` (GUI composition entry), `training_export_complete_dialog.py` (GUI completion hook), and `training_export_ui.py` (legacy GUI delegation) at their existing root paths. These are distinct compatibility boundaries, not duplicate shims. Preserve v2/v3 training manifest identifiers, PDIC automatic baseline, export ZIP, and selected-page GUI semantics.
- Expected root Python count after integration with merged PR #572: **228 → 225** (count includes root `__init__.py` and entry points); verify against the merged Git tree and postmerge main CI. This training branch was cut before PR #572 and must preserve its illustration/candidate-size and cross-column roadmap entry on merge. This count is not a claim of complete migration or human validation.

## Layout indent visualization leaf (in-progress branch)

- Physically relocate `layout_indent_visibility.py` to `layout/indent_visibility.py` without a root shim. Update the summary compositor and runtime tests to the canonical path.
- Preserve the deferred import of `layout_visualization_summary` via the parent package to avoid the existing circular dependency, including `_INDENT_TAG` identity and Canvas draw order.
- Add an architecture guard that rejects the former root path and requires the canonical module. This bounded migration reduces the merged-main root count from **225 to 224** when integrated, subject to independent recount; no claim of full Layout migration or CI acceptance before the PR checks.

## Layout provenance and physical-lane summary leaves (Issue #562)

- Physically move `layout_role_provenance.py` to `layout/role_provenance.py` and `layout_lane_summary_extension.py` to `layout/lane_summary_extension.py`, removing former root paths without shims.
- Update the Layout visualization summary/shared compositor and focused tests. Preserve `get_layout_line_classification` and `drift_corrected_indent_blocks` as module globals in the new provenance owner so existing monkeypatch tests retain their behavior. Summary ordering and read-only diagnostic output remain unchanged.
- Architecture guard ratchets both owners. This bounded 2-module follow-up targets root **224 → 222** after integration, subject to independent count and CI/CodeQL acceptance; larger Layout UI/algorithm/persistence owners remain unmoved until separately audited.

## Layout diagnostic and evidence cohort (Issue #562, PR #575 expansion)

- Migrate **17 additional** Layout geometry/evidence/visual-diagnostic implementation modules under `layout/` in the same PR as the two earlier provenance/lane helpers. Canonical leaf owners: `character_height`, `parameter_evidence`, `scale_experiment`, `step_trace`, `textbox_leading`, `column_drift`, `column_indent_recovery`, `line_start_refinement`, `local_indent_visualization`, `oversized_ink_continuation`, `illustration_mask`, `mask_source_guard`, `reliability`, `role_visual_consistency`, `verified_oversized_heads`, `visualization_readability`, and `details_window`.
- Physically remove the 17 root modules, fix static and lazy imports across Layout pipeline, page profiles, production rendering/training and tests, preserve all algorithms and settings. Maintain the image-backed role guard, source-coordinate/PPP read-only mask semantics, summary draw order, and the existing reader/GUI entrypoints.
- Explicitly **retain** root `layout_visualization_role_theme.py` as an existing named compatibility no-op entry point instead of silently changing its historical import. Do not count this module as migrated. Retain higher-risk detector, `layout_physical_indent`, `layout_transform`, `layout_rows_cache`, and Layout UI composition at root pending distinct dependency/spawn audits.
- The combined PR #575 cohort is **19 actual root module relocations** (2 existing + 17 added), with no root shim modules. Expected root Python file count **224 → 205**, subject to independent Git-tree enumeration. This is not acceptance: require full Python 3.10/Windows/macOS/Ubuntu CI, GUI smoke, wheel, CodeQL, reviews and postmerge `main` CI before merging.

## Crop planning and overlay presentation cohort (Issue #562; CI pending)

- Physically move seven internal modules, with **no root shims**: `crop_logging.py` → `crop/logging.py`, `crop_plan_formatting.py` → `crop/plan_formatting.py`, `crop_preview_display_settings.py` → `crop/preview_display_settings.py`, `crop_preview_labels.py` → `crop/preview_labels.py`, `overlay_layout_helpers.py` → `ui/overlay_layout_helpers.py`, `overlay_line_anchor.py` → `ui/overlay_line_anchor.py`, `overlay_opacity.py` → `ui/overlay_opacity.py`.
- Update the production GUI, processing-core, crop logging, illustration-opacity and overlay-builder imports, plus direct unit tests. Keep `processing_core` and `app` function-level re-exports unchanged; preserve source-pixel crop logs, PPP labels, editor geometry, reading direction, one-sided guide/marker anchoring, and alpha rendering.
- Ratchet canonical physical ownership in the architecture guard and a dedicated test. This cohort does **not** change PDIC/PPP/SECTION serialization, GPU workers, Y refinement, or source image data. It is seven internal relocations, not a completion claim for all crop/UI or project modules.
- Target root count **205 → 198** after acceptance; this is a predicted count until independently enumerated on the PR tree. Require full platform CI, GUI smoke, wheel, CodeQL, reviews and postmerge main push checks before merge. Historical external imports of these internal module paths are not documented public entrypoints; no compatibility shims are added.
