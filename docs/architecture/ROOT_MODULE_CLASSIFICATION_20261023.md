# Root module classification — Issue #562 (2026-10-23)

This current inventory supersedes the root-43 inventory for **physical locations**;
that earlier report remains historical evidence, not the current move list.
Scope: direct `src/picture_capture/*.py`, including package entry files.
The repository's launch/install wrappers remain at repository root so documented
OS launch commands continue to work.

PR #628 merged as `7d004fdf`, grouping project and SECTION storage implementations
in `persistence/` (18 → 16 files), after six-platform CI and CodeQL passed. The following OCR resume move reduced 16 → 15, and the shared image-analysis
owner migration reduced 15 → 14 without root shims. Acceptance depends on exact-head CI/reviews; this inventory is not a
claim that Issue #562 or the oversized-module refactor is complete.

## Remaining root contracts (7/7 classified)

Each row names an existing physical root file. Retention means keep its current
import contract while extracting implementation separately when justified.

| Root file | Domain owner | Reason to retain the current root path |
| --- | --- | --- |
| `__init__.py` | package | Version metadata and side-effect-free package import. |
| `__main__.py` | bootstrap | `python -m picture_capture` and `freeze_support()` entry. |
| `app.py` | bootstrap / ui | Retained Tk app entrypoint and all callback signatures. Complete 24-method preprocessing mode, perspective edit, analysis, diagnostic, preview and batch export workflow now physically resides in `ui/preprocess_workflow.py`; 12-method foreground batch scheduling and task progress now reside in `ui/batch_workflow.py`, and nine-method recent-project launcher, project restore and page reload now reside in `ui/project_session_workflow.py`; other sizeable GUI responsibilities remain for staged extraction. |
| `models.py` | shared models | Entry/AppSettings/ProjectState identity, settings schema and historical model imports. |
| `ocr_channel.py` | ocr | OCR selection/session/cache facade; `OcrTextChoice` serialized identity remains this module. |
| `paddle_headwords.py` | ocr | Historical public/private OCR symbols and assignment-mirroring compatibility boundary. |
| `processing.py` | processing / ordinary | Public detection facade and assignment mirroring; ordinary/GPU worker coordination contract. |

## Canonical moved owners and consumers

- Project routing and SECTION persistence: `persistence/project_storage.py` and
  `persistence/page_sections.py`. Production, scripts and tests must use these
  canonical paths, including string-based monkeypatch targets.
- Verified OCR page checkpoints: `ocr/page_resume.py`. GUI batch reads/writes
  import this owner directly. `picture_capture.ocr_page_resume` is retired;
  external private import users must update to `picture_capture.ocr.page_resume`.
- After relocation, `_algorithm_environment_key()` must scan the **whole
  picture_capture package**, using `Path(__file__).resolve().parents[1]`.
  Scanning only `ocr/` would permit false resume hits after Layout, settings or
  refinement changes. Existing checkpoint format and fail-closed behavior stay
  unchanged. Changed source paths/bytes conservatively invalidate prior cache
  keys, so a prior completed page may be recalculated once after upgrading.

The former `image_utils.py` implementation is now the physical
`preprocess/analysis_image.py`, with pixel primitives re-exported by identity
from `preprocess/page_pixels.py`. All in-repository consumers have been routed
to the canonical owner; this **retired root import path is a deliberate Python
import compatibility change**, unlike the retained pickle-bearing facades.
Migration: replace `picture_capture.image_utils` with
`picture_capture.preprocess.analysis_image`. No serialized data format, image
coordinates, or dataclass identities change.

The inventory regression compares this table with the actual root files. The
architecture guard prohibits the retired resume root, requires its canonical
owner and the whole-package fingerprint anchor, and ratchets the root count to
10. Existing dataclass/pickle, pixel, spawn, persistence and GUI gates stay in
force. Native CUDA and real scanned-page/manual GUI parity are not established
by automated CI. No root shim, new runtime installer or proxy is introduced.


