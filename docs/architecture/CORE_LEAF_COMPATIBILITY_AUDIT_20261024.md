# PR #663: Core leaf extraction and compatibility audit (2026-10-24)

This is an internal extraction, **not** another root-module retirement. The
physical root count remains **10**. `processing_core.py`,
`paddle_headwords_core.py`, `processing.py`, and `paddle_headwords.py`
remain importable; this change does not touch persistence schemas.

## Newly established package owners

| Core entrypoint | Physical algorithm owner | Compatibility mechanism |
| --- | --- | --- |
| `processing_core._point_in_rect`, `_point_in_polygon`, `_orientation`, `_on_segment`, `_segments_intersect`, `polygon_intersects_box`, `polygon_fully_inside_boxes`, `_box_intersection_area` | `crop/polygon_geometry.py` | Thin core delegates; call-time callback injection for patchable subordinate primitives |
| `processing_core.resolve_crop_worker_count` | `crop/worker_policy.py` | Core passes its current `os.cpu_count` callback, retaining legacy `processing.os` monkeypatch behavior |
| `paddle_headwords_core.normalize_headword` | `ocr/headword_normalization.py` | Core injects its current `_SYLLABLE_SEPARATORS` and `re` globals at call time |

All historical core function *definitions* and their original call signatures
remain at their original import paths, so callable `__module__` values stay
unchanged. The package leaves are stateless and do not import Tk, PaddleOCR,
or sidecar storage.

The pre-existing facade assignment mirrors in `processing.py` and
`paddle_headwords.py` remain unchanged. These assignments are intentional
compatibility behavior: setting a known symbol on a public facade mirrors
the value into the corresponding core module. Do not replace those two
facades with plain re-exports as part of this extraction.

## Second extraction batch — commit a9fe8ec4

- `geometry/column_tracking_math.py` owns `_smooth_track` and
  `_column_tracking_dimensions`; the historical `processing_core`
  functions remain call-time forwards for older tooling.
- `ocr/paddle_results.py` owns PaddleOCR JSON-v3 result unpacking and
  conversion to OCRRecord. The core injects its current JSON parser,
  model constructor, and NumPy module so public monkeypatch paths work.
- `tests/test_issue562_core_leaf_round2_20261024.py` covers both paths,
  polygon fallback and historical object identities.

## Third extraction batch — subsequent commit

- `ordinary/ink_threshold.py` owns legacy Otsu thresholding and
  ordinary foreground-mask selection; the core injects the live Otsu
  callback to retain the legacy public patch point.
- `ocr/headword_script.py` owns OCR-language/script guards; core
  delegates with live script-family and language-parts callbacks,
  preserving East Asian script compatibility rules and monkeypatches.
- `tests/test_issue562_core_leaf_round3_20261024.py` adds threshold,
  Unicode script-family and facade callback tests.

These changes do not rename or relocate the public `processing_core`,
`paddle_headwords_core`, `processing` or `paddle_headwords` modules.
The root count stays at ten. OCRRecord and HeadwordParse remain the
existing classes with unchanged pickle identities.

## Fourth and fifth extraction batches — 2026-10-24

- `crop/entry_column_bounds.py` owns per-column crop box calculations;
  `processing_core` forwards using live source-pixel conversion and box clamp
  callbacks. `ocr/lemma_repairs.py` owns length-preserving OCR digit-confusion
  repair. These remain non-persistent helpers.
- `geometry/reading_order.py` owns interval/gutter-aware click classification,
  SECTION-first reading order and PDIC repair sorting. Historical core entrypoints
  inject live column-classifier, SECTION indexing and normalization callbacks,
  rather than capturing public patch targets at import time. The real Geometry
  data class is **not** relocated to this calculation-only leaf.
- `ocr/line_grouping.py` owns OCRRecord grouping and logical line merging,
  while preserving original OCRLine model identity and live overlap callback.
- Characterization tests `test_issue562_core_leaf_round4_20261024.py` and
  `test_issue562_core_leaf_round5_20261024.py` check structured page ordering,
  image crop geometry, OCR text/box/score parity and old monkeypatch hooks.

## Exact-head test status notes

Earlier Windows Python 3.13 CI on `5b891ecb` reported
`_tkinter.TclError: Can't find a usable init.tcl` during a Tk-only test.
The Linux/macOS and Python 3.10 suites passed on that head; the Tcl/Tk runner
issue must be assessed separately, not conflated with OCR/geometry parity.
The current refactor commits must be judged on their **own** exact-head CI and
OCR smoke results before PR readiness.

## Sixth, seventh and eighth extractions — 2026-10-24

- `ordinary/separator_position_policy.py` owns local whitespace evidence and
  ordinary/OCR marker-position choice, preserving live core scoring callbacks.
- `ocr/alphabetical_warnings.py` owns diagnostic-only alphabetical anomalies,
  retaining SECTION/column/axis ordering and public patch points.
- `crop/entry_vertical_bounds.py` owns literal-pixel crop top/bottom bounds
  and special-page lookup, with current geometry, special-pages paths and pixel
  converters passed by historical `processing_core` callables.
- `ocr/band_preprocessing.py` owns Paddle input RGB/grayscale/autocontrast/
  binary modes, scaling and OCR-local Otsu, while the legacy core forwards
  the current image normalizer and threshold callback at call time.
- `ocr/language_resolution.py` owns historical Chinese/Japanese selectors and
  Paddle model mapping. These must remain distinct from the semantic language
  script guard; the original fallback priorities are preserved.
- Regression coverage: `test_issue562_core_leaf_round6_20261024.py`,
  `test_issue562_core_leaf_round7_20261024.py`, and
  `test_issue562_core_leaf_round8_20261024.py`.

These changes leave the historical core functions, ten root modules,
persisted data classes, OCR cache keys, PDIC/PPP sidecar schemas and crop
publish transactions untouched. Last fully verified green baseline before
this series: `e573b64d`. Review the *new exact-head* CI before acceptance.

## Ninth and tenth extraction batches — 2026-10-24

- `preprocess/core_analysis_pixels.py` now owns legacy processing-core
  analysis RGB resizing and OpenCV-free adaptive dark-ink masks. Original
  `_analysis_image` and `_adaptive_dark_mask` entrypoints remain in
  `processing_core`, and forward live source normalization, NumPy, Pillow
  class and filter implementations. Normalized page pixels are not persisted.
- `ocr/band_coordinates.py` owns **in-memory** mapping of OCR record boxes
  from source-band to canonical analysis space. The old core method continues
  to import the current `LayoutTransform` on each call and passes the original
  `OCRRecord` constructor. Recovered-record metadata and parent-box
  coordinates are preserved; source input pixels and raw OCR cache are
  intentionally not rewritten.
- `ocr/boundary_measurements.py` owns OCR ink ratio, leading-headword box,
  contiguous true-runs, left-column separator ROI and running-header cutoff.
  The legacy core passes its current `_true_runs` callback to header cutoff
  at each call to preserve the public facade assignment-mirror seam.
- `tests/test_issue562_core_leaf_round9_20261024.py` exercises image-size/
  EXIF-alpha-safe normalization, adaptive local contrast, mirrored/rotated OCR
  records, synthetic CJK recovery metadata and live class/image hooks.
  `tests/test_issue562_core_leaf_round10_20261024.py` checks local box/ink,
  OCR run intervals, separator ROI and running-header policy.
- Root inventory remains **10** Python modules. `OCRRecord` and `OCRLine`
  preserve their historic `__module__` and constructor identities.
  Staged crop publishing, PDIC/PPP schemas, raw engine caches, GUI and
  manual selection remain unchanged.

Judge the current series by its own exact-head CI and three-platform OCR
smoke. Do not infer green from the previous stable baseline alone.

## Eleventh extraction batch — 2026-10-24

- `crop/line_box_geometry.py` owns half-open PIL `clamp_box` and single-line
  `line_box` calculations. Original `processing_core` functions retain
  historical signatures and delegate with *current* `column_index`,
  `_source_px` and `clamp_box` callbacks. This leaf computes boxes only;
  it does not publish, rename, remove or overwrite any export files.
- `ocr/image_separator_geometry.py` owns independent grayscale-only blank-
  to-ink separator candidate proposals and mutual-nearest OCR-line matching.
  The `paddle_headwords_core` wrappers supply *current*
  `_separator_analysis_x_bounds`, `_otsu_threshold`, `_true_runs` and NumPy
  operations. The emitted boundary keys and pairing metadata remain unchanged.
- `tests/test_issue562_core_leaf_round11_20261024.py` checks the
  inventory, legacy origins/signatures, literal-pixel crop geometry,
  box/clamp/column monkeypatch hooks, synthetic blank-band candidate generation
  and mutual-nearest OCR line pairing.
- No `Entry`, `OCRLine` or `OCRRecord` class was relocated. Raw OCR
  engine caches, source-coordinate persistence, GUI orchestration,
  manual-review/arbitration, and file-publishing transactions remain untouched.

The last exact-head verified baseline was `552bc8c1`, which completed
full six-platform CI and three-OS OCR smoke successfully. This newly extracted
batch requires its **own exact-head** CI and OCR smoke before readiness.

## Twelfth batch: four physical owners, seven core functions — 2026-10-24

- `ocr/line_structure_repairs.py` owns three established OCR logical-line
  recovery policies: same-row right fragments, next-row POS wraps, and the
  bounded two-line grammar state machine. Original `paddle_headwords_core`
  entrypoints inject current parser, overlap, merge, POS cue, prefix stripping,
  `OCRLine` constructor, NumPy and regex functions at call time. Source
  record boxes, first-line Y and pickle model identity remain unchanged.
- `ordinary/auto_layout_policy.py` owns per-page optional Layout estimate
  application. Project settings are still copied, not mutated; the original
  switches and measured-row-padding guard are respected. Detector imports
  remain lazy after the master toggle, and core passes current switch bindings.
- `ordinary/fusion_entry_mapping.py` owns the combined-mode metadata
  constructor and valid latent review-candidate-to-`Entry` conversion.
  Current core `Entry` class is passed at invocation; this changes no
  accepted/rejected decision, serialized fields, or PDIC/PPP schema.
