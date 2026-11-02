# R7.3 — Nonlinear ROI knot preimages and half-open crop safety

**Date:** 2026-11-02  
**Repository:** `chigre/Picture_Capture`  
**Implementation PR:** [#663](https://github.com/chigre/Picture_Capture/pull/663), Draft/Open/Unmerged  
**Exact source/test HEAD:** `d87d83e3dc1dcf9b6ec8c39ff38041a438e90f9b`

## Scope and safety boundary

This increment hardens the read-only `PreprocessCoordinateMap` polygon contract. It does not change PDIC, PPP, SECTION or Profile persistence schemas/writers, original source-image XY, image rasterization algorithms, OCR behavior, or experimental defaults. No real dictionary scan or human operator acceptance was performed.

## Defect and correction

A nonlinear orthogonal replay stores interpolation knots in the coordinate frame entering each orthogonal stage. Those coordinates are not necessarily the caller's polygon frame:

- Forward mapping: source points pass through layout canonicalization, deskew and perspective before entering the first orthogonal stage; later stages receive points after earlier orthogonal warps.
- Reverse mapping: output-canvas points must first undo canvas placement and crop offsets, then undo later orthogonal stages before reaching the input frame of the stage whose knots are being checked.

The earlier implementation inserted saved knot values directly into raw source/output XY. That could miss an ROI edge excursion when a projective transform or crop/canvas offset shifted the actual knot preimage.

The corrected sampler evaluates each edge in the actual input frame of every orthogonal stage, sizes bounded spatial coverage in both caller and stage frames, brackets saved x/y/separator knot crossings, and root-finds their edge-parameter preimages. Reverse sampling undoes canvas/crop offsets and later stages first.

A finite-precision root can land a few ULPs inside an excluded upper crop edge even when the exact crossing is on the half-open boundary. Orthogonal polygon validation therefore treats a (10^{-7})-pixel uncertainty band immediately below the exclusive right/bottom crop edges as outside. Crop boxes are now validated as four strict integer coordinates; fractional and boolean coordinates are rejected instead of being silently truncated by `int()`.

## Regression evidence

The RED-first tests cover:

1. Forward knot preimage after a projective translation.
2. Reverse knot preimage after crop offset and centered output-canvas placement.
3. Fractional and boolean crop-box bounds.
4. Existing narrow separator excursions, NumPy polygon inputs, source-size/EXIF consistency, malformed legacy replay snapshots, multi-step orthogonal replay and raster-pixel parity.

RED: test-only commit `a59a904bdbc2c4d2895a77bbc74a7c8490ca326b`, [CI #41344061364](https://github.com/chigre/Picture_Capture/actions/runs/41344061364). All six Windows/macOS/Ubuntu × Python 3.10/3.13 regression jobs failed the three intended crop-box assertions. The canvas+crop reverse-knot regression passed with the preceding stage-frame fix.

Source sequence:
- `4b2a1cb1be3498452ef03705c77e6750bbd02e8e`: stage-frame knot preimage root finding.
- `d589e318520ab4189253c4b649f92b0ea26e6061`: conservative half-open crop-edge numerical guard.
- `d87d83e3dc1dcf9b6ec8c39ff38041a438e90f9b`: strict integer crop-box validation.

## Exact-head verification

[CI #41344312511](https://github.com/chigre/Picture_Capture/actions/runs/41344312511): **SUCCESS 6/6**, Risk-tier and Risk-tier CI gate SUCCESS.

| Platform | Python 3.13 | Python 3.10 |
|---|---:|---:|
| Windows | 5353 passed / 2 skipped | 5352 passed / 3 skipped |
| macOS | 5353 passed / 2 skipped | 5353 passed / 2 skipped |
| Ubuntu | 5352 passed / 3 skipped | 5352 passed / 3 skipped |

[OCR Platform Smoke #41344312514](https://github.com/chigre/Picture_Capture/actions/runs/41344312514): **3/3 SUCCESS**.  
[CodeQL #41344308665](https://github.com/chigre/Picture_Capture/actions/runs/41344308665): **Analyze Python and Actions 2/2 SUCCESS**.  
Documentation architecture check: **SKIPPED; not counted as a pass**.

## Limitations and next work

- Orthogonal inverse replay remains the existing bounded approximate inverse; this work does not claim an exact inverse.
- Knot root finding detects bracketed crossings over bounded spatial intervals. Pathological multiple or tangential contacts without a sign change remain an explicit follow-up target.
- The (10^{-7})-pixel band is a conservative numerical guard only; it does not alter stored crop geometry.
- Next: test tangential/non-monotonic knot contacts and validate `OutputCanvasInfo` dimensions/content-box as strict integer raster snapshots; audit actual map-construction callsites for raw-size/EXIF metadata propagation.
- R7.3 remains **in_progress**. Human acceptance, Windows R3 E3, #483 W1–W11, #503 manual Undo/Redo and real-project scan/save-reopen remain unperformed/deferred.


## Follow-up: tangential knot contacts, malformed transforms and EXIF frame audit

**Source/test HEAD:** \`39aaa983f858755f8d18ac0a4278c1d05d641f55\`  
**Implementation PR:** #663 remains Draft/Open/Unmerged.

### Tangential and non-monotonic knot contacts

The bounded polygon sampler now has two explicit composed-stage tangency regressions in \`tests/test_r7_3_tangential_knot_preimages_20261102.py\`:

- Forward: an X-varying row-angle stage creates a smooth local minimum in the next stage's input Y; a later separator knot is touched between the ordinary 8 px samples without a value sign change.
- Reverse: the inverse composition creates a smooth local maximum in the separator-stage input Y, again touching a saved knot between ordinary samples.

Both cases require the ROI polygon to fail closed even though all vertices and the coarse samples map. These are constructed bounded counterexamples, not a mathematical certificate for arbitrary high-frequency or multiple-extremum warp fields.

### Malformed layout-transform contract

RED-first test commit \`04e2e8a6bfa4c735962e6506c616b32abc69c4fe\`, [CI #41433985246](https://github.com/chigre/Picture_Capture/actions/runs/41433985246): all six Windows/macOS/Ubuntu × Python 3.10/3.13 matrix jobs failed on the two unhashable \`list\`/\`dict\` transform-kind cases. Ubuntu Python 3.10 and 3.13 each reported **2 failed, 5417 passed, 3 skipped**. The defect was an unguarded set-membership check in \`LayoutTransform.__post_init__\`, which leaked \`TypeError\` instead of the documented \`ValueError\`.

Minimal fix \`39aaa983f858755f8d18ac0a4278c1d05d641f55\` first requires a string before checking the four supported transform literals. The valid identity/mirror/quarter-turn paths and the coordinate-map rejection of non-\`LayoutTransform\` objects remain covered.

### EXIF/source-coordinate audit

Read-only source inspection confirms the intended source frame:

- \`preprocess.pipeline.analyze_preprocess_page\` calls \`normalize_page_rgb\` before taking analysis dimensions and deriving geometry.
- \`ui.controllers.page\` normalizes the opened page before loading and displaying the page alongside PDIC/PPP annotations.
- \`persistence.page_sections\` uses \`ImageOps.exif_transpose(...).size\` for the source dimensions used by SECTION coordinate conversion and persistence.

Therefore \`PreprocessCoordinateMap.source_size\` is the EXIF-oriented pixel frame. \`raw_source_size\` and \`exif_orientation\` validate the relationship between raw and oriented dimensions; they do not make the map accept raw, pre-EXIF annotation XY. The map class is not yet constructed by a production source callsite on this PR head. No production propagation or UI integration is claimed. A future caller must capture raw dimensions/orientation from the opened image before normalization and pass the oriented size consistently with the analysis and persisted annotation frame.

### Exact-head automated evidence

- [CI #41434426536](https://github.com/chigre/Picture_Capture/actions/runs/41434426536): **6/6 platform/Python jobs SUCCESS**; Risk tier and Risk-tier CI gate SUCCESS.
- Test counts: Ubuntu 3.13 **5419 passed / 3 skipped**; macOS 3.13 **5420 / 2**; Windows 3.13 **5420 / 2**; Ubuntu 3.10 **5419 / 3**; macOS 3.10 **5420 / 2**; Windows 3.10 **5420 / 2**.
- [OCR Platform Smoke #41434426792](https://github.com/chigre/Picture_Capture/actions/runs/41434426792): **3/3 SUCCESS**.
- Documentation architecture check: **SKIPPED, not PASS**.
- Exact-head CodeQL Python/Actions result was not independently retrieved; no CodeQL pass is claimed.

### Current boundary and next work

R7.3 remains **in_progress / synthetic E2 only**. No production coordinate-map callsite was found, so do not wire this API into the page UI or persistence path as part of this bounded increment. No PDIC/PPP/SECTION schema or writer, original source XY, renderer, OCR policy, or experiment default changed. No real dictionary scan, Windows operator E3, or human acceptance was performed.

Next bounded review: probe whether multiple extrema can occur inside one already-partitioned stage interval beyond the two constructed tangencies; if the bounded derivative search cannot resolve a case, prefer fail-closed behavior over claiming completeness. Preserve the EXIF-oriented source-frame contract and defer production integration until a real consumer and its ownership semantics are separately reviewed.