## 2026-10-24 further root migration in PR #663 (14 → 12)

`entry_classification.py` is now `proofreading/classification.py`: its weakref/LRU
registry, single read/modify/write sidecar transaction lock and JSON-v1 format
stay together. `image_preprocessing.py` is now `preprocess/pipeline.py`: its
patchable callable methods remain together; preprocessing dataclasses are already
owned by `preprocess/models.py`. Internal imports are migrated; external Python
imports from the two retired root paths must be updated. Historical PDIC/PPP data
format is unchanged. `training_export.py` is **retained**: both
`TrainingExportCancelled` and `make_training_zip` explicitly retain
`picture_capture.training_export` pickle identities, so dropping this module
without a migration mechanism would break unpickling.


## 2026-10-24 bootstrap CLI/launcher ownership (12 → 10)

`cli.py` is now physically `bootstrap/cli.py`, with the installed
`picture-capture-cli` console-script target updated. The same commands,
arguments, synchronous core-service bootstrap, PDIC/PPP and image processing
are preserved. `launcher.py` is physically `bootstrap/launcher.py`; actual
GUI and `python -m picture_capture` entrypoints were already routed through
`bootstrap/application.py` and are unchanged. No root wrappers remain.
External Python imports `picture_capture.cli` and `picture_capture.launcher`
are deliberately retired; use their `picture_capture.bootstrap.*` owners.
The installer command names remain unchanged. Root inventory is **10** files.


## 2026-10-25 Round 42: processing root business logic reduction

`processing.py` continues as the historical detection facade and call-time patch point. Actual optional illustration masking, Layout-only versus composed understanding and analysis-image cleanup now live in `layout/current_page.py`; ordinary Layout-role Entry materialization (including refined canonical Y and classification metadata) and fallback-only VB execution live in `ordinary/layout_roles.py`. Three former implementation bodies were removed from the root, with exact legacy signatures retained as delegates. Root remains 10 physical Python modules for public/API and serialization reasons, not because the moved algorithms are still rooted. No persistence schema or OCR cache layout changed; real scanned-page acceptance remains pending.


## 2026-10-25 Round 43: Profile symbol-role and Layout trace owners

- `profile/setup.py` retains the actual `ProjectProfileWizard(tk.Toplevel)`
  UI class, its method signatures, public Profile label tables and historical
  helper functions. The label/catalog tables and real CJK bracket-vs-entry
  normalization and marker-capture precedence algorithms are now physically
  owned by `profile/wizard_catalog.py`. Legacy setup helpers inject the
  current `split_configured_symbols` and `BRACKET_ROLE_SYMBOLS` at call time
  to preserve runtime monkeypatch behavior. No Tk widget is created off-thread.
- The real read-only Layout replay stage snapshot and added/removed provenance
  algorithm now lives in `ordinary/debug_stage.py`. The public
  `processing._record_ordinary_debug_stage` name re-exports the same callable,
  and `processing.detect_entries` still resolves that name at call time.
- New focused regression `tests/test_issue562_profile_catalog_debug_stage_20261025.py`
  protects symbol role precedence, sample nonmutation, patch injection,
  read-only trace deltas and physical ownership. The root-file count remains
  **10**; these are implementation extractions, not root API retirements.
  Real dictionary scans, Profile GUI interaction, PDIC/PPP reopen and crop
  export parity remain pending manual acceptance; PR stays Draft.


## 2026-10-25 Round 44: shared geometry and ordinary observations