- `ocr/ordinary_marker_crop.py` owns source-direction-correct temporary
  marker OCR crops, retaining existing live classification/visual-scale/row
  metrics and core-normalization behavior. Crops remain in-memory.
- Added `test_issue562_core_leaf_round12_processing_20261024.py` and
  `test_issue562_core_leaf_round12_ocr_20261024.py` for legacy patch seams,
  Entry metadata and class identity, physical glyph pixels, layout switch
  policy, logical line tags and unchanged first-line anchor.
- The prior `90f3b49c` complete CI failure was confined to
  **Windows Python 3.10 Tcl/Tk setup** (`tk.Tcl(): init.tcl`); all other
  CI platforms and all three OCR smoke platforms passed. The previous
  `552bc8c1` CI was fully green. New exact-head checks are required.

Keep the PR Draft until representative real-page GUI scan/edit/save/reopen
and PDIC/PPP/crop acceptance has been independently verified.

## Thirteenth extraction batch — four owners and twelve core functions — 2026-10-24

- `ocr/visual_rescue_policy.py` owns physical overlap association of accepted
  one-Han OCR glyphs to visual ink runs; explicitly selected post-lemma grammar
  evidence; saved Profile v1 visible visual-rescue thresholds versus Profile v0
  backward-compatible thresholds; and the strong-left-edge visual rescue gate.
  Historical core functions continue to pass current Han classifier and
  threshold functions at call time.
- `ocr/peer_typography.py` owns robust page-local median/MAD and an
  **annotation-only** typography match of softly rejected OCR candidates.
  It does not directly flip acceptance or relax hard semantic guards. Existing
  core median/MAD monkeypatches remain effective through callback injection.
- `ordinary/review_signals.py` owns hard-negative consensus (single/dual),
  visual-positive veto, and collection of non-selected refined candidate
  positions on the canonical reading axis. The core passes live visual
  classifier, negative-reason registry and column-index functions.
- `geometry/column_offsets.py` owns literal-pixel column-start nudges and
  safe non-crossing column order. Current core pixel converter is passed
  at invocation; Geometry/ColumnPath data classes and pickle module paths
  stay in the original core.
- `tests/test_issue562_core_leaf_round13_ocr_20261024.py` and
  `tests/test_issue562_core_leaf_round13_processing_20261024.py`
  characterize all twelve historical signatures and primary policy branches.
- **No changes** to raw OCR caches, page/PDIC/PPP schemas, manual review
  finalization, OCR engine selection, or crop publish transactions.

The previous exact head `67a0000d` passed full six-platform CI and all three
OCR smoke jobs. The present commit requires independent exact-head CI;
keep PR #663 Draft pending representative GUI scan/edit/save/reopen acceptance.

## Fourteenth extraction batch — nominal/curved geometry and editable rules — 2026-10-24

- `geometry/geometry_construction.py` owns four prior `processing_core`
  geometry constructions (nominal canonical, nominal source transform, actual
  canonical analysis, actual source transform). The old core wrappers inject
  **current** RGB normalizer, transform class, pixel scaling, column nudges,
  deformable-column tracker, and the original `Geometry` and `ColumnPath`
  constructors at call time. No class moves or pickle path changes.
- `ocr/user_filter_rules.py` owns parsing, BOM-safe loading, matching and
  deterministic `reject > accept` priority of user-editable headword rules.
  The old core retains the actual `_RULE_ALIASES`/`_RULE_KINDS` registry,
  `HeadwordFilterRule` constructor, parser and matcher patch seams.
  No user-facing rule syntax or on-disk rule format was changed.
- `tests/test_issue562_core_leaf_round14_geometry_20261024.py` and
  `tests/test_issue562_core_leaf_round14_rules_20261024.py` cover nominal
  and curved column paths, mirrored/rotated source transform, constructor
  identity, live geometry dependencies, rule aliases, regex validation, BOM
  and matched-rule priority.
- Root directory remains **10 physical Python files**. Raw OCR engine
  caches, PDIC/PPP schema, manual arbitration, crop publish transactions
  and GUI workflows remain untouched.

Previous exact-head baseline `b22bb190` passed complete six-platform CI
and all three-platform OCR smoke. Verify this new head independently.

## Fourteenth-batch addendum: grammar-tail state machine — 2026-10-24

- `ocr/grammar_tail_parsing.py` now owns five in-memory parser primitives:
  leading morphology cues, double-bar/ambiguous parallel markers, whitespace
  cursor advancement, structured grammar-tail state machine and diagnostic bug
  tag generation. The historical `paddle_headwords_core` entrypoints retain
  signatures, origins and the original `GrammarTailParse` pickle identity.
- The core forwards the current POS finder, prefix-modifier stripper, cursor,
  regex module, usage-abbreviation inventory and grammar result constructor
  on every call. No page/cache JSON fields, sidecar files or acceptance
  arbitration logic were moved.
- `tests/test_issue562_core_leaf_round14_grammar_20261024.py` characterizes
  parallel markers, morphology, POS and usage parsing, patchable grammar hooks
  and ordered deduplicated bug tags.
- Across round 14: **three** new physical leaf modules, **13** historical
  function implementations extracted, without adding root-level shims.

## Explicit no-move boundaries

- The core and model data classes (including `ColumnPath`, `Geometry`,
  `CropRecord`, page crop plans and `OCRRecord` / `OCRLine`) remain
  importable through the same historical modules. Do not reassign their
  module identities or pickle paths merely to decrease file size.
- OCR engine cache, page-resume fingerprints, raw-cache signatures, cache
  compaction, source-coordinate serialization, manual-selection overrides,
  and review finalization require independent characterization before moving.
- `app.py` is still a Tk integration point, not an immediate relocation.
  `training_export.py` retains the explicit
  `picture_capture.training_export` historical serialization identity.

## Automated acceptance checks

`tests/test_issue562_core_leaf_extract_20261024.py` guards:

1. New package owners physically exist, with no additional root shims.
2. Historical core function origins and signatures are stable.
3. Polygon boundary/intersection behavior matches the leaf implementation.
4. Existing public `processing` assignment-mirror monkeypatch behavior is
   preserved at **call time**, including nested orientation/segment callbacks.
5. Headword normalization retains historical separators and accepts a patched
   public configuration.
6. The worker count policy remains identical over representative CPU and user
   settings, including patched `os.cpu_count`.

Related existing regression coverage checks the OCR model pickle identities,
facade-mirror registry, source-layout architecture and root inventory.
Cross-platform CI/OCR smoke must be reviewed at the **new exact head**.

## Remaining manual acceptance

Keep PR #663 in **Draft** until an independent GUI check exercises a
representative dictionary scan: layout/OCR/crop, editing, sidecar save-reopen,
and PDIC/PPP parity across real OCR engines. CI is necessary but does not
replace these checks.


## Round 15 — OCR cache persistence and pixel fingerprint (2026-10-24)

- `src/picture_capture/ocr/source_coordinate_persistence.py` owns recursive removal of transient `_axis_v` / canonical coordinates and the exact normalized-RGB pixel hash. The previous functions in `paddle_headwords_core.py` remain at the same import path, signature, and `__module__`.
- The SHA-256 input remains precisely `{width}x{height}|RGB|` in ASCII followed by the complete normalized RGB byte stream; the core supplies the *current* `normalize_page_rgb` and `hashlib` on each call, preserving monkeypatch seams.
- Source-coordinate JSON persistence retains recursive list/tuple handling, key filtering, unmodified inputs, and authoritative `source_y` fields (including Paddle, Tesseract, and Lens coarse/anchor variants). No cache schema or invalidation rule was intentionally changed.
- Regression: `tests/test_issue562_core_leaf_round15_cache_20261024.py` covers nested JSON projection, nonmutation, historical origins, deterministic digest parity, and live normalization monkeypatches.
- The root still has ten Python files; no class relocation, root shim, UI changes, PDIC/PPP schema update, or crop output transaction changes.
- **Acceptance pending:** exact-head six-platform CI and OCR platform smoke plus independent representative GUI scan, edit, and save/reopen verification. Keep PR Draft and unmerged.


## Round 16 — legacy VB brightness sampling (2026-10-24)

- Extracted `_legacy_is_point` and `_legacy_row_brightness_1000` implementations from `processing_core.py` into `ordinary/legacy_brightness_sampling.py`; the historical core function names, signatures, and `__module__` remain unchanged.
- Keep original VB.NET-compatible semantics: inclusive vertical sample rows with the historical `area_x * area_y` divisor, reading-direction sampling, image boundary checks, NumPy float64 accumulation, Python `round`, and 0–1000 row scale. Call-time `np` injection preserves the live core monkeypatch seam.
- Characterization tests: `tests/test_issue562_core_leaf_round16_brightness_20261024.py` for point thresholds, row brightness, reverse direction, bounds, callable origin, and live NumPy callback.
- Root Python inventory remains ten. No public model, serialized schema, PDIC/PPP/crop transaction, OCR acceptance decision, or GUI work intentionally changed.
- **Pending:** exact-head CI/OCR smoke and representative manual dictionary page scan, editing and save/reopen. Keep PR Draft.


## Round 17 — full legacy ordinary detection and oversized-CJK postpasses (2026-10-24)

**Scope:** The actual source-pixel VB.NET `Draw_Auto` separator and scan implementations have left `processing_core.py`; these are not root-level compatibility stubs.

