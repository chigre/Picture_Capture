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
