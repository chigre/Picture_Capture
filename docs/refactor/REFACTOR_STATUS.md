# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 12 — bounded ownership cleanup is underway. Phase 12E is complete: the effective Layout diagnostic role theme and summary-extension order are now statically owned by the visualization layer, and GUI bootstrap no longer mutates the summary formatter.**

Phase 12E is merged on `main@a1016a8aa8ef3fd50ff3c50b1e8433db9cd5122b`. Phase 12D remains complete on `main@762e2bc22eb2780549fad097b778f2bc303105e0`, Phase 12C remains complete on `main@3632ff4bce26eafec28cf3eebd2e57b7f36c7870`, Phase 12B remains complete on `main@037922b0dc874730f14cb3eaefca7672776596f4`, Phase 12A remains complete on `main@0f37f14f2c428dd5d28a903cb2a72dd63b291a06`, and Phase 11 remains closed on `main@0d73836c6ecb64bab54a653ac0f6ca8a54d7c79f`. Phase 4 controller decomposition and Phase 5 runtime-patch cleanup also remain closed: all production `*_runtime.py` modules are gone and the zero-runtime-debt architecture ratchet remains active.

The Phase 8 full OCR cold/warm benchmark gate remains open and must not be replaced by unmeasured micro-optimization. Phase 9 facade compatibility remains an intentional public boundary. The OCR-boundary process-global runner bridge remains a real debt candidate, but its current call chain reaches the oversized mature parser core and is not yet approved as a bounded production write.

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

Phase 7J publication:
- PR #304 fixed head `8f586157ddcca6975f19d51d3468dd18d5feb022` passed CI 2158 on Ubuntu/Windows/macOS and CodeQL 2139 Actions/Python;
- PR #304 merged as `de1d55a1514e86bfddf75912a305df3a3cadec2e`;
- post-merge CI 2159 and CodeQL 2140 both passed.

## Phase 7K OCR text I/O ownership
Phase 7K extracts four leaf helpers that own OCR cleanup rules and the legacy `.OCRed` text format:
- `load_replace_rules(...)`;
- `process_ocr_text(...)`;
- `export_ocred(...)`;
- `import_ocred(...)`.

They move to `ocr_text_io.py`, which depends only on `Path`, regular expressions, and the shared `read_noncomment_lines(...)` helper. The four functions do not call each other, so moving them does not shift nested lookup away from `processing_core`.

`processing_core.py` imports and re-exports all four names. Existing CLI and UI controllers continue to import them through the historical `processing` facade. Core OCR routines continue to resolve `process_ocr_text` through the core global alias, so public assignment mirroring remains effective.

