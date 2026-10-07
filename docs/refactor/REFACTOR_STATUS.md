# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 7 — oversized-module decomposition is underway. Phase 7J extracts crop-plan naming/serialization leaf helpers from `processing_core.py` while preserving core-global monkeypatch lookup semantics.**

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

Phase 7C publication:
- PR #297 fixed head `7a6d8b2a9a34eca16fb8bbc7e039a7450184a3eb` passed CI 2142 on Ubuntu/Windows/macOS and CodeQL 2123 Actions/Python;
- PR #297 merged as `d5fd425396cf92fdc0acd104044949b2c03838b7`;
- post-merge CI 2143 and CodeQL 2124 both passed.

## Phase 7D page-aware word-mapping ownership
Read-only inventory of `app.py` found a cohesive, GUI-independent helper block that owns page-aware headword text parsing and comparison:
- `_parse_words_of_pages_text(...)`;
- `_fill_page_entries(...)`;
- `_page_word_mapping_text(...)`;
- `_compare_page_word_sequences(...)`;
- `_compare_page_word_mappings(...)`.

These helpers do not depend on Tk widgets or mutable app state. They parse page-bounded legacy/PDIC text, fill one page without cross-page spillover, render page-aware mappings, and compute deterministic per-page sequence diffs.

Phase 7D moves them into `page_word_mapping.py`. `app.py` imports and re-exports the same underscore names, so:
- `HeadwordController` constructor injection remains unchanged;
- old/new comparison code continues to call the same names;
- private compatibility imports from `picture_capture.app` remain available.

Focused tests cover stable app re-export identity, page-boundary parsing, no-cross-page filling, and page-local diff semantics.

The production sizes move from:
- `app.py`: 809,833 bytes -> 802,903 bytes;
- new `page_word_mapping.py`: 7,416 bytes.

The previous app oversized guard was still a loose 867,212-byte historical ceiling. Phase 7D ratchets it directly to the current 802,903-byte tree size, capturing both this extraction and already-completed earlier app decomposition.

Phase 7D publication:
- first CI run 2144 exposed one stale source-inspection regression that still expected the parser implementation in `app.py`; the test was updated to assert the same one-lookup contract in the new owner;
- fixed head `139154d7307cf4f9b66ca67b225d3a84f1260f32` passed CI 2145 on Ubuntu/Windows/macOS and CodeQL 2126 Actions/Python;
- PR #298 merged as `6af34809520e60ce1024a3e6d07f04f9f0b2a745`.
- post-merge CI 2146 and CodeQL 2127 both passed.

## Phase 7E pure review-text ownership
Phase 7E deliberately excludes every helper whose behavior is runtime-patched or performs review/PDIC mutation. In particular, `_review_line_box`, review crop context, height resolvers, and focused-review page updates remain in `app.py`.

The extracted helpers are two GUI-independent groups:
- review text/font/range utilities: `_review_editor_font_size`, `_entry_font_spec`, similarity normalization/scoring, focused-review character parsing, page-range parsing, and single-character detection;
- OCR candidate presentation utilities: nearest candidate matching, explicit source-word lookup, semantic similarity color, and deterministic candidate-choice rows.

They move to `review_text_helpers.py`, which depends only on Python text utilities plus `AppSettings`/`Entry`. It has no Tk, PIL, processing, controller, or app dependency.

`app.py` re-exports every historical underscore helper name. This is important because review runtime extensions still consult selected app-module slots, while the one actively replaced slot (`_review_line_box`) remains app-owned and unchanged.

The production sizes move from:
- `app.py`: 802,903 bytes -> 796,866 bytes;
- new `review_text_helpers.py`: 6,617 bytes.

The architecture guard ratchets `app.py` to 796,866 bytes.

Phase 7E publication:
- first CI run 2147 exposed one stale source-inspection assertion that still expected a candidate helper implementation in `app.py`; the UI/source contract was split so UI text remains asserted in `app.py` while helper ownership is asserted in `review_text_helpers.py`;
- fixed head `69f636529c5b1f62eb6f82d8e3c3a61bf9f7a57c` passed CI 2148 on Ubuntu/Windows/macOS and CodeQL 2129 Actions/Python;
- PR #299 merged as `df2b1042bb8dbce21548456983b6511465d46d93`;
- post-merge CI 2149 and CodeQL 2130 both passed.

