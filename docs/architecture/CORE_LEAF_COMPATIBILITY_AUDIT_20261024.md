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
