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