- `ordinary/legacy_separator_search.py`: two-stage upward separator-Y search, full-white priority, row-brightness threshold fallback, short-run whitespace adjustment and historical reasons/thresholds. The core forwards **current** `np`, `_legacy_row_brightness_1000` and `legacy_row_brightness_scores_1000` per call.
- `ordinary/legacy_page_detection.py`: transform-aware source column edges and complete original-resolution `_detect_entries_left_edge` candidate/anchor/marker sweep. The core retains the old signature and passes the current image normalization, geometry, SECTION normalization, VB point/separator hooks, marker constructors, sorting and CJK postpasses. Adaptive OCR refinement remains a *lazy* import of the same public Paddle façade, so UI-time patches still work.
- `ordinary/cjk_marker_reconciliation.py`: independent oversized-Han duplicate-marker collapse and missing-marker rescue, without OCR content acceptance. Calls back through current core CJK column, grayscale/threshold, sorting, Entry constructor and source-pixel operations; the old lazy OCR helper imports are preserved by adjusting only the relative package path.
- Earlier `ordinary/legacy_brightness_sampling.py` and `ordinary/vb_brightness.py` remain separate owners for the VB point, row and vectorized brightness primitives.
- `tests/test_issue562_core_leaf_round17_legacy_20261024.py` characterizes full-white/fallback separator outcomes, reverse transforms, preserved signatures/origins, real-time public monkeypatch seams and CJK no-op guards.
- **Invariant:** Ten package-root Python source modules (no new root shims), unchanged `Entry`/`Geometry` identities, untouched PDIC/PPP/SECTION/raw OCR JSON and crop publishing, and full-resolution source-coordinate marker results. All five historical `processing_core` entrypoints stay callable on their original paths.
- **Acceptance outstanding:** latest exact-head six-configuration CI, three-OS OCR smoke, representative source-page ordinary/OCR/combined scan, crop export, manual edit and PDIC/PPP save/reopen parity. Keep PR **Draft**.


## Round 18 — OCR profile symbols, candidate source mapping and anchor variants (2026-10-24)

- `ocr/symbol_inventory.py` now owns the complete role-aware `_configured_symbol_inventory` implementation: legacy versus explicit v1 symbol inventories, independent standalone-marker and bracket-open roles, saved template modes, role filtering, confidence limits and visual-family collection. The original `paddle_headwords_core._configured_symbol_inventory` remains as a same-signature callable and forwards **current** `_split_configured_symbols`, `visual_marker_samples_from_settings` and `_SYMBOL_FAMILY_BY_LITERAL` on every invocation.
- `ocr/source_candidate_coordinates.py` owns transformation of private axis/coarse/anchor coordinates into public source-image pixel X/Y plus diagnostic header cutoff coordinates. The old `_attach_source_candidate_coordinates` mutates the exact same objects through the new owner; the earlier `source_coordinate_persistence` still strips transient fields before saved JSON.
- `ocr/review_anchor_variants.py` owns `_expand_original_y_fallback_candidates`: independent unchecked original-anchor Y alternatives, deterministic `-rawy` IDs, position groups, no manual override, independent issue lists and unchanged sort order. The historical core function preserves its name/signature/module.
- New characterization suites: `tests/test_issue562_core_leaf_round18_symbols_20261024.py`, `tests/test_issue562_core_leaf_round18_coordinates_20261024.py`; cover preserved role semantics, current core symbol/template callbacks, transformed-to-source coordinates and source-only projection, mutation/ordering and review candidate identity.
- **Invariant:** Root remains exactly ten physical Python modules; no root compatibility stubs; persistent models, raw OCR cache format/fingerprint, PDIC/PPP/SECTION sidecar formats, crop publisher and GUI entrypoints are unchanged. No acceptance threshold or candidate selection outcome was intentionally changed.
- **Acceptance pending:** exact-head six-platform CI, three-OS OCR smoke and independent real dictionary-page ordinary/OCR/combined scan, edit, export and save/reopen parity checks. Keep PR Draft and do not merge automatically.


## Round 19 — complete headword parser and manual review selection (2026-10-24)

- `ocr/lemma_parser.py` now owns the **complete** former `parse_headword_text` implementation (about 11.3 KB source): numbered-prefix / bracketed CJK / pinyin / single-character / Latin / Arabic / Kana profile gates, regex group span and punctuation repairs, grammar tail parsing, normalized lemma creation and `HeadwordParse` construction.
- The old `paddle_headwords_core.parse_headword_text(text, settings, patterns=None, profile=None)` remains a callable at the same module and signature; **16 live dependencies** (including `HeadwordParse`, profile symbol roles, language/script helpers, regex compiler, OCR repairs, parallel/grammar parsers and normalizer) are provided at invocation, not captured at import. No persisted model type moved; no parser thresholds intentionally changed.
- `ocr/review_manual_selection.py` owns three prior core implementations: selected refined/original Y variant exclusivity (manual wins), read-only `<stem>_manual_selection.json` override ingestion and in-memory manual choice/text/engine override application. The core passes its current manual sidecar path function and JSON reader each call. Duplicate `MANUAL_OVERRIDE` issue tags still cannot accumulate.
- Tests `tests/test_issue562_core_leaf_round19_parser_20261024.py` and `tests/test_issue562_core_leaf_round19_manual_20261024.py` check old public signatures/module origins, Latin/Arabic/Japanese parse paths, live patchable collaborators, existing image-coordinate candidate precedence and sidecar roundtrip/error tolerance.
- Package root remains **10** physical Python modules; no new root shim; OCR cache, PDIC/PPP/SECTION schemas, saved manual override keys and crop output publishing stay unchanged.
- **Acceptance pending:** full exact-head CI across Windows/macOS/Ubuntu and Python 3.10/3.13, OCR three-OS smoke, then real representative dictionary-page GUI scan/edit/export and save/reopen parity. Keep Draft and unmerged.


## Round 19 corrective CI fix and Round 20 POS-grammar extraction (2026-10-24)

- The six-platform Round 19 CI on `8507138c` reported a single new test expectation mismatch: `test_issue562_core_leaf_round19_parser_20261024.py` expected `HeadwordParse.__module__ == "picture_capture.ocr.headword_models"`, but the production class deliberately uses the historical `picture_capture.paddle_headwords_core` identity for compatibility. `6c623dc4` corrects the **test assertion only**, checks identity against `core.HeadwordParse`, and does not relocate the class or change any stored object format.
- Round 20 introduces `ocr/pos_cue_policy.py`, now owning the implementations of `_compile_patterns`, `_strip_entry_modifiers`, and `_find_pos_cue`. Core keeps exactly the same public function signatures and module identities while injecting its current `re`, `AppSettings` and patchable `_strip_entry_modifiers` per call.
- The moved logic retains profile-specific Latin-only narrowing of generic lemma regex, invalid user-regex error mapping, POS token-boundary/noise checks, pronunciation exclusions, gender/morphology and Roman-marker removal, and optional numeric prefix cues. No accepted lemma/class/decision rule was intentionally changed.
- New regression `tests/test_issue562_core_leaf_round20_pos_20261024.py` covers signature/origin, Latin profile and invalid regex handling, narrow OCR POS noise, pronunciation/numeric handling and current-core modifier monkeypatch path.
- Root physical Python inventory remains **10**, with no compatibility stub. OCR saved classes, cache, Profile, PDIC/PPP/SECTION and manual selection formats, as well as crop output transactions, remain in their existing owners.
- **Verification requirement:** recheck exact latest-head six-platform CI and three-platform OCR smoke; then perform independent actual dictionary-page GUI scan/edit/export/sidecar reopen. Keep PR **Draft**; never auto-merge.


### Round 20 CI regression correction (2026-10-24)

- CI on `bd16c293` failed during `tests/conftest.py` import: `ocr/pos_cue_policy.py` unintentionally contained `_BUNDLED_PROFILE = load_dictionary_profile(...)`, resulting in `NameError`. The cause was a source-range extraction that captured the *adjacent* grammar-tail wrappers and module globals following `_find_pos_cue`.
- `2696eb03` restored `_leading_inflection_cue`, `_parallel_marker_extension`, `_BUNDLED_PROFILE`, `_USAGE_ABBREVIATIONS`, `_consume_leading_space`, `_parse_structured_tail`, and `_parse_bug_types` to their original `paddle_headwords_core` module and initialization order. `efe20945` removed those unintended definitions from `ocr/pos_cue_policy.py`.
- `141822ad` added an AST contract that the new leaf owns **exactly three** functions and that all original grammar-tail wrappers and bundled dictionary profile still exist at their historical core paths. The intended three POS entrypoints remain wrappers with live dependency injection; no stored type, schema, or user-facing rule change was made.
- Re-run exact-head CI and three-platform OCR smoke before considering the correction verified; real dictionary-page GUI acceptance remains pending, and PR stays Draft.


## Round 21 — CJK OCR lemma prefix and single-Han implementation split (2026-10-24)

- `ocr/cjk_prefix_parsing.py` owns three implementations formerly in `paddle_headwords_core.py`: reject known-but-unconfigured headword symbols; parse configured marker-led CJK+pinyin heads; parse closed/wrapped/marker-only Chinese brackets and Japanese-reading-prefix brackets.
- `ocr/cjk_single_lemma_parsing.py` owns three implementations: parse single Han with optional asterisk/pinyin; construct single-Han `HeadwordParse` visual candidates; parse unbracketed single Han and short variant strings while vetoing radical section labels.
- All six original functions are still defined in `paddle_headwords_core.py` with unchanged signatures and historical `__module__`. Current `_configured_symbol_inventory`, `_is_chinese_ocr`, `_repair_headword_ocr`, `_make_chinese_visual_headword`, ideograph detector, `re`, `unicodedata`, `HeadwordParse` constructor and relevant regex constants/mappings are injected at call time.
- **Previous round regression prevented:** extraction boundaries are explicit per function. Module-level `_CJK_SINGLE_PINYIN_RE`, `_CJK_IDEOGRAPH_RE`, `_CJK_RADICAL_SECTION_RE`, `_BRACKET_CLOSER_BY_OPENER`, and all persisted model definitions remain owned/initialized by the original core. Both leaves have no new runtime regex/profile/model globals. The new leaf method signatures are keyword-only and do not change public facades.
- Characterization tests: `tests/test_issue562_core_leaf_round21_cjk_20261024.py`, including exact AST owner boundaries, core globals, Japanese and Chinese bracket variants, marker allowlists, pinyin/short-Han rescue, radical veto, class origin and live monkeypatch seam.
- Root Python file count remains **10**, no root stubs. No intentional changes to OCR acceptance or manual review, source pixels, PDIC/PPP/SECTION sidecars, serialized candidate schemas, save/reopen or crop publishing.
- **Verification:** Previous Round 20 head `a4e52f32` passed six-platform CI and three-OS OCR Smoke. **Round 21 HEAD must independently pass** six-platform CI and three-OS OCR Smoke, then real page GUI scan/edit/crop/sidecar save-reopen acceptance. Keep PR Draft and unmerged.


