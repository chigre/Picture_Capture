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