Five complete root `processing.py` algorithms now physically live in two
cohesive owners: `layout/shared_geometry.py` constructs source/canonical
`Geometry`/`ColumnPath` and freezes nonuniform ordinary column offsets;
`ordinary/observation_policy.py` enforces page-template and SECTION Entry
gates, reads OCR review-cache candidates without writes, and computes
conservative hard-negative consensus rows. All five original processing
function signatures and `__module__` stay stable; historical callers,
`_geometry_from_page_design`, and `_shared_detector_observations` resolve
the old callable names at runtime. Delegates inject current core factories,
settings copier, template/SECTION filters, JSON decoder and consensus hooks,
preserving monkeypatch behavior. Regression:
`tests/test_issue562_shared_geometry_observations_round44_20261025.py`.
No new root stub, serialized model move, Tk worker change, PDIC/PPP or OCR
cache schema change. Real scanned dictionary-page ordinary/OCR/combined,
Profile, PDIC/PPP save/reopen and crop/export parity remain **manual
acceptance pending**. PR stays Draft and unmerged.


## 2026-10-25 Round 45: detection orchestration and Profile scroll owners

The shared Page Understanding OCR/combined observation pipeline moved from
root `processing.py` into `detection/shared_observations.py`, retaining the
historical processing API and live patch points. Four Profile Wizard wheel/
canvas/descendant algorithms moved from `profile/setup.py` to
`profile/wizard_scroll.py` with Tk event/main-thread behavior intact.
Characterization test: `tests/test_issue562_shared_observations_wizard_scroll_round45_20261025.py`.
Root file count stays 10. Independent real dictionary scan, PDIC/PPP
save/reopen and crop/export parity remain pending; PR remains Draft.


## Round 46 — OCR channel, project page discovery and Profile validation

Root `ocr_channel.py` retains stable public models, session and hooks; seven algorithm implementations moved into `ocr/channel_preparation.py` and `ocr/channel_results.py`. Root `models.py` retains persisted model identity but delegates four project discovery/sorting algorithms to `project/page_discovery.py`. Four Tk validation algorithms moved from `profile/setup.py` to `profile/wizard_validation_controls.py`, with the historical methods still running on the original main UI event path. Focused tests: `tests/test_issue562_ocr_channel_project_profile_round46_20261025.py`. Ten root Python files remain, no stubs. Representative dictionary scans, PDIC/PPP save/reopen and export parity remain pending; PR stays Draft.


## Round 47 — PaddleOCR channel model lifecycle owner

`ocr/paddle_engine_lifecycle.py` now owns lazy engine construction and clearing inactive caches. The original `ocr_channel._create_paddle_engine` and `clear_ocr_channel_paddle_engine_cache` functions inject current providers and preserve the historical API, worker/resource owner and GPU single-pipeline policy. Characterization regression: `tests/test_issue562_ocr_paddle_lifecycle_round47_20261025.py`. Root remains 10 Python modules with reduced bytes. Real scanned dictionary-page/OCR/combined, PDIC/PPP reopen and crop/export manual acceptance remain pending; Draft stays unmerged.


## Main UI root-retirement Phase 1 (2026-10-25)

Moved 19 concrete UI methods from root `app.py` into physical `ui/main_appearance_policy.py`, `ui/main_sidebar_sections.py`, and `ui/quick_settings_apply.py`. Public `PictureCaptureApp` signatures, patched Tk globals and event-loop dispatch stay unchanged. Focused suite: `tests/test_issue562_root_ui_ownership_phase1_20261025.py`. End state targets just `__init__.py` and `__main__.py` at package root, subject to compatibility gates and representative dictionary-page manual acceptance. No merge/Ready.


## Phase 2: Profile Wizard physical ownership (2026-10-25)

Five real methods moved from `profile/setup.py` to `wizard_tab_builders`, `wizard_profile_events`, `wizard_headword_explanations`, and `wizard_settings_assembly`. Compatibility method signatures and call-time patchpoints retained. End goal of only `__init__.py` and `__main__.py` at root remains pending compatibility proof and real scanned-page acceptance.


## Phase 3: review crop, OCR current-page and durable Tk close (2026-10-25)

Eight actual `app.py` implementations physically migrated to `ui/review_crop_geometry.py`, `ui/ocr_current_workflow.py`, and `ui/main_app_lifecycle.py`, with old public call signatures and call-time patched collaborators retained. Test: `tests/test_issue562_root_review_ocr_lifecycle_phase3_20261025.py`. Root count stays 10; no pickle/PDIC/PPP changes. Real scanned dictionary page, Profile, ordinary/OCR/combined and save/reopen/export manual acceptance remains pending. PR stays Draft.


