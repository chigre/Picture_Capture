# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 7 — oversized-module decomposition is underway. Phase 7C extracts preprocessing analysis/manual-geometry persistence without changing analysis behavior or public imports.**

Phase 4 controller decomposition and Phase 5 runtime-patch cleanup are complete. Phase 5 remains closed: all production `*_runtime.py` modules are gone and the zero-runtime-debt architecture ratchet remains active.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Final Phase 5 checkpoint — Phase 5AA
- precondition/help-contract repair PR: **#287 — repair illustration-mask checkbox help contract**
- Phase 5AA production PR: **#288 — remove final illustration-mask runtime seam**
- Phase 5AA production base: `72bd7d22fd84c7e8f30c1a57616aaace681ed8d2`
- production head: `a5ab7206840bfc01fde66863adf5b3a8cba5bf15`
- validated/merged production tree: `def12146459e5a82d924b58fed56add116ce356f`
- production merge / current architecture main: `9ec52afe99647e74ffd5d2d62f1bbe8d3dc7d7e6`

### Pre-Phase-5AA help-contract repair
Read-only preparation for the final runtime deletion found that the native/static Settings schema had the illustration-mask label/help text needed for the final move, but the dedicated checkbox help contract needed an explicit regression before deleting the runtime source.

PR #287 was deliberately narrow:
- add the dedicated `CHECK_HELP["layout_mask_illustrations"]` contract using the same wording already owned by the runtime seam;
- add focused regression coverage;
- do not change checkbox order, cache key, masking behavior, settings persistence, or runtime ownership.

PR #287 gates:
- CI run **2119**: passed;
- CodeQL run **2100** Actions/Python: passed;
- Advanced Security run **1852**: passed.

PR #287 merged as `72bd7d22fd84c7e8f30c1a57616aaace681ed8d2`.

Post-repair main verification:
- CI run **2120**: passed;
- CodeQL run **2101** Actions/Python: passed.

### Final static illustration-mask Settings/cache ownership
Phase 5AA removed the last production runtime module, `layout_illustration_mask_runtime.py`.

The final static ownership is:
- `AppSettings.layout_mask_illustrations`: native dataclass setting/default/persistence;
- Settings Center checkbox ordering: static `ui/settings/schema.py`, immediately after `ordinary_auto_layout`;
- Settings Center label/help: static settings schema/help metadata;
- illustration detector: static `processing_core.detect_illustration_regions_from_image(...)`;
- mask policy/diagnostics: non-runtime `layout_illustration_mask.py`;
- Page Understanding masking/fail-open/lifetime: static `processing._understand_page_current(...)`;
- training-export masking: static `layout_illustration_mask.mask_large_illustrations_for_layout(...)`;
- Layout visualization invalidation: static `layout_visualization_ui._layout_cache_key(app)`, preserving the historical setting-name + boolean tuple contribution;
- GUI bootstrap no longer imports/calls an illustration-mask runtime installer.

Phase 5AA intentionally did not change masking thresholds, detector behavior, PPP/crop formats, settings persistence, Page Understanding routing, training export, or GUI wording.

### Phase 5AA production gate
PR #288 publication shape:
- **1 commit / 6 changed paths**;
- runtime file deleted;
- architecture guard ratcheted runtime debt to zero;
- review submissions: none;
- review threads: none;
- PR comments: none.

Fixed-head PR #288 gates:
- CI run **2121** Ubuntu/Windows/macOS: passed, including pytest, platform GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL run **2102** Actions/Python: passed;
- Advanced Security run **1853**: passed.

PR #288 merged as `9ec52afe99647e74ffd5d2d62f1bbe8d3dc7d7e6`, retaining production tree `def12146459e5a82d924b58fed56add116ce356f`.

### Phase 5AA post-merge verification
On `main@9ec52afe99647e74ffd5d2d62f1bbe8d3dc7d7e6`:
- push CI run **2122**: passed;
- CodeQL run **2103** Actions/Python: passed;
- merge tree exactly matches `def12146459e5a82d924b58fed56add116ce356f`.

Structural Phase 5 completion proof:
- recursive `main` tree contains **zero** `src/picture_capture/**/*_runtime.py` files;
- `scripts/architecture_guard.py` now has `LEGACY_RUNTIME_FILES: set[str] = set()`;
- future production `*_runtime.py` additions therefore fail the architecture ratchet.

