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

## Ordinary drawing internal helpers (Issue #562; validation pending)

- From `main@7a6ef9c3` (independently verified **198** root `.py` files in the complete 843-entry, untruncated Git tree), physically relocate **15** ordinary drawing evidence, postprocessing, consistency, visualization and quick-setting modules to `ordinary/`, without root shims. New owner names: `ordinary/cjk_large_heads.py`, `ordinary/crossing_separator.py`, `ordinary/final_visual_consistency.py`, `ordinary/independent_indent_rescue.py`, `ordinary/lane_polarity.py`, `ordinary/layout_inspector.py`, `ordinary/marker_ocr_text.py`, `ordinary/oversized_head_guard.py`, `ordinary/postprocess.py`, `ordinary/secondary_recovery.py`, `ordinary/symbol_evidence.py`, `ordinary/unified_diagnostics.py`, `ordinary/unified_visualization.py`, `ordinary/vb_brightness.py`, `ordinary/quick_settings.py`.
- Update root processing orchestration, `processing_core`, Layout composition, compact GUI controllers, supporting ordinary code, and focused unit tests. Preserve feature algorithms, OCR provenance identifiers, source coordinates, pre-existing GUI/CLI entry points and `processing` function re-exports.
- Explicitly **retain** `ordinary_parallel.py`, `ordinary_cpu_pool.py` and `ordinary_gpu_pipeline.py` at root, because Windows spawn and GPU single-model resource ownership require separate measured testing; keep `ordinary_visual.py`, `ordinary_large_head_evidence.py`, `ordinary_large_head_role_guard.py`, `ordinary_bracket_pair.py` and `ordinary_indent_topology.py` at root pending deeper API and monkeypatch compatibility audit. Their retention is not counted as migration.
- Expected post-cohort root count **198 → 183**, subject to independent post-branch Git-tree verification. Acceptance still requires Python 3.10, Windows/macOS/Ubuntu CI, GUI smoke, architecture guard, wheel, CodeQL, reviews and main push CI; no claim of success or scanned-image manual validation before evidence.

## Issue #562: eight physical leaf owners (validation pending)

- Move `unlined_blank_detection` → `unlined/blank_detection.py`, `unlined_physical_rows_resolver` → `unlined/physical_rows_resolver.py`, `page_thumbnail_cache` → `thumbnail/cache.py`, `page_thumbnail_tasks` → `thumbnail/tasks.py`, `generic_block_roles` → `layout/generic_block_roles.py`, `ink_safe_separator` → `refinement/ink_safe_separator.py`, `entry_crop_settings` → `crop/entry_crop_settings.py`, and `separator_y_settings` → `refinement/separator_y_settings.py`.
- All eight are real moves without root shims. Preserve existing single-line export, merge and spawn-worker root APIs pending their own compatibility gate; no claim of a completed `unlined/` package. The large proofreading cohort is also deferred pending safe app consumer edits.
- Expected root Python count **183 → 175** after merge, subject to independent recount. CI/CodeQL, GUI and manual image acceptance remain separate requirements.

## Issue #562: preprocessing internal ownership cohort (PR validation pending)

- **10 actual root module relocations** to `preprocess/`, no root shims: `image_preprocessing_canvas.py` → `preprocess/canvas.py`, `image_preprocessing_constants.py` → `preprocess/constants.py`, `image_preprocessing_models.py` → `preprocess/models.py`, `image_preprocessing_persistence.py` → `preprocess/persistence.py`, `image_preprocessing_reporting.py` → `preprocess/reporting.py`, `image_preprocessing_storage.py` → `preprocess/storage.py`, `preprocess_geometry.py` → `preprocess/geometry.py`, `orthogonal_dewarp.py` → `preprocess/orthogonal_dewarp.py`, `text_line_geometry.py` → `preprocess/text_line_geometry.py`, `image_metadata_status.py` → `preprocess/image_metadata_status.py`.
- Preserve public `image_preprocessing.py` as the orchestration/monkeypatch API, `image_utils.py` and `adaptive_denoise.py` as shared root helpers, and `document_unwarping.py` as a Paddle/GPU lifecycle boundary. Geometry and image algorithms, project storage and JSON schemas, source-pixel coordinates, Windows spawn and GPU single-owner semantics remain unchanged. This is a file relocation and import-ownership change only.
- Ratchet architecture guard and focused tests. Expected root Python count **175 → 165**, pending independent untruncated tree recount, complete Python3.10/Windows/macOS/Ubuntu CI, GUI smoke, wheel, CodeQL, reviews and main push CI. Real scanned-page UI acceptance remains manual.