## Phase 4: complete page detection and ordinary worker ownership (2026-10-25)

Root `processing.py` now preserves the stable public `detect_entries` and `detect_entries_job` signatures but physically delegates their former full algorithms to `detection/page_pipeline.py` and `detection/ordinary_page_job.py`. Call-time dependency snapshots retain legacy runtime monkeypatches; Windows spawn entry remains importable. The ordinary Layout, VB emergency fallback, OCR/combined, GPU preflight and PDIC writer sequences are unchanged. New regression: `tests/test_issue562_detection_pipeline_owner_phase4_20261025.py`. Real scan GUI/Profile/PDIC/PPP/reopen/export acceptance remains outstanding; Draft must remain open.


## Phase 5 — main canvas display cache, crop planner and PDIC save ownership (2026-10-25)

Twelve real `app.py` algorithms now live in `ui/main_display_cache.py`, existing `ui/main_canvas_render_workflow.py`, and `ui/main_pdic_persistence.py`. The original Tk class and runtime-patched public methods remain stable; R3 recovery quarantine, PDIC changed-only writes, batch PPP suppression, Profile geometry and image caching remain intact. Regression: `tests/test_issue562_main_display_pdic_owner_phase5_20261025.py`; no-op autosave source guard now checks the physical owner. Root remains 10 files, smaller by the physically migrated code. Real scanned-page acceptance remains pending and PR stays Draft/unmerged.


## Phase 6 — OCR session engine execution (2026-10-25)

Five substantive engine and orchestration algorithms moved from `ocr_channel.OcrChannelSession` into `ocr/channel_engine_execution.py`. Root `ocr_channel.py` retains stable session/dataclass public identities and call-time monkeypatch forwarding. Paddle preprocessing/source boxes, Tesseract TSV, Lens conflict/diagnostic policy, and crop fusion ordering are preserved; no persistence or Tk changes. Characterization: `tests/test_issue562_ocr_channel_engine_execution_phase6_20261025.py`. Root file count stays 10; the root-only `__init__.py`/`__main__.py` goal is not yet achieved. Real scanned-page GUI/Profile/PDIC/PPP reopen/export acceptance remains pending; keep Draft.


## Phase 7 — Review responsive layout and Settings form physical owners (2026-10-25)

Moved 13 substantive methods from root `app.py` into `ui/review_layout_events.py` (10 proofreading window pane/zoom lifecycle methods), existing `ui/settings/field_form_runtime.py` (settings value conversion), and existing `ui/settings/interactive_panels.py` (collapsible settings and intro widgets). Existing Tk class methods and runtime monkeypatch injection are preserved; no new root compatibility files. Regression: `tests/test_issue562_review_settings_layout_phase7_20261025.py`; historical source guards reanchored to real implementations. Target remains root `__init__.py`/`__main__.py` only after compatibility gates and manual scanned-page acceptance; Draft/unmerged.


## Phase 8 — Dialog lifecycle and page persistence (2026-10-25)

Nine complete `app.py` methods now physically live in `ui/main_dialog_lifecycle.py` (five Tk dialog/window opening and reuse flows) and existing `ui/main_pdic_persistence.py` (four PDIC/PPP navigation saves, user save and SECTION persistence flows). Root `PictureCaptureApp` retains stable call-time patched callbacks and Tk-thread ownership. Regression: `tests/test_issue562_main_dialog_page_save_phase8_20261025.py`. Root file count remains 10; end-state only `__init__.py`/`__main__.py` is still pending compatibility proof. Manual real scanned-page acceptance is NOT DONE. Draft/unmerged.


## Phase 9 — Main window PPP and quick-control ownership (2026-10-25)

