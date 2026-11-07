# G3 R5.1/R5.2 current-head parity recheck — 2026-11-01

**Current source HEAD:** `3b06e89034cc8c5b93db3613fd0d10fe811bdc70`  
**PR:** [#663 — Draft / Open / Unmerged](https://github.com/chigre/Picture_Capture/pull/663)

The current source HEAD was re-run through the complete six-platform regression matrix. The dedicated parity suites were present in each full-suite job and passed on all six Windows/macOS/Ubuntu × Python3.10/3.13 combinations:

- `tests/test_g3_r5_candidate_score_parity_20261030.py`: 12 immutable primitive boolean features, exhaustive (2^{12}=4,096) exact historical candidate-score comparisons, JSON roundtrip, pure-import contract and integrated old/new pipeline differential cases.
- `tests/test_g3_r5_engine_quality_parity_20261030.py`: 128 boolean flag vectors × four score/confidence/repair/boundary scenarios (512 exact q comparisons), malformed/missing boundary and conversion cases, and full arbitration record parity for Paddle/Tesseract/Lens including diagnostic-only Lens, forced overrides, ties, repairs and source coordinates.

Exact current source-head gates:
- [CI #41289630397](https://github.com/chigre/Picture_Capture/actions/runs/41289630397): 6/6 + Risk-tier + Risk-tier CI gate SUCCESS.
- [OCR #41289630408](https://github.com/chigre/Picture_Capture/actions/runs/41289630408): 3/3 SUCCESS.
- [CodeQL #41289628415](https://github.com/chigre/Picture_Capture/actions/runs/41289628415): Analyze Python and Actions 2/2 SUCCESS.

No score weights, acceptance thresholds, arbitration policies, tie rules, diagnostics or source coordinates were changed. This is pure-function and synthetic integrated E2 parity, not human-labeled OCR accuracy, dictionary-level F1, or a real scan benchmark. No model training or shadow deployment is authorized by this work.

## Current batch boundary

B5/R5.1+R5.2 is marked synthetic E2 complete. B6/R6 remains blocked pending reliable R2 human-verified source-consistent labels and project/dictionary-level independent partitions. B4 remains active for post-terminal no-hit source drift and focused-save partial publication/reconciliation. R3 E3, #483 W1–W11, #503 manual Undo/Redo, R6 real-label learning and R8 real scan remain NOT PERFORMED / DEFERRED as recorded in STATE.