### 2026-10-20 checkpoint (Issue #562; PR creation blocked)

- Baseline main SHA `ce8b00c0b4de97359559307dd8b6a8e50d4c34bb` after merged #579; postmerge CI `39370108855` and Push `39370109600` succeeded. Open PR count: zero when checked.
- Prepared branch `refactor/issue562-preprocess-internals-20261020` with 10 real Git rename moves; independently verified complete untruncated tree root `.py` count **175 → 165**. No old-location shim. Static relative import audit resolved **42/42** imports in the modified production modules. These checks do not establish runtime correctness.
- PR creation and Issue #562 checkpoint comments were blocked by GitHub write safety checks. No PR CI, cross-platform Python 3.10, GUI smoke, wheel, CodeQL, human review or postmerge main checks have been run for this new cohort. No merge permitted yet. The branch is a recovery checkpoint, not acceptance.
- Next: open Draft PR from existing branch, complete all required tests and repair failures, verify review gates, merge safely, verify main push CI, then continue the next business cohort. Keep Issue #562 open; manual scanned-image verification remains pending.


## Issue #562 — REF ownership completion cohort (not yet accepted)

- Physically relocate three REF implementation modules: `ref_boxes.py` → `ref/boxes.py`, `ref_box_detection.py` → `ref/detection.py`, `ref_box_ocr.py` → `ref/ocr.py`, with no old-root shims. Maintain the historical application and CLI entrypoints, but replace direct imports in actual callers and tests.
- Preserve REF JSON persistence, atomic ticketed writes, source-image pixel coordinates, direction-sensitive detection, OCR engine resource management and original-image immutability. Cross-package callers use canonical REF owners; no behavior/threshold changes are intended.
- Add architecture guard ratchet and module ownership assertions. Baseline root `.py` count **165**; expected after merge **162**, requiring independent Git tree enumeration.
- This is a bounded three-module REF business package completion (rather than an unrelated 15–30 module batch). Require full Python 3.10/3.13 Windows/macOS/Ubuntu CI, GUI smoke, wheel, CodeQL, reviews, postmerge main CI and real-image manual verification where available before declaring full acceptance. No claim of CI success before it actually runs.


## Issue #562 — Illustration implementation canonical owners (not yet accepted)

- Physically relocate three remaining Illustration root implementation modules: `illustration_detection.py` → `illustration/detection.py`, `illustration_labels.py` → `illustration/labels.py`, `illustration_batch_association.py` → `illustration/batch_association.py`. No obsolete root shim; keep app/export/CLI entry points as before.
- Update illustration UI, processing_core, Layout/ordinary illustration evidence, real-scan ROI validator, lazy cross-column detector dependency and focused PPP/reading-order/cross-page/concurrent-edit tests. Preserve original PPP payload/line and manual edits, source-image coordinates, reading direction, association ordering, read-only detection semantics, atomic PPP write safety and no extra OCR/Paddle process owners.
- Add canonical ownership assertion and architecture guard. Root count baseline **162**, expected migration result **159** after independent complete Git tree audit.
- PR acceptance is separate: Windows/macOS/Ubuntu × Python 3.10 & 3.13 full CI, Tk GUI smoke, wheel, CodeQL, review, postmerge main CI and documented manual scanned-page verification limitations. No result is claimed before observed.


## Issue #562 — Project Center / recent registry ownership cohort (pending PR acceptance)

