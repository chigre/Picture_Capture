# Round 52 — paired text scale safety audit owner (2026-10-25)

Complete numerical implementations of polygon inline/cross measurement,
robust log-plane spatial gradient and **paired before/after text scale audit**
were moved from the 80 kB `preprocess/geometry.py` into
`preprocess/text_scale_audit.py`.

This owner is strictly numpy/math-only: it neither imports the geometry
facade nor Tk, OCR, persistence, pandas, or GPU libraries. It evaluates
relative inline/cross ratios, P05/P50/P95, spatial gradients, local
anisotropy and old absolute trend diagnostics with the same formulas.

Legacy `geometry.audit_text_scale_stability`,
`geometry._polygon_inline_cross_size` and
`geometry._robust_spatial_gradient_ratio` remain callable at their
existing import paths and with exact original signatures. `geometry` retains
the **original** `TextScaleStabilityAudit` frozen dataclass identity and
its five published `TEXT_SCALE_*_MAX` thresholds. All five thresholds, the
Audit class, and both legacy helper hooks are passed to the new owner at
**call time**, including any application-level monkeypatch.

Characterization covers uniform versus spatially varying text scale,
anisotropic glyph shape safety, insufficient/malformed data, vertical writing
mode, threshold patches and pickle roundtrip.

No safety threshold was relaxed; no numerical acceptance policy changed.
No PDIC/PPP/SECTION, Profile, OCR, source-coordinate or export format changes.
Full exact-head CI + OCR Platform Smoke and real scanned-page manual gates apply.
Retain Draft PR #663.