## Round 21 CI correction + Round 22 source-pixel OCR band sampling (2026-10-24)

- Round 21 six-OS/interpreter CI on `c9c3ea14` failed only in the new `test_issue562_core_leaf_round21_cjk_20261024.py::test_original_signatures_and_live_single_visual_constructor`: it asserted `__module__` on a test-installed `spy` while `core._make_chinese_visual_headword` was still monkeypatched. Commit `b974aec5` restores the original core callable before its module-origin assertion. No production class or parsing logic changed. The three-OS OCR smoke already passed.
- Round 22 extracted the **complete** original-resolution `unwrap_column_band` implementation to `ocr/column_band_sampling.py`. The original `paddle_headwords_core.unwrap_column_band(image, geometry, column, settings, source_width=None, *, source_rgb=None)` remains at the same historical module/signature. It passes current NumPy, Pillow and page RGB normalizer at call time.
- Preserve non-identity transform cropping, source RGB H×W×3 cache validation (including 4-channel truncation), dynamic curved column left-edge sampling, user width ratio or exact source-width override, white-fill outside the source image, and exact source-top/left-margin return semantics. No OCR source coordinate, serialized cache, PDIC/PPP/SECTION, manual review or crop publication format changed.
- Co-located two minor helpers with existing canonical owners: `_candidate_axis_v` implementation in `ocr/source_candidate_coordinates.py` and `_looks_like_marker_noise_lemma` in `ocr/lemma_parser.py`. Core aliases retain the same signatures/module identities and current regexp callback.
- New tests `tests/test_issue562_core_leaf_round22_band_20261024.py` cover source-pixel sampling and white margin, precomputed RGB parity and invalid array rejection, transformed crop route, live normalizer, both helper contracts, and an AST guard against accidentally moving adjacent module initializers or more than the intended function.
- Root physical Python modules remain **10**, without new root shims. Before considering this accepted, check exact-head six-platform CI, three-OS OCR Smoke, and independent real scanned dictionary GUI ordinary/OCR/combined edit/export/PDIC/PPP reopen parity. Keep PR Draft and unmerged.


## Round 23 — large processing-core algorithms split (2026-10-24)

The preceding Round 22 head `2578c5c4` passed exact-head six-platform CI and three-OS OCR Smoke. Round 23 targets three **complete** nontrivial source-pixel algorithms, not a rename of existing delegates.

- `quality/detection_entry_fusion.py` now owns the ~14 KB ordinary/OCR event fusion implementation: globally ordered one-to-one candidate pairing, rejected OCR latent evidence enrich/veto, full-white boundary veto protection, oversized single-Han forward occupancy suppression, ordinary-vs-OCR position arbitration, issue annotation, and strict final dedup. `processing_core._fuse_detection_entries` keeps its seven-argument historical signature, supplies **12 live core collaborators** per call, and preserves `Entry` instances and original pixel coordinates.
- `geometry/column_path_tracking.py` owns the ~5 KB curving/deformed text-column X/Y tracking algorithm (adaptive dark mask, regional edge strength and rules suppression, missing-block fill, slope smoothing, source-resolution anchor construction). `processing_core._estimate_column_paths` keeps its historical eight-argument signature, passing its current tracking constants, mask helpers, `np`/`ImageOps`, smoothing and **original `ColumnPath` constructor**. `Geometry`, `ColumnPath` and other persisted/public models do not move.
- `ocr/ordinary_marker_text_enrichment.py` now owns the ~8 KB multi-engine OCR text fill workflow on existing ordinary lines: CJK large-vs-regular crop decisions, profile-aware parser/bracket handling, channel selection, replacement rules, manual selection guards, stats, and hard source-X/Y invariants. `processing_core.ocr_existing_entry_words_from_markers` retains its existing signature, delegates with live core crop/geometry/sort/text helpers, and does not change the persisted entry count or PDIC/PPP sidecar contracts.
- New regression suite `tests/test_issue562_core_leaf_round23_large_split_20261024.py` characterizes three single-function leaf owners using AST boundaries, exact historical core signatures/origins, current monkeypatch callbacks, no-op fusion ordering, flat source-pixel path anchors and marker OCR delegation. Full pre-existing fusion and marker text OCR regression suites continue as acceptance gates.
- `processing_core.py` shrunk by approximately **24 KB** this round; root stays at 10 physical Python modules with no compatibility stubs. No intentional changes to GUI entrypoints, printed scan coords, OCR review cache, manual override, crop publishing transaction, PDIC/PPP/SECTION formats or models.
- **Round 23 acceptance:** exact latest-head six-platform CI and three-platform OCR smoke and independent real-page GUI scan/edit/crop/sidecar save-reopen parity. Keep PR Draft, do not auto-merge.


## Round 23 CI correction and Round 24 — six algorithm-owner extractions (2026-10-24)

**Round 23 CI issue:** The exact `af34d8e1` CI failed five legacy *source-location* tests (entry-classification, entry crop policy, shared OCR channel, ordered marker matching, bracketed OCR) that searched `processing_core.py` for implementation text after complete algorithms were moved. All five tests are now updated to validate the historical **core compatibility facade and canonical leaf implementation together**, preserving channel, crop, language-policy, and ordered-matching requirements. There was no runtime assertion failure in that run; the 3-OS OCR Smoke succeeded.

**Round 24 implementation:** Six complete algorithms now live in package submodules; all public/historical signatures and `__module__` origins remain available from `processing_core` with live call-time callbacks:
- `detection/page_method_dispatch.py`: Project Profile-aware ordinary, OCR and combined detection dispatch, cached candidate reading, source/SECTION eligibility and ordered results. Core forwards current detector, layout/geometry, image preprocessing, fusion, sorting and JSON callbacks.
- `refinement/existing_entry_positions.py`: original image-to-canonical Y refinement for existing entries, optional whole-column verified ink-top shift, max-shift clamp and original-source coordinate projection. Core forwards live column index, pixel scaler, NumPy/Pillow and original dataclass `replace` function.
- `ocr/legacy_entry_text_reading.py`: existing text-only OCR of entry crops with profile-guarded CJK brackets, selected Paddle/Tesseract engines, user replacement rules and reading order. Core forwards its current geometry, line box, engine and text-processing callbacks.
- `crop/illustration_export.py`: complete standalone/associated PPP illustration crop export, mask/alpha/transparent-background behavior, skipped contained/partial polygons, names/manifest, staged plan, stale outputs and **atomic publish/rollback**. Core forwards all current plan, image, staging, publish and persisted model constructors.
- `crop/illustration_source_bounds.py`: source-space image-crop top/bottom/margin policy under identity/mirrored vs rotated layout transforms, SECTION bounds and canonical-pixel settings.
- `crop/single_line_export.py`: complete SW single-line crop staging and manifest output, stale cleanup and atomic publish preserving current entry geometry and whitened source preprocessing.

**Safety/compatibility:** No persisted `Entry`, `Geometry`, `CropRecord`, `IllustrationSplitResult` or other class moved. No root compatibility shims created; root remains **10 .py files**. No intended changes to source coordinates, PDIC/PPP/SECTION, manual selection schema, OCR caches, GUI routing, WW/SW/PPP naming, manifest content or atomic crop semantics. New targeted tests `test_issue562_core_leaf_round24_detection_20261024.py` and `test_issue562_core_leaf_round24_crops_20261024.py` include AST one-function leaf boundaries, exact historical signatures and call-time patch seams. Existing end-to-end regression suites and golden fixtures remain required.

**Acceptance:** Run exact latest-head six-platform CI and three-platform OCR Smoke; independent genuine page ordinary/OCR/combined GUI scan, editing, crop and PDIC/PPP save/reopen acceptance is still outstanding. Keep PR **Draft** and unmerged.


## Round 25 — OCR runtime, image geometry, refinement, and crop jobs (2026-10-24)

- Previous Round 24 head `d6fc435f`: **Windows/macOS/Ubuntu OCR smoke succeeded**; six-job full CI was still queued at the time of Round 25 implementation. No early claim of a green baseline is made.
- `ocr/paddle_engine_lifecycle.py`: moved implementations of `clear_paddle_engine_cache`, `get_paddle_engine`, and `run_paddle_band`. The original `paddle_headwords_core` owns `_ENGINE_CACHE`, `_ENGINE_CACHE_LOCK`, `_RAW_OCR_THRESHOLD` and all three historical signatures. Each call passes the current cache/lock, garbage collector, language/device selector, Windows GPU DLL setup route, preprocessing, image arrays and OCR record class. Preserve lazy Paddle import, legacy no-MKLDNN flag fallback, cache eviction and band-coordinate inversion.
- `ocr/tesseract_subprocess.py`: moved the complete old Tesseract subprocess invocation and RGB PNG stdin encoding. The core retains `run_tesseract(image, language, executable="tesseract", psm=7)` with current discovery, subprocess, PNG and source RGB dependencies; retain timeouts and failure messages.
- `refinement/existing_entry_workflow.py`: moved the complete `refine_existing_entries` orchestration and source-image context disposal, keeping core geometry and saved-marker refiner callbacks live.
- `illustration/ppp_detection_update.py`: moved complete `detect_illustrations_to_ppp` logic while preserving manual PPP shapes, replacing only AUTO shapes, refusing overlaps and calling the old ordered-PPP writer.
- `illustration/crop_box_policy.py`: moved `illustration_polygon_box` physical source-X/Y clipping policy with the current `clamp_box` callback.
- `crop/spawn_job_owners.py`: moved both spawn-safe WW and PPP crop worker implementations. `processing_core.split_whole_entries_job` and `processing_core.split_illustrations_job` keep original importable names, signatures and current PDIC/PPP reader, crop publisher and previous-page relation callbacks.
- **Nine production implementation functions** moved in this batch. No persisted class (Entry, OCRRecord, CropRecord, IllustrationSplitResult, etc.) was moved. The two core modules decreased by roughly 4.7 KB net because history-preserving signature wrappers remain. Package root remains **10 .py files**, no new root-level shims.
- Tests `tests/test_issue562_core_leaf_round25_paddle_20261024.py` and `tests/test_issue562_core_leaf_round25_processing_20261024.py` test AST boundary, historical call signatures/model origins, engine cache reuse and raw OCR source coordinates, subprocess invocation, PPP manual-annotation persistence, source crop clipping and live multiprocessing job readers. Existing larger suites remain required.
- **Release gate:** exact-head 6-job CI and 3-OS OCR Platform Smoke must pass; actual dictionary-page GUI ordinary/OCR/combined scan, manual correction, image export and PDIC/PPP save-reopen parity remain independent acceptance gates. Keep PR Draft and do not merge.