- **Six physical moves, no root shims:** `project_center_metadata_cache.py` → `project/metadata_cache.py`; `project_center_preview_cache.py` → `project/preview_cache.py`; `project_folder_launcher.py` → `project/folder_launcher.py`; `project_parameter_templates.py` → `project/parameter_templates.py`; `recent_project_locking.py` → `project/recent_locking.py`; `recent_projects.py` → `project/recent_projects.py`.
- Project Center GUI composition stays in `app.py` as a historical entrypoint. The registry modules continue to use the existing user-config files, atomic temp/replace operations and interprocess lock, while the separate metadata/thumbnail caches preserve existing invalidation, project identities, lazy loading and first-paint behavior. Parameter templates preserve their serialized settings values and Profile/PDIC/PPP/SECTION handling. Folder opening stays an OS-specific, call-time UI side effect.
- Update the actual app's static and deferred imports, training export dialog, test imports and source-inspection fixtures; no alias installer, global monkeypatch or old-root shim. Keep `project_storage.py` at the root pending **separate high-risk** persistence/write-contract audit. Existing `profile_* .py` files also remain pending GUI/Profile/reading-order parity audit; neither category is counted as moved here.
- New owner test and additive architecture guard reject root module resurrection and require six canonical owners. Expected complete Git tree root `.py` count **159 → 153** after physical moves; independently check before claiming.
- No change to PDIC/PPP/SECTION bytes, project lock, manual edits, GPU one-owner/spawn, or source-image coordinates is intended. Acceptance requires complete Python 3.10 and 3.13 Windows/macOS/Ubuntu CI, GUI smoke, wheel, CodeQL, reviews and postmerge main CI. True Windows GUI and scanned-image manual parity cannot be inferred from synthetic automation.

## Proofreading bounded ownership: three verified physical paths (Issue #562)