## Completed Phase 5 ownership milestones
- Phase 5A–5K: earlier runtime/controller compatibility slices completed; details remain in checkpoint history.
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native settings + static UI/rendering ownership.
- Phase 5P: illustration fill opacity became native settings + static UI/rendering ownership.
- Phase 5Q: long-band logical row recovery became static.
- Phase 5R: character-height fallback became static.
- Phase 5S: column-drift remeasurement became static.
- Phase 5T: identity-only spawn-layout wrapper was removed.
- Phase 5U: spawn-safe ordinary worker became static `processing.detect_entries_job`.
- Phase 5V: guarded oversized-head detection and row/fusion authorization became static.
- Phase 5W: unlined physical-row fast worker became static.
- Phase 5X: Layout-entry classification and existing-marker crop/OCR became static processing ownership.
- Phase 5Y: illustration-mask setting became native and shared detector ownership became static.
- Phase 5Z: illustration masking policy/diagnostics and Page Understanding preprocessing became static.
- Phase 5AA: Settings Center metadata and Layout cache invalidation became static; the final runtime module was deleted.

## Current architecture ratchets
Runtime-installer/module debt is now zero.

The next explicit compatibility debt category in `architecture_guard.py` is dynamic module proxy/namespace mirroring:
- `processing.py`;
- `evidence_fusion.py`;
- `paddle_headwords.py`.

These facades are not equivalent to the retired runtime seams. They preserve a long-standing monkeypatch/debug compatibility contract where assignments to facade/private names are mirrored into historical core modules. Removing the proxy class or namespace copying without first defining that compatibility contract could break tests, plugins, debugging workflows, or external tooling even if normal application execution remains green.

Current approximate facade sizes on final Phase 5 main:
- `paddle_headwords.py`: ~2.9 KB, but its module-class proxy is inherited from `evidence_fusion` and protects the public historical import path;
- `evidence_fusion.py`: ~18.2 KB and also patches supervised decision functions into `paddle_headwords_core`;
- `processing.py`: ~23.3 KB and mirrors many historical `processing_core` symbols while owning current detection behavior.

## Phase 6A bounded contract
Read-only inventory separated two previously conflated behaviors: import-time core mutation and public assignment mirroring.

Observed compatibility contract on the Phase 5 completion baseline:
- direct monkeypatch/integration usage targets the historical public `paddle_headwords` path, including `get_paddle_engine`, `run_paddle_band`, and `refine_separator_y`;
- no direct assignment-mirroring dependency was found for the implementation module `evidence_fusion`;
- existing supervised-fusion regression explicitly requires `filter_headword_records` and `_annotate_peer_typography_matches` to remain patched into `paddle_headwords_core` at import time;
- `processing.py` still has the broadest namespace/proxy surface and remains out of scope for the first Phase 6 write.

Phase 6A therefore narrows, rather than deletes, compatibility behavior:
- `evidence_fusion` returns to ordinary module assignment semantics;
- the module-class proxy is owned directly by the historical public `paddle_headwords` facade;
- assignments on `paddle_headwords` still mirror to an existing same-named core attribute;
- the supervised import-time core patches remain unchanged;
- namespace copying from `paddle_headwords_core` remains unchanged;
- architecture guard now ratchets namespace copying and module-class proxying as separate debt categories.

This removes one dynamic module-class proxy instance without changing OCR decision behavior, supervised rescue behavior, public import paths, or the established public monkeypatch contract.

## Phase 6B explicit supervised-hook contract
Phase 6B removes the two default import-time assignments from `evidence_fusion` into `paddle_headwords_core`:
- `_core.filter_headword_records = filter_headword_records`;
- `_core._annotate_peer_typography_matches = _annotate_peer_typography_matches`.

The mature core now exposes two optional call hooks without changing existing callers:
- `filter_headword_records(..., peer_typography_annotator=None)` defaults to the native core annotator;
- `detect_paddle_headwords(..., record_filter=None)` defaults to the native core filter and uses the selected filter consistently for Paddle, Tesseract, and Lens.

`evidence_fusion` explicitly injects the supervised annotator into its filter wrapper and explicitly injects the supervised filter into its detector wrapper. Historical public monkeypatch behavior remains authoritative: if the public facade has mirrored a different same-named core callable, the wrapper preserves that override instead of replacing it.

This is a behavior-preserving ownership change:
- importing `evidence_fusion` no longer mutates either supervised core symbol;
- direct core callers retain native behavior by default;
- the public OCR boundary path still receives the supervised behavior;
- the `paddle_headwords` assignment-mirroring contract remains unchanged;
- `processing.py` remains untouched.

Because `paddle_headwords_core.py` had only eight bytes of growth headroom under the oversized-module ratchet, the hook change also trims redundant detector documentation so the core shrinks rather than grows. The architecture guard now forbids the two retired evidence-fusion assignment forms from returning.

## Phase 6C public namespace ownership
Read-only inventory showed that production code consumes `evidence_fusion` directly only for the supervised detector path, while the broad public/private symbol surface is consumed through the historical `paddle_headwords` module. The namespace-copy compatibility debt therefore belongs to the public facade, not the supervised implementation module.

