# Round 51 — Homography and source-paper fill single ownership (2026-10-25)

The public `preprocess/geometry.py` geometry surface and original
`preprocess/deskew.py`/`preprocess/orthogonal_dewarp.py` raster entrypoints
remain intact. Their duplicated private implementation was consolidated in
**`preprocess/homography_ops.py`**, a leaf-only numpy/Pillow owner:

1. 4-corner linear homography solver and analytic Jacobian;
2. 3×3 homogeneous point/polygon mapping with safe zero denominators;
3. inverse-matrix Pillow PERSPECTIVE sampling on same-size RGB source;
4. 4-corner sampled median background fill shared by three prior modules.

The original function signatures, import locations, deskew's pickled
`preprocess.pipeline._paper_fill` identity, default source pixel conversion,
source-coordinate semantics, interpolation and exact median rounding remain.
Each wrapper injects its **current** normalization/fill/point mapping callback
rather than bypassing runtime test or application patchpoints. No app, pipeline,
Tk, layout inference, OCR model or GPU dependencies are imported by the new owner.

Added characterization tests for numerical translation, identity Jacobian,
singular/wrong-shaped matrices, RGB/RGBA/paletted median equality,
source immutability, per-call patched point/paper callbacks, and Python
compatibility signatures plus pickle identity.

No settings, PDIC/PPP/SECTION, Profile schema, OCR cache, export or detection
behavior changes. Full exact-head 6-matrix CI and 3-OS OCR smoke required;
real scanned dictionary-page GUI/ordinary/OCR/combined, saved file reopen and
crop/export equivalence remains a separate manual gate. Keep PR #663 Draft.