Fifteen actual main-window methods were physically moved from root `app.py` to existing `ui/controllers/canvas.py`, `ui/canvas_pointer_workflow.py`, `ui/quick_settings_apply.py`, and `ui/main_app_lifecycle.py`. Legacy Tk callbacks, staticmethod identities and call-time patchpoints remain. Dedicated regression: `tests/test_issue562_main_canvas_ppp_quick_owner_phase9_20261025.py`. Physical root remains 10 files; final goal of only `__init__.py` and `__main__.py` is still pending compatibility gates and real-page manual acceptance.


### Phase 10 — residual Tk navigation, UI-worker generations and OCR runtime versions (2026-10-25)

- Physically relocated **10 complete algorithms** out of `app.py`: sidebar pointer hit-testing and Windows/Linux wheel routing (3) to existing `ui/main_sidebar_sections.py`; Treeview wheel/overlay navigation (2) to `ui/page_index_workflow.py`; transformed-coordinate write safety guard (1) to `ui/main_app_lifecycle.py`; UI-worker generation activity/invalidation (2) to `ui/background_job_runtime.py`; installed distribution-version lookup and comparison (2) to `ui/paddle_environment_report.py`.
- Public `PictureCaptureApp` callbacks and `staticmethod` identities remain. `tk`, `transformed_geometry_pending`, `importlib_metadata`, and `re` are injected at call time, preserving original monkeypatch seams. Tk operations remain on the UI thread; no OCR/ordinary/combined pipeline, PDIC/PPP, model, spawn or crop/export format changes.
- Characterization: `tests/test_issue562_root_remaining_ui_algorithms_phase10_20261025.py`. Root-only `__init__.py`/`__main__.py` goal is not yet reached. Real scanned dictionary-page GUI/Profile/ordinary/OCR/combined/PDIC/PPP save-reopen/crop-export manual acceptance remains **NOT DONE**. Keep PR Draft, Open and unmerged.

### Phase 11 — Model persistence and real project-open workflow (2026-10-25)

- Physically moved `AppSettings.to_json` and `AppSettings.from_json` JSON serialization/migration implementations out of root `models.py` into `profile/settings_storage_io.py`, including same-directory unique temp file, lock, fsync, atomic replacement, cleanup and historical settings defaults.
- Physically moved the complete `ProjectState.open` project bootstrap out of root `models.py` into `project/state_opening.py`. The new owner retains the managed-vs-legacy boundary, incomplete crop transaction recovery, settings/Profile precedence, bounded wordslist read, and QT output directories. `AppSettings`/`ProjectState` identities, public method signatures and call-time patched dependencies remain in `models.py`.
- Targeted regression: `tests/test_issue562_model_io_project_open_phase11_20261025.py` plus existing atomic settings, project/storage, Profile and IO tests. No PDIC/PPP/OCR cache serialization fields or export formats changed. Root file count still 10; precise bytes are measured from committed Git tree.
- **Manual acceptance NOT DONE:** real scanned dictionary pages covering normal/OCR/combined detection, Profile UI, PDIC/PPP save and reopen and cropped/exported results. Keep PR #663 Draft, Open, unmerged.

### Phase 12 — legacy VB and profile-specific visual recovery (2026-10-25)

- Physically moved the actual `processing._detect_entries_left_edge` detector/recovery sequence into `ordinary/visual_fallback.py:detect_entries_left_edge_with_recovery`. The root processing facade retains the historical public signature, source-contract docstring and callable module identity, passing the *current* legacy detector, CJK/indent predicates, topology/oversized-head and non-CJK visual recovery callbacks, and SECTION reading-order sorter at invocation time. No OCR engine or sidecar/crop/export transaction was relocated.
- Added `tests/test_issue562_ordinary_visual_fallback_phase12_20261025.py` to characterize the CJK topology/oversized path, combined-mode skip, no-indent skip, non-CJK visual recovery, stable sorting, and live facade monkeypatches. `profile/setup.py` remains an already-delegating Tk compatibility surface and is not cosmetically split.
- Direct root module count remains 10. Real scanned dictionary-page GUI/Profile/ordinary/OCR/combined and PDIC/PPP save/reopen/crop-export parity acceptance remains **NOT DONE**; PR #663 must remain Draft/unmerged.

