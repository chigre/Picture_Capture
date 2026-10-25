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

## Remaining root contracts (10/10 classified)

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
| `paddle_headwords_core.py` | ocr | Retained historical OCR core/model and patchable exported functions; selected review-finalization chain lives in `ocr/review_finalization.py` and the full multi-engine sequence matching, Lens arbitration and coordinate mapping now live in `ocr/pairing_arbitration.py`. OCR image-first symbol/marker and CJK visual projection/context evidence resides in `ocr/visual_evidence.py`; the whole verified CJK local-recovery and three-way separator Y refinement chain now resides in `ocr/cjk_recovery.py`, while original call signatures and recovery policy names remain in the patchable core. The entire OCR candidate parsing, visual-structure scoring, accept/reject and per-page diagnostic orchestration now resides in `ocr/candidate_filter.py` with 42 call-time bindings. The complete multi-engine page invocation (45 live patchable callbacks/policies), raw/reusable cache, review arbitration and v3 report write transaction now belongs to `ocr/page_detection.py` with the original core detection entrypoint preserved as a live adapter. GUI preprocessing operations already live in `ui/preprocess_workflow.py` (merged #647). The complete GUI batch ownership/dispatch/parallel queue/pause-stop lifecycle now resides in `ui/batch_workflow.py` (12 original app method adapters); existing batch results and status semantics remain unchanged. Existing facade mirror, original cache/pickle identity and runtime model remain unchanged. |
| `processing.py` | processing / ordinary | Public detection facade and assignment mirroring; ordinary/GPU worker coordination contract. |
| `processing_core.py` | processing / crop | Historical geometry/crop dataclass/pickle identities and public call-time adapters; canonical whole-entry planning and export now reside in `crop/page_workflow.py`. The whole-entry page crop plan, entry/PPP pairing, union crop, staging and atomic publication execution live in `crop/page_workflow.py`, with live callback composition from the retained `processing_core.py` facade. Page crop dataclass/pickle identities and root public entry points remain stable. |
| `training_export.py` | training | Training API and monkeypatch boundary; ZIP cancellation and publisher preserve this module's pickle identity. |

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