## Round 26 — 7 source-pixel geometry, spawn and atomic crop staging implementations (2026-10-24)

Previous Round 25 head `200bdd3c`: Windows, macOS and Ubuntu OCR Smoke **all passed**, while the main six-platform CI remained queued as this batch began. All new code remains unmerged in Draft PR #663.

**New implementation owners:**
- `geometry/page_runtime_context.py`: moved `_page_geometry_context` Profile resolution and disposable analysis-image/geometry construction, preserving source-image pixels and current preprocessing/Profile/geometry callbacks. Historical `processing_core._page_geometry_context` retains its signature/module origin.
- `detection/spawn_job_execution.py`: moved `detect_entries_job` one-page spawn-safe ordinary-marker scan, SECTION read and PDIC commit. `processing_core.detect_entries_job` retains the importable top-level function, original source width/coordinate semantics and live PNG/detector/PDIC hooks.
- `illustration/source_detection_jobs.py`: moved `detect_illustration_regions` image-file loading and disposable source RGB detection, plus `detect_illustrations_job` background-safe PPP update dispatch. Both historical core APIs remain unchanged; source file and detection functions are passed on each call.
- `crop/image_staging_io.py`: moved `_save_crop`, `_stage_text_file`, `_stage_crop` actual implementations. Persisted source cropping, alpha conversion and path clamping remain the same. UTF-8 staging continues to flush/fsync to temporary files without publishing early. Failure cleans up partially written temporary output, and crop/transaction callbacks remain dynamically patchable. Atomic publish is still performed by the existing caller once all pieces are successfully staged.

**Compatibility regression suites:** `tests/test_issue562_core_leaf_round26_page_jobs_20261024.py` checks exact AST ownership, untouched historical signatures, live geometry callbacks, source image and one-page PDIC context, and illustration jobs. `tests/test_issue562_core_leaf_round26_staging_20261024.py` checks exact AST ownership, live crop staging hooks, source pixel crop parity, UTF-8 manifest writes and failure cleanup.

**Scope:** Seven complete function bodies migrated into four new leaf modules. No `Entry`, `Geometry`, `CropRecord`, `IllustrationSplitResult` or other class moved; no root compatibility shims created; package root remains ten Python modules. Core source size is nearly unchanged because call-time injection and full historic signatures are retained in the compatibility entrypoints. No intentional alterations to OCR parsing, cache data, source pixel coordinates, manual edits, PDIC/PPP/SECTION metadata, temp filename formats or crop publish semantics.

**Acceptance gate:** exact Round 26 HEAD six-platform CI and Windows/macOS/Ubuntu OCR Smoke must pass independently; representative real dictionary page GUI ordinary/OCR/combined scan, editing, crop and PDIC/PPP save/reopen parity remains outstanding. Keep PR Draft and do not merge automatically.


## Round 26 CI correction and Round 27 — physical model ownership with historical pickle identity (2026-10-24)

The exact Round 26 CI job set on `3caa91d1` reported **14 failures** on Ubuntu/Python 3.10 and Windows. The core runtime cause was three accidental `deps={{...}}` set-of-dict literals in the `detect_entries`, `_refine_existing_entries_with_geometry` and `ocr_entries` historical façades, causing `TypeError: unhashable type: 'dict'`. Commit `e2892160` repairs all three to `deps={...}`. Four other existing source-location checks were updated to follow historical facade -> canonical owner without removing the original guarantees: auxiliary-line planning now includes `crop/illustration_export.py`; Paddle GPU DLL import timing is validated in `ocr/paddle_engine_lifecycle.py`; marker Y refinement and shared separator-Y caller are verified in `refinement/existing_entry_positions.py`. The corrections are test/compatibility fixes, not change requests for OCR behavior. Previous Round 26 three-OS OCR Smoke passed, but its full CI did not.

**Round 27 genuine class ownership extraction:** eight dataclass definitions (~3.6 KB) are no longer physically in `processing_core.py`. `geometry/processing_models.py` defines `ColumnPath` and `Geometry`; `crop/plan_models.py` defines `CropRecord`, `EntryCropPiecePlan`, `IllustrationCropPlan`, `PageCropPlan`, `IllustrationCropEvent`, and `IllustrationSplitResult`. The core imports **these exact objects** and resets `__module__ = "picture_capture.processing_core"` explicitly for each; it does not introduce subclass proxies or change field order/defaults/slots/sequence behavior. Historical `from picture_capture.processing_core import Geometry/CropRecord/...` and pickle class lookup identity must stay compatible for older projects, Python subprocess workers and downstream modules.

New `tests/test_issue562_core_leaf_round27_model_compat_20261024.py` asserts AST class ownership, class `is` identity in both domains and old core, historical `__module__` and `__qualname__`, pickle roundtrips of classes/Geometry/crop plans/results, coordinate conversion and class field/sequence semantics. Also adds an AST guard requiring actual `ast.Dict` in all three formerly malformed `deps` call-sites. Existing tests/fixture serialization checks remain essential.

Physical Python root count still **10**; no root stubs added. `processing_core.py` shrank a further approximately **2.9 KB** after model relocation. No intentional changes to source pixel geometry, PDIC/PPP/SECTION, cached OCR/morphology model representations, manual overrides, WW/SW/PPP naming or transactional export. Round 27 must pass **its own** six-job CI and three-OS OCR Smoke, and real dictionary GUI ordinary/OCR/combined scan/edit/export/save-reopen acceptance remains outstanding. Keep PR **Draft** and do not merge.


## Round 28 — high-volume Tk GUI method extraction (~39 KB removed from root app, 2026-10-24)

Round 27 `b4e8c9c0` OCR smoke on Windows/Ubuntu succeeded while macOS and the remaining full CI jobs were still queued at the start of Round 28. The main UI extraction proceeds on the same Draft PR but must pass its own head-specific automation independently.

Four substantial original `PictureCaptureApp` methods are now physically implemented by three UI owners, not copied into root-level duplicate modules:
- `ui/main_appearance_policy.py` owns `_configure_global_appearance` (~5.8 KB) and `_configure_main_workspace_styles` (~6.6 KB). Entire Tk theme selection, PC.* opt-in component styles, control colors and scoped dark/light appearance policy are retained. The old class method names/signatures remain in `app.py` and inject the currently imported `ttk`, `tk`, `normalize_appearance_mode` and `appearance_palette` globals per call.
- `ui/quick_settings_apply.py` owns `apply_quick_settings` (~7.6 KB): Profile percentage to source-image pixels, quick-field type/range validation, header/footer limits, content font normalization, OCR/Lens choices, UI-only diagnostic controls, optional persistence, redraw and error reporting. The original app method retains exact defaults/kwargs and passes live conversion/validator constants/modules per call.
- `ui/detection_batch_execution.py` owns `_detect_pages` (~21.8 KB): ordinary/OCR/combined multi-page single-writer batch flow, human/manual PPP flush, source pixel/PDIC preservation, OCR restart checkpoints, per-page final decision audit, staged GPU and CPU pool options, worker resource handling, progress reporting and final quality/performance summary. Its local imports now use the correct parent-package paths from `ui/`. The original `PictureCaptureApp._detect_pages(self, indices, *, method, force_refresh)` stays top-level as a class method with its exact signature and 20 current live dependency globals (including `messagebox`, `os`, `ProcessPoolExecutor`, `detect_entries_job`, PDIC save and reading helpers).
- **Actual reduction**: `app.py` decreases from ~340,021 bytes to ~301,215 bytes, net **38,806 bytes**, despite retaining four explicit method facades and three submodule imports. Package root still has ten physical `.py` files; no new root shims. Tk event registration, old callback assignment signatures and monkeypatch surfaces remain on `PictureCaptureApp`.

Safety: existing source-location tests in ordinary CPU pool/parallel dispatch, OCR checkpoint, ordered PDIC final audit and combined blank-only OCR text protection are updated to inspect both the retained `app.py` adapter and canonical `ui/detection_batch_execution.py` implementation. Assertions for single-writer scheduling, manual PPP safety, forced refresh, save-before-final-audit and no-overwrite of manually selected OCR text were **not** deleted. New `tests/test_issue562_ui_round28_large_batch_20261024.py` verifies the exact AST module owners, old public signatures, call-time injected app global patch seams, no-project early exit and ordering of critical PDIC/OCR transactions.

No intended change to physical pixels, Profile, GUI menus, PDIC/PPP/SECTION sidecars, OCR resume cache, crop publishing or persisted class identity. Exact Round 28 SHA must independently pass six-job CI and three-OS OCR Smoke; real scanned dictionary GUI scan/edit/crop/save-reopen acceptance still awaits a human run. Keep PR Draft and do not merge.


## Round 28 CI source-location corrections + Round 29 UI widget construction extraction (2026-10-24)

