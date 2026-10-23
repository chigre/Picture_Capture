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


## Issue #562 — Platform-aware Tk UI compatibility functions (2026-10-21; Draft #594)

- Physically move internal `ui_compat.py` to `ui/compat.py` without introducing a legacy root shim; callers in dialogs, controllers, canvas overlays, Project Profile setup and Environment Center reference the same font/work-area helpers through the canonical owner.
- Preserve Tk font selection, native Windows caption semantics, geometry and user settings; function code is unchanged. Do not move public launcher/GUI entrypoints or alter startup side effects. CI and human Windows/macOS Tk parity remain acceptance gates.


## Issue #562 — UI owner cohort (2026-10-21, pending CI)

Base main `81c245f6544ceca3bb0ef7d2be6970e04424231c`: 54 root Python files. Candidate moves five modules without shims: `appearance.py`, `environment_center.py`, `unicode_nonbmp_input.py`, `layout_visualization_ui.py`, `layout_visualization_ui_v2.py` into `ui/` under their existing basenames; expected root 49 pending tree recount. Static and delayed imports, Tk GUI smoke, tests and physical-owner guard are updated. Root `layout_visualization_ui_v3.py` is retained for separate legacy-UI acceptance; `ui_terminology.py` and `settings_help_restore.py` remain historical compatibility. No data schema, Y algorithm, GPU owner, Windows spawn, source coordinates, PDIC/PPP/SECTION, manual review or parent-only writes are intentionally changed. Exact-head six-platform CI, CodeQL, GUI smoke, wheel, review, postmerge main and real scanned-page manual acceptance remain mandatory; no unverified green claims.

### Recovery checkpoint — 2026-10-21

- Candidate branch head `7dac0d11903c58f76413182d94321d3c98502b3f` was independently counted at **49** root `.py` (five actual physical moves from main 54). Diff has five renames, no deleted tests; app 784730 bytes is below unchanged 784737 ratchet. **No PR or candidate CI yet.**
- GitHub PR creation and Issue #562 comment/body-update calls were rejected by connector safety checks; Issue cannot be checkpointed through that channel in this run. Next run: verify main/open PR, retry the single Draft PR from this branch and post the checkpoint to Issue, then run exact-head six-platform CI, GUI smoke, wheel, CodeQL and reviews. Do not merge without full acceptance or claim human scanned-page parity. Issue remains open and hourly task continues.

### Provisional 49 root owners after this five-module candidate

Public/entry (11): __init__, __main__, app, cli, picdic, launcher, gui_io, processing, processing_core, facade_compat, models.
Persistence/Review (9): formats, project_storage, page_sections, pdic_restore, pdic_text_cleanup, processing_publish, entry_classification, entry_classification_fields, simplified_review.
UI compatibility (3): layout_visualization_ui_v3, settings_help_restore, ui_terminology.
Layout (7): layout_core_understanding, layout_detection, layout_detection_actions, layout_detection_legacy, layout_detector_live_binding, layout_physical_indent, layout_rows_cache.
OCR/GPU/runtime (9): ocr_channel, ocr_channel_legacy, ocr_engines, ocr_page_resume, paddle_headword_models, paddle_headwords, paddle_headwords_core, windows_gpu, runtime_environment.
Refinement (2): separator_y_refinement, marker_refinement_parallel.
Image (2): image_preprocessing, image_utils.
Evidence (2): evidence_fusion, symbol_evidence.
Crop export (2): single_line_parallel, unlined_line_export.
Training compatibility (2): training_export, training_export_ui.

All 49 are provisionally assigned, not final migration/retention decisions. Verify each with static/deferred imports, Windows spawn, GPU owner, Profile, PDIC/PPP/SECTION, real scans and original-pixel/Y/parent-writer invariants. Do not infer eligibility completion from root count.


### 2026-10-21 continuation: UI candidate repair and review gates (#562)

- Re-audited unchanged main `81c245f6544ceca3bb0ef7d2be6970e04424231c` (54 root Python files), no open PR; postmerge CI run 39603526591 and push/CodeQL run 39603527108 succeeded. The separate Dependabot resolution run 39603700868 failed and remains unrelated to package movement.
- Existing five-file no-shim UI candidate `refactor/issue562-ui-layout-diagnostics-20261021` was independently counted at **49** root Python files (untruncated Git tree, 886 entries). Repair deferred Environment Center imports with `..quality.draw_performance_profile` and `..quality.inference_monitor`; correct relocated source-path tests; exercise both callbacks without requiring Tk display or model initialization.
- Repair a preexisting lazy import in `app.py` for refinement per-page progress: `from .refinement.progress import report_refinement_page`. Add regression for the canonical owner and skip reporting. Do not change the refinement Y algorithm, workers, parent publication, image coordinates, manual review or PDIC/PPP/SECTION/Profile formats.
- This is **candidate code**, not accepted: exact branch-head six-platform Python3.10/3.13 CI, GUI smoke, wheel, CodeQL, reviews, secure merge and postmerge main CI/CodeQL must all be checked and recorded in Issue. No root shim or test/guard relaxation.
- The 49 remaining roots are provisionally assigned in the owner table above; the count is **not** a completed fraction of eligible migrations. Retained entry/facade/API paths and high-risk GPU/spawn, Layout, Y-refinement, PDIC/PPP/SECTION, Review and Profile boundaries need independent ownership decisions and human scanned-page/native Windows/macOS acceptance. Continue hourly; do not close Issue.

### Issue #562 — 2026-10-21 proofreading companion-sidecar and selected-scope cleanup cohort (candidate)

- Base verified main `710b92c1766f318d9303e9ee71ad0ee7abd64817`, **49** direct root Python files. Previous postmerge CI #39626950673 **6/6 SUCCESS** and push CodeQL #39626956591 **SUCCESS**; no open PR prior to new branch.
- Real no-shim physical owners: `simplified_review.py → proofreading/simplified_review.py` (review companion JSON reader/writer) and `pdic_text_cleanup.py → proofreading/pdic_text_cleanup.py` (explicit selected-page PDIC word-only cleanup). Move 2 modules; intended candidate root **47** (verify exact full tree). Update App static/deferred imports, refinement guard, explicit marker move controller, proofreading bundle, tests and architecture ratchet; no old-root compatibility files.
- Serialized simplified companion JSON `picture_capture_simplified_review` / version 1 / page / stable XY keys unchanged, write strategy remains temp+replace. PDIC text clearing still validates every source before atomic write and requires confirmation, saves foreground edited page, preserves marker coordinates and all other columns; do not alter actual PDF/PDIC/PPP/SECTION or semantic thresholds. Existing Python logic unchanged except relative package import.
- App source size ratchet **not loosened**: shorten an adjacent equivalent reading-order docstring to offset two canonical imports; no change to the reading-order algorithm. Keep Tk, parent-only guarded writes, Windows spawn and GPU owners unchanged.
- Remaining 47 provisional owners: entry/API (11) `__init__, __main__, app, cli, picdic, launcher, gui_io, processing, processing_core, facade_compat, models`; persistence/review (7) `formats, project_storage, page_sections, pdic_restore, processing_publish, entry_classification, entry_classification_fields`; UI historical (3) `layout_visualization_ui_v3, settings_help_restore, ui_terminology`; layout (7) `layout_core_understanding, layout_detection, layout_detection_actions, layout_detection_legacy, layout_detector_live_binding, layout_physical_indent, layout_rows_cache`; OCR/GPU/runtime (9) `ocr_channel, ocr_channel_legacy, ocr_engines, ocr_page_resume, paddle_headword_models, paddle_headwords, paddle_headwords_core, windows_gpu, runtime_environment`; refinement (2) `separator_y_refinement, marker_refinement_parallel`; image (2) `image_preprocessing, image_utils`; evidence (2) `evidence_fusion, symbol_evidence`; crop export (2) `single_line_parallel, unlined_line_export`; training compatibility (2) `training_export, training_export_ui`. This is provisional classification, NOT proof all are safely movable. Entry points, legacy adapters and guarded process/model/persistence owners need individual keep-vs-move decisions.
- **Candidate only**: require exact HEAD six Python3.10/3.13 × Windows/macOS/Ubuntu CI, GUI smoke, source guard, wheel, CodeQL, reviews, fixed-head merge, postmerge main CI/CodeQL. Real native Tk/manual scanned-page/Profile/PDIC/PPP/SECTION/GPU/Y/parent-safe-write acceptance remains human-unverified; do not close Issue until original DoD.


### Issue #562 — Entry classification descriptor physical owner (candidate synchronized after PR #596, 2026-10-22)

- Baseline merged main `19fdcddaf6190de35dfcc8f071dded92a4cc9dbe` has **47** direct root Python files (complete direct Git-tree enumeration). PR #596 physically packaged two proofreading sidecars; preserve their ownership guard and tests.
- Physical no-shim relocation `entry_classification_fields.py` → `proofreading/entry_classification_fields.py`, including all eight deferred `models.Entry` property imports and the focused pipeline test; install no-op and registry/lifetime/height/manual-override semantics unchanged. Keep `entry_classification.py` at root until further cycle/serialization audit.
- Architecture guard now enforces both the PR #596 owners and this Entry owner; one new focused test validates absence of old path and canonical imports. This is **one** bounded low-risk leaf migration separated from incompatible Layout/OCR/GPU/PDIC cohorts, not a default batch-size change or a full subpackage completion. If merged, predicted direct root 47→46; must verify in complete Git tree.
- Provisional remaining **46** after this candidate: public/entry 11; persistence/review 6; UI historical 3; Layout 7; OCR/GPU/runtime 9; refinement 2; image 2; evidence 2; crop/export 2; training compatibility 2. Retention/eligibility must be individually audited before claiming completion. All historic CLI/GUI/PDIC/PPP/SECTION/Profile/Y/manual proofreading, GPU single-model ownership, Windows spawn and parent guarded writers stay intact.
- **Acceptance pending**: exact candidate six-job Python 3.10/3.13 × three OS CI, deferred/static imports, architecture guard, GUI smoke, wheel, CodeQL, reviews, safe fixed-HEAD merge and postmerge main CI. Native scanned-page UI/GPU/Y/PDIC parity is still human-unverified. Issue #562 remains open.


### Issue #562 — OCR engine helpers and headword-data model owner (2026-10-22, candidate)

