# G3 R4.1 — source-valid, explainable review risk (2026-10-30)

## Fixed-source evidence

R5.1 candidate parser/visual score and R5.2 engine arbitration **q** are independent; neither is a verified label. R5.2 exact documentation HEAD `11aa70a0a9327b7bac6080f863aa212da1af27de` passed [CI 40968076780](https://github.com/chigre/Picture_Capture/actions/runs/40968076780) six Windows/macOS/Ubuntu × Python3.10/3.13 + Risk-tier, [OCR 40968076632](https://github.com/chigre/Picture_Capture/actions/runs/40968076632) 3/3, and [CodeQL 40968072905](https://github.com/chigre/Picture_Capture/actions/runs/40968072905) Python/Actions 2/2. Conditional documentation check was skipped.

R4.1 test-first `c3caec35fa19e8aad01b66169ff0494d8e29d1ba` produced the expected missing-module error in [CI 40971735341](https://github.com/chigre/Picture_Capture/actions/runs/40971735341), Ubuntu Python3.13 job 123789938199. Source `460383db864663854905e7f8d2dd1abd665e26ca` adds `src/picture_capture/proofreading/review_risk.py` and nine synthetic tests in `tests/test_g3_r4_provenance_risk_20261030.py`. Source [CI 40971810563](https://github.com/chigre/Picture_Capture/actions/runs/40971810563), [OCR 40971810731](https://github.com/chigre/Picture_Capture/actions/runs/40971810731), [CodeQL 40971805624](https://github.com/chigre/Picture_Capture/actions/runs/40971805624): inspect actual final conclusions, **pending is not success**.

## Ownership, semantics and fail-closed contract

The pure frozen `ReviewRiskProvenance` and `classify_review_risk` do not access files or Tk. Caller must independently hash actual current OCR JSON and saved PDIC bytes and verify matching origin/current project, page, SECTION, unique exact Entry source X/Y and candidate ID. Identical caller-supplied hashes alone do not establish real provenance. Sectionless pages require an explicit stable sentinel. The module does not guess from list index, nearby Y or OCR text.

- **unknown** for missing/stale/malformed source hashes, changed project/page/SECTION, ambiguous/duplicate source XY, candidate identity or source-coordinate mismatch, original-Y fallback, unselected row, Lens diagnostic-only, unknown issue type or incomplete dual evidence. Unknown is not an error label and not normal.
- **priority** for uniquely source-anchored current selected candidates with known review signals: OCR/acceptance conflict, repair, weak structure, low confidence, Lens disagreement, visual rescue, or explicit `needs_review`. Stable deduplicated reasons denote *review attention*, never a proven FP/FN.
- **normal** only for fresh unique selected `dual_agree_higher_quality`, two accepted Paddle/Tesseract observations with equal nonempty casefolded lemma, finite confidences and no review issues. This is not a correctness assertion.

Synthetic tests cover JSON-serializable immutable output, stale hashes, identity collisions, cross SECTION, exact XY drift, diagnostic-only Lens, unrecognized/missing diagnostics, rescue/repair and normal agreement. No OCR thresholds, candidate score, arbitration q, chosen engine, source pixels, crop, PDIC/PPP/SECTION/Profile or user record changes.

## R4.2 next independent owner work

The existing `ui/focused_filter_workflow.py::run_focused_filter` uses a near-Y OCR candidate helper suitable for text filtering but **not** proof of unique review-risk ownership. Before integrating, add an exact-byte provenance adapter with negative tests for stale PDIC/OCR, duplicates, cross SECTION and asynchronous races. Then add a separately explicit default-**OFF** priority queue; specify per-batch versus global ordering without silently reordering displayed rows. Preserve default page/SECTION navigation, autosave/Undo and crop. No real operator time savings, OCR F1 or label accuracy claim.

PR #663 sole Draft/Open/Unmerged; main unchanged; #503/#562/#483 open. Windows R3 E3 and #483 W1–W11 human acceptance **NOT PERFORMED**. R6 labels absent; R7 performance and R8 real scan deferred.