- **Round 28 failed CI** on `9477d640`: the complete test matrix reported ~15 legacy source-location assertions still reading the physical `app.py` for appearance, quick settings, and detection orchestration implementations, which had been moved to `ui/main_appearance_policy.py`, `ui/quick_settings_apply.py`, and `ui/detection_batch_execution.py`. No new production runtime behavior failure was established by those assertions. Windows/macOS/Ubuntu OCR Platform Smoke all passed.
- Updated all identified failing assertions to inspect **both** the original `PictureCaptureApp` adapter and the actual owner. Coverage retained for ttk theme palette/listbox colors, rail/treeview density, source-to-percent field validation and OCR/Lens propagation; per-page PDIC single-writer, manual PPP preflight, source image masking, combined blank-only OCR and final-decision audit remain covered. This is an ownership update to existing tests, **not removal** of behavior checks.

**Round 29 actual implementation extraction:**
- `ui/main_workspace_build.py`: physically owns `PictureCaptureApp._build_ui` widget creation and callback wiring (~15.3 KB): permanent status bar, batch progress, page tree, navigation rail, canvas and source-coordinate pointer binds, selected-section layout, toolbar/sidebar installation. Historical `PictureCaptureApp._build_ui(self)` remains callable with exact signature from `app.py`; current `ttk` and `tk` modules are injected at call time. Relative package import of `workspace_tools` is correctly resolved inside `ui/`.
- `ui/settings/interactive_panels.py`: physically owns `SettingsDialog._add_check_group` and `SettingsDialog._scrollable_settings_page` (~9.4 KB): grouped advanced settings with check-help bindings, multi-column responsive settings frame, help section with live textvariables, scroll region and mousewheel controls. Historical methods remain on `SettingsDialog`, unchanged in signature and widget lifecycle, with current Tk/ttk callback modules supplied per call.
- Root `app.py` decreases another **23,616 bytes** to **277,599 bytes** (about 340 KB → 278 KB across Round 28+29, net −62,422 bytes). Package root remains **10 Python files**, with no root shims and no moved persisted model classes.
- Updated source-location checks for `ui/settings/interactive_panels.py` and `ui/main_workspace_build.py` (settings help live binding/wheel, checkbox help layout, modern workspace and page controls). Added `tests/test_issue562_ui_round29_widget_owners_20261024.py` asserting AST owner boundaries, original public class method signatures, live Tk/ttk forwarding, main canvas/status ordering, and help/checkbox behavior.

**Acceptance gate:** require full 6-job CI and three-OS OCR Smoke for the *exact latest HEAD*. Existing GUI source-image/manual-entry/crop/PDIC/PPP save-reopen parity remains a separate manual release gate. PR must remain **Draft**, do not merge.


## Round 29 CI location guard repair and Round 30 validated Settings/Review migration (2026-10-24)

**Prior head `b696e6b7`**: OCR Smoke fully green on all three operating systems; six-job CI failed because approximately 25 existing tests were still searching `app.py` for formerly in-class workspace widgets, page tree, canvas bindings, SettingsDialog scroll/help construction and appearance behavior. The failures were assertions against source-location, not established production runtime faults. Updated legacy source-based tests across `test_auxiliary_lines_issue428`, `test_core`, `test_image_metadata_status`, `test_index_first_workspace`, `test_next_stage_regressions`, `test_page_range_enter_jump`, `test_review_window_compact_height_and_zoom`, `test_settings_runtime_audit` and `test_sidebar_divider_toolbar`. Each now checks the retained app method delegation and the implementation owner, preserving original UI/PDIC/tab/keyboard invariants.

**Round 30 implementation ownership:**
- `ui/settings/field_form_runtime.py` now physically owns `SettingsDialog._setting_widget` (OCR/lang/wordslist/layout font/picker controls), `SettingsDialog._add_setting_group` (responsive unit/help/field rows) and `SettingsDialog.save` (field validation and percent-to-source-pixel mapping, OCR/language fallbacks, headword rule parse, Profile writes, settings storage, font normalization and redraw). All original SettingsDialog method signatures, error reporting, persist/close behavior and app-module runtime patchpoints remain intact via injected globals; no migrated dataclasses.
- `ui/review_style_policy.py` physically owns `ReviewWindow._configure_review_styles` scoped PCR.* widgets and dark/light color palettes. Historical ReviewWindow entrypoint and live `ttk`/`appearance_palette` are preserved.
- `app.py` decreased another **16,694 bytes** to **260,905 bytes**, cumulative reduction from before Round 28 about **79.1 KB**. New owner tests in `tests/test_issue562_ui_round30_form_review_20261024.py` cover AST exact owner functions/valid syntax, unchanged method signatures, live monkeypatch callbacks and preserved Profile/rule/color validations. Color picker and validate-before-mutation regression tests now inspect owner through historical façade.
- Root physical Python files remain **10**; no root alias stubs. No intentional changes to settings JSON, Profile rules, PDIC/PPP/SECTION, source pixel geometry, OCR cache, canvas editing or crop export; existing behavioral regression suites remain required.

**Acceptance:** require exact Round 30 HEAD full six-job CI and three-OS OCR Smoke, plus separate real dictionary GUI scan/manual correction/export/PDIC-PPP save-reopen parity. Keep PR #663 Draft, do not merge.


## Round 30 CI source-owner correction and Round 31 runtime/UI extraction (2026-10-24)

**Round 30 failure at exact HEAD `7f0609ef`:** six-platform CI reported 11 failures, all legacy assertions against physical `app.py` code that had moved to `ui/settings/field_form_runtime.py` or `ui/review_style_policy.py`; the three-OS OCR Platform Smoke was fully green. Corrections updated the existing `test_core`, `test_next_stage_regressions`, `test_page_range_enter_jump`, `test_settings_illustration_tab`, `test_ui_settings_crop` and `test_windows_at_font_overlay` suites to verify current canonical owners **and** original class entrypoints, preserving UI validation, normalized floats, cropping settings, Windows font exclusion, style palette and quick page navigation tests.

**Round 31 six complete method bodies migrated into four real UI implementation owners:**
- `ui/background_job_runtime.py`: original `_start_ui_worker` and `_poll_ui_worker_queue` generation-based, close-safe, nonblocking worker lifecycle. Core `PictureCaptureApp` methods keep old signatures, patched `threading`/`traceback`/`queue`/`tk` globals and main-thread Tk event scheduling. Preserve stale-job suppression, waiting for durable writes at close, GUI callback error handling and bounded 48-message drain.
- `ui/quick_settings_sync.py`: full `sync_quick_settings` state reflection and source-image pixels ↔ Profile percentages, font normalization, bool/color choices and Lens state. Original method forwards live conversion helpers and current field constants. `_quick_syncing` is reset in a `finally` block.
- `ui/paddle_environment_report.py`: full `_paddle_environment_text` OCR runtime report (PaddleOCR/PaddleX/PaddlePaddle, PP-OCRv6 threshold, CPU vs GPU, available CUDA). Original `PictureCaptureApp._paddle_environment_text` receives current `importlib_util` and device selection callback per call.
- `ui/main_action_buttons.py`: full sidebar and footer action button construction with original emphasized/neutral style semantics, source widget references and live `ttk`/`tk` modules. Historical `_sidebar_action_button` and `_footer_action_button` signatures remain unchanged.

Root `app.py` further decreased **9,058 bytes** to **251,847 bytes**; root physical modules still **10**, no compatibility stubs. Added `tests/test_issue562_ui_round31_runtime_20261024.py` verifying exact AST ownership and syntax, old signatures and module identity, patched call-time dependencies, worker generations without worker-thread Tk callbacks and `finally` quick-state restoration. Updated existing tests for original footer/worker facades plus canonical modules; older behavioral suites remain required.

**Acceptance:** exact latest-head six-job CI and three-OS OCR Platform Smoke, plus independently executing genuine dictionary GUI ordinary/OCR/combined scans, text correction, pixel-aligned crops and PDIC/PPP save-reopen parity. Keep PR Draft, unmerged.


## Round 31 CI correction and Round 32 — two full Tk window constructors (2026-10-24)

**Round 31 CI `3d49e68a`:** Windows/macOS/Ubuntu OCR Smoke all passed. Four initial pytest jobs exposed exactly two *source ownership* failures in `tests/test_next_stage_regressions.py`: (1) sidebar button `highlightthickness=1` was moved to `ui/main_action_buttons.py`; (2) generation-based background worker close-wait and callback state moved to `ui/background_job_runtime.py`. Corrected both source audits to validate **original PictureCaptureApp façade → canonical owner**, without removing button/chrome checks, critical write close waiting, stale generation detection or UI-only delivery guarantees. No new runtime failure was shown in those logs.

**Round 32 large constructor extraction:**
- `ui/settings/dialog_initialization.py`: complete ~24 KB `SettingsDialog.__init__` implementation after the original `tk.Toplevel.__init__` call, including window/workarea geometry, Settings Center tabs, standard/advanced parameters, Profile/help/illustration/REF/inference/crop setup, notebook handlers, live color/font selection and responsive text, modeless behavior, autosave `trace_add` hooks, validated close handling.
- `ui/review_window_initialization.py`: complete ~16 KB `ReviewWindow.__init__` body after the original Tk `super()`, including compact-workarea geometry/titlebar-safe positions, ordinary/large-letter crop sizing, wordslist and online lookup state, auto OCR/review modes, editing/digit map controls, filtered-review cache, UI render/prefetch jobs, style/build calls and after-idle final layout, guarded close and per-var persistence callbacks. Intra-package import of `_preset_work_geometry` now points to the same `ui.workspace_tools` owner via a local relative import.
- Both old constructors stay **on their original `SettingsDialog` and `ReviewWindow` classes in `app.py`**, with identical positional/keyword signatures and the original **zero-argument `super().__init__(parent)`** executed **before** calling the corresponding new leaf. This preserves Tk widget initialization/MRO semantics, and forwards all used runtime helpers, parser choices and Tk modules through live `deps` dictionaries; no new root shims or stale import-time snapshots.
- Original `app.py` further decreased **40,964 bytes** from 251,847 to **210,883 bytes**. The package root still has **10 physical `.py` files**; no persisted model class or sidecar schema was relocated.
- Regression `tests/test_issue562_ui_round32_window_init_20261024.py` checks leaf AST/syntax owner boundaries; old API signatures/module; Toplevel super-before-delegate call ordering via synthetic, no-display test doubles; current Tk/ttk/Profile dependencies; Settings Center help/autosave/non-modal semantics; and compact Review workarea, after-idle layout and callback wiring. Existing full suite remains mandatory.
- Proactively updated Settings Center/source location regressions and legacy `test_core.py` ReviewWindow source assertions to use the new owner **in addition to** historical class methods. Preserve negative assertions and no-real-GUI regressions.