Phase 6C preserves the historical symbol surface while relocating ownership:
- `evidence_fusion` no longer copies `vars(paddle_headwords_core)` into its own namespace;
- it explicitly imports only the model/types needed by its supervised implementation;
- `paddle_headwords` now owns the complete non-dunder core namespace copy;
- evidence-fusion overrides are applied after that copy, so supervised filter/typography behavior still replaces the corresponding public symbols;
- `paddle_headwords.__all__` contains the complete core namespace plus evidence-fusion additions and shared public adapters;
- assignment mirroring remains owned by `paddle_headwords`;
- the architecture ratchet moves the allowed namespace-copy owner from `evidence_fusion.py` to `paddle_headwords.py`, so the implementation module cannot silently regain broad mirroring.

This is an ownership relocation, not a compatibility-surface reduction: existing imports from `picture_capture.paddle_headwords` remain available, including private diagnostic/test helpers.

## Phase 6D explicit processing left-edge hook
After Phase 6C, the historical `paddle_headwords` broad namespace is intentionally preserved as an external compatibility surface rather than reduced from repository-local evidence alone. The next narrower debt was the only explicit default import-time mutation remaining in `processing.py`:

- `_core._detect_entries_left_edge = _detect_entries_left_edge`.

Read-only call-graph inspection showed that `processing_core.detect_entries()` resolves that helper only in its two ordinary/combined left-edge branches. Phase 6D therefore replaces the module rewrite with one optional call hook:

- `processing_core.detect_entries(..., left_edge_detector=None)` defaults to the native core implementation;
- the enriched facade passes `processing._detect_entries_left_edge` explicitly only when it delegates to the core fallback path;
- ordinary Layout-role materialization and the existing facade-owned combined observation path remain unchanged;
- the public `processing` assignment proxy remains unchanged, so explicit facade monkeypatch/debug assignments still mirror to same-named core attributes;
- importing `processing` no longer changes the core's default left-edge detector.

The architecture guard now forbids the retired `_core._detect_entries_left_edge =` assignment from returning. Broad namespace copying and module-class proxying remain separate compatibility debts and are not changed in this slice.

## Phase 6E explicit separator-refiner ownership
Read-only inventory after Phase 6D found exactly one remaining default top-level facade-to-core write across `processing.py`, `paddle_headwords.py`, and `evidence_fusion.py`:

- `_core.refine_separator_y = _shared_refine_separator_y` in `paddle_headwords.py`.

That assignment could not simply be deleted because the mature CJK adaptive refiner falls back to `refine_separator_y` on extremely dense pages. Phase 6E therefore makes both levels explicit:
- `paddle_headwords_core.refine_separator_y_adaptive(..., fallback_refiner=None)` defaults to the native core local-valley engine;
- `paddle_headwords_core.filter_headword_records(..., separator_y_refiner=None)` defaults to the native core refiner and forwards the selected refiner into both direct Latin refinement and CJK adaptive fallback;
- `evidence_fusion.filter_headword_records()` injects the neutral shared separator-Y refiner by default, but preserves a same-named core override when the historical public monkeypatch proxy has installed one;
- the historical public `paddle_headwords.refine_separator_y` remains the shared neutral refiner;
- `paddle_headwords.refine_separator_y_adaptive` is now a thin public adapter that passes the shared/public refiner explicitly into the mature adaptive core;
- importing `paddle_headwords` no longer rewrites `paddle_headwords_core.refine_separator_y`.

The oversized `paddle_headwords_core.py` ratchet remains strict: the hook work is paired with a shorter adaptive-refiner docstring, so the core shrinks rather than grows.

### Phase 6 safe completion boundary
After Phase 6E, the three Phase 6 facades perform no default top-level writes into their historical core modules. Architecture guard ratchets prevent the retired evidence-fusion, processing left-edge, and Paddle separator-refiner assignments from returning.

Two compatibility mechanisms intentionally remain on the historical public facades:
- broad non-dunder core namespace re-export on `processing.py` and `paddle_headwords.py`;
- module-class assignment mirroring on `processing.py` and `paddle_headwords.py`.

These are retained public compatibility surfaces, not silent runtime installers. Repository-local usage is insufficient evidence to delete them because plugins, debugging scripts, pickled/spawned callables, and external tooling may depend on the historical module paths/private names. Any future removal should be treated as an explicit compatibility/deprecation project rather than routine debt cleanup.

## Phase 7A image-preprocessing reporting ownership
Phase 7 inventory compared the five oversized production modules by size, top-level ownership, and call graph. The first bounded extraction is deliberately not a geometry or GUI state-machine move.

`image_preprocessing.py` contained two large reporting-only functions that consume completed analysis state but do not participate in page analysis or geometry mutation:
- `export_summary_csv(...)` (~456 lines);
- `result_summary(...)` (~175 lines).