### Phase 13 — OCR engine-selection policy physical ownership (2026-10-25)

- Moved the complete multi-engine, legacy fallback, Lens diagnostic/conflict/full mode and voting-selection algorithm from root `ocr_channel.py:resolve_ocr_channel_plan` into `ocr/channel_policy.py:resolve_plan`. The public callable retains its signature and `__module__`; historical `OcrChannelPlan` dataclass/pickle identity remains in root. Current engine alias resolver, order and constructor are injected on each call to preserve monkeypatch seams. This policy neither initializes engines nor modifies OCR caches/PDIC/PPP.
- Added `tests/test_issue562_ocr_channel_policy_phase13_20261025.py` for physical owner, stable dataclass, Lens-only legacy fallback, invalid modes, diagnostic voting, rescue Tesseract, and runtime patched engine order/factory. Real dictionary-page manual GUI/Profile/ordinary/OCR/combined and PDIC/PPP reopen/export parity acceptance remains **NOT DONE**; keep Draft/unmerged.


### Phase 14 — AppSettings runtime validation and storage aliases (2026-10-25)

- Moved **three complete algorithms** from root `models.py` to `profile/settings_value_policy.py`: `_normalize_display_opacity` (numeric/NaN clamping), `_app_settings_storage_alias` (native slotted alias descriptors), and `AppSettings.__setattr__` (crop width, physical-row projection width, separator-Y ink safety and opacity assignment validation). The model's full validator branches now have Profile ownership; root methods are legacy delegation points only, resolving the opacity callback and `math` at call time for monkeypatch compatibility.
- Preserved native `AppSettings` dataclass field order, exact `__module__`/pickle identity, `_AppSettingsMeta` constructor translation, and settings JSON migration/atomic save implemented in the previous phase. No GUI thread, OCR/ordinary/combined, PDIC/PPP/SECTION, project or crop/export format changes.
- Focused regression `tests/test_issue562_appsettings_value_policy_phase14_20261025.py` checks physical ownership, ctor and assignment range checks, failed-setter state retention, integer ink threshold, patched opacity/math providers, aliases, and pickle roundtrip. Existing settings migration, profile, import and full platform suites remain gating. `profile/setup.py` remains the Tk callback compatibility surface and should not be reduced by adding pointless forwarding layers.
- Representative **real scanned dictionary-page manual acceptance remains NOT DONE**: Profile UI, normal/OCR/combined detection, PDIC/PPP save/reopen, crop and export parity. PR #663 stays Draft, Open, unmerged.


### Phase 15 — Native AppSettings model field ownership (2026-10-25)

- Physically transferred the **entire native slotted `AppSettings` dataclass definition, 150+ field schema, compatibility descriptors, metaclass constructor, row-height property, public setters and persistence hooks** from root `models.py` to `profile/settings_model.py`. No subclass, no duplicate dataclass: the root exports the exact same class and metaclass objects with historical `__module__ == "picture_capture.models"` preserved for pickle. `Entry`, `PolygonRegion`, and `ProjectState` remain independently defined in `models.py`.
- Native model methods use call-time imports of root `models` for monkeypatchable normalizer, migration providers, JSON writers and synchronization lock. Physical parameter-validation algorithms remain in `profile/settings_value_policy.py` and atomic storage in `profile/settings_storage_io.py`.
- Targeted test: `tests/test_issue562_appsettings_native_owner_phase15_20261025.py` for owner identity, pickle roundtrip, field order/aliases, dataclass replace, legacy hooks, assignment rollback and JSON roundtrip. Preserves GUI/OCR/normal/combined and PDIC/PPP/SECTION/export formats; independent real scanned dictionary-page manual acceptance **NOT DONE**. PR #663 Draft/Open/unmerged.