- Starting point: verified `main@b5b2bd8ef24228dd50389639343ea6e3ad839923`, **46** direct root Python modules, [postmerge CI #39639715061](https://github.com/chigre/Picture_Capture/actions/runs/39639715061) Python3.10/3.13 × Win/macOS/Ubuntu **6/6 SUCCESS**, [CodeQL #39639716931](https://github.com/chigre/Picture_Capture/actions/runs/39639716931) **2/2 SUCCESS**. Open PR count zero before this candidate.
- Physically move two OCR-owned internal leaf modules, without old-root shim: `ocr_engines.py` → `ocr/engines.py` (Tesseract binary discovery/status, Google Lens parsing/runner) and `paddle_headword_models.py` → `ocr/headword_models.py` (headword OCR dataclasses). Update `paddle_headwords_core`, `ocr_channel`, `processing_core`, `ui/environment_center`, `ocr/tesseract_runner`, and large/focused tests to canonical imports and monkeypatch paths.
- **Preserve pickle module identity** for OCR classes: `__module__ = "picture_capture.paddle_headwords_core"` and the historical `paddle_headwords` facade/core API. Preserve Tesseract search fallback and Lens data/coordinate behavior, GPU single-engine ownership, Windows spawn and source pixel geometry. Retain root `ocr_channel`, `ocr_channel_legacy`, `paddle_headwords_core`, public facade and `ocr_page_resume` (the latter has root-relative source-tree fingerprinting and a specific root ownership guard); do not move them with this leaf cohort.
- Physical ownership guard added without changing any existing ratchet; focused test asserts no retired import path in source/tests/scripts, stable pickle/identity, and proper canonical path. Candidate root count expected **46 → 44**; independently verify using complete Git tree, not a claim of CI acceptance.
- PR Python3.10/3.13/Windows/macOS/Ubuntu matrix, GUI smoke, wheel, specialized OCR/parser/portability tests, architecture guard, CodeQL/reviews, fixed-head merge, postmerge main CI and genuine scanned-page manual/GPU/PDIC/PPP/SECTION/Profile/Y behavior are separate nonwaived gates. No human parity claimed.


### Issue #562 — GUI Layout detection action owner (prepared, 2026-10-22)

- Baseline after merged #598: `main@f33e2139641c573024b9535c64c855289b3d045e` with **44** directly rooted Python files (postmerge CI/CodeQL still pending at preparation time; do not treat queued main as accepted). This is a preparation branch only; no new PR until exact-head #598 main CI/CodeQL passes.
- Move the **single GUI callback implementation** `layout_detection_actions.py` → `ui/layout_detection_actions.py` with no old root shim. Keep `PictureCaptureApp.detect_layout_current`, `detect_layout_consistency_selected` and the original GUI batch worker/done semantics, confirmation, robust aggregation, settings update, reading direction and source-coordinate reports exactly as they were. Rewrite its package-relative dependencies to `..layout_detection`, `..geometry`, `..project_storage` and `..layout.parameter_evidence`; update `app.py` wiring and tests containing direct source-path reads. This is a UI action owner, not a relocation of Layout algorithms/detector facades.
- Preserve root `layout_visualization_ui_v3.py` deliberately: `tests/test_ui_physical_ownership_20261021.py` explicitly treats it as a high-risk retained historical integration boundary; preserve `layout_detection.py` facade and `layout_detection_legacy.py` monkeypatch seams, `layout_physical_indent.py`/row cache/Y semantics. Do not rename or delete these to meet an arbitrary batch count.
- Tighten physical owner architecture guard without changing baselines, plus focused UI-owner regression. Candidate **44→43** roots only after actual complete-tree enumeration and eventual merge. Full exact-head Python3.10/3.13 × Win/macOS/Ubuntu, GUI smoke, wheel, static/lazy imports, CodeQL/reviews and postmerge main CI plus real native scanned-page human parity remain mandatory.

### Issue #562 — 43-root full ownership & compatibility audit (2026-10-22)

- Audited `main@020b8a81e9bb2e64c5e604b58c860cd10535b01a` direct 43 `.py` roots (non-truncated Git tree; 43/43 static source inspected), correlated bootstrap, guard, package scripts and existing tests. **Full detailed audit:** [`ISSUE562_ROOT43_OWNERSHIP_AUDIT_20261022.md`](ISSUE562_ROOT43_OWNERSHIP_AUDIT_20261022.md).
- Decisions: **31 currently retained roots (K), 11 conditional migration only after explicit compatibility gates (D), 1 initial single-file candidate (P: `symbol_evidence.py` → `layout/symbol_evidence.py`)**. These are review decisions, not proof of future safe migration.
- High-risk boundaries explicitly retained: Layout original-image X/Y and read direction; shared image source pixels, EXIF/alpha; worker bootstrap/spawn-pickled functions and single GPU owner; `ocr_page_resume` full package fingerprint; PDIC/PPP/SECTION/Profile, manual page locks, parent-only writes and crash journal; pickle/monkeypatch facade.
- Non-migration follow-up risks to test separately: direct `AppSettings.to_json` write; fixed `<section>.tmp` name in `write_page_sections`; repeated DLL handle retention in Windows GPU config. Not proven defects and **not** used to bypass tests or change migration guard.
- Baseline [main CI #39645635340](https://github.com/chigre/Picture_Capture/actions/runs/39645635340) six-platform 6/6 and [push/CodeQL #39645635860](https://github.com/chigre/Picture_Capture/actions/runs/39645635860) 2/2 succeeded. Native GPU, real scanned-page manual parity remain unverified; #562 stays OPEN and hourly task enabled.


### Issue #562 — sampled Symbol Evidence canonical Layout ownership (candidate; 2026-10-22)

- **Gate:** [#600](https://github.com/chigre/Picture_Capture/pull/600) root43 audit merged as `main@04995a7f3e24ac1db63aac0528a7fc9a78cab442` after original-head 6/6 CI and 2/2 CodeQL. Verify #600 postmerge main CI before accepting any next move; do not conflate doc-only PR checks with new runtime migration.
- **One physical no-shim domain move proposed:** `symbol_evidence.py` → `layout/symbol_evidence.py`; source imports now use `..image_utils`, `..layout_detection`, `..models`, `..ordinary.visual`, `..visual.marker_templates`, and the local Page Design helper `..design.page_design`. Static consumers `layout/page_understanding.py`, `layout/page_understanding_fusion.py`, `layout_core_understanding.py` and synthetic Profile marker tests use the new exact owner. This module is distinct from existing `ordinary/symbol_evidence.py`, which must remain unchanged. No tests removed or legacy-root shim provided.
- Safety ratchets: package `layout/__init__.py` remains import-light; root `layout_detection.py` facade, PageUnderstanding/Y/physical caches, core bootstrap, GPU/Windows spawn and data writers remain unchanged. Proposed regression asserts actual physical owner, no old imports, saved-sample **entry** marker can propose an entry while **bracket_open** cannot, marker source coordinates round trip for identity/mirror/CCW/CW, and previous Profile + fusion fixtures still pass.
- **Candidate expected root 43→42** (must independently verify via complete Git tree and again postmerge). Class objects `SymbolMarkerEvidence`/`SymbolEvidenceResult` are internal runtime data; their `__module__` changes with physical move. Historical external pickle compatibility for these internal classes is not established; do not assert it. Persisted PDIC/PPP/SECTION/Profile/Y/Entry schema unchanged.
- Merge requires exact-head 3.10/3.13 × Windows/macOS/Ubuntu complete pytest, GUI smoke, wheel, static and deferred imports, architectural and change-policy guards, CodeQL/Review, fixed-head lease merge and postmerge main CI. Real scanned-page and NVIDIA GPU/human correction parity is still unverified. If circular-import/serialization issues appear, keep Draft and fix before merge; #562 stays OPEN.

### Issue #562 — approved risk-tier CI policy (2026-10-22; pending policy PR)

- Approved classification and gates are proposed in `docs/architecture/CI_RISK_POLICY.md` and enforced by `scripts/ci_risk_tier.py`. Documentation-only: lightweight architecture guard; verified AST import-only/root-rename: Ubuntu Python3.13 + Ubuntu/Windows Python3.10 full suites; actual behavior, API/format, GPU, spawn, image/geometry, dependency and workflow changes: full six-platform 3.10/3.13 matrix.
- Daily full main CI, tag/manual full CI, stable risk-tier aggregate gate and CodeQL/reviews remain. This alters **test cadence, not architecture ratchets or feature behavior**. If branch rules still require old individual macOS checks, defer to the rules until an authorized admin updates them; GitHub protection read returned 403.
- Existing PR #601 completed old full matrix before merge; do not retroactively relabel old runs as risk-tier CI. No real scanned-page, native CUDA or human PDIC/Y acceptance implied.


### Issue #562 — next single OCR-channel compatibility bridge owner (2026-10-22; candidate)

- **Previous accepted main:** `6a54be91d1bff2c68e596da5b69fa97f10065f2f`, 42 direct root Python files, with [main CI #39719037295](https://github.com/chigre/Picture_Capture/actions/runs/39719037295) 6/6, [push CodeQL #39719037639](https://github.com/chigre/Picture_Capture/actions/runs/39719037639) 2/2. No open PR at candidate preparation; Issue #562 OPEN.
- **One physical move, no old import shim:** `src/picture_capture/ocr_channel_legacy.py` → `src/picture_capture/ocr/channel_legacy.py`. This is the narrow internal OCR-channel compatibility bridge, **not** the public `ocr_channel.py` API, the parser core or the OCR engine owner. Production bridge client `ocr/boundary_detection.py` now uses sibling import; two test modules use new canonical path. The OCR package initializer remains import-light, and no old root is created. Proposed direct root count **42→41**; must validate complete tree before merge and main tree after.
- **Preserved behavior:** Original `_LEGACY_RUNNER_LOCK` (process-local reentrant mutex), cached original legacy core function objects, conditional respect for an externally patched runner, and `try/finally` restoration of all four core runner call sites. Channel plan → old `paddle_*` settings uses a copy; neutral OCR records preserve source rectangle, y-overlap regrouping and error handling. Existing `tests/test_ocr_channel.py` and `tests/test_ocr_channel_runner_semantics.py` remain; added targeted regression for nested bridge context, exceptions, exact original-runner identity, no retired root shim and no obsolete production/test Python imports.
- **Historical compatibility judgment:** The `ocr_channel_legacy.py` name is explicitly a parser runner *adapter*, not an advertised stable public entrypoint; known in-repo callers have been updated, `ocr_channel.py`/public `paddle_headwords.py` stay at root. However, third-party private imports of the old bridge module have **not** been inventoried outside the repository and will break with intentional no-shim physical removal. No classes with historical `__module__` pickle identity are defined by the bridge. Do not claim universal third-party import compatibility.
- **Strict risk tier:** `src/picture_capture/ocr/` is protected by `scripts/ci_risk_tier.py`; this migration MUST run full Windows/macOS/Ubuntu × Python3.10/3.13, GUI smoke, wheel, architecture/change guards and CodeQL, then fixed-head review and postmerge main. It must not be misclassified as fast despite import-only AST. Real Windows CUDA/GPU model owner, genuine scan-page human review/PDIC/PPP/SECTION/Profile/Y remain unverified.


### Issue #562 — AppSettings configuration-save transaction hardening (2026-10-22; independent candidate)

- Base `main@a60eb259e6781f8ee59078adc2e67a6432515e5d`, 41 direct root Python modules, no open PR; prior [main CI #39721069436](https://github.com/chigre/Picture_Capture/actions/runs/39721069436) six-platform 6/6 + gate, [CodeQL #39721069631](https://github.com/chigre/Picture_Capture/actions/runs/39721069631) 2/2. After 41-root reassessment, remaining candidate moves have higher historical API / monkeypatch / image / spawn / persistence risk; deliberately prioritize a **single high-value transaction-safety bug** instead of forcing another file-count reduction.
- Verified `AppSettings.to_json()` currently serializes canonicalized settings correctly, but publishes with `path.write_text()` directly into the live settings file. A truncated/failed save can leave the user's project configuration unreadable. **Candidate change only to publish stage:** same-directory unique temporary (no competing fixed `.tmp`), flush and `fsync` temporary, then `os.replace` original; clean temporary on failure. Preserve canonical JSON, unicode, display opacity normalization, roundtrip historical settings migration and public `models.AppSettings` API. `from_json()`, project migration, PDIC/PPP/SECTION/Profile and GUI controller unchanged. This protects against ordinary process interruption before atomic replace; it does not establish power-loss directory durability or safe precedence among concurrent writer updates (last complete writer wins).
- Add failpoint regression that raises `OSError` at `fsync` and `os.replace` and checks **original config bytes unchanged**, no temporary artifacts, and old `AppSettings.from_json()` still succeeds; nonexistent target stays absent on failed first publish; roundtrip Unicode/legacy compatibility remains; concurrent saves must leave one full valid JSON document and clean temps.
- **High risk under automatic classifier:** `models.py` is a pinned root schema owner; this is a behavior change and must remain `full` (Windows/macOS/Ubuntu × Python3.10/3.13 + Risk-tier gate, CodeQL and reviews). Do not move `models.py`, change schema/defaults or relax tests/ratchet. PR, CI and postmerge main evidence to be recorded separately. Issue #562 stays OPEN; real crash/power-loss in physical hardware and native GPU/manual page review remain unverified.

- **Windows concurrent-writer correction (PR #604 follow-up):** First exact-head [CI #39722283981](https://github.com/chigre/Picture_Capture/actions/runs/39722283981) had one real Windows3.13 failure: eight concurrent saves can overlap `os.replace` and cause `PermissionError: [WinError 5]` even with unique temporary names (other 3044 tests passed). Fixed by adding an in-process `threading.Lock` around the complete temporary-write/replace/cleanup transaction. Keep the concurrent-save test, re-run all six platforms on new exact HEAD. This does not guarantee serialized precedence across distinct processes or external antivirus open handles.


### Issue #562 — SECTION sidecar atomic publication and same-page writer safety (2026-10-22; candidate)

- Verified existing main `36c5068dda30b678cb227829f4c3b2b1546244cb`: 41 direct root modules; [full main CI #39723236619](https://github.com/chigre/Picture_Capture/actions/runs/39723236619) **6/6 plus Risk-tier gate** and [main CodeQL #39723236941](https://github.com/chigre/Picture_Capture/actions/runs/39723236941) **2/2 success**. Zero open PRs at task start. This batch is a **safety correction**, not a forced module migration; root count remains **41**.
- **Pre-existing real race / truncation risk:** `page_sections.write_page_sections()` writes to a fixed `*.json.tmp` using `Path.write_text` before `Path.replace`. Overlapping same-page save calls can share/truncate the same staging file; an interrupted process leaves a stale fixed tmp and Windows may reject overlapping replace. This concerns user-managed SECTION sidecar data, so no changes to coordinate conversion, reading direction, JSON v2 schema, or original-image source X/Y mapping are permitted.
- **Candidate fix:** same-directory *unique* temp file and serialized complete payload; flush and `os.fsync` before `os.replace`; cleanup temp on exception. One module-level in-process `threading.Lock` covers publication and Section=0 canonical deletion to prevent same-process publication/removal overlap. Existing rule preserved: Section=0 with migrated QT fallback writes an explicit empty canonical sidecar rather than removing it, preventing legacy sections from reappearing. No source-size or transform changes; no PDIC, PPP, Profile or parent-writer alterations.
- **Regression:** byte-for-byte previous SECTION file intact after injected `fsync` or `replace` failure; initial failed publish leaves absent target, no partial new temp; eight simultaneous writers produce one fully valid SECTION v2 sidecar; pre-existing abandoned fixed `.json.tmp` cannot contaminate new publication; explicit Section=0 without migrated history still unlinks; identity, mirror-x, rotate-cw90 and rotate-ccw90 source-coordinate roundtrips checked. All pre-existing migrated-QT fallback / proofreading section identity tests remain.
- **Risk tier:** protected `page_sections.py` is full. Gate requires exact-head six Python3.10/3.13×Windows/macOS/Ubuntu test jobs, UI smoke, wheel, architecture/change guards, CodeQL, fixed-head merge and postmerge main. Cross-process writer ordering, physical power loss/parent crash and native CUDA/actual human scan acceptance remain unproven; Issue #562 remains OPEN.


### Issue #562 — managed-v2 project manifest atomic publication (2026-10-22; current candidate)

- Accepted base: `main@5b91d3a31f699a304f03f4ef6e6b7e49ecee0695`, 41 direct-root Python modules and **zero open PR**. [Main CI #39730409823](https://github.com/chigre/Picture_Capture/actions/runs/39730409823) six full jobs and Risk-tier CI gate SUCCESS; [CodeQL #39730409861](https://github.com/chigre/Picture_Capture/actions/runs/39730409861) both jobs SUCCESS.
- **Audited ownership:** `project_storage._write_json_atomic` is used to publish managed-v2 `_PictureCapture/project.json` in `ensure_project_storage()` **and** the same manifest inside the explicit legacy-migration staging directory. The pre-existing code uses a fixed sibling `project.json.tmp`, text write and replace without fsync. Two concurrent opens/manifest refreshes can share that temporary path; an interrupted writer can leave a truncated stale staging file. The manifest is how `is_managed_project()` decides whether files belong in managed-v2 or legacy paths, so this is a higher-impact persistence boundary than a cache.
- **Scoped change, no schema update:** serialize exactly the same `ensure_ascii=False, indent=2` JSON, write a **unique same-parent temporary**, flush+fsync, close and atomically `os.replace`, then clean uncommitted temp on error. Process-local lock around publication prevents concurrent same-process replacements on Windows. Existing `PROJECT_FORMAT`, format version 2, `created_with`, `last_opened_with`, cache identity invalidation, migration stage publication, user-scanned source files and all legacy paths remain unchanged. This is *not* a module relocation; root count **41**.
- **Tests-first regression:** managed-v2 manifest JSON/Unicode/project routes and unchanged user scan plus `created_with` contract; failpoint `fsync`/`replace` retains old manifest bytes and managed path selection; failed first replace does **not** make an unmanaged project appear migrated; eight concurrent refreshes yield one complete v2 manifest; a stale retired `project.json.tmp` is never touched and cannot contaminate new data. Preserve all prior legacy migration and malformed-version tests.
- **Strict gate:** protected `project_storage.py` and behavior change must run full Windows/macOS/Ubuntu×Python3.10/3.13 CI, architecture/change guards, GUI smoke, wheel, CodeQL and stable gate; fixed-head merge and postmerge main recheck. A process-local lock does **not** provide inter-process CAS or guarantee ordering between different processes, directory fsync under hard power loss, or native GPU/scanned-page human parity. Issue #562 OPEN.


### Issue #562 — crop journal self-confinement at project startup (2026-10-22; candidate)

- **Intake:** accepted `main@be88614a51886ab5c4b8641b58c43b07aa822bf4`, [main CI #39733144144](https://github.com/chigre/Picture_Capture/actions/runs/39733144144) all six+Risk-tier gate SUCCESS and [main CodeQL #39733144121](https://github.com/chigre/Picture_Capture/actions/runs/39733144121) 2/2 SUCCESS; zero open PRs. Complete non-truncated Git tree **900 entries**, direct root Python files **41**. PR #604 settings, #605 SECTION, #606 managed-v2 manifest have already merged; none are being reworked here.
- **Specific safety gap (existing implementation, no production incident alleged):** `processing_publish._recover_journal(..., allowed_root=QT)` checked every `originals`/`staged` payload path against the resolved project QT root but **not the journal file itself**. A journal located outside QT (e.g. discovered via a symlinked immediate QT child folder) could therefore be read and consumed during project-open recovery, rolling back in-project output or deleting in-project backups even though the transaction marker belongs to another directory. The normal publisher generates journals inside the first target's QT output folder, so a strict journal-path check should preserve legitimate exports.
- **Single narrow correction:** resolve and validate the journal's own path against `allowed_root` **before JSON read or any mutation**; preserve existing payload confinement, pending rollback, committed cleanup, cross-QT-directory crop plan/PNG transaction, journal v1 schema, backup naming, project paths, API and `allowed_root=None` local rollback. No module move, no data format or image coordinate change; root count **41**.
- **Deterministic positive/negative regression:** external journal with fully internal payload is rejected in both pending and committed states, and both old/new in-project bytes and external journal remain untouched; malformed outside JSON is rejected before parse; legitimate internal cross-directory pending rollback and committed cleanup remain idempotent; existing outside-payload refusal still protects original user scan. Existing tests for injected failed publication, failed rollback preservation, project-open recovery and monkeypatch API remain. No test removed/xfailed and no guard relaxed.
- **Gate:** `processing_publish.py` is `ALWAYS_FULL` in `scripts/ci_risk_tier.py`; require exact-head Python3.10/3.13×Windows/macOS/Ubuntu six-job CI, GUI smoke/wheel, Risk-tier gate, CodeQL, review threads and stable main before fixed-head squash; postmerge main checks mandatory. This validates synthetic path/failpoint scenarios, **not** arbitrary symlink races/TOCTOU, cross-process publication ordering, hard power loss, real scanned-page Tk/PDIC/Y, or native CUDA. Issue #562 remains OPEN.


### Issue #562 — Windows managed-v2 manifest reader/publisher synchronization (2026-10-22; candidate)

- **Base:** `main@f7b0534076ac2b33275d2b371e8b77c0b6a79e2f`; postmerge #607 main six-job CI and CodeQL successful, no open PR, complete 901-entry untruncated Git tree, root `.py` = **41**. #607 was one crop-journal boundary fix and is not modified by this cohort.
- **Observed trigger:** #607's first Windows Python3.13 CI attempt raised `PermissionError: [WinError 5]` during #606's eight-thread `ensure_project_storage` test at `project_storage._write_json_atomic(): os.replace(temp, manifest)`, while 3066 other tests passed; retry succeeded. This is a real one-off CI failure, not evidence of disk corruption or a verified root cause on all Windows systems.
- **Narrow gap:** #606's non-reentrant `_MANIFEST_WRITE_LOCK` guarded only the temporary file write and replacement. `ensure_project_storage()` loaded/modified the existing manifest **before** acquiring that lock; `is_managed_project()` parsed it outside the same writer lock. Concurrent readers can hold a destination handle when Windows rename/replacement occurs, and concurrent refreshes can derive updates from stale content.
- **Fix:** replace that process-local lock with `threading.RLock`; protect the complete `ensure_project_storage` read/modify/atomic-publish/cache-clear transaction and the `is_managed_project` stat/parse/cache lookup. Protect explicit cache clear as well. Keep the nested low-level writer lock. No retry/sleep masking, no file format changes, no cross-process lock claims. Unique same-directory staging, flush/fsync, and `os.replace` are retained; `created_with`, `last_opened_with`, metadata passthrough, legacy routing and migration remain unchanged.
- **Regression:** deterministic pause of a managed manifest parser with a synthetic Windows open-reader refusal on `os.replace` demonstrates that a writer waits for the reader; staged first publication with a second concurrent opener proves the latter cannot read stale metadata and the last version plus external metadata survive. Preserve #606's original 8-thread stress, failpoint fsync/replace, first-create nonactivation, and legacy project migrations.
- **Gate:** high-risk `project_storage.py` requires exact-head Python3.10/3.13 × Win/macOS/Ubuntu full CI, Tk smoke, wheel, risk-tier gate, CodeQL Python/Actions, review and postmerge main. Real GPU, real scans, inter-process readers, antivirus locks, external direct `Path.read_text` and hard power loss are out of scope. Issue #562 remains OPEN.


### Issue #562 — physically move the Crop publication transaction owner (2026-10-22; candidate)

- Base `main@f72db47d59a2f70eee32867753d0c0df04d08fa7` with postmerge CI [#39740059993](https://github.com/chigre/Picture_Capture/actions/runs/39740059993) and CodeQL [#39740060368](https://github.com/chigre/Picture_Capture/actions/runs/39740060368) successful; zero open PR at start. Complete baseline Git tree 902 entries, direct-root Python **41**.
- Physical owner `processing_publish.py` → `crop/publish.py`, **no old root shim**, expected direct-root Python **41→40** pending complete candidate-tree recount. Production `processing_core` retains public/facade aliases and `processing.py` monkeypatch propagation, while `ProjectState.open` continues to invoke the same recovery function from its new canonical module.
- Adjust root-relative lazy `qt_root` import for package depth, all known production static/lazy and test imports; update crop journal failpoint, pending-vs-committed recovery and symlink-boundary regressions. Strict architecture guard rejects resurrecting the original root module.
- **Safety:** preserve journal v1 payload, pending rollback and committed cleanup, temp `os.replace`, original-image/file paths, no over-QT recovery, independent crop/stale cleanup, operator edits, PDIC/PPP/SECTION/Profile and no new Paddle/GPU/session ownership. No intended behavior change. Historical imports of this internal implementation path must use the canonical package path; no compatibility file is retained at the old location.
- **Acceptance:** protected crop domain in `ci_risk_tier.ALWAYS_FULL_PREFIXES`; exact-head full Python3.10/3.13 × Win/macOS/Ubuntu six jobs, Tk smoke/wheel, architecture guard, CodeQL, no unresolved review thread, fixed-head merge, postmerge main verification. Real scanned pages, native GPU and power-loss concurrency have not been validated; Issue remains OPEN.


### Issue #562 — OCR supervised evidence-fusion owner physical move (2026-10-22; candidate)

- Accepted intake baseline: `main@520a47f829e335281a6c09f5a17590b33938bb9b`, main CI #39744826885 SUCCESS, CodeQL #39744827500 SUCCESS, no open PR, 903-entry untruncated main Git tree and **40** root Python modules.
- Move `evidence_fusion.py` → `ocr/evidence_fusion.py` without a root shim. Preserve executable function bodies and original `OCRRecord` / `HeadwordFilterRule` class identity in `paddle_headwords_core`; only rewrite package-relative imports, `paddle_headwords` public facade, `ocr/boundary_detection` lazy consumer, tests, architecture guard and Ruff path-specific diagnostic exception. Do not move `paddle_headwords.py` or core (legacy plugin/monkeypatch/pickle contracts).
- Retain supervised filter callback injection and no import-time `_core` assignments, user-reviewed evidence decisions, source X/Y, page/column boundaries, manual/auto PDIC, GPU singleton lifecycle and OCR-channel engine choice. Existing supervised/peer-style/model-identity tests plus new physical path/facade identity tests must pass.
- Package move changes an internal dotted implementation import; external consumers should use canonical `picture_capture.ocr.evidence_fusion`, public `picture_capture.paddle_headwords` remains. No deep-compatibility shim. Full-risk path (OCR protected prefix) requires six OS/py matrices, source guard, Tk/wheel and CodeQL, fixed-head merge and postmerge verification. Manual real scanning and native GPU still not claimed; Issue #562 OPEN.


### Issue #562 — serialize EntryClassification sidecar transactions (2026-10-22; candidate)

- Accepted baseline `main@98fd3b3a498d33f40c8c320b8b2fd4223d8ea25d`; the previously pending macOS Python3.13 postmerge CI now succeeded: full main CI #39746548896 and CodeQL #39746548965 both SUCCESS, OCR platform smoke #39746548917 SUCCESS. Complete 904-entry untruncated tree; root Python count **39**, no open PR at intake.
- **Focused persistence gap:** existing `entry_classification.write_classification_sidecar()` reads old sidecar rows and matches/preserves manual overrides before its atomic `os.replace`. Concurrent same-process writes can load stale rows before another saves, causing manual classification changes to be lost despite each individual JSON write remaining parseable; `apply_classification_sidecar()` could also read between logical publication stages.
- **Narrow fix:** a module-private process-local `threading.RLock` wraps the complete write read/match/manual-preservation/`_atomic_json` transaction and the apply read/map transaction. Core matching algorithm, JSON v1 schema, EntryClassification runtime registry and weakref identity, PDIC writer wrapper, fsync/same-directory unique temp/atomic replace and no-op semantics are unchanged. Avoid cross-process/CAS/durable disk guarantees.
- **Regression:** deterministic event-gated pair of writers saving different manual corrections on the *same* page with distinct Entry objects; assert the second waits, resulting final sidecar and fresh Entry restore retain both choices. Parallel sidecar reader waits for first writer's publication; injected `os.replace` failure leaves old JSON bytes and cleans unique temp. Prior registry, manual delta, no-op autosave, PDIC composition tests remain intact.
- **Gate:** protected `entry_classification.py` requires exact-head six CI platform/py jobs, GUI/wheel/architecture guard, Risk-tier final gate, Python/Actions CodeQL, zero unresolved review, fixed-head squash and postmerge main CI. No file move; direct-root module count **39→39**. Issue OPEN, no real-scan/manual UI, native GPU, antivirus or interprocess claims.


### Issue #562 — extract pure OCR-channel text arbitration to canonical OCR owner (2026-10-22; candidate)

- Accepted base `main@f6804bc8d0a888282d09cb7a42b7d906d50c724c` with successful postmerge [CI #39749363020](https://github.com/chigre/Picture_Capture/actions/runs/39749363020) (6/6 and risk gate) and [CodeQL #39749362753](https://github.com/chigre/Picture_Capture/actions/runs/39749362753) (2/2), no open PR. Full untruncated tree 905 entries and **39** direct-root Python files.
- Existing ownership audit explicitly freezes `layout_rows_cache.py`, `layout_physical_indent.py`, `layout_visualization_ui_v3.py`, `image_utils.py` and historical compatibility shims. Do not bypass those tests merely to reduce a file count. This batch is an **implementation extraction**, not a root-file move; count remains **39→39**.
- Move the *unchanged bodies* of `channel_text_key` and `choose_ocr_text` from the historical public `ocr_channel.py` to **`ocr/text_arbitration.py`**; re-export exactly those function objects at the original public import path. The new import-light leaf uses only pure Unicode/text voting logic; `OcrChannelPlan` and `OcrTextChoice` remain physically defined in `ocr_channel.py` to keep their pickle `__module__` and type identity. No OCR engine, GPU lifetime, candidate geometry, page coordinates or headword parser policy is changed.
- Regression asserts canonical vs legacy function identity, NFKC/whitespace agreement, priority and diagnostic Lens exclusion, stable first-voter fallback, OcrTextChoice pickle type identity and standalone leaf-first import with no cycle. Architecture guard forbids duplicate channel voting bodies and requires the canonical import.
- Gate: OCR owner path and the historical `ocr_channel.py` are protected (full six Python 3.10/3.13 × Windows/macOS/Ubuntu jobs, GUI smoke/wheel, risk-tier gate); CodeQL Python and Actions, optional OCR CPU platform smoke, fixed PR HEAD/base and no unresolved reviews, then main postmerge checks. Real scans/native GPU still not manually validated. Issue remains OPEN.


### Issue #562 — extract source-space pixel primitives to preprocess owner (2026-10-22; candidate)

- Accepted intake baseline `main@12c8e86735d5c005d3a8dccad54cddebf29f718b`, [main CI #39755070667](https://github.com/chigre/Picture_Capture/actions/runs/39755070667) six-matrix + final gate SUCCESS, [main CodeQL #39755071556](https://github.com/chigre/Picture_Capture/actions/runs/39755071556) 2/2 SUCCESS, no open PR. Full nontruncated 907-entry tree with 39 direct-root Python modules.
- Preserve the explicitly frozen `image_utils.py` root import contract. Physically extract the **unchanged** bodies of `normalize_page_rgb`, `_box_sum` and `_generic_analysis_ink` into canonical `preprocess/page_pixels.py`, and re-export the very same function objects at historical `picture_capture.image_utils`. `build_analysis_image` retains its original body and resolves these names through its own module globals; source-space coordinate resolution, EXIF transpose, RGBA/LA/P white alpha compositing, RGB deep-copy, signed-equivalent uint8 threshold, and 2D integral zero-padding semantics are preserved.
- No new analysis pixel path, no change to `adaptive_speck_remove_mask`, user denoise choices, prepared-image experimental default, geometry/deskew, original scan ownership or picture file formats. The root facade's implementation shrinks by 81 lines; root Python file count **39→39** because outside callers/tests explicitly require that import path.
- Regression: physical leaf owner and exact public function identity, fully transparent/semitransparent RGBA and palette transparency, EXIF rotation=6 with unchanged input and correct output X/Y size/pixels, RGB detached copy, signed historical ink parity across several shapes, zero-border summed-area counts, and leaf-first import with no cycle. Existing source/speck/PDIC golden tests remain intact. Architecture guard bans dual implementations.
- Gate protected `image_utils.py` and `preprocess/` means six Python3.10/3.13 × Windows/macOS/Ubuntu CI jobs, GUI smoke/wheel, final risk-tier gate, CodeQL Python/Actions, fixed-head review-free squash, then postmerge main CI/CodeQL. Native GPU, actual dictionary scan parity and real GUI interaction still require manual validation. Keep Issue #562 OPEN.


### Issue #562 — training candidate-to-saved-PDIC matcher physical owner (2026-10-22; candidate)

- Accepted `main@738ea28cedbe88efbbc141a0595c5c0452e91339` with [main CI #39759042157](https://github.com/chigre/Picture_Capture/actions/runs/39759042157) 6/6 + final gate SUCCESS and [CodeQL #39759041851](https://github.com/chigre/Picture_Capture/actions/runs/39759041851) 2/2 SUCCESS; zero open PR at intake; root Python **39**.
- Narrow owner extraction: the original, **unchanged** `_candidate_ground_truth_link` function moves from historical `training_export.py` to canonical import-light `training/ground_truth_matching.py`; the old root module re-exports that **same object**. Its public training-export entrypoints, `TRAINING_EXPORT_FORMAT`, image exports, staging, context, ZIP atomic publish/cancellation, data dictionaries, source X/Y annotations, PDIC/PPP parsing and page layout policies remain intact. Root `training_export.py` is explicitly protected by prior package ownership compatibility tests, so the direct-root count is intentionally **39→39**.
- Core invariant: candidate/PDIC matching and distance threshold are calculated on a **temporary canonical reading axis** (including rotated/vertical layouts), but saved nearest-ground-truth coordinates and deltas are **original source X/Y**; only candidates within the **same column** can match, invalid records must fail closed. New regression pins rotated geometry differing from source Y proximity, rejected distant links, wrong column/malformed candidates, refined-source-y fallback, min four-pixel tolerance, legacy identical function-object export, leaf-first import with no GUI/old training exporter dependency. Architecture guard prevents dual implementations.
- Complete protected-path cross-platform Python3.10/3.13 × Win/macOS/Ubuntu CI, GUI smoke/wheel, final risk gate, CodeQL Python/Actions, exact-head/base/review verification before fixed-head squash, plus postmerge main checks. Real scanned-page visual parity, GPU and native GUI interactions remain manually unverified. Keep Issue #562 OPEN.


### Issue #562 — physical owner for training v2 context snapshots and manifest contract (2026-10-22; candidate)

- Accepted baseline `main@8cbfb9c1d35b4b0ced274dc959e23d574bb728ec`: postmerge [CI #39761364268](https://github.com/chigre/Picture_Capture/actions/runs/39761364268) six matrices and final Risk-tier gate SUCCESS; [CodeQL #39761364461](https://github.com/chigre/Picture_Capture/actions/runs/39761364461) Python/Actions 2/2 SUCCESS, zero open PR. Root Python **39**.
- Move the **unchanged** `copy_project_context` and `write_training_manifest` implementation bodies into `training/manifest_v2.py` as sole canonical physical owner. The v2 format string `picture-capture-training-v2` is owned there too. Root `training_export.py` re-exports the identical functions and format marker; current v3 `training/export_composed.py` continues to compose the *same* v2 function object. All legacy call paths, names, v2 format/schema and v3 composition remain stable.
- `training_export.export_training_page`, training zip publisher, its `TrainingExportCancelled` exception and in-process cancellation/rollback semantics are untouched. Copy source asset bytes verbatim, skip missing legacy files, preserve original ordering/path names; manifest includes saved-PDIC source X/Y training contract and unchanged dictionary metadata and page counts. No OCR/GPU/cropping/PDIC/PPP/SECTION/Profile semantics changed.
- Tests pin canonical/legacy function identity and import-light leaf-first bootstrapping, exact project-context byte copy, skipped missing file (no phantom _Replace.txt), stable file list order, v2 marker and coordinate-source metadata, aggregated counts, exported AppSettings dataclass fields, empty project and empty pages. Architecture guard forbids duplicated manifest implementations.
- Protected training export triggers full six Python3.10/3.13 × Windows/macOS/Ubuntu, GUI smoke/wheel, final risk-tier gate, CodeQL Python/Actions, then fixed-head review-free squash and main postmerge checks. Root count intentionally **39→39** because historical training_export is an explicit ABI/facade gate. Manual real dictionary scans/native GPU remain out of scope; Issue #562 remains OPEN.


### Issue #562 — training ZIP publication/cancellation canonical owner (2026-10-22; candidate)

- Accepted baseline main SHA 654fba329a43498782d1c97e1424062294e69e5c. The preceding main CI #39770896822 succeeded on six matrices + Risk-tier final gate and main CodeQL #39770897444 succeeded Python/Actions 2/2; zero open PR; root Python modules 39.
- Physically move unchanged TrainingExportCancelled class and make_training_zip callable from protected training_export.py to canonical import-light training/zip_publish.py. Root re-exports the identical class and callable; training/export_composed.py and ui/controllers/export.py retain existing import paths. Preserve historical __module__ on both objects so pickled class, exception instances and callable still resolve through picture_capture.training_export. These metadata assignments do not alter archive behavior.
- Preserve unique same-directory UUID temp ZIP, deterministic path order, exact file bytes, cooperative should_stop checks before/during/after file enumeration, and final replace only after successful close. Cancellation and writer exceptions delete temp without clobbering prior published archive. No changes to manifest v2/v3, training labels, source X/Y, PDIC/PPP/Profile/SECTION, OCR, GPU or GUI.
- Regressions: owner/root/v3 identical object identity, pickle stability, Unicode archive name and byte preservation, partial-write cancellation preserving existing target, synthetic write failure rollback with no orphan staging ZIP, leaf-first imports without loading GUI. Architecture guard enforces single owner and legacy compatibility.
- Root training_export.py shrinks while file count remains 39 due required public facade. Gate with six Python 3.10/3.13 × Windows/macOS/Ubuntu, GUI/wheel, Risk-tier final gate and CodeQL; confirm stable head and no reviews, then squash and independently check postmerge main. Native hardware and real scanned pages require manual acceptance. Issue #562 remains OPEN.


### Issue #562 — remove two retired root no-op installers (2026-10-22; candidate)

- Accepted baseline `main@f7c74fff475435c8b98556d89174b3fa893a63df`: [main CI #39773106136](https://github.com/chigre/Picture_Capture/actions/runs/39773106136) six-platform 6/6 + final gate SUCCESS, [main CodeQL #39773105695](https://github.com/chigre/Picture_Capture/actions/runs/39773105695) Python/Actions 2/2 SUCCESS; zero open PR, untruncated 915-entry tree; root Python files **39**.
- Physically relocate two *unused, no-op* internal diagnostic compatibility installers, byte-for-byte unchanged: `layout_detector_live_binding.py` → `layout/detector_live_binding.py` and `settings_help_restore.py` → `ui/settings/legacy_help_restore.py`. **No root shims**; expected root files **39→37**, verify full tree before acceptance. Live detector policy remains statically forwarded from `design/layout_policy.py`; Settings help wording/binding remains owned by `ui/settings/schema.py`. No active production import is found for either legacy installer, nor do GUI/worker/bootstrap call them.
- **Compatibility disclosure:** Unlike previous root-facade-preserving batches, the two former dotted imports (`picture_capture.layout_detector_live_binding` and `picture_capture.settings_help_restore`) intentionally cease to resolve. External diagnostic plugins using them must switch to `picture_capture.layout.detector_live_binding` and `picture_capture.ui.settings.legacy_help_restore`. This is a conscious retirement of two unused no-op compatibility paths, not a promise of identical public ABI. Documented application/CLI, scanned-page source X/Y, OCR, PDIC/PPP/SECTION/Profile, GPU, spawned jobs, and training ZIP paths are untouched.
- Changed two old "must remain at root" ownership assertions to require **canonical package owners** and no former-root module; retain actual detector monkeypatch forwarding test and unchanged installer no-op/nonmutation assertions. New subprocess leaf-first no-GUI/no alias check, runtime static detection forwarding assertion, original unchanged Python body comparison, guard forbidding resurrected old files. Do not weaken pixel/worker/transaction gates.
- Complete Python 3.10/3.13 × Windows/macOS/Ubuntu CI, GUI smoke/wheel, final Risk-tier gate, Python/Actions CodeQL and fixed-head review check required before squash; independently repeat on merged `main`. Real scanned pages/native GPU/manual GUI still unverified. Issue #562 remains OPEN.


### Issue #562 — legacy training range and UI terminology helpers physically relocated (2026-10-22; candidate)

- Accepted `main@51bb8a98ed3749596e094f24b346dbd40130a476`, [main CI #39775954421](https://github.com/chigre/Picture_Capture/actions/runs/39775954421) six OS/Python jobs plus final Risk-tier gate SUCCESS, [main CodeQL #39775955450](https://github.com/chigre/Picture_Capture/actions/runs/39775955450) Python/Actions 2/2 SUCCESS, 0 open PR; complete untruncated main tree **916 entries**, root Python **37**.
- Move byte-for-byte unchanged **real helper implementations** `training_export_ui.py` → `training/legacy_scope_ui.py` (historic page-range parser and delegated no-op UI action) and `ui_terminology.py` → `ui/terminology_compat.py` (historic UI text normalizer and no-op installers). Delete both root files, no shims. Target **37→35** root Python files, to be independently verified on branch and merged main trees. The live ExportController instead derives selection from main window `selected_page_indices()`; Settings/UI wording is owned by source-native controls. These helpers are not invoked by active product paths.
- Compatibility trade-off: these two retired **old direct module import paths** are intentionally removed. Third-party diagnostic tools importing `picture_capture.training_export_ui` or `picture_capture.ui_terminology` must use the new `picture_capture.training.legacy_scope_ui` and `picture_capture.ui.terminology_compat` imports. No false claim of old import ABI preservation. All documented app/CLI launchers, training export button, OCR selection, source-image pixels and coordinates, PDIC/PPP/SECTION/Profile, GUI/GPU, Windows spawn workers and ZIP publisher remain unchanged.
- Keep coverage, not relax it: migrate former-root source-inspection tests to physical owners and add explicit old-root-absence + canonical-owner assertions; keep Unicode/numeric/reversed page-range parsing checks, non-string and idempotent text-normalization checks, Tk constructor no-mutation checks, leaf-first subprocess with no app import. Architecture guard now scans the canonical UI terminology source against forbidden global Tk/ttk mutation markers and rejects both retired root files if recreated.
- Six Python 3.10/3.13 × Windows/macOS/Ubuntu suites, GUI smoke, wheel, Risk-tier final gate and Python/Actions CodeQL must be green on PR and independently on squash-merged main; verify fixed head/base and review threads. No actual scanned-page/native GPU/manual GUI evidence; #562 remains OPEN.


### Issue #562 — physical ownership for the shared facade assignment mirror (2026-10-22; proposed PR)

- Baseline `main@37e7a6ce8ca651d232f64d2d03f917f54a644022`, zero open PR, initial direct-root Python files **35**; previous #618 postmerge cross-platform CI 6/6 and CodeQL 2/2 SUCCESS. This candidate aims for **35→34** by physically moving `facade_compat.py` to `compat/facade_mirror.py` with the identical Git blob and **no root shim**.
- Only the import paths in the historical public `processing.py` and `paddle_headwords.py` facades change. Both retain their original module path, exported symbol identity, core namespace publication and monkeypatch assignment-mirroring behavior. The stateful `_CORE_BY_MODULE` registry remains in a single owner, rather than copied. No OCR, GPU, Windows spawn, source pixels/X/Y, PDIC/PPP/SECTION, Project/Profile, or detection policy is changed.
- The retired internal diagnostic import `picture_capture.facade_compat` is **not compatible**; external diagnostic tooling must import from `picture_capture.compat.facade_mirror`. The two public facade module APIs remain at their old paths; this migration must not be described as preservation of the retired helper's dotted import.
- Update ownership tests to the physical source, prove old-root absence and leaf-first non-GUI import, and tighten `architecture_guard` to reject reinstatement of the old root path or a missing/duplicated mirror owner. Preserve existing monkeypatch/reinstall registry tests and the guard's prohibition on new facade-compatibility users. Do not weaken any tests or relax a risk tier.
- Do not merge until the exact PR head passes all six Windows/macOS/Ubuntu Python 3.10/3.13 test matrices, GUI smoke, wheel, final Risk-tier gate and Python/Actions CodeQL, and until reviews/threads and base SHA are checked; independently verify the merged main checks. Real scans, native GPU, and manual GUI are still not verified; Issue #562 stays OPEN.


### Issue #562 — physically own manual PDIC backup restoration in Proofreading (2026-10-22; proposed PR)

- Accepted base `main@92bd592a720e6fac30145ae25375cff24285f96f`, root Python **34** and zero open PR; prior #619 main push CI **6/6** and CodeQL **2/2** SUCCESS. Move `pdic_restore.py` to `proofreading/pdic_restore.py` with only three parent-relative import changes (`formats`, `models`, `project_storage`), and physically remove old root file without shim. Expected **34→33**; no parsing, coordinate, publication or algorithm changes.
- Redirect the exact active consumers in `app.py`, `ui/controllers/export.py`, and `proofreading/page_word_mapping.py`; their public app wrappers and controller monkeypatch points stay unchanged. Preserve old PDIC backup token precedence, zero-padded numeric/suffix ambiguity fail closed, source X/Y, page-local records, empty-page/invalid-file safety, and existing fixed temp + `os.replace` + artifact-edit notification. This PR does **not** claim to remedy potential same-page concurrent tmp races; that requires a separate behavioral change, with dedicated fault/interleaving verification.
- Update existing physical-owner test to assert canonical import and old-root absence, keep all existing UI/worker parsing and atomic tests, add leaf-first no Tk/no app import regression and injected publish failure preserving prior PDIC bytes with temp cleanup. New architecture guard rejects root resurrection or removal of canonical writer; `scripts/ci_risk_tier.py` already includes the old critical path and the `proofreading/` full-risk prefix and is **not weakened**.
- **Explicit external diagnostic ABI change**: `picture_capture.pdic_restore` is retired. Third-party tools directly importing the old helper must use `picture_capture.proofreading.pdic_restore`. The documented GUI/menu action to restore a PDIC backup remains. Do not claim the old helper dotted-import remains available.
- Require fixed PR head and unchanged base, all six Python3.10/3.13 × Windows/macOS/Ubuntu jobs, GUI smoke, wheel, architecture guard, final Risk-tier gate, CodeQL Python/Actions and no unresolved review; independently verify postmerge main CI. Real scan files, native GPU and manual interactive UI remain unverified; #562 remains OPEN.


### Issue #562 — move active Layout visualization v3 controls into UI package (2026-10-22; candidate PR)

- Accepted baseline `main@b12e5e82282cfc5b8d820cfa66a3d5767132b38c` with independently successful [main CI #39786683824](https://github.com/chigre/Picture_Capture/actions/runs/39786683824) six OS/Python jobs and final Risk-tier gate, and [main CodeQL #39786689703](https://github.com/chigre/Picture_Capture/actions/runs/39786689703) Python/Actions 2/2. No open PR at intake and **33** direct-root Python modules.
- Physically move the active **v3** Layout diagnostics UI source `layout_visualization_ui_v3.py` to `ui/layout_visualization_ui_v3.py` with only relative imports corrected; do **not** touch the separate historical `ui/layout_visualization_ui.py` or `ui/layout_visualization_ui_v2.py`. No shim at root; target **33→32**. Update only the active imports in `app`, compact UI, quick state, workspace controls, Layout detail window, ordinary Layout inspector and large-head visualization. Preserve `draw_layout_visualization_if_enabled`, exclusive hide/restore semantics, user-session-only display settings, replay action, shared denoise control, overlay order and no Tk class monkeypatch.
- Move old source-reading tests to physical canonical owner while **retaining all behavior checks**, including detailed/compact drawing monkeypatch, replay, details, large-head, inspector visibility and GUI construction. Add root-absent / leaf-import-no-Tk-root assertions. Tighten architecture guard to scan forbidden global Tk mutations at new UI owner and ban resurrected old root; direct-root module ratchet **≤32**. UI paths force six-platform full risk CI, not a reduced fast lane.
- **Intentional diagnostic-plugin import break:** retired `picture_capture.layout_visualization_ui_v3` no longer resolves; external integrations must use `picture_capture.ui.layout_visualization_ui_v3`. GUI product controls stay enabled at their original locations and no documented user-facing command changes.
- Accept only after fixed-head six Python 3.10/3.13 × Windows/macOS/Ubuntu suites, GUI smoke, wheel, final Risk-tier gate, Python/Actions CodeQL, no unresolved review, then independent merged-main CI/CodeQL and physical root-count recheck. Native GPU, real scanned-page visual parity and manual GUI acceptance remain unverified. Issue #562 stays OPEN.


### Issue #562 — three coordinated Layout implementation migrations (2026-10-22)

- Accepted `main@5364928122041d902b08dee7747799a21f62c926` with independent [main CI #39789216100](https://github.com/chigre/Picture_Capture/actions/runs/39789216100) six-platform 6/6 success and [main CodeQL #39789350141](https://github.com/chigre/Picture_Capture/actions/runs/39789350141) Python/Actions 2/2; zero open PR, direct-root Python 32.
- **One grouped package migration** moves `layout_core_understanding.py` → `layout/core_understanding.py`, `layout_physical_indent.py` → `layout/physical_indent.py`, and `layout_detection_legacy.py` → `layout/detector_legacy.py`, no old root shims, direct-root count **32→29**. These are actual original algorithm implementations: preserve executable functions/bodies, alter only necessary relative imports and redirect all known callers/tests. Maintain root `layout_detection.py` facade, `layout_rows_cache.py` (persistent cache), and stable GUI/processing consumers. Do not replace real algorithms with compatibility no-ops.
- Explicitly retire diagnostic import paths `picture_capture.layout_core_understanding`, `picture_capture.layout_physical_indent`, `picture_capture.layout_detection_legacy`. Users with private deep imports must switch to `picture_capture.layout.core_understanding`, `picture_capture.layout.physical_indent`, `picture_capture.layout.detector_legacy`; old deep-import pickle-qualified dataclass names in historical cache objects are **not** declared backward compatible. No saved external pickle migration is claimed; test it separately if needed.
- Keep unchanged ordinary/HD detector public facade and its lazy Windows GPU DLL setup, strict Layout/PDIC coordinate semantics, evidence/caching and pure CPU test assertions. Keep CodeQL, import/physical-owner regression tests, core/indent/legacy detector behavior tests and architecture guard, tighten the direct-root ratchet to **≤29**. Both previous critical-root and new `layout/` paths remain in the conservative full six-platform risk tier.
- Required verification is one fixed-HEAD PR with Win/macOS/Ubuntu×Python3.10/3.13 6/6, GUI smoke, compatibility runner, wheel, final Risk-tier gate and CodeQL 2/2; independent postmerge main CI/CodeQL required, and no competing PR during acceptance. Real scan image pixel parity, native GPU CUDA behavior, and manual GUI workflows still not verified. Issue #562 remains OPEN.


### Issue #562 — grouped refinement ownership batch (2026-10-22)

- On accepted `main@64f23cd64ee12fcd4af3591f1ace8ef980e4413d` (root Python **29**), push two related real implementations together to the `refinement/` package: `marker_refinement_parallel.py` → `refinement/parallel.py`; `separator_y_refinement.py` → `refinement/separator_y.py`. No root shim; target **29→27** in one PR. Unlike the last group, proceed without waiting for the independent main postmerge GitHub Actions runs at the user's explicit direction; PR's own cross-platform and CodeQL checks still gate any merge.
- Retain all worker/coordinator algorithm functions, existing-PDIC safety guards, atomic parent-only commit, and separator Y subpixel/margin estimation; only adapt necessary relative imports and the real source importers (`paddle_headwords`, `processing`, `ocr/evidence_fusion`). Preserve `paddle_headwords.py` façade and downstream `refine_separator_y` callback identity; no change to `paddle_headwords_core` native implementation. Regression tests cover old root absent, new owner, spawn pickle by module reference, original-PDIC preservation on commit errors, shared refined Y source, OCR cache fingerprint source and dynamic runtime setting audit.
- Runtime compatibility note: old private `picture_capture.marker_refinement_parallel` and `picture_capture.separator_y_refinement` imports are intentionally removed. New module names `picture_capture.refinement.parallel` and `picture_capture.refinement.separator_y`; existing GUI and `paddle_headwords` public function remain. Python pickle qualified function paths written in previous versions (if any) are not promised compatible without explicit migration; legacy external plugins using private paths must update.
- Explicit domain ownership architecture guard and direct-root ratchet **≤27**, keep old-root and new `refinement/` full-risk entries so move cannot bypass Windows/macOS/Ubuntu × Python 3.10/3.13 complete CI; full PR checks and CodeQL 2/2 required, plus independently check merged main when available. Native NVIDIA CUDA GPU, real scanned page image parity and manual GUI cannot be claimed proven from these tests.


### Issue #562 — one grouped crop line-export coordinator migration (2026-10-22)

- After merging [PR #623](https://github.com/chigre/Picture_Capture/pull/623) into `main@daf3f0f2684d028a1f7b0a520fba9ca49bccbaa2`, the direct-root Python count is **27**. This separate, grouped branch physically moves the two matching page-level crop/export coordination owners from root into **one shared `crop/` package**: `single_line_parallel.py` → `crop/single_line_parallel.py` and `unlined_line_export.py` → `crop/unlined_line_export.py`. No root compatibility shims; target root Python **27→25**.
- Preserve page-worker and parent orchestration semantics, Windows `spawn` multiprocessing, no worker shared-log writes, PDIC foreground-edit ownership, line/crop padding, near-blank filtering, unlined row image and original source coordinate contracts. Only necessary relative imports, live controller imports, tests/guards, and a canonical source-owner module path change. `crop/single_line_merge_settings.py` and `crop/unlined_export_filter_settings.py` remain existing stable owners.
- Regression checks include source and module ownership, process-worker pickle path/roundtrip, all controller tests and layout-row caching, architecture root-count ratchet **≤25**, and full risk tier on both old and canonical paths. This is an internal import path break: plugins must use `picture_capture.crop.single_line_parallel` / `picture_capture.crop.unlined_line_export`; old external pickle module references may require migration.
- User explicitly requested beginning next batch without waiting on prior **postmerge main** CI/CodeQL; current PR's own Win/macOS/Ubuntu×Python3.10/3.13 six-matrix CI, GUI smoke, wheel, and CodeQL Python/Actions must still pass before merge. Native platform CUDA, real image pixel equivalence, and manual GUI workflows are not established by these tests. Issue #562 remains OPEN.


### Issue #562 — grouped formats / PicDic / GUI I/O migration (2026-10-23)

- On verified `main@7fb3ff651413e89526655a092ad50ccf4c716b6a` with 25 root Python files, group three tightly related persistence implementations in `io/`: `formats.py`→`io/formats.py`, `picdic.py`→`io/picdic.py`, `gui_io.py`→`io/gui_io.py`. A single PR covers all three physical moves, all known production/testing callers, and root count **25→22**, with no root shims.
- Preserve the existing atomic PDIC/PPP writers, fail-safe transactional PicDic package publication, `formats` module object dynamically patched by classification bootstrap, and the GUI `gui_io` write-capture callable identity. Only change imports and necessary source-reading assertions. Archive names, output formats and treatment of missing directories are unchanged. The former private root module imports must be updated to `picture_capture.io.formats`, `.picdic`, and `.gui_io`.
- The `image_preprocessing` and `image_utils` root pair is intentionally not moved in this batch: historical `__module__` identity and pickle compatibility of image preprocessing classes and helper functions, enforced by explicit tests, require separate ABI planning. Deep-import compatibility is not declared for relocated private I/O modules; real end-to-end scan pixel parity, native GPU and manual GUI not yet established.
- CI risk tier remains full, architecture guard requires three owners, forbids old root files and ratchets direct-root Python count **≤22**. One fixed PR HEAD must pass Win/macOS/Ubuntu×Python 3.10/3.13 CI, GUI smoke, wheel, compatibility runner, final risk gate and CodeQL 2/2 before merge. User explicitly prefers starting the next PR without awaiting prior postmerge main workflow completion; #562 stays OPEN.


### Issue #562 — paired Layout detector and row-cache ownership (2026-10-23)

- From accepted main 1586227e10202ff02d13f9542446c0f56e4cf71d (22 root Python files), this one grouped PR physically relocates layout_detection.py → layout/detection.py and layout_rows_cache.py → layout/rows_cache.py; the old root modules disappear, target direct-root count **20**. Importers, test path contracts, risk classification and architecture guard are updated together. Retain the live detector module-object monkeypatch injection seam, cache serialization/atomic persistence and coordinate/reliability semantics. No no-op root compatibility modules.
- Explicitly did not migrate public OCR channel: the source documents saved-pickle identities for its dataclasses. Moving it without a root compatibility layer (forbidden by this issue) would break those saved objects. An OCR exploratory tree existed only in an unused branch, with no PR; no OCR source or tests in this Layout change.
- The former deep imports picture_capture.layout_detection and picture_capture.layout_rows_cache become picture_capture.layout.detection and picture_capture.layout.rows_cache. Keep full six-platform PR CI and CodeQL, preserve real scanned-image / native CUDA / hands-on GUI acceptance as separate nonclaims. Issue #562 remains OPEN.


## Issue #562 — grouped cross-platform runtime and Windows GPU owners (2026-10-23)

Candidate based on merged `main@97dc554a5d52a71f953b2441bf5dd057fbb745cf` (20 direct-root Python files). Move the **two** platform/runtime implementations together: `runtime_environment.py` → `runtime/environment.py` and `windows_gpu.py` → `runtime/windows_gpu.py`. Source functions are identical; update all known internal imports and source-verification contracts, do not add old root shims. Proposed root count **20→18**. This is conditional on CI, CodeQL and full platform tests, not a claim of merge or real native GPU validation.

Safety boundaries: historical runtime.json fields, OS-specific user configuration/data directories, foreign legacy file-path fallback, Tesseract precedence, Paddle device cache policy, and the Windows NVIDIA DLL preparation call **before** PaddleOCR/TextDetection/DocPreprocessor import are unchanged. The relocated Windows helper still stores DLL directory handles for process lifetime; the prior audit's native-Windows repeated-handle uncertainty remains. Update `tests/test_ocr_channel_runner_semantics.py` rather than weakening its ordered-import assertions. Strict physical ownership guard and risk-tier full platform selection must include the new `runtime/` directory. External code importing undocumented former deep-module paths must update to `picture_capture.runtime.environment` or `picture_capture.runtime.windows_gpu`.


## Issue #562 — Project storage and SECTION sidecar grouped persistence migration (2026-10-23; pending CI)

After accepted `main@674133f1a0bf775acf7ea108692c2898966414cb`, the direct root contains **18** Python files. This candidate groups two physical storage owners into `persistence/` without leaving old root shims: `project_storage.py` → `persistence/project_storage.py` (managed-v2/legacy routing and manifest atomicity) and `page_sections.py` → `persistence/page_sections.py` (source-coordinate SECTION v2, migrated QT semantics, unique-temp atomic writes). The original implementation bodies and persisted bytes/schema are not deliberately altered; relative import resolution and dozens of real production/test callers are migrated together. Root target **18→16**, subject to full CI and merged tree verification.

No waiver of versioned project manifests, Profile/PDIC/PPP/SECTION, user image ownership, original-image X/Y, Section=0 migrated legacy precedence, crash-failure injection, concurrency locking or transactional read/write coverage. Both old and new paths remain full risk tier; this change requires six-platform Python 3.10/3.13, GUI smoke/wheel, CodeQL, reviews and postmerge push checks. Deep external imports of the two old private dotted paths and historical external Python pickles using their class module identities are **not established compatible**; no fake root-level shims are introduced. Real scanned pages, native CUDA and interactive human GUI acceptance remain separate.


## Issue #562 — final root classification and verified OCR resume owner (2026-10-23; pending acceptance)

Classify all 15 retained roots in [the current inventory](ROOT_MODULE_CLASSIFICATION_20261023.md). Physical migration `ocr_page_resume.py` → `ocr/page_resume.py` (16→15, after #628) changes its whole-package fingerprint anchor to `parents[1]`, preserving fail-closed invalidation for Layout/refinement/models and future modules. GUI imports and all checkpoint tests follow the canonical owner; no root shim. Existing saved checkpoint keys conservatively invalidate after package source/path changes. Regression checks compare the exact package-wide path/byte/version digest, deletion invalidation and the complete root table. Architecture ratchet only tightens, full six-platform tier and CodeQL remain required.

Preparation also repaired three missed test references from #628 (two static imports and one string monkeypatch), extending its AST guard across source/tests/scripts and dynamic targets. The retained root files are actual entry/API/identity/state contracts, not unclassified leftovers. Large app/core/preprocessing implementations still need staged extraction; this inventory does not close #562 or establish manual scan/native GPU parity.


## Issue #562 — preprocessing deskew and content-frame implementation extraction (2026-10-23; pending acceptance)

Base `main@6871cea577526f896c0e70ef6c46a40d43246830` has 15 explicitly retained root contracts and passed both PR and postmerge six-platform CI/CodeQL. This batch keeps those 15 roots and makes the retained preprocessing API thinner: `image_preprocessing.py` **150797→137295 bytes** (−13502), with 11 skew/rotation/source-canvas helpers physically owned by `preprocess/deskew.py` and four projection/content-frame helpers owned by `preprocess/content_bounds.py`. No preprocessing pipeline, threshold, interpolation mode, coordinate rounding, crop format, model construction or saved analysis is redesigned.

The root statically re-exports pure helpers with historical callable pickle module names, following the existing `preprocess/canvas.py` convention. Three root functions remain one-return adapters: they explicitly supply the current `analysis_ink_mask` or `infer_layout_from_boxes` callable, so root-level detector substitution is resolved at call time. The leaf modules never import the root facade or GUI shell, and add no runtime installer, proxy, namespace copy or mutable hook. Existing model/canvas pickle identities remain unchanged.

Verification prepared: 46 existing preprocessing/ownership/pixel tests and 22 new ownership/pickle/leaf-first/alpha/palette/source-coordinate/detector-injection/CRLF cases pass; local comparison against the frozen base preserves extracted primitive AST bodies and passes 51 deterministic original-versus-new pixel/geometry cases, including large-image downsampling, nonzero deskew and vertical mode. Full regression, compatibility runner, wheel, architecture/change guards, F821 and exact-head six-platform CI/CodeQL remain the acceptance gates. A new guard prohibits primitive implementations returning to the root and tightens the preprocessing facade ceiling to 137300 bytes without relaxing the old oversized-module baseline. Root count remains 15; the remaining large preprocessing analysis pipeline, app and processing/OCR cores are still open work. Native CUDA and real scanned-page/manual GUI parity remain unverified.

Cross-platform gate correction: the first Windows Python3.10 architecture run exposed a disk-size/CRLF mismatch in the newly added facade ceiling. Reuse existing `_normalized_source_size()` for that check, keeping the ceiling137300 unchanged. Added a synthetic Windows checkout regression that proves both LF/CRLF equivalence and rejection of actual source growth. No production algorithm or facade byte changed by this fix.


## Issue #562 — orthogonal acceptance policy and saved-geometry replay extraction (2026-10-23; accepted #631)

On accepted `main@03976b1c754984796e0e76ea1ef660d5e72187f2` (#630; exact-head and postmerge six-platform CI/CodeQL passed), move six related policy/step-payload functions into `preprocess/orthogonal_policy.py` and saved geometry rendering into `preprocess/replay.py`. The retained API shrinks **137295→128042 bytes** (−9253), root count remains 15. Five pure helpers retain historical callable/pickle module names. The candidate selector and `geometry_corrected_image` stay as thin root adapters supplying current auditors, polygon/image transforms, quality evaluator and step decoder explicitly. Public signatures and the geometry renderer's docstring remain; no new proxy, installer, namespace copy or GUI-to-domain dependency.

Keep original score weights, mildest-gain ordering, fractional safe cap, worst-column/count/scale guards, payload field names/defaults, saved-step precedence, pre-v22 legacy-field fallback and deskew→homography→UVDoc→ordered-orthogonal replay sequence. No model, output schema or coordinate conventions are changed. Static root exports and injected operations preserve the tested root replacement seams; leaf-first imports initialize neither root GUI nor Paddle.

New tests cover ownership/pickle, leaf-first import, quality/count/cap boundaries, rejected/absent candidates, payload round trips, save/reopen/replay order and legacy/disabled branches. Frozen-base comparison normalizes only explicit dependency parameters/names: all seven original function bodies are unchanged, and 182 deterministic numerical/payload/pixel comparisons pass (including curve/grid replay; native UVDoc is stubbed). Retain synthetic-vs-native validation limits: real scanned-page/manual GUI/native CUDA acceptance is not established.

Guard requires the two canonical owners and rejects duplicated pure bodies. Tighten the preprocessing facade ceiling 137300→128050, now named `MAX_PREPROCESS_FACADE_BYTES`, continuing to use normalized LF source size. Existing CRLF/actual-growth regression follows this named policy limit; its rejection requirement is preserved. No old oversized baseline is relaxed. Full exact-head six-platform CI, GUI smoke, wheel, CodeQL, reviews and independent postmerge main checks are required before acceptance. Large analysis/app/core work remains open.


## Issue #562 — reviewed image rendering and file encoding (2026-10-23; accepted #632)

On accepted `main@5abbb8a2` (#631; exact-head and postmerge six-platform CI/CodeQL passed),
move six preview/crop/canvas/encoding bodies to `preprocess/rendering.py`. Retain six
thin historical API functions with identical signatures and callable/pickle paths.
The facade supplies normalization, saved geometry rendering, overlays, crop rendering,
canvas factory and save renderers at call time. The leaf imports only models/Pillow,
never the root facade or GUI. Root count remains 15; facade shrinks **128042→125548 bytes**.

Preserve clamp/overlay RGBA behavior, original crop coordinates, source immutability,
canvas expansion without scan resampling, preview minimum long side 320 and no upscaling,
JPEG preview quality88/optimization, full JPEG quality95/no subsampling, TIFF LZW,
and destination parent creation. Existing source and result paths/formats remain unchanged.
Frozen #631 comparison verifies all six public signatures and normalized AST bodies,
plus deterministic pixel and byte-for-byte encoded output parity. New tests cover
leaf-first imports, callable ownership, live replacements, palette/alpha/grayscale,
canvas overflow, JPEG/TIFF/PNG reopen and preview bounds. Full local regressions,
compatibility runner, wheel, guards, F821 and exact-head six-platform CI/CodeQL plus
independent main acceptance are required. Tighten normalized facade ceiling to125550;
new ownership guard requires six thin adapters and their canonical bodies. No historical
baseline is loosened. Native CUDA/real scanned-page/manual GUI acceptance and the large
analysis/app/core decomposition remain open work.


## Issue #562 — source geometry evidence stage (2026-10-23; accepted #633)

On accepted `main@80ef82a9` (#632; exact-head and independent main six-platform
CI/CodeQL green), begin decomposing `analyze_preprocess_page` itself. The new
`preprocess/source_evidence.py` owns source detection, too-few-box/failure fallback,
line-geometry warnings, OCR/projection angle estimation, horizontal physical header
anchoring, dead zone and automatic rotation limit. `SourceGeometryEvidence` hands
13 explicitly named values to the subsequent transform stages. Its lists are per-page
working state; the result container is frozen and is never written to a project.
Root Python count remains15; facade shrinks **125548→121552 bytes**.

Composition supplies six current operations/factories and five current scalar policies
at call time, preserving the existing root replacement seams without installing global
hooks. Source normalization, mode normalization, manual handles, later geometry/cropping
and the existing `PreprocessAnalysis` constructor stay in their current positions.
Warnings, ordering, inclusive header quality bounds, vertical-page skip, sample count,
projection fallback, disabled deskew and retained coordinate/schema/pickle contracts
are unchanged. Leaf-first import must load neither root facade/GUI nor Paddle.

37 new tests cover failure branches, exact policy thresholds, width-scaled residuals,
mode-specific warnings, ordered input-identity callbacks, per-page state and public
analysis→save/reopen/pickle. Frozen #632 comparison checks the extracted algorithm AST,
360 source-evidence results and48 complete analysis payload/cropped-pixel cases (UVDoc
stubbed). Full local regression and compatibility runner, normalized LF/CRLF guard,
F821/compile/wheel, exact-head six-platform CI/GUI smoke/CodeQL/reviews and independent
main acceptance remain required. Tighten normalized facade ceiling125550→121560;
require the source owner/composition and reject direct source skew collection returning
to the analysis root. No historical baseline is loosened. Real scanned-page/manual
GUI/native CUDA and large later-stage analysis/app/core acceptance remain open.


## Issue #562 — final page audit, retained bounds and confidence (2026-10-23; accepted #634)

On accepted `main@6356509a` (#633; exact-head and independent main six-platform
CI/CodeQL green), extract the final measurement stage of `analyze_preprocess_page`
into `preprocess/finalization.py`. This owner re-detects advanced transformed pages
when needed, keeps transformed original boxes on detector failures, summarizes final
horizontal alignment, chooses structural/projection crop bounds, adds review warnings
and computes evidence count/confidence/status. A frozen 22-field per-page result feeds
the existing `PreprocessAnalysis` constructor, whose fields/conversions remain unchanged.
Root count remains15; facade shrinks **121552→115065 bytes** (−6487).

Seven current operations are explicitly supplied at call time: text detector,
horizontal auditor, absolute quality evaluator, structural/projection bounds,
box expansion and text bounds. Original source dimensions are passed separately
from the corrected working image. Existing warnings/method lists remain shared only
within the current page so ordering and model serialization stay identical. No GUI or
public-facade import, global hook/installer, namespace copy or persisted-model clone.

37 new cases cover re-detection gates and polygon identity, detector/structure/audit
failures, UVDoc-only insufficient/unavailable warnings, legacy optional tail defaults,
all final alignment metrics, warning ordering, projection failure propagation, margins,
confidence/area thresholds, source pixel immutability and public save/reopen/pickle.
116 focused existing/new cases pass. Frozen #633 comparison verifies unchanged
extracted algorithm and complete model-constructor AST after result/dependency-name
normalization,1728 final-result/warning/method cases and96 complete public analysis
payload/crop-pixel cases (UVDoc stubbed). Local3290 passed/3 skipped; compatibility93;
F821/compile/wheel and architecture/change guards required. Exact-head six-platform
CI/GUI smoke/CodeQL/review plus independent main checks gate acceptance.

Tighten normalized facade ceiling121560→115070; require the finalization owner and
composition, prohibit final crop calls returning to the analysis root. Historical
baselines remain untouched. Remaining central perspective/orthogonal algorithm stages,
oversized app/processing/OCR cores and real scanned-page/manual GUI/native CUDA
acceptance are still open work.


## Issue #562 — projective candidate generation and selection (2026-10-23; accepted #635)

On accepted `main@5477b184` (#634; exact-head and independent main six-platform
CI/CodeQL green), move structural/residual-horizontal projective candidate generation,
shared Jacobian/text-scale/row audits, automatic safety gates, explicit override
selection and rejected diagnostic ranking into `preprocess/projective_selection.py`.
The frozen 17-field result retains original candidate/audit dictionary identities;
source image pixels are never transformed by this owner. Eight current operations
and seven current policy values are passed explicitly at call time. Root count
remains15; facade shrinks **115065→105233 bytes** (−9832).

Preserve source-width threshold max(5px,width×0.002), structural-keystone and line
support gates, Jacobian inclusivity, stable/insufficient text scale, base→partial
VP optimization, composed candidate row-audit replacement, row-count/trend/spread
thresholds, auto-vs-explicit priority, diagnostic cost weights and stable tie order.
Carry the horizontal total candidate itself back to existing identity-based safety
checks. Manual/UVDoc processing, diagnostics-to-model conversions, transform execution,
warning order and public signatures/formats/settings/coordinates remain unchanged.
No facade/GUI import, global hooks/installers, namespace copies or model clone.

52 new tests cover inclusive thresholds, low/curved/missing evidence, unknown VP
spread, column/region drivers, explicit override and 0.75px base threshold, failure
reset, structural fallback, diagnostic ranking/ties, operation ordering/identity,
input immutability and public live-operation/policy save/reopen. Existing42 focused
preprocessing/diagnostic cases pass; local full3342 passed/3 skipped; compatibility93.
Frozen #634: normalized candidate algorithm AST, public signature and persisted-model
constructor unchanged;1080 selection comparisons and96 complete public analysis
payload/crop-pixel comparisons passed (UVDoc stubbed). F821/compile/wheel, architecture/
change guards and exact-head six-platform CI/GUI smoke/CodeQL/review plus independent
main checks gate acceptance.

Tighten normalized facade ceiling115070→105240; require canonical selection owner
and composition, reject returning the nested distortion/selection implementation to
root. Historical baselines stay unchanged. Remaining manual/UVDoc/orthogonal stages,
diagnostic mapping, oversized app/processing/OCR cores and real scanned-page/manual
GUI/native CUDA acceptance remain open work.


## Issue #562 — candidate pixel acceptance and retained-image re-audit (2026-10-23; merged #636; independent main acceptance pending)

On accepted `main@88156923` (#635; exact-head and independent main six-platform
CI/CodeQL green), move candidate body/tail pixel acceptance and final retained-pixel
re-audit into `preprocess/pixel_row_policy.py`. CandidatePixelAssessment carries seven
acceptance values. RetainedPixelDiagnostics carries13 final measurements/verdicts,
initialized explicitly from the current per-page diagnostics. Both are internal working
results, never persisted. Current pixel auditor and six policy values are supplied at
call time; no owner import back to facade/GUI or new global hook/installer/namespace copy.
Root count remains15; facade shrinks **105233→98305 bytes** (−6928), now below the normal
100000-byte threshold. Keep historical oversized baselines as historical records.

Preserve candidate row sample≥8 plus valid-column≥1, final re-audit's original sample-only
row gate, absolute and relative row limits, tail sample≥2/column≥1, baseline epsilon,
exact floating-point comparisons, tail-progress ratio/regression budget and verdict
priority. Tail retention and convergence remain separate: a body-improving candidate
may remain retained while a non-regressing tail still needs another pass. Final re-audit
uses accepted working pixels and first valid initial evidence, keeping old before-values
when unavailable. Skipped/insufficient/failing audits preserve prior measurements, and
an exception after some assignments preserves those partial updates and warning order.
Image transforms, loop stop/rollback order, public signatures and model conversions,
formats/settings/pickle/source coordinates stay unchanged.

43 new tests cover candidate/retained gates and their intentional difference, exact
boundaries, progress vs retainability, combined verdicts, insufficient/absent/exceptional
measurement, partial updates, input identity/immutability and public live-auditor/policy
save/reopen/pickle. Existing42 focused cases pass; full3385 passed/3 skipped; compatibility93.
Frozen #635: both policy AST bodies, public signature and normalized model constructor
unchanged;768 candidate cases,480 retained partial-result/warning cases and3 complete
accepted/rejected multi-pass payload/crop-pixel fixture comparisons pass (native image
operations stubbed by existing fixtures). F821/compile/wheel and architecture/change
guards pass; exact-head six-platform CI/GUI smoke/CodeQL/review and independent main
checks gate acceptance.

Tighten normalized facade ceiling105240→98310 and require canonical routines/composition;
prohibit retained pixel implementation returning to analysis root. Historical baselines
remain unchanged. Remaining manual/UVDoc/orthogonal orchestration and diagnostics,
oversized app/processing/OCR cores and real scanned-page/manual GUI/native CUDA
acceptance remain open work.


## Issue #562 — explicit UVDoc and post-perspective redetection stages (2026-10-23; merged #637)

After #636, retain the current public analysis facade, but move explicit user-selected
UVDoc fallback and auto-perspective pixel re-detection into
`preprocess/geometry_stages.py`. No auto UVDoc path is introduced. Call-time
`unwarp_document_image` and `detect_text_polygons` are injected; result objects
carry only working image/polygon/mode/redetection values and are not persisted.

Preserve UVDoc failure warning and prior image/box identity, success clearing
stale boxes, method append order, and post-perspective detection only for
`requested=auto`, `actual=perspective`, with nonempty boxes. The min-box gate is
inclusive; failed, insufficient or exception-raising detection retains the
transformed input boxes and prior warnings. Successful detection converts
every polygon with `np.asarray(..., dtype=float)` before recording the method.
The previous exact public signature, persisted model, image transforms,
coordinate conventions and downstream orthogonal pass remain unchanged.

Current branch `refactor/562-geometry-stage-redetection` shrinks the facade
**98305→97436 bytes**, while retaining 15 classified root files. Ratchet the
normalized facade ceiling 98310→97440 and require both canonical leaf routines
and explicit composition in the analysis adapter; no historical baseline
relaxation. New direct tests cover skip/success/failure, injected operations,
identity, warning/method order, threshold inclusivity and polygon conversion.
Cross-platform CI/GUI/wheel/CodeQL, exact-head review and independent merged-main
validation remain required before acceptance. Native UVDoc/CUDA, real scanned-page
and manual GUI testing are still outstanding.


## Issue #562 — full manual/selected projective execution chain (2026-10-23; merged #638)

Starting from merged `main@e5696d72` (#637), move the manual four-point
perspective application and the downstream selected automatic/explicit perspective
application, complete diagnostic field mapping and warning construction to
`preprocess/perspective_stages.py`. Keep the already-extracted candidate
generation and safety selection in `preprocess/projective_selection.py`;
the public facade composes them with current callbacks and thresholds at call time.

An explicit 72-field mutable `PerspectiveState` carries the original per-page
diagnostic defaults and assignments; mutation inside a failed manual callback
intentionally preserves partially assigned diagnostics before the original warning
is appended. Both image-stage routines return working pixels/polygons, effective mode
and strength, never a persisted model or dynamically injected namespace.
Manual source quadrilateral rotation stays before rectification. The UVDoc stage
still occurs between manual and selected auto/explicit perspective as before.
The selected stage preserves candidate identity checks, inclusive 0.75px
application threshold, original distortion review reasons, warning priority,
conversion/clamping, method parts and safety/selection consequences.
The complete `PreprocessAnalysis` constructor remains unchanged.

Facade `image_preprocessing.py`: **97436→75841 normalized bytes** (−21595);
15 retained root files still explicitly classified. Normalize-size policy is
tightened 97440→75850 without relaxing any historical baseline. New tests target
no-manual skips, source-coordinate rotation, failed/manual partial updates,
selected-candidate 0.75 boundary, explicit unsafe warning, object identities,
call-time operations and leaf imports. Existing full regression, cross-platform
Python3.10/3.13 and OS matrix, GUI smoke, compatibility, wheel, CodeQL and
reviews are mandatory gates before merging. Real scanned-page, manual UI,
UVDoc/CUDA and actual GPU resource validation remain pending.


## Issue #562 — complete orthogonal closed-loop execution and retained audit (2026-10-23; candidate)

On merged `main@efb3a7f3` (#638), move the whole orthogonal residual-correction
pipeline from `analyze_preprocess_page` to `preprocess/orthogonal_pipeline.py`.
The extracted owner includes 59 defaulted per-page orthogonal diagnostics, the
full gated multi-pass estimate/pixel-transform/re-detect/audit/retain-or-rollback
loop, convergence conditions, final retained-pixel re-audit via canonical
`pixel_row_policy`, and the nonlinear-curve manual UVDoc review warning.
The `OrthogonalRuntime` captures **14 current callbacks and 16 scalar gates
at call time**; explicit `OrthogonalRunResult` returns 59 diagnostics plus the
actual retained image/boxes, geometry strength/mode, redetection state and
retained pixel diagnostics. No global hooks, installer, facade/GUI imports,
persisted model clone, new root shim or new GPU resource.

Preserve automatic-mode and writing-direction guards; min-polygon thresholds,
pixel-driven vs OCR-driven scoring and exact inequalities; separator/header/
tail safety checks; warning and method order; per-pass partial observations,
first-valid baseline, retained candidate vs loop stop separation, late rejected
pass preserving the previously accepted pixels, existing fallback state and
source coordinates. The `PreprocessAnalysis` constructor and saved field
conversion/rounding remain byte-for-byte unchanged. The algorithm body moved
byte-for-byte; only the explicit owner boundary and caller result restoration
differ. Facade **75841→55316 bytes** (−20525), normal ceiling
**75850→55320**, retained root count **15**. Architecture guards require
physical canonical owners and correct composition, with no historical oversized
module baseline weakened. Tests cover skipped modes, vertical writing, absent
boxes, estimator failure, policy budget failure, accepted candidate/retained
re-audit, accepted first pass followed by failed second pass, callback and
warning order, identity and source isolation. Complete cross-platform
Python3.10/3.13, GUI smoke, compatibility, wheel, CodeQL, reviews, and
postmerge independent main checks remain mandatory. Native UVDoc/CUDA, real
scan/manual GUI acceptance still cannot be inferred from these synthetic tests.