## Phase 7F overlay/editor-layout ownership
Phase 7F extracts the contiguous GUI-independent helper block used to compute overlay typography, binary preview display, and editor/menu/index placement:
- `effective_main_overlay_font_size(...)`;
- `scaled_overlay_line_width(...)`;
- `review_auto_fit_zoom(...)`;
- `binary_preview_image(...)`;
- vertical marker/editor/menu helpers;
- transformed/horizontal editor anchors;
- `entry_index_label_layout(...)`.

These functions move to `overlay_layout_helpers.py`, which depends only on PIL image conversion and `AppSettings`. It does not import Tk or `app.py`.

`app.py` continues to re-export all 11 historical names, so existing tests and internal/external imports remain stable. Existing behavior tests in `test_next_stage_regressions.py` continue to exercise those app imports. A focused ownership test additionally requires direct object identity between app aliases and the new owner.

Moving `binary_preview_image` also removes the last `ImageOps` dependency from `app.py`.

The production sizes move from:
- `app.py`: 796,866 bytes -> 789,609 bytes;
- new `overlay_layout_helpers.py`: 7,798 bytes.

The architecture guard ratchets `app.py` to 789,609 bytes.

Phase 7F publication:
- PR #300 fixed head `a154978b9203f953a899e9c07d835b84aea5a840` passed its PR validation;
- PR #300 merged as `02a2c0a2c4f9c8dda69f031b7299e5d3c4360239`;
- post-merge CI 2151 and CodeQL 2132 both passed.

## Phase 7G layout-percent ownership
Phase 7G extracts the GUI-independent source-pixel/percentage conversion contract used by Settings Center, quick settings, and proofreading-height display:
- `LAYOUT_PERCENT_AXES`;
- `_layout_percent_denominator(...)`;
- source-image pixel/% conversion and formatting helpers;
- configured-column-width pixel/% conversion helpers;
- proofreading-height pixel/% wrappers.

These helpers move to `layout_percent_helpers.py`, which depends only on PIL's `Image` type and `AppSettings`. It has no Tk, app-state, controller, processing, persistence, or runtime-extension dependency.

`app.py` re-exports the complete historical helper surface, so existing functional tests and external/private imports remain stable. Two source-inspection regressions are updated deliberately:
- Settings Center UI/content continues to be inspected in `app.py`;
- axis mapping and conversion implementation ownership are inspected in `layout_percent_helpers.py`.

Focused ownership tests additionally require direct app/new-owner identity and preserve width-vs-height axis semantics.

The production sizes move from:
- `app.py`: 789,609 bytes -> 787,094 bytes;
- new `layout_percent_helpers.py`: 3,044 bytes.

The architecture guard ratchets `app.py` to 787,094 bytes.

Phase 7G publication:
- PR #301 fixed head `5a6331e6cb7a844d202e3da55cc0b4eb2f31c135` passed CI 2152 on Ubuntu/Windows/macOS and CodeQL 2133 Actions/Python;
- PR #301 merged as `6b99da85d984112f5d8d90ea0904b2d8aba22f4b`;
- post-merge CI 2153 and CodeQL 2134 both passed.

## Phase 7H page-list helper ownership
Phase 7H extracts the three GUI-independent helpers that support the project page Treeview without depending on Tk objects:
- `_natural_text_key(...)`;
- `_sorted_page_list_rows(...)`;
- `_fill_status_cell_style(...)`.

They move to `page_list_helpers.py`, which depends only on the shared `models.natural_text_key` implementation. The sorting helper preserves stable page iids, natural numeric ordering, empty cells at the bottom in both directions, and legacy four/five-column row compatibility. The status helper preserves the semantic background/foreground mapping used by the overlay labels.

`app.py` re-exports all three historical private names. Bookmark sorting, page-list header sorting, and fill-status overlay rendering therefore keep the same call sites. Because the extracted block was the only direct `natural_text_key` usage in `app.py`, that import is also removed from the oversized owner.

Focused tests cover app/new-owner identity, natural ordering with empty rows last, legacy bookmark-row compatibility, and each semantic fill-status color.

The production sizes move from:
- `app.py`: 787,094 bytes -> 784,737 bytes;
- new `page_list_helpers.py`: 2,595 bytes.

The architecture guard ratchets `app.py` to 784,737 bytes.

