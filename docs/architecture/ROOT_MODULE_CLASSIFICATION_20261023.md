# Root module classification — Issue #562 (2026-10-23)

This current inventory supersedes the root-43 inventory for **physical locations**;
that earlier report remains historical evidence, not the current move list.
Scope: direct `src/picture_capture/*.py`, including package entry files.
The repository's launch/install wrappers remain at repository root so documented
OS launch commands continue to work.

PR #628 merged as `7d004fdf`, grouping project and SECTION storage implementations
in `persistence/` (18 → 16 files), after six-platform CI and CodeQL passed. The following OCR resume move reduces 16 → 15 without root
shims. Acceptance depends on exact-head CI/reviews; this inventory is not a
claim that Issue #562 or the oversized-module refactor is complete.

## Remaining root contracts (15/15 classified)

Each row names an existing physical root file. Retention means keep its current
import contract while extracting implementation separately when justified.

| Root file | Domain owner | Reason to retain the current root path |
| --- | --- | --- |
| `__init__.py` | package | Version metadata and side-effect-free package import. |
| `__main__.py` | bootstrap | `python -m picture_capture` and `freeze_support()` entry. |
| `app.py` | bootstrap / ui | Existing GUI application entry and callback surface; oversized implementation still requires a separate staged extraction. |
| `cli.py` | bootstrap | Installed `picture-capture-cli` entry and explicit core-service composition before I/O capture. |
| `launcher.py` | bootstrap | Documented backward-compatible `main` / `prepare_app_module` facade. |
| `models.py` | shared models | Entry/AppSettings/ProjectState identity, settings schema and historical model imports. |
| `entry_classification.py` | proofreading | One process-wide weakref/LRU classification registry, sidecar transaction lock and bootstrap I/O integration; moving only imports does not simplify this ownership. |
| `image_preprocessing.py` | preprocess | Public preprocessing facade; model/helper pickle identities explicitly name this module. Skew/rotation and content-frame bodies now live in `preprocess/deskew.py` and `preprocess/content_bounds.py`, with call-time detector adapters retained here. Orthogonal policy/step payloads and saved geometry rendering are owned by `preprocess/orthogonal_policy.py` and `preprocess/replay.py`; their root adapters supply current audits/transforms explicitly. Preview/crop/encoding bodies belong to `preprocess/rendering.py`. The source evidence stage of analysis belongs to `preprocess/source_evidence.py`, with explicit per-page results and call-time operations/policies. Final re-detection, alignment/crop diagnostics and confidence are owned by `preprocess/finalization.py`. Projective candidate generation/safety/selection belongs to `preprocess/projective_selection.py`, with explicit operation/policy composition. Candidate pixel acceptance and retained-image re-audit belong to `preprocess/pixel_row_policy.py`. Explicit UVDoc fallback and automatic post-perspective re-detection belong to `preprocess/geometry_stages.py`. The manual quadrilateral correction and selected automatic/explicit projective application, diagnostics and safety warning mapping belong to `preprocess/perspective_stages.py`. The complete multi-pass orthogonal correction/acceptance/convergence and retained-pixel audit orchestration belong to `preprocess/orthogonal_pipeline.py`; both owners receive current operations and policies at call time. The public facade remains below 100000 bytes. |
| `image_utils.py` | preprocess | Shared image-analysis API and public helper contract; pixel primitives already owned by `preprocess/page_pixels.py`. |
| `ocr_channel.py` | ocr | OCR selection/session/cache facade; `OcrTextChoice` serialized identity remains this module. |
| `paddle_headwords.py` | ocr | Historical public/private OCR symbols and assignment-mirroring compatibility boundary. |
| `paddle_headwords_core.py` | ocr | Historical OCR core/model pickle identities; large implementation extraction remains separate work. |
| `processing.py` | processing / ordinary | Public detection facade and assignment mirroring; ordinary/GPU worker coordination contract. |
| `processing_core.py` | processing / crop | Historical geometry/crop types and functions; large implementation extraction remains separate work. |
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

The inventory regression compares this table with the actual root files. The
architecture guard prohibits the retired resume root, requires its canonical
owner and the whole-package fingerprint anchor, and ratchets the root count to
15. Existing dataclass/pickle, pixel, spawn, persistence and GUI gates stay in
force. Native CUDA and real scanned-page/manual GUI parity are not established
by automated CI. No root shim, new runtime installer or proxy is introduced.