Phase 7A moves them to `image_preprocessing_reporting.py` and re-exports them from the historical `image_preprocessing` module. Existing imports in `app.py`, tests, and external callers therefore remain unchanged. The new reporting module has no runtime dependency back on `image_preprocessing`; type-only references are guarded by `TYPE_CHECKING`.

The production sizes move from:
- `image_preprocessing.py`: 242,626 bytes -> 212,874 bytes;
- new `image_preprocessing_reporting.py`: 30,243 bytes.

The architecture guard ratchets the oversized `image_preprocessing.py` allowance down to 212,874 bytes so the extracted reporting code cannot silently return.

Phase 7A publication note:
- PR #295 fixed head `2ec9c3835c4508858459c569dc72621b34dabf8a` passed CI 2138 on Ubuntu/Windows/macOS and CodeQL 2119 Actions/Python;
- GitHub's PR merge endpoint repeatedly returned an internal control-plane error despite the PR remaining mergeable;
- the already-validated PR tree was integrated as a standard two-parent merge commit `304bfd01a85116b7d608bd7165b87a84d66d10fd`, with parents `c45bd16ef9e1ca5f6b1537fd609f97bba2d0e492` and the fixed PR head;
- the subsequent push CI 2139 failed before job creation with `startup_failure` and could not be retried. This is recorded as infrastructure failure; no post-merge test job failed.

## Phase 7B preprocessing storage/promotion ownership
The next bounded seam is the filesystem-only output/promotion responsibility:
- `preview_output_root(...)`;
- `processed_output_root(...)`;
- `promote_processed_pages(...)`.

These functions do not participate in geometry analysis. They own output directories and the transactional promotion of selected processed pages into project working images, including decode verification, staging, rollback, and preservation of first-generation originals.

Phase 7B moves them into `image_preprocessing_storage.py` and re-exports all three names from the historical `image_preprocessing` module. Existing callers and tests therefore retain the same import path.

The production sizes move from:
- `image_preprocessing.py`: 212,874 bytes -> 206,934 bytes;
- new `image_preprocessing_storage.py`: 6,316 bytes.

The architecture guard ratchets `image_preprocessing.py` to 206,934 bytes.

Phase 7B publication:
- PR #296 fixed head `c471ae973bd8e0ac1a929e80c7159a81d4cd9fbf` passed CI 2140 on Ubuntu/Windows/macOS and CodeQL 2121 Actions/Python;
- PR #296 merged as `43b6e55a5bd45f58dfa901b67953cfb9fb976d95`;
- post-merge CI 2141 and CodeQL 2122 both passed.

A larger data-model extraction remains a strong later candidate: `OutputCanvasInfo` + `PreprocessAnalysis` form a cohesive ~43 KB pure dataclass/serialization seam. The current GitHub connector rejects that single large generated file payload. Do not split the model unnaturally merely to satisfy connector limits; retry it when a reliable large-file write path is available.

## Phase 7C preprocessing persistence ownership
Phase 7C extracts the small JSON persistence layer:
- `result_path(...)`, `save_analysis(...)`, and `load_analysis(...)`;
- `manual_geometry_path(...)`;
- manual perspective geometry load/save/clear;
- `MANUAL_GEOMETRY_FORMAT` and `MANUAL_GEOMETRY_VERSION`.

The new `image_preprocessing_persistence.py` owns filesystem JSON serialization and manual-geometry validation. It does not import the oversized implementation module at import time. Only `load_analysis()` performs a local call-time import of `PreprocessAnalysis` when deserialization actually needs to construct the model, avoiding an import cycle.

All historical names remain re-exported from `image_preprocessing.py`, so app/test/external imports do not change. Existing roundtrip and manual-quad tests continue to exercise those stable imports.

The production sizes move from:
- `image_preprocessing.py`: 206,934 bytes -> 204,153 bytes;
- new `image_preprocessing_persistence.py`: 3,441 bytes.

The architecture guard ratchets `image_preprocessing.py` to 204,153 bytes.

## Recommended next slice — Phase 7D
After Phase 7C validation, reassess the remaining `image_preprocessing` rendering/canvas helpers and `processing_core` crop/illustration domains. Prefer a seam that can move without importing the oversized owner back at module import time. Continue to leave the 2,500+ line `analyze_preprocess_page()` state machine untouched.

## Standing continuation authorization
The user has authorized faster continuous progression through confirmed-safe refactor slices without stopping for a checkpoint after every small change. Phase 6 is complete; Phase 7 follows the same bounded-slice rule.

Continue across related low-risk changes once contracts and focused tests are clear. Use checkpoints at phase milestones, material compatibility-boundary changes, plan changes, merge/finalization boundaries, or when recovery state would otherwise become ambiguous.

Stop production writes for unexplained behavior/test/CI failure, public/file-format compatibility uncertainty, concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