### Phase 16 — physical OCR core relocation with stable root import identity (2026-10-25)

- Moved the complete OCR core runtime implementation (154 functions, state and integrations) from `paddle_headwords_core.py` to `ocr/headword_core_runtime.py`; the old root module now consists solely of an **intentional import-identity compatibility bridge**. The bridge is required because bare `import picture_capture` is strictly metadata-only, and a lazy finder registered by package initialization would violate that existing contract.
- The root bridge installs the **canonical module object itself** into `sys.modules["picture_capture.paddle_headwords_core"]`. No duplicate state or function wrappers: old imports, public `paddle_headwords` monkeypatch mirrors, and the old function `__module__`/pickle identities still resolve to the same live module. No eager OCR import on bare package initialization.
- Direct root Python inventory stays **10 files**, while root source bytes shrink by approximately **77 KB**. This is genuine physical implementation migration, not a root-file-count reduction; the stable bridge is not counted as retired.
- Reanchored tests for the real implementation source and the preserved public module. Added targeted subprocess, callable-pickle and monkeypatch tests. Exact-head six-platform CI and three-OS OCR Smoke are required. Manual real scanned dictionary-page GUI/Profile, ordinary/OCR/combined, PDIC/PPP save/reopen, crop/export parity **NOT DONE**. PR #663 remains Draft/Open/unmerged.

### Phase 17 — root processing core becomes a single canonical runtime owner (2026-10-25)

- Physically moved **all 83** top-level legacy processing functions (Geometry/column integration, ordinary/OCR delegates, entry sorting, crop plans, PDIC/PPP crop export and spawn worker coordination) from `src/picture_capture/processing_core.py` to `runtime/processing_core_runtime.py`. The actual geometry, crop and detection leaf algorithms remain in their existing responsibility-bound packages; this runtime module is their shared composition layer.
- The historical root path retains only an explicit **single-module-identity compatibility bridge** (not duplicated implementations). Public `processing` facade monkeypatches mutate the same runtime global namespace. Historical `__module__` and pickle paths for 83 locally-defined functions, the geometry and crop dataclasses and Windows spawn workers remain `picture_capture.processing_core`. No `picture_capture.__init__` side effects.
- Targeted regression `tests/test_issue562_processing_core_runtime_phase17_20261025.py` checks canonical ownership, call-time patching, old worker pickle paths, shared class identity, source-coordinate crop boundaries and import laziness.
- This is a reduction of root **business implementation bytes**, not a dishonest claim that a compatibility entrypoint was deleted: file count stays at 10. `profile/setup.py` is unchanged in this phase. Real scanned dictionary-page manual GUI/Profile, ordinary/OCR/combined, PDIC/PPP save/reopen and crop/export parity remain **NOT DONE**. Keep PR #663 Draft, Open and unmerged.

### Phase 18 — Retire physical root training exporter, preserve live identity (2026-10-25)

- Moved the remaining complete exporter composition and helper implementations (`_read_json`, `_copy_if_exists`, `export_training_page`) from root `training_export.py` to `training/export_runtime.py`. Original root `training_export.py` is **deleted**, reducing root module count. The old `picture_capture.training_export` import is now a package-level `training_export/__init__.py` identity bridge, resolving to the **same live module instance**, not duplicated functions/state; original per-call monkeypatch dependencies and `TrainingExportCancelled`/`make_training_zip` pickle names remain stable. ZIP, manifest and page export formats untouched.
- Hardened `scripts/architecture_guard.py` to require the canonical training runtime, the package legacy alias, **no root module file**, the original delegated APIs, and root Python module count <=9. Four historical source-location tests were reanchored while preserving actual invariants. Added `tests/test_issue562_training_root_retirement_phase18_20261025.py` for legacy-module identity, live monkeypatch, pickle, JSON/copy bytes, and bare package laziness. Previous training export and profile tests remain required.
- `app.py` and `profile/setup.py` remain pending, with root eventual only `__init__.py` and `__main__.py` not yet achieved. Real scanned dictionary page manual GUI/Profile/ordinary/OCR/combined/PDIC/PPP save-reopen/crop export acceptance **NOT DONE**. PR #663 stays Draft/Open/unmerged.