The `.OCRed` persistence contract remains unchanged: each line is `NNN|`text`, with UTF-8 writing and UTF-8-SIG reading compatibility.

Focused tests cover:
- core/public/new-owner object identity;
- replacement-rule parsing and literal/regex cleanup behavior;
- exact legacy backtick-delimited `.OCRed` roundtrip;
- public-facade assignment mirroring for `process_ocr_text`.

The production sizes move from:
- `processing_core.py`: 160,934 bytes -> 159,680 bytes;
- new `ocr_text_io.py`: 1,583 bytes.

The architecture guard ratchets `processing_core.py` to 159,680 bytes.

Phase 7K publication:
- PR #305 fixed head `24b563a69420867a8c536791b5fc038b651076e4` passed CI 2160 on Ubuntu/Windows/macOS and CodeQL 2141 Actions/Python;
- PR #305 merged as `ad777f84738d71acff8e3af4775d89c2649ac97d`;
- post-merge CI 2161 and CodeQL 2142 both passed.

## Phase 7L crop logging ownership
Phase 7L extracts the two leaf logging helpers used by crop and illustration workflows:
- `append_crop_log(...)`;
- `append_illustration_crop_log(...)`.

They move to `crop_logging.py`, which depends only on `Path`, the project-storage log/QT path helpers, and type-only `CropRecord`/`IllustrationCropEvent` annotations. There is no runtime import back into `processing_core.py`.

`processing_core.py` imports and re-exports both names. The historical `processing.py` explicit forwarders remain unchanged, so CLI, parallel crop coordination, and UI controllers keep their established imports and call sites. Public assignment mirroring still reaches the core aliases.

The ordinary crop log keeps its self-describing `source_image_pixels` header and writes source X/Y/width/height. The illustration crop log keeps the legacy tab-separated `PPPnnn` event line format.

Focused tests cover:
- core/new-owner identity;
- single-header append behavior and source-pixel row formatting;
- illustration-event line formatting;
- public-facade assignment mirroring for `append_crop_log`.

The production sizes move from:
- `processing_core.py`: 159,680 bytes -> 158,561 bytes;
- new `crop_logging.py`: 1,602 bytes.

The architecture guard ratchets `processing_core.py` to 158,561 bytes.

First PR CI caught one extraction-boundary regression: `AUTO_ILLUSTRATION_LABEL_TOKEN` sat immediately after the moved ordinary crop-log function and was accidentally removed with that block. It is detector state, not logging state, so Phase 7L restores it in `processing_core.py` and adds a focused ownership regression to keep it core-owned.

Phase 7L publication:
- first CI run 2162 failed only because that adjacent detector constant had been removed; 1342 tests otherwise passed;
- repaired fixed head `01a4ac7ac165edd3f3b3bd790288d2ae16b6fb5d` passed CI 2166 on Ubuntu/Windows/macOS and CodeQL 2147 Actions/Python;
- PR #306 merged as `e77f878231a62e24b82e0414b168790a620ca96e`;
- post-merge CI 2167 and CodeQL 2148 both passed.

## Phase 7M image-preprocessing data-model ownership
The previously deferred cohesive model extraction is now feasible as one intact file. Phase 7M moves:
- `OutputCanvasInfo`;
- `PreprocessAnalysis`;
- `PREPROCESS_FORMAT`;
- `PREPROCESS_FORMAT_VERSION`;
- `DEFAULT_SAFETY_MARGIN_PX`

into `image_preprocessing_models.py`.

The complete model block is ~979 lines / 43 KB and depends only on `dataclass/asdict` plus the three preprocessing format/default constants. It does not depend on NumPy, PIL, geometry detection, filesystem paths, or the 2,500+ line analysis state machine.

`image_preprocessing.py` imports and re-exports the classes/constants, preserving the historical public import surface. Phase 7M additionally pins both class objects' `__module__` to `picture_capture.image_preprocessing`, so external pickle/debug tooling keeps the historical class module path even though implementation ownership moves.

`image_preprocessing_persistence.py` now imports `PreprocessAnalysis` directly from the model owner for runtime JSON deserialization, eliminating its previous call-time dependency back on the oversized implementation module. `image_preprocessing_reporting.py` points its type-only model imports at the same owner.

Focused tests cover:
- old-module/new-owner object identity;
- persistence/new-owner identity;
- historical class `__module__` values and pickle class roundtrip;
- re-exported format/version/safety constants.

The production sizes move from:
- `image_preprocessing.py`: 204,153 bytes -> 160,734 bytes;
- new `image_preprocessing_models.py`: 43,931 bytes.

The architecture guard ratchets `image_preprocessing.py` directly to 160,734 bytes.

Phase 7M publication:
- PR #307 fixed head `180359bdf561849a0a5eac53f77efec9ecfe7e67` passed CI 2168 on Ubuntu/Windows/macOS and CodeQL 2149 Actions/Python;
- PR #307 merged as `41cd19e5ba6c71b1c3760c775366a0c7cafb8207`;
- post-merge CI 2169 and CodeQL 2150 both passed.

## Phase 7N Paddle headword data-model ownership
Cross-owner inventory selected the pure data-model layer at the top of `paddle_headwords_core.py` rather than any OCR/filter/parser algorithm cluster.

Phase 7N moves five dataclasses into `paddle_headword_models.py`:
- `OCRRecord`;
- `OCRLine`;
- `GrammarTailParse`;
- `HeadwordParse`;
- `HeadwordFilterRule`.

The new module depends only on `dataclass` and `re`; it has no Paddle engine, PIL/NumPy, project profile, parser, evidence-fusion, or runtime-hook dependency.

`paddle_headwords_core.py` imports and re-exports all five classes. The historical public `paddle_headwords` facade therefore continues to expose the same objects through its broad namespace compatibility surface. Direct imports from `paddle_headwords_core` (including evidence fusion) remain valid.

Each class explicitly keeps `__module__ = "picture_capture.paddle_headwords_core"`, preserving the historical pickle/debug module path even though implementation ownership moves. Focused tests require:
- core/new-owner identity;
- public-facade/new-owner identity;
- evidence-fusion direct model identity;
- pickle class roundtrip via the historical core path;
- public-facade assignment mirroring into the core alias.

The actual core file moves from 377,684 bytes -> 375,114 bytes; new `paddle_headword_models.py` is 3,080 bytes. The previous architecture guard was a slightly looser 378,513-byte ceiling, so Phase 7N ratchets it directly to 375,114 bytes.

Phase 7N publication:
- PR #308 fixed head `fe55f2bafdf80ba715181eee3c43593fedf726f5` passed CI 2170 on Ubuntu/Windows/macOS and CodeQL 2151 Actions/Python;
- PR #308 merged as `4a1a8d98ceaa46b4690271aac803fa7dab9b6d67`;
- post-merge CI 2171 and CodeQL 2152 both passed.

## Phase 7O output-canvas geometry ownership
Phase 7O follows the Phase 7N recommendation to avoid forcing Paddle cache/diagnostic internals across their retained core-global compatibility boundary. Cross-owner inventory instead selected the final-canvas geometry builder in `image_preprocessing.py`.

Phase 7O moves:
- `_normalize_canvas_alignment(...)`;
- `output_canvas_info(...)`

into `image_preprocessing_canvas.py`.

The new module depends only on the Phase 7M data models `PreprocessAnalysis` and `OutputCanvasInfo`. It has no NumPy/PIL image processing, project-storage, analysis-state-machine, or filesystem dependency.

`image_preprocessing.py` imports and re-exports both helpers. `processed_image_with_canvas(...)` and `export_diagnostic_json(...)` intentionally remain in the historical module and continue to resolve `output_canvas_info` through that module global. This keeps the larger rendering/export behavior in place and avoids moving algorithm constants into the new owner.

Both extracted callables explicitly keep `__module__ = "picture_capture.image_preprocessing"`, preserving historical pickle/debug paths in addition to the stable import aliases. Focused tests require:
- old-module/new-owner object identity;
- historical callable module path and pickle roundtrip;
- custom-canvas margin/right-bottom alignment geometry;
- invalid alignment normalization to center/top.

The production sizes move from:
- `image_preprocessing.py`: 160,734 bytes -> 157,244 bytes;
- new `image_preprocessing_canvas.py`: 3,986 bytes.

The architecture guard ratchets `image_preprocessing.py` to 157,244 bytes.

Phase 7O publication:
- PR #309 fixed head `489b35cbb88ae82c3f7f4dda9f5ec9c6403661f4` passed CI 2172 on Ubuntu/Windows/macOS and CodeQL 2153 Actions/Python;
- PR #309 merged as `7e1d673c686d9357db56ea1d5a71143945660953`;
- post-merge CI 2173 and CodeQL 2154 both passed.

## Phase 7P Paddle cache-storage implementation ownership
Phase 7P switches back to `paddle_headwords_core.py`, but deliberately avoids direct re-export of a mutually-calling cache helper cluster.

The implementation moves into `paddle_cache_storage.py`:
- atomic text/JSON publishing;
- candidate compaction;
- compact OCR cache payload construction;
- regenerable sidecar path generation;
- one-file cache compaction/sidecar cleanup.

Historical names remain defined as wrappers in `paddle_headwords_core.py`:
- `_atomic_write_text(...)`;
- `_atomic_write_json(...)`;
- `_compact_cached_candidate(...)`;
- `compact_ocr_cache_payload(...)`;
- `_regenerable_sidecars(...)`;
- `compact_ocr_cache_file(...)`.

Each wrapper passes the **current core global dependencies** into the implementation at call time. For example, `_atomic_write_json` passes the current `_atomic_write_text`, and `compact_ocr_cache_file` passes the current `compact_ocr_cache_payload` and `_atomic_write_json`. This preserves the Phase 6 public facade assignment-mirroring contract: monkeypatching a historical helper on `paddle_headwords` still affects nested cache operations.

The implementation module has no import back into `paddle_headwords_core`, so the ownership direction is one-way. Existing concurrency/source-contract markers in the public facade remain untouched.

Focused tests require:
- historical wrapper `__module__` paths remain `picture_capture.paddle_headwords_core`;
- monkeypatched public `_atomic_write_text` is used by core `_atomic_write_json`;
- monkeypatched public `_compact_cached_candidate` is used by `compact_ocr_cache_payload`;
- monkeypatched public payload/json hooks are used by `compact_ocr_cache_file`.

The production sizes move from:
- `paddle_headwords_core.py`: 375,114 bytes -> 372,228 bytes;
- new `paddle_cache_storage.py`: 4,617 bytes.

The architecture guard ratchets `paddle_headwords_core.py` to 372,228 bytes.

Phase 7P publication:
- PR #310 fixed head `ccf014a28cc3e61acfed76b0978d1a110e7f5ae4` passed CI 2174 on Ubuntu/Windows/macOS and CodeQL 2155 Actions/Python;
- PR #310 merged as `7cfa16c6e0a37737009d5182aca49c28302462b1`;
- post-merge CI 2175 and CodeQL 2156 both passed.

## Phase 7Q Paddle diagnostic formatting ownership
Phase 7Q applies the same core-wrapper pattern to the strict OCR diagnostic/report formatting layer.

The implementation moves into `paddle_diagnostic_formatting.py`:
- TSV cell sanitization;
- candidate reason construction;
- strict 12-column candidate rows;
- strict 12-column page diagnostics;
- strict 27-column Paddle/Tesseract comparison;
- strict 13-column engine-long table;
- strict 12-column fusion table;
- strict 16-column issue table.

Historical formatter names remain wrappers in `paddle_headwords_core.py`:
- `_tsv_clean(...)`;
- `_candidate_reason(...)`;
- `_candidate_tsv_row(...)`;
- `_diagnostic_text(...)`;
- `_comparison_text(...)`;
- `_engines_long_text(...)`;
- `_fusion_text(...)`;
- `_issues_text(...)`.

The schema header constants remain core-owned:
- `_DIAGNOSTIC_HEADER`;
- `_COMPARISON_HEADER`;
- `_ENGINES_LONG_HEADER`;
- `_FUSION_HEADER`;
- `_ISSUES_HEADER`.

Each wrapper passes current core globals into the implementation at call time. `_candidate_tsv_row` receives the current cleaner/reason-builder; `_diagnostic_text` receives the current header, `_candidate_rows`, candidate-row formatter, and cleaner; the other report wrappers receive their current header and cleaner. Public facade assignments therefore continue to affect nested formatting rather than being bypassed by module-local bindings.

The new implementation module has no runtime import back into the core. Existing docs/file-format contracts remain unchanged: 12/27/13/12/16 columns respectively.

Focused tests require:
- historical wrapper `__module__` paths remain `picture_capture.paddle_headwords_core`;
- monkeypatched core candidate-row/candidate-list hooks are used by diagnostics;
- monkeypatched comparison header and TSV cleaner are used dynamically;
- exact column counts for diagnostic, comparison, engine-long, fusion, and issue tables.

The production sizes move from:
- `paddle_headwords_core.py`: 372,228 bytes -> 364,070 bytes;
- new `paddle_diagnostic_formatting.py`: 10,685 bytes.

The architecture guard ratchets `paddle_headwords_core.py` to 364,070 bytes.

Phase 7Q publication:
- PR #311 fixed head `7da800fc94872cc2e12034afc1ed1bbc7a4f1feb` passed CI 2176 on Ubuntu/Windows/macOS and CodeQL 2157 Actions/Python;
- PR #311 merged as `1e3cb5fcf4b2f43da72bad14c69f5adb96ba33e6`;
- post-merge CI 2177 and CodeQL 2158 both passed.

## Phase 7R preprocessing diagnostics/reporting ownership
Cross-owner inventory showed that the remaining oversized files are now dominated by genuine GUI classes or algorithm state machines. Rather than continue micro-extracting Paddle or splitting Tk state, Phase 7R selects a larger cohesive preprocessing reporting boundary.

Phase 7R introduces `image_preprocessing_constants.py` for the locally owned preprocessing thresholds/gains previously defined inside `image_preprocessing.py`. The historical module imports and re-exports every constant, so existing imports remain valid.

The 165-line diagnostic JSON implementation moves into the existing `image_preprocessing_reporting.py` owner as `_export_diagnostic_json_impl(...)`. `image_preprocessing.py` keeps the historical public `export_diagnostic_json(...)` callable as a thin wrapper. The wrapper passes the **current module-global** `output_canvas_info` callback into the reporting implementation, preserving any test/debug monkeypatch on that historical hook.

The reporting owner imports diagnostic constants from their authoritative modules and has no runtime import back into `image_preprocessing.py`. Existing JSON schema, effective-settings payload, algorithm-constant payload, source/canvas geometry fields, UTF-8 formatting, and atomic temp-file replacement remain unchanged.

Focused tests require:
- old-module/new-constants object identity for all locally owned preprocessing constants;
- `export_diagnostic_json.__module__ == "picture_capture.image_preprocessing"`;
- monkeypatching `image_preprocessing.output_canvas_info` still affects diagnostic export;
- the reporting owner has no runtime back-import into the oversized implementation module.

The production sizes move from:
- `image_preprocessing.py`: 157,244 bytes -> 150,818 bytes;
- `image_preprocessing_reporting.py`: 30,243 bytes after Phase 7A -> 38,968 bytes;
- new `image_preprocessing_constants.py`: 1,028 bytes.

The architecture guard ratchets `image_preprocessing.py` to 150,818 bytes.

Phase 7R publication:
- PR #312 fixed head `5423f687b1ba2abaefe19836831f37e3fb35340c` passed CI 2178 on Ubuntu/Windows/macOS and CodeQL 2159 Actions/Python;
- PR #312 merged as `47fcfbd539b1498abb26f32be3f885a3e33acd42`;
- post-merge CI 2179 and CodeQL 2160 both passed.

## Phase 7S final oversized-owner inventory and completion boundary
A final read-only inventory re-evaluated every remaining oversized production owner after Phase 7R.

Current production sizes:
- `app.py`: 784,737 bytes;
- `paddle_headwords_core.py`: 364,070 bytes;
- `profile_setup.py`: 174,009 bytes;
- `processing_core.py`: 158,561 bytes;
- `image_preprocessing.py`: 150,818 bytes.

The remaining size is now dominated by genuine stateful/algorithmic owners rather than detachable support responsibilities:
- `profile_setup.py`: 3,847 lines, of which ~3,604 lines belong to the single stateful `ProjectProfileWizard` GUI class;
- `image_preprocessing.py`: `analyze_preprocess_page(...)` alone occupies ~2,565 lines; the remaining larger helpers are the same geometry/orthogonal-correction algorithm chain;
- `processing_core.py`: the remaining large functions are marker detection/recovery/fusion, crop planning/splitting, OCR recovery, and illustration detection algorithms with substantial cross-calls;
- `paddle_headwords_core.py`: the remaining large functions are parser/filter/arbitration/separator/CJK recovery and engine-pipeline algorithms; `filter_headword_records(...)` alone remains >1,100 lines;
- `app.py`: the safe GUI-independent helper seams have been extracted; the remaining body is dominated by Tk classes, mutable application state, worker/result boundaries, and runtime extension slots.

Phase 7S therefore finds **no remaining larger one-way ownership seam** that can be extracted without crossing at least one of these boundaries:
- mutable GUI/class state;
- algorithm state-machine cohesion;
- mutually calling geometry/detection/parser clusters;
- historical core-global monkeypatch lookup semantics;
- worker/pickle/module-path compatibility.

Phase 7 is consequently **closed**. Further line-count reduction is no longer an optimization target by itself. Existing oversized-module ratchets remain in force and must not be loosened.

Phase 7S publication:
- PR #313 fixed head `c80d05122f752ecef89f99417d875f2897905db6` passed CI 2180 on Ubuntu/Windows/macOS and PR security analysis 2161;
- PR #313 merged as `a3d9e86a637a37da7e0dc97fffaa863d1178f524`;
- post-merge CI 2181 and security analysis 2162 both passed.

## Phase 8A detection runtime baseline
Initial runtime inventory found no existing `perf_counter()`-based wall-clock profiling in production or benchmark code. Existing performance mechanisms are primarily:
- OCR/cache paths in detection and review workflows;
- process pools for single-line/unlined export;
- a thread pool for network lexical lookup;
- limited `lru_cache` use for reference sorting and runtime Paddle-device resolution.

The existing `scripts/detection_benchmark.py` is therefore the safest baseline harness: it already opens project pages, runs selected detection modes, compares against PDIC ground truth, supports OCR cache paths/force-refresh, and does not mutate project data.

Phase 8A adds timing **only to the benchmark path**:
- project-open wall time;
- per-page image decode/convert wall time;
- per-page page-section/ground-truth I/O wall time;
- per-mode `detect_entries(...)` wall time, including failed attempts;
- per-page pairwise-comparison wall time;
- per-page total wall time;
- benchmark total wall time.

Per-mode timing summaries report sample count, total, mean, median, p95, min, and max. Page-total timing receives the same summary. All values are milliseconds and use `time.perf_counter()`.

The existing benchmark format identifier remains `picture-capture-detection-benchmark-v1`; every existing accuracy/count field is preserved. Timing is added only as new nested `timing_ms` fields, so current consumers remain compatible.

A small `performance_metrics.py` owner provides deterministic timing aggregation and is not imported by production execution paths. Focused tests cover empty/non-finite timing samples, deterministic median/p95 behavior, and the presence of every benchmark stage timer.

Phase 8A publication:
- PR #314 fixed head `ae45ce60ad9201e31d9ada66b9a83a082f09b743` passed CI 2182 on Ubuntu/Windows/macOS and PR security analysis 2163;
- PR #314 merged as `c166f8890173be03297d4b3e6277597a4e19110e`;
- post-merge CI 2183 and security analysis 2164 both passed.

## Phase 8B cold-vs-warm cache timing
Phase 8B extends only the benchmark CLI with `--timing-repeats N`. The default remains `1`, so existing benchmark behavior is unchanged.

For each page/mode:
- the first detection call is exactly the formal benchmark result used for marker counts, ground-truth comparison, and pairwise comparison;
- only after that first call succeeds are optional timing repeats executed;
- repeated calls reuse the same temporary cache path;
- repeated calls always use `force_paddle_refresh=False`, even when the first run used `--force-ocr`, so they measure the actual warm-cache path;
- repeat failures are recorded but do not replace or alter the formal first-run result.

The existing per-mode `timing_ms` field continues to mean **first-run wall time**. New fields add:
- `timing_runs_ms` for first + repeat attempts;
- `repeat_timing_ms` summary for repeat attempts only;
- `repeat_errors`;
- cache metadata: enabled, existed-before-first, exists-after-first, first-run force-refresh, repeat force-refresh.

Top-level `timing_repeats` records the requested repeat count. Mode summaries also report aggregated `repeat_timing_ms`, while all existing accuracy/count fields and the v1 format identifier remain unchanged.

Focused regressions require:
- default repeat count remains one;
- repeat mode validates `N >= 1`;
- warm repeats use `force_paddle_refresh=False`;
- the formal `detected[mode]`/ground-truth result is established from the first call before the repeat loop and is never overwritten by repeats.

Phase 8B publication:
- PR #315 fixed head `3beb76f5b3e3491edd95f30d31f90db3d370f19f` passed CI 2184 on Ubuntu/Windows/macOS and PR security analysis 2165;
- PR #315 merged as `8e47a1330682af0e387ffae399e346480b9a4518`;
- post-merge CI 2185 and security analysis 2166 both passed.

## Phase 8C warm CPU profiling
Phase 8C adds an **opt-in benchmark-only** `--warm-cpu-profile-dir PATH` mode.

The existing `benchmark(...)` timing function remains untouched by profiler execution. `main()` first completes the full Phase 8A/8B wall-clock benchmark and only then, when explicitly requested, invokes a separate `warm_cpu_profiles(...)` pass.

For each selected page/mode, the profile pass:
- opens the page and loads page sections outside the profiler;
- executes one unprofiled warm-up call;
- reuses the same temporary cache path;
- profiles one additional detection call with `force_paddle_refresh=False`;
- writes a binary `.prof` file and a human-readable cumulative top-50 `.txt` summary;
- records profile/summary paths and any profiling error in the benchmark JSON manifest.

The profile run is **not** a formal accuracy result and is **not** included in `timing_ms`, `timing_runs_ms`, or repeat timing summaries. This keeps cProfile overhead from contaminating the wall-clock baseline.

No production module imports cProfile or pstats; profiling remains isolated to `scripts/detection_benchmark.py`.

Focused regression requires:
- `warm_cpu_profiles(...)` is defined outside and after `benchmark(...)`;
- `benchmark(...)` never calls the profiler;
- the CLI invokes it only when `--warm-cpu-profile-dir` is supplied;
- profiled calls use `force_paddle_refresh=False`;
- profile output includes both `.prof` and cumulative top-50 text output;
- the manifest explicitly records that profiled calls are not timing samples.

Phase 8C publication:
- PR #316 fixed head `6dd27b49d3064ca9aa86d8e78c8149641839c542` passed CI 2187;
- PR security analysis run 2168 passed;
- PR #316 merged as `404c13b61b78af75dce974e4b7854dd983052b82`;
- post-merge CI 2188 and main security analysis 2169 both passed.
- the separate code-scanning AI findings workflow failed for the same external quota reason seen in earlier phases; it did not represent a code/test/security-scan failure.

## Phase 8D representative-project measurement gate
Repository, Library, and GitHub issue/PR attachment inventory found no accessible representative Picture Capture project containing the real scan pages, project settings, `.pdic` ground truth, and OCR diagnostics needed for a trustworthy runtime decision.

The repository does contain:
- four small headword example crops;
- layout screenshots;
- documentation recording real OCR work on pages 0055-0070, including repeated investigation of pages 55-60.

Those example images are not a representative full-page workload and must not be used to choose a production optimization.

The standard Phase 8D protocol is now documented in `docs/refactor/PHASE8D_BENCHMARK_RUNBOOK.md`. The preferred minimum run is:
- pages 55-60;
- modes `left_edge,paddleocr,combined`;
- first OCR pass forced cold with `--force-ocr`;
- `--timing-repeats 4`, yielding three warm repeats per page/mode;
- separate warm cProfile output via `--warm-cpu-profile-dir`.

No production optimization is authorized from source inspection alone. The first production change must be selected from the benchmark JSON plus warm-profile outputs and must preserve formal first-run correctness/ground-truth fields.

## Phase 8E representative-page execution and duplicate analysis reuse
A recovery pass found the real scanned pages `0055.png` through `0060.png` in the authorized Library and materialized them only into the private execution environment. They were **not** uploaded to the public repository.

The environment did not contain the matching project settings, `.pdic` ground truth, headword-rule sidecars, OCR cache, installed Picture Capture package, or Paddle/PaddleOCR runtime. Network-isolated container execution also could not clone/install the repository from GitHub. Therefore the standard Phase 8D `detection_benchmark.py` cold/warm OCR command was **not** represented as completed.

Available representative-page component measurements were still used to reject or authorize only narrowly matching work:
- Pillow decode + RGB conversion across pages 55-60: median about **30.6 ms/page**;
- grayscale + ndarray + threshold-mask surrogate across the same pages: median about **3.0 ms/page**;
- an identical-cache-write avoidance microbenchmark did not show stable benefit and was rejected rather than shipped.

Source verification then found one exact duplicate computation in the policy-aware layout path. `infer_dictionary_page_layout(...)` already owned the canonical `page_ink`, but `finalize_layout_column_drift(...)` immediately repeated `_analysis_page -> grayscale -> analysis_ink_mask` solely to remeasure the same layout rows. Historical Phase 5S notes had explicitly deferred this duplicate pass rather than changing it during ownership migration.

Phase 8E therefore:
- adds an optional existing `page_ink` argument to `finalize_layout_column_drift(...)`;
- passes the already-computed mask from `dictionary_page_layout_policy.py`;
- preserves the complete historical fallback when callers do not supply a mask;
- adds regression coverage proving the reuse path does not call `_analysis_page` or `analysis_ink_mask`, while the existing fallback test still exercises the old path;
- changes no OCR threshold, layout decision, geometry, file format, cache format, compatibility facade, or worker semantics.

Phase 8E publication:
- PR #318 fixed head `fe12e87f9dd10fd0e7aba399d4db0f6d2d9253e6`;
- exact production/test diff: 3 files;
- PR CI 2191 passed on Ubuntu/Windows/macOS, including pytest, GUI smoke, compatibility runner, compile, F821, and wheel build;
- PR CodeQL 2172 passed; Advanced Security 1893 passed;
- PR #318 merged as `d629b714440c3e63c985ba46e18aae40aaadbcfc`;
- post-merge CI 2192 passed; post-merge CodeQL 2173 passed.

## Phase 8F real-page left-edge profiling and shared denoise integral reuse
The representative-page gate was partially unblocked without weakening the earlier OCR boundary.

The Library still contains only the real scan images `0055.png` through `0060.png`; matching project settings, headword rules, `.pdic` files, PaddleOCR caches/diagnostics, and a Paddle/PaddleOCR runtime are still unavailable. However, inspection of `scripts/detection_benchmark.py` and `ProjectState.open(...)` confirmed that:
- `.pdic` ground truth is optional for timing/profile execution;
- an image-only project can open with default `AppSettings()`;
- `left_edge` does not require PaddleOCR when selected explicitly.

To move the already-CI-validated package into the network-isolated execution container, temporary draft PR #320 added only a CI wheel upload step. Its Ubuntu job produced the current package artifact; PR #320 was then closed **without merge**. The six real scan pages were never uploaded to GitHub.

A four-call-per-page `left_edge` run plus one extra warmed cProfile call per page found:
- image decode median: about **29 ms/page**;
- initial baseline first-call median: about **1.73 s/page**;
- baseline same-machine warm median: **145.9 ms/page**;
- six warmed profile calls: about **1.02 s** total;
- `build_analysis_image`: about **0.764 s** total;
- `adaptive_speck_remove_mask`: about **0.659 s** total;
- five separate local-window integral calculations: about **0.625 s** total, with 60 NumPy `cumsum` calls taking about **0.436 s**.

The adaptive cleaner needed five local-support windows (5x5, 11x11, 13x1, 1x13, and 17x17), but the historical implementation rebuilt a separate padded integral image for every window. A prototype reused one max-padded integral image for all five windows.

Equivalence validation before production change:
- all five window sums matched the historical `_box_sum(...)` pixel-for-pixel on randomized masks;
- the same five windows matched pixel-for-pixel on every real page 0055-0060;
- the five-window component median fell from about **88.2 ms** to **30.1 ms** (~2.93x).

Phase 8F therefore:
- keeps the historical single-window `_box_sum(...)` helper unchanged;
- adds a private multi-window helper that builds one integral image and derives all five sums by slicing;
- changes no denoise threshold, strength rule, geometry, OCR behavior, setting, cache format, file format, or compatibility surface;
- adds focused exact-equivalence regression coverage.

End-to-end representative-page validation:
- baseline same-machine warm median: **145.9 ms/page**;
- Phase 8F warm median: **88.9 ms/page**, about **39% lower**;
- every page's complete `(word, x, y)` marker list matched the baseline exactly.

Post-change warmed profiling moved the bottleneck:
- six warmed calls: about **0.623 s** total;
- shared integral calculation: about **0.253 s** total;
- separator-Y refinement: about **0.107 s** total;
- generic analysis ink construction: about **0.088 s** total;
- image fingerprinting: about **0.068 s** total.

No single remaining non-OCR hotspot is large enough to justify an immediate follow-on rewrite without a new equivalence microbenchmark.

Phase 8F publication:
- PR #321 fixed head `1aa7a2068e24b5bb15a320a994e1d18ec7572495`;
- production/test diff: 2 files;
- PR CI 2196 passed on Ubuntu/Windows/macOS;
- PR CodeQL 2177 and Advanced Security 1896 passed;
- PR #321 merged as `156547615dac92234c438eedc9029860e866696f`;
- post-merge CI 2197 and CodeQL 2178 passed.

## Phase 8G full-page memory conversion cleanup
Post-Phase-8F profiling showed that the remaining non-OCR cost was already much more distributed. Several candidate optimizations were therefore measured and rejected before production writes:
- separator-Y refinement was about 18 ms/page, but its adapter re-analysis path did not repeat the Phase 8F denoise and changing its image/transform lifecycle would have widened architectural risk;
- Layout Core's content fingerprint was about 11-12 ms/page, but weakening the BLAKE2 content key would reduce stale-cache protection and was rejected;
- removing only the redundant `_allowed_entries(...)` normalization saved only about **1.8 ms/page** in robust paired testing and was too small to ship alone.

A second exact-equivalence candidate was found in `_generic_analysis_ink(...)`. The historical expression widened two full-page grayscale arrays to signed int16 only to evaluate:
`gray <= 150 or (gray <= 205 and gray + 20 <= local)`.
The equivalent uint8 predicate adds an explicit `local >= 20` guard and compares `gray <= local - 20`, avoiding underflow while preserving the historical result.

Equivalence and component measurements:
- randomized full-range uint8 grayscale arrays matched the historical int16 predicate pixel-for-pixel;
- all real pages 0055-0060 matched pixel-for-pixel;
- generic-ink helper median fell from about **14.75 ms** to **12.14 ms**;
- the already-normalized-source reuse in `_allowed_entries(...)` was combined with this change because both remove redundant full-page memory conversions.

Paired representative-page end-to-end validation on warmed `left_edge` calls:
- baseline median: **91.63 ms/page**;
- Phase 8G candidate median: **87.80 ms/page**;
- improvement: about **3.83 ms/page (4.2%)**;
- every one of pages 0055-0060 improved in the paired test;
- complete `(word, x, y)` marker output matched exactly on every page.

Phase 8G therefore:
- stops `_allowed_entries(...)` from making a second RGB page copy when all private callers already pass the normalized source and the filter only needs page size;
- keeps generic local-contrast evaluation in uint8 and reuses the grayscale ndarray already owned by `build_analysis_image(...)`;
- changes no threshold, geometry, OCR behavior, Layout cache key, file format, cache format, or compatibility behavior;
- adds regression coverage against the historical int16 formula and a no-renormalization contract test.

Phase 8G publication:
- PR #323 fixed head `0ef9877599b587e31b71cdfb3809abe1ec705086`;
- production/test diff: 3 files;
- PR CI 2200 passed on Ubuntu/Windows/macOS;
- PR CodeQL 2181 and Advanced Security 1898 passed;
- PR #323 merged as `d0d8413c51dd8395304c0102904d166e804fc113`;
- post-merge CI 2201 and CodeQL 2182 passed.

Post-Phase-8G warmed profiling across the six real pages measured about **0.587 s** total. The largest remaining items were approximately:
- shared adaptive-denoise `_box_sums`: 0.235 s total (~39 ms/page);
- separator-Y refinement: 0.109 s total (~18 ms/page);
- Layout Core image fingerprint: 0.073 s total (~12 ms/page);
- generic analysis ink: 0.078 s total (~13 ms/page);
- BoxBlur: 0.068 s total (~11 ms/page).

## Phase 8H candidate rejection
The remaining largest non-OCR hotspot, `_box_sums`, was tested with a mathematically equivalent preallocated/in-place arithmetic implementation intended to reduce temporary int32 arrays.

The prototype matched the existing output exactly on randomized masks and all six real pages, but the component median improved only from about **31.42 ms** to **31.12 ms** (~0.9%), with several real pages becoming slightly slower. The candidate was rejected and no production code was written.

This result, together with the distributed post-8G profile, is the stopping point for opportunistic non-OCR micro-optimization. Further changes in this path require a new representative-page candidate with a materially larger and stable end-to-end gain, not merely source-level plausibility.

## Phase 8D representative Paddle/combined cold-warm benchmark completed
The previously blocked OCR measurement gate is now complete on the real scan pages `0055.png` through `0060.png`.

The isolated benchmark environment was reconstructed without uploading any scan page to GitHub:
- temporary PR #325 installed the repository-locked Linux Python 3.13 `ocr-cpu` profile, initialized PaddleOCR 3.7.0 / PaddlePaddle 3.3.0 with cached PP-OCRv6 medium detection and recognition models, split the runtime into transport-sized artifacts, and was closed without merge;
- temporary PR #326 exported the then-current `main` wheel for the isolated container and was closed without merge;
- the real pages remained only in the authorized private execution environment;
- matching `.pdic` ground truth was still unavailable, so this run is a timing/cache/pairwise measurement and **not** an accuracy-validation result.

A one-page Paddle smoke on page 0055 completed successfully in about **167.1 s**, produced 21 OCR headword markers, and wrote a valid cache.

The full six-page benchmark then completed for both `paddleocr` and `combined`, using a forced-refresh first call per page/mode and two cache-reusing repeat calls:
- PaddleOCR cold: n=6, median **163.815 s/page**, mean 163.938 s/page, range 162.342-165.795 s;
- PaddleOCR warm cache: n=12, median **1.442 s/page**, mean 1.465 s/page, range 1.328-1.745 s;
- Combined cold: n=6, median **162.659 s/page**, mean 161.638 s/page, range 158.103-163.987 s;
- Combined warm cache: n=12, median **1.905 s/page**, mean 1.914 s/page, range 1.699-2.190 s.

The cold result shows that CPU PP-OCRv6 inference dominates the forced-refresh path by roughly two orders of magnitude over warm cache execution. Source-level orchestration micro-optimization must therefore be evaluated primarily against the warm-cache path; it should not be presented as materially reducing the ~164 s/page cold CPU model cost.

Pairwise marker comparison showed that Paddle markers were mostly a subset of the much denser Combined result on these pages, with median matched-marker vertical delta of about 1 px. Because no `.pdic` files were available, these pairwise differences are descriptive only and do not establish which mode is more accurate.

Warm cProfile runs on all six pages/modes identified page-understanding shape consensus as a major warm-path hotspot. The historical `_shape_consensus(...)` called `_patch_similarity(...)` for O(N^2) patch pairs, and every pair redundantly repeated PIL resize, float32 centering, and norm computation on patches already processed many times.

## Phase 8I shape-consensus signature precomputation
A candidate implementation preserved the historical 12x24 nearest-neighbor float32 signature, mean centering, L2 norm, pairwise cosine formula, and **0.52** threshold, but prepared each patch exactly once per cluster.

Validation proceeded in progressively stricter layers:
- randomized clusters matched the historical implementation exactly;
- six-page end-to-end experiments produced identical complete `(word, x, y)` marker lists, although page-level timing comparisons were recognized as cache-order confounded and were **not** used to claim the speedup;
- a cache-independent function benchmark captured **85 actual shape-consensus clusters** from real pages 0055-0060, with cluster sizes from 1 to 66 patches;
- the new and historical functions matched exactly on all 85/85 real clusters;
- sum of per-cluster median timings fell from about **5301.9 ms** to **135.6 ms**, about **39.1x** for the measured function work;
- the largest measured 66-patch cluster fell from about **209.9 ms** to about **4.2 ms**.

Phase 8I therefore:
- adds a private historical-equivalent shape signature helper;
- prepares every patch once per cluster;
- preserves the historical pairwise cosine comparison rather than introducing matrix/vector approximation;
- changes no threshold, layout semantics, OCR behavior, file/cache format, or compatibility surface;
- adds exact regression tests against the historical `_patch_similarity(...)` implementation, including randomized and degenerate patches.

Phase 8I publication:
- PR #327 fixed head `70a4d11537a32b1f338ff43738e29407e46a8273`;
- production/test diff: 2 files;
- PR CI 2207 and CodeQL 2188 passed;
- PR #327 merged as `7d4ea8af6f7e6ac35095d1546b6c14c05d544fe2`;
- post-merge CI 2208 and CodeQL 2189 passed.

## Phase 8J VB fallback brightness caching
A fresh post-Phase-8I warm-cache profile was run on real pages 0055-0060 for both `paddleocr` and `combined`. The profile confirmed that shape-consensus cost had moved out of the dominant position and exposed several smaller hotspots.

One candidate, `ordinary_visual._components(...)`, looked promising in isolation:
- exact component output matched on all 12 representative real masks;
- function-level aggregate time improved from about **642 ms** to **431 ms** (~1.49x).

However, a paired end-to-end warm-cache check did **not** show a production benefit; the first stable Paddle sample on page 0055 became slower (about **542 ms -> 647 ms**) while output remained exact. The candidate was rejected. Function-level speedup alone is not sufficient when the complete detection path regresses.

The next measured hotspot was legacy VB separator fallback. Historical `_legacy_find_separator_y(...)` repeatedly called `_legacy_row_brightness_1000(...)` for the same fixed horizontal span while the threshold descended from 999 toward 700. The same rows could be summed hundreds of times per candidate.

A lazy cache prototype was validated directly against the legacy ordinary detector on the six real pages:
- **737 actual separator calls** captured;
- old and cached implementations returned identical separator values and metadata for **737/737** calls;
- 428 calls exited through the historical `vb_full_white` fast path;
- 309 calls used `vb_brightness_fallback`;
- historical total separator time was about **585 ms**;
- lazy cached-row total was about **79 ms** (~**7.4x** less function work);
- median individual call was about **0.080 ms -> 0.074 ms**;
- an earlier eager-precompute version was rejected because it penalized the cheap full-white path.

Phase 8J therefore:
- leaves the historical method-1 full-white search unchanged;
- computes fallback row brightness only after method 1 fails;
- computes each possible row's historical 0..1000 score once for the fixed candidate span;
- reuses those exact scores while threshold descends;
- changes no threshold, geometry, row-step behavior, OCR logic, cache/file format, or compatibility surface.

The first implementation placed the new batching logic inline in the protected oversized `processing_core.py`. Functional tests passed, but the architecture guard correctly rejected growth of the legacy module. The implementation was consequently extracted into the new focused module `ordinary_vb_brightness.py`, and the integration in `processing_core.py` was compacted until the legacy core was smaller than the pre-Phase-8J main version. This is an architecture constraint, not a waived baseline.

Phase 8J publication:
- PR #329 final fixed head `aaf27bf887bfaf49f2471c7d9b2df4b70a2097d3`;
- final production/test diff: one new helper module, a compact legacy-core integration, and focused regression coverage;
- PR CI 2214 passed on Ubuntu/Windows/macOS;
- PR CodeQL 2196 passed;
- PR #329 merged as `71a9b9ee4b45074685ded5c74d58674a465618fa`;
- post-merge CI 2215 and CodeQL 2197 passed.

## Phase 8K reuse fusion grayscale for separator scoring
The post-Phase-8J warm path exposed another exact duplicate full-page conversion in Combined fusion. During one fusion call, `_prefer_ocr_separator_position(...)` may evaluate many ordinary/OCR marker pairs. Each `_separator_whitespace_score(...)` call historically re-normalized the same source image to RGB and then rebuilt the same full-page grayscale array even though only small local ROIs differ between marker candidates.

The safe optimization boundary was one fusion call: build the grayscale image once, pass that exact ndarray to every separator score, and retain the historical self-contained path when no precomputed grayscale image is supplied.

Representative validation on real page 0055:
- **40 actual separator-score calls** captured from the warmed Combined path;
- historical and precomputed-gray scores matched exactly for **40/40** calls;
- historical 40-call median aggregate: about **137.8 ms**;
- reused-gray aggregate: about **2.81 ms**;
- measured score-path work: about **49x faster**, eliminating roughly **135 ms** of repeated full-page RGB/grayscale conversion on that page;
- paired end-to-end warmed Combined output remained exact and improved from roughly **1056 ms** to **1010 ms** median despite runtime noise.

Phase 8K therefore:
- builds the separator-arbitration grayscale image once per fusion call;
- reuses that exact ndarray for all ordinary/OCR whitespace-score comparisons;
- preserves the historical score implementation as the fallback when no precomputed gray is supplied;
- changes no Otsu rule, whitespace-score threshold, ROI geometry, fusion decision, OCR behavior, cache/file format, or compatibility surface.

The protected oversized legacy-core constraint remained active during implementation. The final branch was compacted so `processing_core.py` stayed within the architecture baseline rather than weakening or updating the guard.

Phase 8K publication:
- PR #331 fixed head `b6a463b086e317a2ac289cb3023f2e1d355fe7bf`;
- PR CI 2219 passed on Ubuntu/Windows/macOS;
- PR CodeQL 2201 passed;
- PR #331 merged as `0836eb3e772b44381c05e5ed0a8414f5968594fd`;
- post-merge CI 2220 and CodeQL 2202 passed.

## Phase 8L build the denoise integral in place
The planned post-Phase-8K OCR warm re-profile could not be reproduced faithfully in the current execution container because the project-level PaddleOCR result cache from the earlier successful Phase 8D run was no longer present after environment reset.

The exported Paddle runtime itself was validated:
- Python 3.13, Paddle 3.3.0 and PaddleOCR 3.7.0 load successfully;
- cached PP-OCRv6 detection/recognition models are present locally;
- a real 600x512 crop from page 0055 completed OCR normally (4-thread inference about 18.7 s);
- however, a full-page 0055 cache rebuild in this container remained active for more than 15 minutes without producing a cache, far outside the earlier validated ~164 s/page CPU baseline.

That full-page discrepancy is treated as an **execution-environment/runtime scheduling anomaly**, not as a production performance regression. No new OCR warm-path production optimization is authorized from this distorted environment until a valid project OCR cache or comparable runtime is available again.

A fresh non-OCR real-page profile on pages 0055-0060 still identified one safe pure-CPU hotspot shared by analysis preprocessing:
- warmed `left_edge` median was about **91.6 ms/page** in the post-Phase-8K package;
- `_box_sums(...)` remained the largest pure NumPy denoise cost;
- Phase 8F had already reduced five separate integral images to one, so Phase 8L targeted only the remaining full-page allocation/copy churn.

The historical multi-window implementation created a padded uint8 image, then one full int32 array for the first cumulative sum, another for the second cumulative sum, and another copy to add the leading zero border. The Phase 8L candidate allocates the final padded int32 integral once, writes the source mask into its centered slice, and runs both NumPy cumulative sums in place with `out=integral`.

Exact-equivalence validation on real pages 0055-0060:
- every one of the five denoise window sums matched the historical implementation pixel-for-pixel;
- randomized mixed-shape/radius masks remained covered by the existing exact regression against `_box_sum(...)`;
- the complete final `build_analysis_image(...)` RGB output matched pixel-for-pixel on all six pages;
- `analysis_denoise_profile` metadata matched exactly on all six pages.

Representative component performance:
- `_box_sums(...)` was roughly **1.25x-1.40x** faster across the real masks;
- full `build_analysis_image(...)` six-page median improved from about **73.8 ms** to **65.0 ms** (~**11.9%**);
- 5/6 pages improved in the paired component run.

Because the complete analysis image and its denoise metadata are exactly identical before downstream Layout/OCR logic consumes them, this component boundary provides a stronger semantic equivalence check than timing a distorted Paddle environment.

Phase 8L publication:
- PR #334 fixed head `33dbaf86091ef70055c56170afb89f7a00f791bd`;
- production diff: one file (`adaptive_denoise.py`);
- PR CI 2224 passed on Ubuntu/Windows/macOS;
- PR CodeQL 2206 passed;
- PR #334 merged as `1dd4d62cfb84653e65b6dfd9692346c54fffa261`;
- post-merge CI 2225 and CodeQL 2207 passed.

## Phase 8M measurement closure — no production rewrite selected
A fresh post-Phase-8L warmed `left_edge` cProfile was then run on the same real pages 0055-0060. The six-page median fell to about **78.2 ms/page**, consistent with the Phase 8L preprocessing improvement.

The new aggregate profile no longer shows a clear duplicate-work hotspot comparable with Phases 8F-8L:
- `build_analysis_image(...)`: about **0.311 s / 6 pages**;
- adaptive speck removal: about **0.207 s / 6 pages**;
- the now in-place shared `_box_sums(...)`: about **0.177 s / 6 pages**;
- Layout-entry Y refinement: about **0.099 s / 6 pages**;
- generic analysis-ink construction: about **0.079 s / 6 pages**, dominated by one necessary Pillow BoxBlur;
- Layout image fingerprinting: about **0.065 s / 6 pages**.

Three follow-up candidates were audited and rejected:
- reversing cumulative-sum axis order was pixel-exact but produced inconsistent/noisy real-page speed changes rather than a stable win;
- Layout image fingerprinting remains intentionally content-based because it protects cross-object cache reuse and stale-cache safety;
- Y refinement and generic analysis ink now spend their time in genuine local Otsu/ROI and blur computations, not repeated full-page preparation. Changing them would alter mature numerical algorithms for low-double-digit milliseconds per page rather than remove redundant work.

No Phase 8M production rewrite is therefore selected. This is an intentional measurement result, not an unfinished optimization.

## Recommended next slice — pause micro-optimization until a new measurement gate opens
Do **not** rebuild the six-page Paddle cold cache in the current execution container merely to obtain warm timing; the current full-page CPU runtime is not comparable with the earlier validated Phase 8D environment.

For OCR/Combined performance work, resume only when either the prior project-level OCR cache is available again or a runtime reproduces the earlier cold-page order of magnitude. Ground-truth accuracy remains separately gated on matching `.pdic` references.

For non-OCR CPU work, do not continue shaving the remaining mature numerical kernels merely because they appear near the top of cProfile. Re-open performance work only when a fresh representative profile exposes a materially larger redundant-work hotspot, a user-visible latency target is missed, or a new implementation can prove exact semantic equivalence plus meaningful end-to-end benefit.

## Phase 9 compatibility containment — centralized, stabilized, and ratcheted
Phase 8 performance work is intentionally paused at the current measurement boundary. The next architecture slice therefore returned to a different residual debt category: the historical public facades `processing.py` and `paddle_headwords.py` still preserve a broad core namespace plus same-named assignment mirroring for plugins, tests, debug tooling, and monkeypatch-based workflows.

A repository-wide compatibility audit confirmed that this behavior is still actively characterized:
- tests patch names on `picture_capture.processing` and expect the same-named core helper to change;
- tests patch `paddle_headwords.refine_separator_y` and rely on the historical public path;
- several regression suites intentionally compare facade/core re-export identity;
- external plugin usage is not observable from this repository.

For that reason Phase 9 does **not** shrink the historical public surface or replace broad mirroring with an allowlist. The safe goal is containment: give the compatibility mechanism one owner, make it explicit and reentrant, and prevent the debt from spreading to new modules.

### Phase 9A centralize facade compatibility
Phase 9A introduced `facade_compat.py` as the single owner of historical namespace publication and assignment mirroring:
- `processing.py` and `paddle_headwords.py` call `publish_core_namespace(globals(), _core)` instead of duplicating local namespace-copy loops;
- both facades call `install_core_assignment_mirror(__name__, _core)` instead of owning local `_CoreProxyModule` implementations;
- the architecture guard ratchets the retired local `vars(_core).items()` namespace-copy form and direct `sys.modules[__name__].__class__` proxy form to zero;
- the broad same-name assignment behavior itself remains unchanged.

Phase 9A publication:
- PR #336 fixed head `e12101cb8be3d3566c948bb0bdada38dbc670201`;
- PR CI 2229 and full PR CodeQL 2211 passed;
- PR #336 merged as `83890ba199d38704b91f4d5fd80bbd5db192f592`;
- post-merge CI 2230 passed;
- the push-level dynamic CodeQL run 2212 reported failure only because the Actions analyzer remained queued and never executed; the Python analyzer completed successfully. The same fixed tree had already passed complete PR CodeQL, so this was treated as runner infrastructure rather than a code finding.

### Phase 9B stabilize the shared mirror registry
Phase 9B removed another implicit part of the compatibility mechanism without narrowing behavior:
- one stable `CoreAssignmentMirrorModule` now serves all retained historical facades;
- `facade_compat.py` owns an explicit module-name-to-core registry;
- reinstall/reload refreshes the selected facade's registered core instead of creating a new closure-generated module subclass;
- focused tests prove two facades remain independent and reinstalling one mapping does not redirect the other;
- existing facade-only names remain facade-only, while same-named core assignments still mirror exactly as before.

Phase 9B publication:
- PR #337 fixed head `258a5d7c686455bbeac285614de9d843ad1fe746`;
- PR CI 2231 ultimately passed on Ubuntu/Windows/macOS;
- PR dynamic CodeQL 2213 completed the Actions analyzer successfully while the Python analyzer remained indefinitely queued and GitHub rejected a job rerun with HTTP 403; this was treated as an infrastructure scheduling failure rather than a scan finding;
- PR #337 merged as `5c843daed0d765ae56f5e6546428320596404720`;
- post-merge CI 2232 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2214 passed with both Actions and Python analyzers actually executed, closing the PR-time validation gap.

### Phase 9C ratchet facade-compatibility users
Phase 9C is guard-only and changes no production runtime behavior. It converts compatibility containment into a monotonic architecture rule:
- the shared facade-compatibility mechanism is allowed only in the two historical facades, `processing.py` and `paddle_headwords.py`;
- the architecture guard scans production modules and rejects any third module that starts calling the shared namespace/mirroring owner;
- the guard still requires both retained historical facades to use the centralized owner;
- a focused regression creates a temporary forbidden production module and proves the guard rejects it.

Phase 9C publication:
- PR #338 fixed head `8bec525143aae2b91951d107433e9706b786dacc`;
- PR CodeQL 2215 passed both analyzers;
- PR Ubuntu and Windows CI completed all substantive checks successfully; the macOS runner was still infrastructure-queued when the guard-only PR was merged after the already-validated runtime tree from Phase 9B;
- PR #338 merged as `4a51f56890e821bef38b89f88f7d9a32173e503a`;
- post-merge CI 2234 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2216 passed both Actions and Python analyzers.

### Current Phase 9 boundary
Compatibility containment is now complete:
- one explicit compatibility owner;
- one stable data-driven assignment-mirroring class/registry;
- exactly two authorized historical facade users;
- architecture ratchets prevent the retired duplicate mechanisms or a third compatibility facade from reappearing.

The remaining broad namespace publication and same-name assignment mirroring are now an intentional **public compatibility boundary**, not unowned architecture drift. Do **not** remove or narrow them solely as a refactor cleanup. Any future reduction requires concrete usage/deprecation evidence, characterization of external/plugin impact, and a migration path that preserves the public contract.

## Recommended next slice — leave facade behavior stable
Do not proceed directly to a Phase 9D that removes broad mirroring or replaces it with an allowlist. The repository contains concrete tests that depend on this behavior and external consumers are not observable.

The next safe architecture slice should target a separate debt category with a clearer internal contract, or add non-invasive characterization/observability that can establish whether a future facade deprecation is safe. Performance micro-optimization also remains paused until the Phase 8 measurement gate reopens.

## Phase 10 static bootstrap bindings — two runtime mutations retired
Phase 9 intentionally left the historical public facades stable. The next architecture slice therefore targeted a separate debt category: process/bootstrap code that still rewrote another module's callable solely to compensate for import-order-sensitive by-value imports.

Phase 10 keeps every historical callable/import path that may still be used by tests, diagnostics, or plugins, but moves the actual relationship into the consuming module as a static dependency. Retired installer names remain compatibility no-ops rather than disappearing.

### Phase 10A static Page Layout detector binding
The previous `layout_detector_live_binding.py` installer rewrote
`dictionary_page_layout_policy.detect_layout_parameters` during
`build_core_services()` so Page Layout would follow the current
`layout_detection.detect_layout_parameters` implementation.

Phase 10A makes that behavior native to the policy module:
- `dictionary_page_layout_policy.detect_layout_parameters(...)` is now a small call-time forwarder to `layout_detection.detect_layout_parameters(...)`;
- patching the authoritative `layout_detection` detector remains immediately visible to Page Layout;
- the historical `policy.detect_layout_parameters` symbol still exists and can itself be monkeypatched by tests/debug tooling;
- `build_core_services()` no longer imports or calls the live-binding installer;
- `layout_detector_live_binding.install_live_layout_detector_binding()` remains importable as an inert compatibility shim and no longer mutates another module.

Phase 10A publication:
- PR #340 fixed head `7081fa81ab7068166b26ec00c2a8085cc5f46b2f`;
- PR CI 2237 passed on Ubuntu/Windows/macOS;
- PR CodeQL 2219 passed Actions/Python;
- PR #340 merged as `1f9576c6264c72fe544208cb51eb4db1e4c1d88e`;
- post-merge CI 2238 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2220 passed Actions/Python.

### Phase 10B static Project Profile layout detector
Project Profile creation must use the dedicated anchor-free/OCR-free projection
detector in `profile_layout_bootstrap.py`. Previously GUI bootstrap achieved
that by rewriting `profile_setup.detect_layout_parameters` before constructing
the Profile wizard.

Phase 10B declares that dependency directly:
- `profile_setup.detect_layout_parameters` is now a static alias of
  `detect_profile_layout_parameters`;
- the historical `profile_setup.detect_layout_parameters` name remains intact,
  so direct test/debug monkeypatching still has the same seam;
- `bootstrap/gui.py` no longer imports or calls
  `install_profile_layout_bootstrap()`;
- `install_profile_layout_bootstrap()` remains importable as a compatibility
  no-op;
- Profile schema, detector thresholds, OCR/cache/file formats, and GUI behavior
  are unchanged.

The first PR fixed head `1268fc5f9fcb065de756db9214b8f686ec927e0e`
passed all functional tests except the architecture size ratchet:
`profile_setup.py` had grown from the 174,009-byte ceiling to 174,091 bytes.
CI 2239 therefore failed on all platforms at the same guard test while
CodeQL 2221 passed. The guard was **not** loosened. The static import was
compacted and a non-runtime wrapper docstring removed, producing a final
`profile_setup.py` blob size of 174,000 bytes.

Phase 10B final publication:
- PR #341 final fixed head `f154317484efffea15578af9202af437bf04ee57`;
- final PR CI 2241 passed the executed Ubuntu/Windows jobs; macOS remained queued
  as a hosted-runner scheduling issue;
- final PR CodeQL 2223 passed Actions/Python;
- PR #341 merged as `6f73b2b098447c7f27fa11df35520ed518c30eed`;
- post-merge CI 2242 passed on Ubuntu/Windows/macOS, closing the PR-time macOS
  scheduling gap;
- post-merge CodeQL 2224 passed Actions/Python.

### Phase 10C static shared Layout snapshot ownership
The remaining bootstrap inventory identified one more narrow pure-rebinding seam:
`install_shared_layout_visualization_source()` only assigned
`layout_visualization_ui._snapshot_for_app = shared_snapshot_for_app`.

Phase 10C makes the UI module own that relationship directly:
- `layout_visualization_ui._snapshot_for_app(...)` now forwards at call time to
  `layout_visualization_shared.shared_snapshot_for_app(...)`;
- GUI bootstrap no longer imports or calls
  `install_shared_layout_visualization_source()`;
- the historical `layout_visualization_ui._snapshot_for_app` symbol remains
  directly monkeypatchable;
- `install_shared_layout_visualization_source()` remains importable as an inert
  compatibility shim and does not overwrite a caller's monkeypatch;
- imports used only by the retired duplicate local snapshot implementation were
  removed;
- role-theme, lane-summary, LayoutRows capture, and other real GUI composition
  installers were intentionally left unchanged.

The first PR run on head
`8677699ed41d39c611e87eda06e2ba1dd2b9fa92` exposed one stale historical
source-shape assertion in
`tests/test_layout_local_indent_visualization_runtime.py`: 1 test failed while
1391 passed, because the test still expected the retired installer call to
precede role-theme/lane-summary setup. Production behavior tests and CodeQL did
not fail. A repository-wide search confirmed this was the last stale test-side
reference; the assertion was updated without changing production code.

Phase 10C publication:
- PR #343 final fixed head `94bc7416b2c577137efa52fc0f73639c3ab40446`;
- final PR CI 2246 passed on Ubuntu/Windows/macOS;
- final PR CodeQL 2228 passed Actions/Python;
- PR #343 merged as `0c0cf783dac0e9a78efd2216e9d375acc04e665e`;
- post-merge CI 2247 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2229 passed Actions/Python.

### Phase 10 closure — static bootstrap-binding cleanup complete
Three bootstrap-only mutation seams are now static:
- Page Layout owns its live detector forwarding relationship;
- Project Profile owns its dedicated bootstrap detector relationship;
- Layout visualization owns its shared snapshot forwarding relationship.

A final read-only audit of the remaining core/worker/GUI installers found no
additional candidate with the same narrow semantics. The remaining installers
perform real runtime composition rather than mere alias wiring, including:
- separator-Y settings migration wraps `AppSettings.__init__`,
  `to_json`, and `from_json` and exposes canonical compatibility properties;
- entry-crop settings performs constructor/JSON migration and compatibility
  property installation;
- entry-classification fields install registry-backed structural properties on
  the slotted `Entry` model;
- PDIC classification wraps PDIC I/O so classification metadata persists in a
  sidecar without changing the PDIC format;
- LayoutRows persistence wraps Layout Core inside an explicit capture context so
  reliable physical-row sidecars can be seeded;
- the remaining visualization/profile/UI installers wrap genuine algorithms,
  formatting, or Tk composition whose order is part of behavior.

These are **not** Phase 10D candidates. Converting them merely to reduce the
number of `install_*` calls would hide meaningful composition, risk import
cycles/startup-order changes, and weaken the explicit process-profile boundary.

Retired Phase 10 installer names remain compatibility shims and must not regain
cross-module assignment behavior.

## Recommended next slice — leave Phase 10 and reselect by evidence
Phase 10 is complete. Do not continue removing bootstrap installers by name.

For the next architecture/refactor phase, first perform a fresh read-only debt
inventory and choose a different bounded category with a clear correctness or
maintainability payoff. Alternatively, reopen performance optimization only
through the Phase 8 measurement gate; do not resume speculative micro-optimization.

Phase 9 facade compatibility remains an intentional public boundary.

## Phase 11 settings-migration ownership

Phase 11 was selected after a fresh debt inventory rather than reopening Phase 7
large-module decomposition. Phase 7 already established that the remaining
historical oversized modules contain stateful GUI/state-machine or algorithm
cores, so line-count reduction alone is not a valid reason to split them again.

The new debt category is settings migration ownership. `AppSettings.from_json()`
still contained roughly 13 KB of historical version-to-version payload migration
logic, while separate compatibility installers for separator-Y and Entry crop
settings intentionally wrap `AppSettings.__init__`, `to_json`, and
`from_json` at the process composition root.

The compatibility wrapper chain is order-sensitive but intentional:
`build_core_services()` installs separator-Y compatibility before Entry-crop
compatibility, and tests/CLI/GUI/worker entry points all use that composition
root. Phase 11A therefore did **not** rewrite or flatten those wrappers.

### Phase 11A extract native AppSettings migration ownership

The historical decoded-payload migration block was moved from
`models.AppSettings.from_json()` into
`app_settings_migrations.migrate_app_settings_payload()`.

Behavioral boundaries preserved:
- `AppSettings.from_json()` remains the public classmethod and still owns JSON
  decoding, opacity normalization, known-dataclass-field filtering, and final
  `AppSettings` construction;
- separator-Y and Entry-crop compatibility installers, bootstrap order, canonical
  keys, legacy aliases, and JSON format remain unchanged;
- the new migration module has no reverse import from `models`;
- former repeated `cls().field` default lookups remain repeated through the
  supplied `defaults_factory`, rather than silently caching one default object;
- the migration helper mutates and returns the same decoded payload object, as
  the former inline code did.

Architecture effect:
- `models.py` shrank from about 47 KB to 34,818 bytes;
- the new focused migration owner is 12,773 bytes;
- no architecture baseline or size guard was changed.

Focused regressions cover:
- one-way dependency ownership (`models -> app_settings_migrations`);
- the native historical right-ratio migration;
- a composed roundtrip crossing separator-Y compatibility, Entry-crop
  compatibility, and the extracted native migration owner.

The first PR head
`4575c36d9d48cc1ee3f62cccfcd9f69a88686369` produced one failure with 1394
tests passing. The failure was in the newly added combined migration test, not
production behavior. The fixture serialized a modern payload first, which
already contained `ordinary_right_divisor=1.0`, then artificially marked only
the right-ratio version as legacy. The historical migration correctly uses
`setdefault` and therefore preserved the existing divisor. The test was fixed
to model an authentic legacy payload by removing `ordinary_right_divisor`
before triggering the old migration. Production code was unchanged by this fix.

Phase 11A publication:
- PR #345 final fixed head
  `e238b9a1d157a6d4ca91105761342c1a1e766f47`;
- final PR CI 2251 passed on Ubuntu/Windows/macOS;
- final PR CodeQL 2233 passed Actions/Python;
- PR #345 merged as
  `50700ac6b094b135c6dc35e349fb45ab6e6d2443`;
- post-merge CI 2252 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2234 passed Actions/Python.

### Phase 11B characterize compatibility install order

The read-only call-chain audit confirmed that the remaining settings installer
order is semantic rather than accidental:
- separator-Y replaces the native AppSettings JSON adapter with its canonical
  separator-key adapter;
- Entry-crop then captures the **current** constructor/to_json/from_json methods
  and wraps them to add canonical crop-height keys and the transient crop-width
  compatibility rule;
- reversing those two installers would allow separator-Y's serializer replacement
  to overwrite the Entry-crop serializer layer instead of being wrapped by it.

Removing that dependency cleanly would therefore require a new shared
dispatcher/registry or equivalent compatibility framework. That would be a
cross-cutting redesign, not a bounded migration cleanup, and would add more
infrastructure than the current explicit composition contract warrants.

Phase 11B deliberately changed no production behavior. It added one focused
characterization guard to `tests/test_core_bootstrap.py` asserting:

`install_separator_y_settings() < install_entry_crop_settings()`

inside the explicit core composition profile.

Phase 11B publication:
- PR #347 fixed head `decd9ea7fde14aeff07f178cc582505da1ecb313`;
- PR CI 2255 passed on Ubuntu/Windows/macOS;
- PR CodeQL 2237 passed Actions/Python;
- PR #347 merged as `fa73e7e541b58f3298a6904c0701f200cb399b74`;
- post-merge CI 2256 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2238 passed Actions/Python.

### Phase 11 closure — migration ownership cleanup complete

Phase 11 is complete:
- native historical AppSettings payload migrations have a focused one-way owner;
- the existing separator-Y and Entry-crop compatibility wrappers remain explicit
  at the process composition root;
- their intentional order dependency is now characterized by test;
- package import remains inert;
- no settings key, constructor alias, JSON format, or bootstrap profile changed.

Phase 11 closure checkpoint publication:
- PR #348 fixed head `2c0f3ba87965355bde3f2f32a329b79d569d6173`;
- PR CI 2257 passed on Ubuntu/Windows/macOS;
- review submissions: none;
- review threads: none;
- PR comments: none;
- PR #348 merged as `0d73836c6ecb64bab54a653ac0f6ca8a54d7c79f`;
- comparing the Phase 11B merge `fa73e7e541b58f3298a6904c0701f200cb399b74`
  to the closure merge changes only `docs/refactor/REFACTOR_STATUS.md`, so the
  Phase 11 production tree is unchanged by the closure publication.

Do **not** introduce a generic compatibility dispatcher merely to eliminate the
remaining installer order unless a future feature independently requires such a
framework. The current explicit chain is smaller and better understood than that
speculative abstraction.

## Phase 12A — core-owned PDIC classification composition

The post-Phase-11 debt inventory initially surfaced the OCR-boundary compatibility
bridge, which temporarily rebinds four mature parser runner globals during one
boundary call. Read-only call-chain analysis showed that removing that bridge
cleanly would require explicit runner plumbing through
`paddle_headwords_core.py`, including the two oversized-CJK recovery helpers.
That remains a meaningful correctness target, but it is a cross-cutting change
inside the ~364 KB mature parser core rather than the safest first Phase 12 write.

A smaller, independently bounded ownership defect was found in process
composition instead. `build_core_services()` already installs
`install_pdic_classification(formats)` before exposing formats/processing to
any GUI, worker, CLI, test, or diagnostic profile. Despite that shared ownership:
- GUI composition wrapped the already-classification-aware writer with automatic
  baseline capture, then called `install_pdic_classification(formats)` again;
- worker composition called the same classification installer again immediately
  after `build_core_services()`;
- both repeated calls were guaranteed no-ops because the shared installer marks
  the formats module as already composed;
- the GUI comment also described the wrapper nesting in the opposite direction
  from the actual composed object graph.

Phase 12A makes the existing ownership explicit without changing persistence:
- `build_core_services()` remains the sole PDIC classification installer;
- GUI composition adds only
  `build_write_pdic_capture(formats.write_pdic)` around the shared composed
  writer;
- worker composition directly reuses `core_services.formats`;
- the GUI comment now describes the real ownership rather than a fictitious
  second classification layer;
- a focused regression composes classification plus automatic-baseline capture,
  proves a repeated classification install is a no-op, and verifies that the
  baseline JSON, PDIC, and EntryClassification sidecar are all still produced;
- worker entry-path guards now require core composition and forbid the duplicate
  worker classification call.

Behavior intentionally unchanged:
- historical PDIC format and coordinates;
- EntryClassification sidecar format/location/semantics;
- automatic-baseline format and first-capture policy;
- GUI/worker output ordering and detection behavior;
- inert bare-package import contract.

Phase 12A publication:
- PR #350 final fixed head `f08736aa61be9550e7ab11509f64a6736b0b227c`;
- an earlier two-file head passed CI 2261 before the same ownership cleanup was
  extended to the worker profile;
- final PR CI 2262 passed on Ubuntu/Windows/macOS;
- review submissions: none;
- review threads: none;
- PR comments: none;
- PR #350 merged as `0f37f14f2c428dd5d28a903cb2a72dd63b291a06`;
- the production slice changed only
  `bootstrap/gui.py`, `bootstrap/worker.py`,
  `test_entry_classification_pipeline.py`, and
  `test_runtime_entry_path_guards.py`.

## Phase 12B — static current training-export composition

Read-only Phase 12B inventory found that current supervised training export was
still selected by GUI import order rather than by an explicit static owner.
Before Phase 12B, `bootstrap/gui.py` imported the v2
`training_export` module, replaced `export_training_page` twice (v3 then
Page Understanding), replaced `write_training_manifest`, and rewrote
`TRAINING_EXPORT_FORMAT` to v3 before importing the application/controller.
The ExportController imported those functions by value, so correct current
behavior depended on GUI bootstrap running first.

Phase 12B preserves the exact wrapper order while removing that process-global
mutation:
- new `training_export_composed.py` statically owns the current pipeline:
  v2 base → v3 correction/baseline layer → Page Understanding;
- `ui/controllers/export.py` imports the current exporter/manifest writer from
  that composed module directly;
- `training_export.py` remains the unchanged v2 base/compatibility
  implementation rather than being mutated at GUI startup;
- `bootstrap/gui.py` no longer rewrites any training-export function or format
  global;
- the legacy `training_export_ui.py` range/shim module no longer imports the
  obsolete exporter stack it stopped using after controller ownership moved;
- regression coverage proves the composed v3/Page Understanding functions are
  available before GUI bootstrap and that the v2 base remains distinct.

Behavior intentionally unchanged:
- current GUI training packages remain v3;
- wrapper order remains v2 → v3 → Page Understanding;
- annotation/manifest/ZIP implementations and schemas are unchanged;
- v2 base helpers remain available for compatibility/benchmark callers;
- no package-level bootstrap side effect was added.

Phase 12B publication:
- PR #352 fixed head `fe1833e370c982c640d0d6740e243340db491c0d`;
- PR CI 2266 passed on Ubuntu/Windows/macOS;
- review submissions: none;
- review threads: none;
- PR comments: none;
- PR #352 merged as `037922b0dc874730f14cb3eaefca7672776596f4`;
- the production slice added `training_export_composed.py` and changed only
  `bootstrap/gui.py`, `training_export_ui.py`,
  `ui/controllers/export.py`, and
  `test_ui_training_export_controller.py`.

## Phase 12C — static Project Profile wizard composition

Read-only inventory found a smaller import-order dependency than the deferred
OCR-boundary runner bridge. Before Phase 12C, GUI startup built the effective
Project Profile class by assigning a nested extension chain back onto
`profile_setup.ProjectProfileWizard`, and only then imported `app.py`.
Because `app.py` imported `ProjectProfileWizard` by value, the application
silently depended on that bootstrap ordering.

The effective historical chain was characterized before editing:
- `profile_setup.ProjectProfileWizard` base;
- `build_project_profile_wizard(...)`, which also applies the validation-mode
  wrapper internally;
- `build_ordinary_evidence_profile_wizard(...)`;
- `build_profile_parameter_help_wizard(...)`.

Phase 12C makes that chain explicit and static:
- new `profile_wizard.py` owns the composed GUI wizard;
- `app.py` imports the finished wizard from that module directly;
- `bootstrap/gui.py` no longer imports the builder chain or assigns to
  `profile_setup.ProjectProfileWizard`;
- the historical `profile_setup` base class remains unchanged and independently
  importable;
- regression coverage locks the MRO/extension order and proves the application
  uses the statically composed class without GUI-bootstrap mutation.

Behavior intentionally unchanged:
- no edits to the ~3,600-line base wizard body;
- no Profile schema, JSON/persistence, detector, OCR, or Layout behavior changes;
- no UI wording/control-order changes;
- validation remains nested after indentation/layout and before ordinary evidence
  and parameter-help wrappers.

The architecture-size ratchet caught two harmless wiring-size regressions during
publication:
- initial CI 2270 ran all 1,396 non-guard tests successfully but rejected
  `app.py` at 784,773 bytes versus the 784,737-byte baseline;
- a compact boundary reduced the delta to one byte; CI 2275 again ran the
  non-guard suite successfully but correctly rejected 784,738 bytes;
- the final head retained the existing ratchet without raising its allowance.

Phase 12C publication:
- PR #354 final fixed head `cac6ae139945d714ee3f58cf13ec3490815c0940`;
- final PR CI 2276 passed on Ubuntu/Windows/macOS, including pytest,
  platform GUI smoke, compatibility runner, compile, F821, and wheel build;
- review submissions: none;
- review threads: none;
- PR comments: none;
- PR #354 merged as `3632ff4bce26eafec28cf3eebd2e57b7f36c7870`;
- production diff is limited to `app.py`, `bootstrap/gui.py`,
  new `profile_wizard.py`, and the focused regression test.

## Phase 12D — static GUI PDIC I/O composition

Fresh read-only inventory first separated several remaining rebinding seams. The
Page Design refined-detector chain was rejected for this slice because it is tied
to call-time physical-indent/line-start preparation, and the OCR-boundary runner
bridge remains too deep in the mature Paddle parser core. The smaller ownership
problem was GUI PDIC I/O.

Before Phase 12D:
- `build_core_services()` composed `formats.read_pdic` / `formats.write_pdic`
  with classification sidecar behavior;
- GUI bootstrap then wrapped the already-composed `formats.write_pdic` again
  with automatic-baseline capture;
- `app.py` imported those callables by value, so application behavior silently
  depended on bootstrap mutating `formats` before importing the app module.

Phase 12D adds `gui_io.py` as the static application-facing boundary:
- `app.py` imports PDIC I/O from `gui_io` rather than directly from
  `formats`;
- `gui_io.read_pdic()` resolves the current core-composed
  `formats.read_pdic` at call time;
- the GUI writer keeps the existing automatic-baseline wrapper, but its inner
  delegate resolves the current core-composed `formats.write_pdic` at call
  time;
- GUI bootstrap no longer assigns `formats.write_pdic = ...`;
- non-GUI consumers continue to use the core-composed `formats` boundary
  without GUI baseline capture.

This call-time delegation is the key compatibility property: importing
`app.py` no longer freezes whichever `formats` callable happened to exist at
that moment, while classification remains owned exclusively by core composition.

Behavior intentionally unchanged:
- PDIC text format is unchanged;
- classification sidecar format/ownership is unchanged;
- automatic-baseline format and first-capture semantics are unchanged;
- GUI writes still pass through classification persistence before returning;
- non-GUI writers do not gain GUI-only baseline capture;
- no Layout, OCR, crop, worker, or public facade behavior changed.

Phase 12D publication:
- PR #356 fixed head `5bea4fc1a32808ee509438d84046bb2822f4eb12`;
- PR CI 2281 passed on Ubuntu/Windows/macOS;
- review submissions: none;
- review threads: none;
- PR comments: none;
- PR #356 merged as `762e2bc22eb2780549fad097b778f2bc303105e0`;
- post-merge CI 2282 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2265 passed;
- the production diff is limited to `app.py`, `bootstrap/gui.py`, new
  `gui_io.py`, and focused PDIC composition regression coverage;
- no architecture ratchet was relaxed.

## Phase 12E — static Layout diagnostic summary composition

Read-only characterization confirmed that the remaining role-theme and
physical-lane summary installers were GUI diagnostic presentation wrappers, not
Layout inference owners. Their only production ordering dependency was in
`bootstrap/gui.py`.

The historical effective GUI order was preserved exactly:
- base Layout summary with entry-source provenance;
- red entry/headword role theme, blue body theme;
- physical-indent lane diagnostics;
- prepared-indent diagnostics.

Phase 12E makes that final state static:
- `layout_visualization_summary.py` owns the effective red/blue role palette;
- summary finalization is explicit and ordered as entry-source provenance,
  physical lanes, then prepared-indent diagnostics;
- GUI bootstrap no longer imports or calls either summary-mutating installer;
- `install_layout_role_theme()` and `install_physical_lane_summary()` remain
  importable compatibility no-ops;
- focused tests now assert the static final state and preserved summary order.

Behavior intentionally unchanged:
- no Layout geometry, row recovery, indentation, role inference, OCR, worker,
  persistence, or file-format behavior changed;
- entry/headword rows remain red and body rows remain blue in the product GUI;
- physical-lane diagnostics still precede prepared-indent diagnostics;
- entry-source provenance remains part of the summary.

Phase 12E publication:
- PR #358 fixed head `8707014ab0e7abf7e5e1f265dd4de7172c66e035`;
- PR CI 2285 passed on Ubuntu/Windows/macOS;
- review submissions: none;
- review threads: none;
- PR comments: none;
- PR #358 merged as `a1016a8aa8ef3fd50ff3c50b1e8433db9cd5122b`;
- post-merge CI 2286 passed on Ubuntu/Windows/macOS;
- post-merge CodeQL 2269 passed;
- production changes were limited to the Layout diagnostic summary/theme/lane
  composition, GUI bootstrap removal, and focused regression updates;
- no architecture ratchet was relaxed.

## Recommended next slice — Phase 12F static LayoutRows capture publication

The next bounded candidate is the LayoutRows persistence seam. The explicit
`capture_layout_rows(...)` context is already static at both production callers:
ordinary-detection worker execution and Layout visualization. The remaining
dynamic debt is only `install_layout_rows_persistence_runtime()`, which wraps
`layout_core_understanding.understand_layout_core` so results produced inside
that explicit context are written to the physical-row sidecar.

A safe static design must preserve both return paths:
- cache hit in `understand_layout_core`;
- newly computed Layout Core result.

Prefer a small publication helper owned by `layout_rows_cache.py` that reads the
existing context target and persists the reliable physical layout. Call that
helper from the Layout Core return boundary for both cached and new results.
Then GUI/worker bootstrap can stop installing the wrapper while
`capture_layout_rows(...)` remains the explicit opt-in side-effect scope.

Preserve:
- semantic-free LayoutRows format and reliability gate;
- original settings fingerprint supplied by the capture context;
- GUI visualization and spawn-worker capture behavior;
- explicit worker-service exposure of `capture_layout_rows`;
- cache-hit persistence behavior.

Keep `install_layout_rows_persistence_runtime()` and the obsolete visualization
cache-context installer importable as compatibility no-ops if characterization
continues to show no required external mutation contract.

Do not combine this with the Page Design physical-indent installer chain. That
chain still changes algorithmic owners and remains a separate, deeper slice.

The OCR-boundary runner bridge remains deferred until explicit hook injection can
be proven safe across oversized-CJK recovery, cache semantics, supervised
filtering, and historical public monkeypatch seams.

Phase 9 facade compatibility remains an intentional public boundary.

## Standing continuation authorization
The user has authorized faster continuous progression through confirmed-safe refactor slices without stopping for a checkpoint after every small change. Phase 11 is complete; Phase 12 follows the same bounded-slice rule.

Continue across related low-risk changes once contracts and focused tests are clear. Use checkpoints at phase milestones, material compatibility-boundary changes, plan changes, merge/finalization boundaries, or when recovery state would otherwise become ambiguous.

Stop production writes for unexplained behavior/test/CI failure, public/file-format compatibility uncertainty, concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