Phase 7H publication:
- PR #302 fixed head `abe6f3ab2bc5e4d23a19f748f4014afb7ece3fbd` passed CI 2154 on Ubuntu/Windows/macOS and CodeQL 2135 Actions/Python;
- PR #302 merged as `d6392b7dc153ce1bccfca064343c3cbdd56319b3`;
- post-merge CI 2155 and CodeQL 2136 both passed.

## Phase 7I processing publish-transaction ownership
Phase 7I switches oversized-owner focus from `app.py` to `processing_core.py` rather than crossing the remaining app runtime-review boundary.

The extracted seam is deliberately limited to two leaf filesystem transaction helpers:
- `_publish_temp_path(...)`;
- `_publish_file_transaction(...)`.

They move to `processing_publish.py`, which depends only on `os`, `uuid`, and `Path`. `processing_core.py` imports and re-exports both names, so existing split/export call sites remain unchanged.

`_stage_text_file(...)` and `_stage_crop(...)` intentionally remain in `processing_core.py`. This preserves the Phase 6 historical assignment-mirroring contract: a debug/test assignment such as `processing._publish_temp_path = fake` still mirrors into the core global that staged text/crop code resolves at runtime. Focused tests explicitly characterize that behavior.

The public `processing._publish_file_transaction(...)` compatibility forwarder remains unchanged. Existing rollback/failure-injection tests continue to exercise the public facade path; the source-contract marker is updated only to identify `processing_publish` as the implementation owner.

The production sizes move from:
- `processing_core.py`: 165,070 bytes -> 162,794 bytes;
- new `processing_publish.py`: 2,493 bytes.

The previous processing-core oversized guard was a loose 169,599-byte historical ceiling. Phase 7I ratchets it directly to 162,794 bytes.

Phase 7I publication:
- PR #303 fixed head `d13e23678cf911d7341cae1ed287d1d41e788d17` passed CI 2156 on Ubuntu/Windows/macOS and CodeQL 2137 Actions/Python;
- PR #303 merged as `7c122a1e7f6338f8115620ead4ec45ed52040b01`;
- post-merge CI 2157 and CodeQL 2138 both passed.

## Phase 7J crop-plan formatting ownership
Phase 7J extracts four leaf helpers used by the crop/illustration plan domain:
- `entry_crop_piece_filename(...)`;
- `_normalized_crop_name(...)`;
- `polygon_display_name(...)`;
- `page_crop_plan_dict(...)`.

They move to `crop_plan_formatting.py`. The new module depends only on text normalization, `SOURCE_COORDINATE_SPACE`, and `PolygonRegion`; `EntryCropPiecePlan`/`PageCropPlan` are type-only imports guarded by `TYPE_CHECKING`, so there is no runtime cycle.

`processing_core.py` imports and re-exports all four names. The actual crop planner, polygon geometry, `_stage_page_crop_plan(...)`, and file publishing remain core-owned. Because each extracted helper is a leaf and core callers continue to resolve the imported name from core globals, the historical `processing` module-class assignment proxy can still override the core alias without being bypassed by nested calls in the new module.

Focused tests cover:
- core/new-owner object identity;
- crop filename, NFKC/P-suffix normalization, and polygon display-name contracts;
- persisted crop-plan schema including canonical `source_image_pixels` coordinates;
- public-facade assignment mirroring for `page_crop_plan_dict`.

The production sizes move from:
- `processing_core.py`: 162,794 bytes -> 160,934 bytes;
- new `crop_plan_formatting.py`: 2,335 bytes.

The architecture guard ratchets `processing_core.py` to 160,934 bytes.

## Recommended next slice — Phase 7K
After Phase 7J validation, continue only with another processing-core leaf or one-way formatting/file helper. Do not extract polygon/crop helper clusters whose internal cross-calls would shift lookup from core globals into a new module and silently weaken the retained facade monkeypatch contract. If no similarly clean seam remains, switch oversized-owner inventory rather than forcing the processing core apart.

## Standing continuation authorization
The user has authorized faster continuous progression through confirmed-safe refactor slices without stopping for a checkpoint after every small change. Phase 6 is complete; Phase 7 follows the same bounded-slice rule.

Continue across related low-risk changes once contracts and focused tests are clear. Use checkpoints at phase milestones, material compatibility-boundary changes, plan changes, merge/finalization boundaries, or when recovery state would otherwise become ambiguous.

Stop production writes for unexplained behavior/test/CI failure, public/file-format compatibility uncertainty, concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