### Phase 19 — Profile language normalization and legacy GUI vocabulary (2026-10-25)

- Physically moved the ISO-639-1 project language vocabulary, OCR-to-index language mapping and first-language normalization algorithm from root `app.py` to `profile/language_policy.py`. `app.PROJECT_LANGUAGE_CODES` and `app.OCR_TO_PROJECT_LANGUAGE` remain the original public object aliases, while `app.project_language_from_ocr` retains its signature and reads the current monkeypatchable mapping on each call.
- Moved Profile Wizard's first-matching-label and OCR-label normalization loops from `profile/setup.py` to the canonical `profile/wizard_catalog.py`; the historical setup functions preserve their call signatures and dynamically patched `OCR_LANGUAGE_LABEL_TO_VALUE` mapping. These are actual policy bodies, not new duplicate wrappers; the compatibility entrypoints remain only because tests and UI integrations import them.
- Targeted regression: `tests/test_issue562_profile_language_policy_phase19_20261025.py`; reanchored the project settings source-location guard. No change to Tk thread dispatch, OCR engine selection, ordinary/combined detection, PDIC/PPP/SECTION serialization, or crop/export formats. Real scanned dictionary-page GUI/Profile/ordinary/OCR/combined, PDIC/PPP save/reopen and crop/export manual acceptance **NOT DONE**; PR #663 remains Draft/Open/unmerged.

### Phase 20 — main-window scrollable text-report widget ownership (2026-10-25)

- Physically migrated the complete Tk report-window construction (Toplevel sizing, font selection, two-axis scrolling, read-only text insertion and grid weights) from root `app.PictureCaptureApp._show_text_report` into existing `ui/main_dialog_lifecycle.py:show_text_report`. This is a real widget assembly implementation, not a copied helper or new generic wrapper layer.
- Original method name/signature remains, with four live app globals passed at call time for monkeypatch and appearance compatibility. No worker thread, `after` scheduling, OCR mode, PDIC/PPP/SECTION or export format changes. Focused test `tests/test_issue562_text_report_owner_phase20_20261025.py` uses fake widgets to verify the actual report contents, read-only state, both scrollbars, sizing, font and live patched collaborators without requiring a display.
- Root file count unchanged. Exact-head six-platform CI and three-OS OCR Smoke required; representative real scanned dictionary-page GUI/Profile, ordinary/OCR/combined, PDIC/PPP save/reopen and crop/export parity manual acceptance **NOT DONE**. Keep PR #663 Draft/Open/unmerged.

### Phase 19 — Historical core imports retired from the physical root (2026-10-25)

- Deleted the two obsolete **root-only compatibility files** `processing_core.py` (411 B) and `paddle_headwords_core.py` (434 B). Their 83 processing and 154 OCR algorithms were **already** physically moved to `runtime/processing_core_runtime.py` and `ocr/headword_core_runtime.py` in earlier phases; this phase retires only the two redundant root compatibility files.
- Both historical imports now exist as lightweight `processing_core/__init__.py` and `paddle_headwords_core/__init__.py` package aliases, bound to the same canonical module object, maintaining pickle, Windows spawn, live monkeypatch behavior and metadata-only import of bare `picture_capture`. No duplication of algorithms or state.
- Root Python file cap and classification tightened from **9 to 7**; guard rejects either removed file returning, requires identity bridges and preserves leaf algorithm checks. Focused unit tests check old import paths and pickle/monkeypatch functionality.
- **Still NOT DONE:** real scanned dictionary-page manual Profile/Tk, ordinary/OCR/combined detection, PDIC/PPP save-reopen, crop/export parity. Draft PR #663 remains open, unmerged, never marked Ready.