**Acceptance:** exact latest Round 32 SHA must pass all six CI matrix jobs and the three-platform OCR Smoke. A real dictionary-page GUI ordinary/OCR/combined scan, hand corrections, exports and PDIC/PPP save-reopen check remains a separate gate. Draft PR #663 stays open and unmerged.


### Round 33 — main Tk application startup and resolved appearance (2026-10-24)

Moved the complete post-`tk.Tk.__init__` startup implementation (session state, widget model variables, worker queues, controller wiring, theme and layout initialization, after-idle hooks) to `ui/main_app_initialization.py`. `PictureCaptureApp.__init__` remains the original class entrypoint and still executes the Tk superclass first, then forwards live dependencies, including the original `app.py` path for icon resource resolution. Also moved the complete theme reconfiguration implementation to `ui/appearance_resolution.py`, adjusting its imports from `ui/` while retaining call-time live palette/normalizer/Tk hooks. Added `tests/test_issue562_ui_round33_app_startup_20261024.py` with AST ownership and super/delegation seam regression checks. No project data-class, PDIC/PPP, OCR cache, physical root Python count (10) or serialized path changes. Full six-job CI and three-platform OCR Smoke plus manual representative-page GUI acceptance are still mandatory; keep the PR Draft and unmerged.


### Round 33 CI GUI construction fix

Six-matrix CI pytest passed its source contracts but the actual Tk GUI construction smoke exposed a missing call-time `LATIN_ORDER` dependency in the relocated SettingsDialog constructor. Explicitly supply the canonical app-module constant to `ui/settings/dialog_initialization.py` and guard the forwarding seam in `test_issue562_ui_round32_window_init_20261024.py`. No change to collation or Settings behavior; owner receives the exact previous constant.


Round 33 follow-up: F821 lint diagnosed twelve annotation-only names in the new post-Tk startup owner that no longer inherited imports from `app.py`. Resolved via explicit `TYPE_CHECKING` imports of existing canonical models/PreprocessAnalysis/dialog classes, and widened only the local `review_window` reference annotation to its Tk base (`tk.Toplevel`) so no new UI→`app.py` import cycle is introduced. Runtime behavior and persisted class identities remain unmodified.


### Round 34 — Profile Wizard three large method implementations (2026-10-24)

Moved complete `ProjectProfileWizard._build_vars` to `profile/wizard_state_initialization.py` and `_build_template_tab` plus `_build_headword_tab` into `profile/wizard_tab_builders.py`. Historical wizard class methods retain original names and call signatures; all module-configured language, template, headword role constants and Tk modules are supplied at call time, not frozen in imported aliases. New AST and live-hook characterization tests `tests/test_issue562_profile_wizard_round34_20261024.py`. No Profile schema, PDIC/PPP, OCR cache, UI labels, callback ordering, or persisted model identity changes. Exact-head six-platform CI and OCR smoke remain mandatory. PR stays Draft pending independent physical page verification.


Round 34 CI source-contract update: four `tests/test_next_stage_regressions.py` checks now traverse the stable `ProjectProfileWizard` wrapper and physical `wizard_tab_builders.py`/`wizard_state_initialization.py` for unchanged page template, CJK bracket and headword structure UI wording, column nudging and persistence guards. No production semantics changed by this test-only adjustment.


### Round 35 — Profile Wizard template preview / settings assembly / image workspace / coverage diagnostics (2026-10-24)

Migrated complete `_refresh_template_preview`, `_settings_from_ui`, `_build_right_image_workspace` and static `_validation_coverage_summary` implementations into `profile/wizard_template_preview.py`, `profile/wizard_settings_assembly.py`, `profile/wizard_workspace_builder.py` and `profile/wizard_validation_diagnostics.py`. Historical `ProjectProfileWizard` class method names, signatures, worker snapshots, UI thread callback split and live import-level dependencies remain through wrappers. Tests moved their source ownership checks without dropping semantic assertions; new characterization tests exercise wrapper dependency seams and important OCR/column/headword guards. No profile schema, OCR cache or PDIC/PPP format change. Six-platform CI/OCR smoke and manual true scanned GUI checks remain necessary. Keep Draft.


Round 35 CI source contracts: appearance, template worker, profile settings/column nudging and diagnostic checks now inspect the physically relocated owners, retaining the previous layout, OCR and image invariants. Inner worker indentation now matches a top-level owner rather than a class method.


### Round 36 — multi-page validation, overlays and feedback (2026-10-24)

Moved six complete implementations out of `profile/setup.py`: `validate_profile` to `wizard_validation_execution.py`, `_build_validation_tab` and `_apply_validation_feedback` to `wizard_validation_controls.py`, and `_marker_preview`, `_render_validation_result`, `_finish_validation` to `wizard_validation_visuals.py`. The original `ProjectProfileWizard` methods, static entrypoint and class/pickle identity remain intact, with explicit call-time forwarding of all live configured dependencies. The OCR verification worker retains forced PaddleOCR refresh, image and settings snapshots, cooperative cancellation and UI-thread completion, with no new PDIC/PPP writes. Image overlays retain translucent marker masks; feedback retains profile-specific CJK rules, revision checks and bounded tuning. Added `tests/test_issue562_profile_wizard_round36_20261024.py`; existing source-owner assertions check migrated implementations rather than abandoned line locations. CI matrix and three-OS OCR smoke plus real scanned-page GUI acceptance remain required. Keep PR Draft and unmerged.


Round 36 first CI revealed three stale test-only source slices still expecting the validation overlay, UI rendering and background queue to physically live in `profile/setup.py`. Assertions now inspect `wizard_validation_visuals.py` and `wizard_validation_execution.py` behind verified old-class forwarding methods, retaining opacity, themed display, batch-gating and worker snapshot checks.


### Round 37 — Representative-page thumbnails, slot selection and async layout analysis (2026-10-24)

Physically extracted 13 `ProjectProfileWizard` methods from `profile/setup.py` to two canonical modules: `wizard_sample_thumbnails.py` owns group rendering/loading, full-set thumbnail decode, per-slot replacement/polling, cell rendering and the complete manual page picker. `wizard_sample_analysis.py` owns asynchronous representative-page layout estimation, queue polling, revision-guarded aggregation and explicit application of layout suggestions. All historical method names/signatures remain on the wizard class and pass live runtime helpers at call time. Threads still only read snapshot indices/paths/settings/images, with Tk cell materialization on the main thread. Slot changes only refresh the affected cell and visible template preview; stale generation/revision results are rejected. Automatic analysis still requires sufficient successful samples; no settings/PDIC/PPP persistence schema changes. New test file `tests/test_issue562_profile_wizard_round37_20261024.py` and existing source-location tests cover delegation, snapshots, stale work and single-slot invariants. Keep Draft pending CI (six OS/Python matrix), OCR smoke and manual scanned-page acceptance.


Round 37 follow-up check: architecture guard rejected one incorrectly generated multiline function signature in the thumbnail renderer; corrected it without behavioral changes. Later pytest identified three old source-location assertions for column offsets, body indent coupling and verified ink-height application, now pointing to `wizard_sample_analysis.py` behind checked legacy wrappers. Underlying offset, height and conservative auto-apply assertions remain unchanged.


### Round 38 — Wizard shell, reading/OCR controls and headword explanations (2026-10-24)

Moved twelve complete `ProjectProfileWizard` implementations from `profile/setup.py` to three leaf modules: `wizard_shell_builder.py` takes `_build_ui`, `_apply_initial_pane_split`, `_apply_left_wraps`, `_show_right_image_page`, `_on_wizard_tab_changed` (persistent 40:60 panes and four-tab navigation); `wizard_reading_controls.py` takes `_build_reading_tab`, `_build_language_section`, `_body_page_range_changed`, `_refresh_language_summary` (dictionary identity, OCR/index language and body-range representative reselection); `wizard_headword_explanations.py` takes `_refresh_headword_description`, `_refresh_headword_structure_summary`, `_refresh_headword_specificity_visibility` (CJK/Latin descriptive help and conditional symbol/tail panels). Class methods remain in `setup.py` as original signatures and patch seams, forwarding call-time live references into physical owners. `__init__`, data storage and Profile persistence remain untouched. No new root compatibility stubs. New `tests/test_issue562_profile_wizard_round38_20261024.py` checks AST ownership, live injected references, preserved keyword-only `row`, 40:60 layout/four tabs, OCR language/body-page range settings and headword visibility. CI and three-OS OCR Smoke and representative-page manual acceptance remain gates; keep Draft.


Round 38 first-CI source-contract adjustment: after moving reading-tab composition and representative photo creation, the existing illustrated-mode router and appearance regression tests now verify `wizard_reading_controls.py` and `wizard_sample_thumbnails.py` with corresponding old-class delegation, rather than requiring implementation strings in `profile/setup.py`. Original illustrated-only scan gate and themed image rendering checks are retained.


### Round 39 — Profile save flow, revision events and visual marker controls (2026-10-24)

Physically moved **25** complete methods from `profile/setup.py` into `wizard_persistence.py` (five functions: partial draft persistence, explicit step saves, confirmation, close/cancel/validation-cooperative stop), `wizard_profile_events.py` (fourteen reading/headword defaults, revision invalidation, CJK normalization and tuning events), and `wizard_visual_markers.py` (six visual symbol inventory summaries, capture dialogs, sample replace/delete, versioned JSON serialization). Original `ProjectProfileWizard` class and each legacy method signature are retained as thin delegates. All external dependencies are forwarded from the module at call time, preserving test patch seams and avoiding `.setup` circular imports. Original settings/profile persistence (`copy_settings`, `settings_path`, `write_project_profile`, `profile_path`, `sync_quick_settings`, optional redraw) is unchanged; close and cancel still save recoverable drafts and safely stop in-progress OCR verification. No PDIC/PPP or OCR schema changes, no new root Python files. Round 39 characterization tests check all 25 method ownership sites, explicit live dependency semantics, draft-vs-final save and stop behavior, marker sample versioned serialization, revision invalidation. Real dictionary-page GUI and persistence round-trip acceptance remains required, keep PR Draft.


