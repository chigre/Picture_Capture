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
- Expected root Python count after merge: **230 → 227**; verify with main and full CI.