- Relocate `proofreading_candidate_history.py` to `proofreading/candidate_history.py`, `proofreading_identity.py` to `proofreading/identity.py`, and `proofreading_section.py` to `proofreading/section.py`. No root-level shim is retained. Keep the R3 transaction implementation, durable PDIC/PPP/SECTION writers, app review editor, and evidence journal at their existing paths pending separate audited migration.
- Update the Review transaction UI and the source-side identity/section capture callers, together with focused tests. The new `proofreading/__init__.py` deliberately does not import Tk or persistence services eagerly. Section layout and image-coordinate semantics, stable candidate history identity and transaction ownership are unchanged.
- This bounded cohort reduces the main-root Python file count **153 → 150** after integration (following merged PR #584; original preparation baseline was 159 → 156), subject to independent postmerge Git tree recount. Five additional candidate modules and associated tests encountered tool-level write safety blocks during preparation; these were **not** migrated or silently shimmed. The rest of the proofreading cohort requires its own risk-gated follow-up.
- CI matrix (Python3.10/3.13 on Windows/macOS/Ubuntu), GUI smoke, wheel, CodeQL, reviews, main push CI and manual scanned-image acceptance remain separate gates; no green claim before evidence.


## Issue #562 — Proofreading coherent 18-owner physical relocation (Draft PR #585; not yet accepted)

- Extend the previously staged 3-module proofreading cohort with **15 additional real root-to-`proofreading/` moves**, without root-level compatibility shims: `candidate_delete`, `capture`, `deferred_save`, `events`, `evidence`, `quality_export`, `review_bundle`, `save_safety`, `transactions`, `verification`, `verify_ui`, `crop_extension`, `entry_classification_ui`, `main_editor_sync`, `text_helpers`.
- Update production and lazy imports, Review/Tk controller imports, scripts, test references, source-path checks and architecture guard. Protect stable event journal and R3 transaction/recovery behavior, PDIC/PPP/SECTION original bytes, parent guarded writes, GUI review events, reading order and OCR/GPU/Windows spawn invariants. Algorithms and external data formats are unchanged.
- Baseline root **153**; proposed result **135** after 18 physical moves; actual count and rename verification required. Full tri-OS Python3.10/3.13, GUI smoke, wheel, CodeQL, focused regression, reviews and postmerge main CI remain separate gates. Manual scanned-page and real-project testing cannot be claimed from CI.


## Issue #562 — Profile and dictionary-page design owners (merged PR #586; automated CI accepted, manual verification pending)

- Move **15 physical root modules** into cohesive `profile/` (10 owners), `design/` (3 owners) and `visual/` (2 owners), with NO deprecated root file shim.
- Profile: `profile_indent_ui`, `profile_layout_bootstrap`, `profile_ordinary_evidence_ui`, `profile_semantics`, `profile_setup`, `profile_validation_modes`, `profile_wizard`, `dictionary_profile`, `parameter_help_ui`, `app_settings_migrations`.
- Page design: `dictionary_page_design`, `dictionary_page_design_refined`, `dictionary_page_layout_policy`. Visual marker owners: `visual_marker_templates` and `visual_marker_ui`.
- Preserve Profile wizard entrypoint, AppSettings serialization/schema, project-specific settings, default profile JSON and bundled headword images, page design/refinement algorithm and source coordinates. The relative lookup in `profile/dictionary.py` and `profile/setup.py` now traverses one parent to the existing `picture_capture/data` directory, without moving asset bytes. Preserve Layout call-time hooks, monkeypatch and Windows-spawn contracts.
- Update actual consumers and tests rather than returning shim modules. The original oversized `profile_setup.py` size ratchet (**174009 bytes**) is retained under canonical path `profile/setup.py` without raising its ceiling. Add an additive physical-owner guard and direct tests for asset locations.
- Merged as PR #586 at `04a54fb89e27579511fa73f611b03d1dca3f8772`: Git Tree independently confirms root `135→120`; PR and postmerge main CI each passed all six Windows/macOS/Ubuntu Python 3.10/3.13 jobs, and main Push/CodeQL `39470919113` passed. No submitted review approvals; scanned pages/real-project manual GUI/data-writing parity remains pending. This is not the final Issue #562 acceptance.

## Refinement physical-leaf cohort (Issue #562, PR acceptance pending; 2026-10-21)

- Move five root implementation modules with no old-root shims: `marker_refinement_analysis.py` → `refinement/analysis.py`, `marker_refinement_fixed_band.py` → `refinement/fixed_band.py`, `marker_refinement_guard.py` → `refinement/guard.py`, `marker_refinement_progress.py` → `refinement/progress.py`, and `marker_refinement_top_edge.py` → `refinement/top_edge.py`.
- Change static and delayed production imports in `processing_core.py`, `unlined_line_export.py`, and `marker_refinement_parallel.py`; adjust focused Y, LayoutRows, PPP/illustration and parent-commit tests. No Y thresholds, algorithms, persisted schema, page pixels or worker orchestration were intentionally changed.
- Explicitly **retain at root** `marker_refinement_parallel.py` (Windows spawn, read-only workers and parent-only guarded PDIC publication), `marker_refinement_layoutrows.py` (shared cached physical settings and historical imports), and `separator_y_refinement.py` (historical processing/Paddle shared-Y API). Each requires its own compatibility and real-page parity gate before any relocation.
- The expected root count on the proposed branch is **120 → 115**, subject to independent Git-tree enumeration; total physical migrations **135 merged + 5 pending**, not a percentage of eligible work. No PR/CI/CodeQL/manual acceptance is implied by this roadmap entry. Preserve original scan bytes, Profile/PDIC/PPP/SECTION, manual proofreading, reading direction, single GPU owner and Windows spawn. Require six OS/Python CI jobs, architecture guard, GUI smoke, wheel, CodeQL, reviews, and postmerge main CI before acceptance.

## Issue #562 — OCR/cache internal leaf owners (candidate, not yet accepted; 2026-10-21)

- Physically relocate **11** internal root modules into the new non-eager `ocr/` package: `ocr_action_guard → ocr/action_guard`, `ocr_boundary_detection → ocr/boundary_detection`, `ocr_final_decisions → ocr/final_decisions`, `ocr_lazy_secondary → ocr/lazy_secondary`, `ocr_pdic_preservation → ocr/pdic_preservation`, `ocr_peer_style → ocr/peer_style`, `ocr_tesseract_runner → ocr/tesseract_runner`, `ocr_text_io → ocr/text_io`, `paddle_cache_storage → ocr/paddle_cache_storage`, `paddle_raw_cache_signature → ocr/paddle_raw_cache_signature`, and `tesseract_raw_cache → ocr/tesseract_raw_cache`. No former-path shim modules.
- Preserve full OCR engine/provider, shared legacy channel, `paddle_headwords_core` monkeypatch hooks and single-GPU process owner at root. In particular, retaining the original leaf filename `paddle_cache_storage.py` within the package preserves module-name introspection required by existing wrapper tests. `ocr_page_resume.py` remains in place: its directory-wide file/path/byte fingerprint determines fail-closed resumability and must receive a separate compatibility gate before relocation.
- Update production, lazy core imports, Review/GUI sources and focused tests. Preserve PDIC content-addressed prewrite snapshots and final-audit freshness, Tesseract/Paddle cache keys and serialization, OCR enabled-engine selection, data coordinates, window-spawn ownership and OCR-channel boundary semantics. The original .OCRed export byte format is unchanged.
- Add a strict physical-owner architecture guard and source/test ownership assertions; no test deletion or bypass. Verified baseline main `0b2a78d8d1182f81ac6fdf37170ec8f5b2d5ab43` has **115** root .py files in the complete Git Tree; candidate target **104** root .py files, pending independent full-tree recount. This is not yet accepted/merged, and claims no CI, manual scan, GUI, wheel, review or CodeQL success until independently observed.
- Separate next-cohort audit: `ocr_channel`, `ocr_channel_legacy`, `ocr_engines`, `paddle_headwords*`, `ocr_crop_preview_ui` and `ocr_page_resume` require higher-risk monkeypatch/GPU/spawn/API analysis, not speculative mechanical moves.

## Issue #562 — Dictionary lexicon and shared text owners (2026-10-21; candidate, not yet accepted)

- Physically move **seven** internal implementation files with no old-root shims: `cc_cedict`, `chinese_simplify`, `collation`, `network_lookup`, `latin_glued_pos_headwords`, and `reference_index` to same-basename files in `lexicon/`; `text_encoding` to `text/encoding.py`. This smaller, dependency-contained package cohort is deliberate; it avoids coupling the refactor to Layout Y, historical GUI, GPU workers or persistence writers solely to reach a numeric PR size.
- Update the real consumers in environment setup, Review/sort controls, Profile settings, file-format readers, OCR evidence, illustration, export and guarded parent-worker text decoding; migrate the relevant monkeypatch tests without weakening assertions. Keep lazy OpenCC, local CC-CEDICT data locations/download limits/atomic install, network timeouts/thread-pool singleton, Unicode collation semantics and exact decoding behavior. Non-eager `__init__.py` for each new package.
- Physical owner guard and focused tests require canonical files and reject all seven root aliases. From verified merged `main@d82e558155519c0a68c6601f7d1d1157919379b9` with 104 root `.py`, proposed target **97**; independently recount full Git tree and require complete tri-OS Python3.10/3.13 CI, GUI smoke/wheel, CodeQL and review gates before merge. Manual real scan / Windows parity remains separate.

### Merged post-check results preserved
- Earlier five-leaf Y refinement [PR #587](https://github.com/chigre/Picture_Capture/pull/587) merged at `0b2a78d8`; postmerge main CI `39477487821` 6/6 and Push/CodeQL `39477487695` 2/2 succeeded. Its historical 'PR acceptance pending' section above is an archived candidate plan, not the current status.
- Eleven-leaf OCR/cache [PR #588](https://github.com/chigre/Picture_Capture/pull/588) merged at `d82e558155519c0a68c6601f7d1d1157919379b9`, source head `e9c35ac7`, original PR CI `39482120718` attempt 2 6/6, PR CodeQL `39482113216` 2/2. The merged main tree has exactly **104** root Python files (from 115); main CI `39552883661` 6/6 and Push/CodeQL `39552884760` 2/2 succeeded. The prior 'candidate, not yet accepted' OCR section documents the original safety plan; these lines record its actual verification. Total merged physical migrations so far **151** from 253 original; net root reduction 149/253 (**58.9%**) is not final eligible-work completeness.


## Issue #562 — Layout physical composition, page-X and display evidence leaves (2026-10-21; PR acceptance pending)

- **Six real physical relocations, no root compatibility shims:** `boundary_placement.py → layout/boundary_placement.py`, `layout_profile_anchor.py → layout/profile_anchor.py`, `layout_composition.py → layout/composition.py`, `page_x_registration.py → layout/page_x_registration.py`, `layout_visualization_shared.py → layout/visualization_shared.py`, `layout_visualization_summary.py → layout/visualization_summary.py`.
- Move focused page-X/profile anchoring, boundary placement, explicit physical-only layout composition, cached visualization snapshot and text-only summary into established `layout/` ownership. Update production and deferred imports, Layout details/indent-visibility/UI consumers, training/export/processing and source-path tests. Preserve call-time `page_understanding` deferred import and the separation between GUI `layout_visualization_ui` and the implementation, avoiding cyclic initialization and unrequested process-level hooks.
- Preserve source-pixel coordinates, Profile defaults, image read-only behavior, PPP masking and Review/PDIC/SECTION integrity; no layout/Y thresholds or persisted formats changed by design. Leave `layout_detection_legacy`, `layout_core_understanding`, `layout_physical_indent`, `layout_rows_cache`, `layout_step_replay_ui` and Tk UI root facades in place until their independent monkeypatch, caching, Windows spawn, GPU and real-page gate. Deliberately retain `layout_detector_live_binding.py` because it is an existing named historical import compatibility path, **not** a newly created shim or counted migration.
- Extend the strict physical-owner architecture guard and focused tests without relaxing ratchets. Verified main baseline `22b29a476b1f4eafcad761ea2deb4f927220e4e2` has **97** root Python files. Candidate target **91** pending complete untruncated Git tree recount; six migrated modules are NOT accepted until full six-platform Python 3.10/3.13 CI, guard, GUI smoke, wheel, CodeQL, reviews and postmerge main checks. Manual real scanned-page/Windows/Tk parity remains unverified.


## Issue #562 — Page coordinate, listing, word mapping and crop pure utility cohort (2026-10-21; PR candidate)

- Physical no-shim root relocations: `coordinate_space.py → geometry/coordinate_space.py`, `layout_transform.py → geometry/layout_transform.py`, `page_list_helpers.py → project/page_list_helpers.py`, `page_word_mapping.py → proofreading/page_word_mapping.py`, `auxiliary_crop_partition.py → crop/auxiliary_partition.py`. These five serve the common original-page coordination boundary: source coordinates/temporary reversible transform, page ordering, page-local word mapping, and crop partitions. They are implementation/utility owners; CLI/App/GUI facade entrypoints remain at root, and `app` continues to re-export its historical helper callables.
- Import updates apply only to Python module bindings (static and deferred) across App, reading/review, Profile, crop/PPP, layout, processing, diagnosis, test and diagnostic scripts; preserve serialized `coordinate_space` and `layout_transform_internal` data keys, original image pixel coordinates, direction and reversible source-canonical transform math, page-local mapping, bookmark ordering and existing crop partitions. No algorithm thresholds, resources, PDIC/PPP/SECTION/Profile schema or image pixel writes deliberately changed.
- Full root physical-owner guard and an additive regression for retired imports; no old-root shim, no deleted test or relaxed rule. Source `app.py` oversized size ratchet stays intact. Old Python import paths internal to code/tests must be updated; no import-at-start GPU engines.
- Candidate baseline merged main `acfbef1f3ff3d2c9585140f0121f4415002e0f04` has **91** root Python files. Target **86** after five physical moves, subject to independently untruncated Git tree recount. Keep root `page_sections`, `project_storage`, `pdic_restore`, `processing_core`, `layout_rows_cache`, `ocr_page_resume`, GPU and Windows spawn owners unmoved pending separate gates. Six tri-OS×Python3.10/3.13 regression, GUI smoke, wheel, architecture/code guards, CodeQL and unresolved reviews plus postmerge main CI required before final acceptance. Real scanned-page/Windows manual editing parity remains unverified.


## Issue #562 — Training baseline/composition/completion owners (proposed, not accepted; 2026-10-21)

- Physically relocate `training_baseline.py` → `training/baseline.py`, `training_export_composed.py` → `training/export_composed.py`, and `training_export_complete_dialog.py` → `training/export_complete_dialog.py`; remove all three obsolete root paths, with **no root shims**. This supersedes the three root-retention choices recorded in the earlier 2026-10-18 Training checkpoint.
- Retain stable `training_export.py` v2 public API and `training_export_ui.py` historical GUI delegation at root pending separate compatibility audit. Keep `training/__init__.py` import-light; no GUI startup side effects in worker imports.
- Update actual `gui_io`, `bootstrap/worker`, `processing`, training v3, bookmarks and GUI export controller callers, plus tests. Preserve automatic baseline sidecar schema and explicit-replace behavior, PDIC original bytes, v2/v3 manifest identifiers, selected-page ordering, ZIP output, Tk completion dialog, Windows spawn and parent-only guarded publication.
- Add strict physical-owner architecture guard and ownership/import tests. Base main `0648dade74b448acc83dfafda218ce4af73a9d2a`, root `.py` **86**, candidate **83** (verify complete Git tree independently). Full Python3.10/3.13 × Windows/macOS/Ubuntu, GUI smoke, wheel, CodeQL, reviews, postmerge main CI and manual scanned-page acceptance are separate gates, **not yet claimed**.


## Issue #562 — 2026-10-21 expanded ordinary / page understanding / OCR owner cohort (candidate; not accepted)

- Base `main@75ef28ece21a7e1b348752a806e53a494faf7fde`: **83** root Python files by complete 879-entry Git tree. Postmerge #592 main CI #39568097190 six jobs **SUCCESS** and push CodeQL #39568097693 both jobs **SUCCESS**. Human scanned-page/Windows GUI parity still unverified.
- Move **15 source modules physically**, without retaining any prior-root shims: `ordinary_bracket_pair.py` → `ordinary/bracket_pair.py`; `ordinary_cpu_pool.py` → `ordinary/cpu_pool.py`; `ordinary_evidence_fusion.py` → `ordinary/evidence_fusion.py`; `ordinary_gpu_pipeline.py` → `ordinary/gpu_pipeline.py`; `ordinary_indent_topology.py` → `ordinary/indent_topology.py`; `ordinary_large_head_evidence.py` → `ordinary/large_head_evidence.py`; `ordinary_large_head_role_guard.py` → `ordinary/large_head_role_guard.py`; `ordinary_parallel.py` → `ordinary/parallel.py`; `ordinary_visual.py` → `ordinary/visual.py`; `entry_ocr_crop.py` → `ocr/entry_crop.py`; `entry_ocr_visual_scale.py` → `ocr/entry_visual_scale.py`; `page_understanding.py` → `layout/page_understanding.py`; `page_understanding_fusion.py` → `layout/page_understanding_fusion.py`; `large_head_visual_diagnostics.py` → `ordinary/large_head_visual_diagnostics.py`; `layout_visualization_role_theme.py` → `layout/visualization_role_theme.py`.
- This is a domain-oriented package-only change. Implement callers, deferred imports, tests and additive architecture guard. Preserve core algorithm parameters, PDIC/PPP/SECTION/Profile, original-source coordinates, review manual edits, Y refinement, parent-only publication, single GPU model and Windows spawn. Until verified do **not** claim parity, readiness or completion.
- Expected root count after this cohort: **68**, pending independent complete-tree recount and exact-head full Python3.10/3.13 tri-OS, GUI smoke, wheel, CodeQL, review, fixed-head merge, and postmerge main checks. Do not close Issue #562 for this step.


## 2026-10-21 bounded UI and refinement cohort — proposed

- From `main@fe6b03f0e292755a90734ce945de2d99e5073f9b` (68 root Python files, zero open PR), physically move `batch_progress_budget.py` to `ui/batch_progress_budget.py` and `line_diff_bookmarks.py` to `refinement/line_diff_bookmarks.py`, without root shims. Update the Tk batch-poll deferred import, compact task menu import, tests and ownership guard.
- Expected count: 68 → 66, pending candidate tree verification. Preserve Tk pause/stop budgets, PDIC automatic-baseline comparison, user confirmation before bookmark replacement and Settings persistence. CI/CodeQL/reviews/wheel/GUI and postmerge main are not yet accepted; real scanned-page/Windows/GPU/PDIC parity remains manual.


## Issue #562 — Crop export Settings physical owners (2026-10-21; Draft PR #594 expansion)

- Physically move `single_line_merge_settings.py` → `crop/single_line_merge_settings.py` and `unlined_export_filter_settings.py` → `crop/unlined_export_filter_settings.py`, without root shims. This expands the existing UI progress/bookmarks candidate PR, not a new overlapping PR.
- Update export runners, Settings UI/controllers and regression imports, relocate source-path mutation guards instead of deleting or relaxing them. Retain per-page output manifests, project-local settings JSON paths, single-line crop merge semantics, unlined-row filtering and all persisted Profile/PDIC/PPP/SECTION data.
- Until exact-head full 3-OS × Python 3.10/3.13, GUI, wheel, CodeQL, review and postmerge main CI are verified, this is a candidate, NOT an accepted migration. Real scanned-page/Windows GUI/GPU parity requires human validation.


## Issue #562 — Auxiliary crop boundaries and UI controller (2026-10-21; Draft PR #594)

- True owner moves: `auxiliary_lines.py` → `crop/auxiliary_lines.py` for independent JSON sidecar and atomic storage; `auxiliary_line_controller.py` → `ui/auxiliary_line_controller.py` for Tk geometry and user edits. No root shims.
- Preserve source-image coordinates, auxiliary gap boundaries, undo/redo, per-page switching and direct PDIC independence. Update App, processing core, monkeypatch tests, architecture guard and source-tree ownership checks.
- Not yet accepted: complete exact-head CI + CodeQL + GUI + wheel + reviews + postmerge main; real image/UI/Windows parity awaits human acceptance.


## Issue #562 — Refinement LayoutRows reuse and inference policy leaves (2026-10-21; Draft #594)

- Physical no-shim moves: `marker_refinement_layoutrows.py` → `refinement/layoutrows.py`; `inference_performance.py` → `quality/inference_performance.py`. Move only the rule/cache reuse helpers and Paddle-agnostic inference settings policy, *not* the LayoutRows cache, refinement worker, GPU model constructors or Windows spawn runtime itself.
- Update both static and deferred imports, tests including policy monkeypatch target, and a stricter physical-owner guard. Preserve source-coordinate cache guards, Settings/CUDA policy, algorithm defaults and Model/PDIC/PPP/SECTION serialization by keeping function implementations unchanged apart from relative import resolution.
- Require exact-head Python 3.10/3.13 × Windows/macOS/Ubuntu, guard, GUI smoke, wheel, CodeQL, reviews and postmerge main CI; real Y/pixel/Windows GPU manual parity still pending.


## Issue #562 — Shared adaptive analysis denoising owner (2026-10-21; Draft #594)

- Physically relocate `adaptive_denoise.py` → `preprocess/adaptive_denoise.py` with zero algorithm changes and no root shim; the direct analysis-image builder, Layout replay, visualization controls and performance profile now import its canonical package path.
- Preserve environment-driven denoise strength, integral-mask semantics and punctuation/diacritic protection. Update existing source-ownership test to require the new owner, retaining its checks for other root facades. Add architecture guard against old path restoration; cross-platform GUI and real scans remain separate gates.


## Issue #562 — Large-head inspection UI diagnostic leaf (2026-10-21; Draft #594)

- Physical owner `large_head_visualization_ui.py` → `ui/large_head_visualization.py`, without root shim. Update opt-in overlays, compact display menu, Layout summary, ordinary inspector and relevant monkeypatch tests to canonical owner. Preserve only observational diagnostics and JSON export; no detection thresholds, PDIC/PPP writes, GPU lifetime, layout policy, or Settings persistence changes.
- Ratchet architecture ownership path; full CI/CodeQL/GUI/wheel, review and postmerge main still required. Human scanned-page diagnostic parity unverified.


## Issue #562 — OCR crop preview UI read-only owner (2026-10-21; Draft #594)

- Move `ocr_crop_preview_ui.py` physically to `ui/ocr_crop_preview.py`, no root shim. App keeps the same two redraw-time invocations; the preview uses the canonical OCR crop box, source canvas coordinates, regular/oversized preview colouring and active manual-review entry highlight.
- Existing architecture mutation guard now reads the new canonical path, with additional root-owner denial, and focused tests use the new module. OCR backend, model initialization, manual review state and PDIC fields are not altered; acceptance still requires full PR and main gates.


## Issue #562 — Layout stage-replay UI ownership (2026-10-21; Draft #594)

- Physically move `layout_step_replay_ui.py` → `ui/layout_step_replay.py`, no root shim. Deferred call from `layout_visualization_ui_v3` now points to UI owner; simulation traces, physical-row diagnostics, overlay/PPP read-only evidence and callback semantics retained. Runtime diagnostic test now expects actual module path, with no weakening of stage annotations.
- Retain Layout detector/physical-indent/cache/visualization installer root facades. Mandatory CI, GUI smoke, wheel, CodeQL and real Windows scanned-page manual review remain pending.


## Issue #562 — Deferred document unwarping preprocessing owner (2026-10-21; Draft #594)

- Move `document_unwarping.py` → `preprocess/document_unwarping.py`, with no model lifetime, GPU initialization or image algorithm change; only resolve parent-relative imports to the same existing Windows GPU initialization guard and environment resolver.
- Tighten source-path ownership and the existing run-time regression so it still verifies the Windows DLL helper executes BEFORE the deferred `paddleocr.DocPreprocessor` import at the moved canonical path; do not weaken or skip timing assertions.
- Requires exact-head cross-platform/CodeQL and real GPU model-owner/manual validation before acceptance.