Round 39 follow-up: original illustrated-mode safeguard remained in extracted `wizard_persistence.move_step` but one old source-location test still expected it physically inside `profile/setup.py`. Assert the legacy delegation plus the intact illustrated-mode condition at its real canonical owner.


### Round 40 — Wizard lifecycle bootstrap and template column interactions (2026-10-24)

Moved **13** cohesive implementation bodies from `profile/setup.py` to two physically owned modules: `wizard_bootstrap.py` now initializes all window/profile state, analysis/cancellation and thumbnail queues, representative indices, Tk variables and deferred thumbnail decode; the `ProjectProfileWizard.__init__` retains the **real `super().__init__(parent)` invocation in the class** and forwards the rest using call-time dynamic dependencies. `wizard_template_interactions.py` now owns 12 column controls, 0.1%-width manual pixel nudge, cached overlay-only line motion, reset and color selection, static point-to-polyline distance, conditional header/footer/side controls and representative template preview navigation. Original wizard methods and signatures remain thin delegates, including `_preview_path_distance_sq` as a staticmethod, with circular imports avoided. No changes to PDIC/PPP, OCR settings schema, thumbnail worker timing or file persistence semantics. Added `tests/test_issue562_profile_wizard_round40_20261024.py` to check owner location, superclass-first construction, live globals, legacy signatures, geometric distance, nudge pixel/reset math and conditional control states without creating a Tk window. Existing root-source string regression tests reanchored to the new owners; keep Draft until CI, OCR smoke and real-scanned-page manual parity pass.


Round 40 first-CI adjustment: two tests mistakenly looked for the moved window-centering implementation in the original wizard initializer, or matched a historical `super().__init__` description inside a docstring. They now check the actual bootstrap owner's centering code and that only the retained class entrypoint invokes the Tk superclass. No behavior assertions were relaxed and no production logic was changed.


### Round 41 — Root training-export v2 page exporter physically migrated (2026-10-24)

The direct root `src/picture_capture/training_export.py` remains a required stable public import and monkeypatch/pickle compatibility boundary, but the **actual v2 per-page annotation export** (`export_training_page` body) now lives in `src/picture_capture/training/export_page_v2.py`. The root `export_training_page(page, project_root, settings, staging_root, page_index)` signature is preserved and delegates with live dependency bindings, including patchable `_candidate_ground_truth_link`, storage paths, source/canonical coordinate helpers, image processing and cache readers. The root module drops from **9,723 to ~2,972 characters**, while one coherent `training/` owner gains the physical implementation. Training v2/v3 static composition, ZIP publisher and cancellation exception identity, v2 manifest and project context are unchanged. No PDIC/PPP coordinate or format changes. Root module count remains 10 *intentionally*: existing source-level compatibility and pickle ABI require retaining `training_export.py` as an entrypoint; migration reduces its business logic rather than deleting it.

New `tests/test_issue562_training_export_page_v2_round41_20261024.py` checks physical canonical ownership, unchanged historical public signature and function identities, call-time forwarding of monkeypatched dependencies, and a real generated image/page export with stubbed geometry including saved PDIC/PPP, OCR review candidates, manual selections, source X/Y and template crop boundary. Continue with six-platform CI and three-OS OCR Smoke on exact HEAD and keep PR Draft until manual real dictionary scans and PDIC/PPP crop/reopen parity.


Round 41 first CI identified a source-location-only regression in the existing alpha-safe image loader test. The test now verifies the historical `training_export.export_training_page` delegation and the exact `normalize_page_rgb(opened)` usage in `training/export_page_v2.py`, preserving behavior and root public API checks.


### Round 42 — Processing facade: Page Understanding and ordinary role/fallback physical owners (2026-10-25)

- Physically extracted `processing._understand_page_current` (illustration masking, trace, Layout-only/composed dispatch, fail-open/fail-closed behavior and temporary image cleanup) to `layout/current_page.py:understand_page_current`. The legacy processing callable remains a stable signature-preserving delegate; layout imports remain lazy in the canonical owner and no runtime installer is invoked.
- Physically extracted `processing._ordinary_entries_from_layout_roles` and `processing._ordinary_vb_fallback` into `ordinary/layout_roles.py`. Layout entry scale/source Y mapping and fallback-only VB behavior are unchanged; the facade forwards its current refinement callback, Entry constructor, VB detector, page-template filter, sorter and dataclass replacement function on every call, preserving monkeypatch seams.
- Root `processing.py`: **41,760 → 36,905 bytes**, **-4,855 bytes**. Root Python files remain **10**, aggregate root Python bytes **449,419 → 444,564**. No new root shims, no model/pickle or persisted schema moves.
- New regression `tests/test_issue562_processing_layout_owner_round42_20261025.py` checks physical AST owners, historical signatures, source path/mask trace/close, live Y-refinement and Entry factory, and VB detector/filter/sort patching. Three prior source-contract tests now inspect the actual physical owner rather than assuming implementation is still in the facade; their behavioral assertions remain.
- This extraction does **not** establish representative scanned dictionary-page GUI acceptance. Ordinary/OCR/combined detection, Tk main-thread behavior, PDIC/PPP save/reopen and crop/export equivalence remain **manual acceptance pending**. CI and OCR smoke must be checked on the exact new commit before any readiness discussion. PR stays Draft; no merge.


## Round 45 — shared OCR/combined observations and Wizard scrolling (2026-10-25)

- Physically relocated `processing._shared_detector_observations` into
  `detection/shared_observations.py:shared_detector_observations`. It still
  normalizes the source once, resolves effective page/template settings,
  creates shared geometry, lazily imports Paddle OCR, reads review candidates,
  and fuses ordinary/OCR entries only in combined mode. The original callable
  and signature remain, injecting **current** core/facade callbacks at call
  time (including fusion, geometry, page-template and ordinary detection).
- Physically relocated four `ProjectProfileWizard` scrolling/ancestry
  methods from `profile/setup.py` to `profile/wizard_scroll.py`. The
  historical instance/static methods and Tk/ttk dependencies are preserved;
  scrolling stays in Tk's event callbacks on the main thread, not a worker.
- New regression: `tests/test_issue562_shared_observations_wizard_scroll_round45_20261025.py`
  characterizes real owners, legacy signatures, runtime patched OCR/combined
  seams, canvas routing, wheel direction, static widget ancestry and
  out-of-range tab behavior.
- Root Python module inventory remains **10** (no root stubs); no PDIC/PPP,
  OCR cache, Entry identity or crop/export schema change. Real scanned
  dictionary-page GUI, ordinary/OCR/combined, Profile, PDIC/PPP reopen
  and crop/export equivalence are **not manually verified**. Keep Draft.


### Round 46 — OCR channel algorithms, project page enumeration and Profile validation handlers (2026-10-25)

- Seven actual OCR functions physically relocated to `ocr/channel_preparation.py` and `ocr/channel_results.py`, leaving signature-preserving old OCR channel public entrypoints which inject **current** NumPy, Pillow, threshold, payload and record/candidate constructors at each call. The model dataclasses and OCR session do not move; pixel space/box ordering/fusion fields and stored formats remain unchanged.
- Four actual project cover/path/page-enumeration/natural-sorting algorithms physically relocated from `models.py` to `project/page_discovery.py`; the existing settings, Entry and project state classes remain at their historical pickle paths. Current cover predicates and sort callbacks are passed by the old entrypoints.
- Four complete Tk validation queue/button/preview/fit algorithms physically moved out of `profile/setup.py` into existing `profile/wizard_validation_controls.py`. All public Wizard methods still dispatch in the original Tk event loop; no new OCR worker/UI concurrency.
- Focused tests `tests/test_issue562_ocr_channel_project_profile_round46_20261025.py` assert physical owners, live monkeypatch seams, source boxes, page discovery and Tk event handling. Also strengthened a previous source-test's unpatched-import identity check in a fresh interpreter to avoid suite-order pollution while retaining the same invariant.
- Root remains **10** Python files; no root alias/shim added. Real scanned dictionary-page GUI ordinary/OCR/combined flow, Profile, PDIC/PPP reopen and crop/export equality, plus independent review, remain **manual acceptance pending**. PR remains Draft; no merge or Ready.


### Round 47 — PaddleOCR engine bootstrap and lifecycle extraction (2026-10-25)

- Physically moved `ocr_channel.clear_ocr_channel_paddle_engine_cache` and `ocr_channel._create_paddle_engine` implementation bodies to `ocr/paddle_engine_lifecycle.py`. The owner retains the lazy PaddleOCR import, Windows CUDA DLL registration, PIR environment suppression, TextDetection cache eviction, constructor compatibility retry, inference telemetry, active-key cache policy and thread-lock ownership. No eager Paddle import or worker-created extra GPU pipelines.
- Original root callables and signatures remain; current `_paddle_language`, `resolve_inference_policy`, `paddle_constructor_variants`, cache map/lock, `gc` and cache-clear callbacks are passed at **call time**, retaining monkeypatch seams and model resource semantics.
- `tests/test_issue562_ocr_paddle_lifecycle_round47_20261025.py` characterizes physical ownership, legacy signatures, type-error constructor fallback, one-active-engine caching, runtime bootstrap order, GPU registration and telemetry with a fake Paddle module. Existing `tests/test_ocr_channel_runner_semantics.py` continues guarding mature constructor behavior.
- Root still 10 modules; persisted OCR/PDIC/PPP/SECTION, Tk, page source pixels and export unchanged. Exact new-head six-platform CI and OCR Smoke are mandatory; manual real scanned-page validation remains **NOT DONE**. Keep Draft and unmerged.
