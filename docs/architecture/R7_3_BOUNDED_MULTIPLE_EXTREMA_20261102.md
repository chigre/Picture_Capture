# PC-CQ B7b/R7.3 — Bounded multiple-extremum stage coordinate sampling

**Date:** 2026-11-02  
**PR:** [#663](https://github.com/chigre/Picture_Capture/pull/663) (Draft/Open/Unmerged)  
**Source/test HEAD:** \`1a7919e8e932a63ebcd4eea0b3fd498cd14634a0\`  
**Scope:** synthetic, read-only source → canonical → transformed → cropped/canvas polygon contract; no production UI/writer integration.

## RED-first counterexample

\`tests/test_r7_3_multiple_extrema_between_knots_20261102.py\` injects an adversarial quartic stage-input Y along an already-partitioned straight ROI edge. Its derivative is \`(t - 0.32) * (t - 0.37) * (t + 1)\`: there are two genuine turns at \`t=0.32\` and \`0.37\`, but the previous five probes (\`0.001, 0.25, 0.5, 0.75, 0.999\`) all see positive slopes. The test covers both forward and reverse stage-input contracts; the monkeypatch is synthetic, not evidence of a materialized raster with this exact quartic.

**Test-only RED:** [\`4c64678bc09a3968bf00afaab9b1c8413ca0af61\`](https://github.com/chigre/Picture_Capture/commit/4c64678bc09a3968bf00afaab9b1c8413ca0af61), [CI #41437504042](https://github.com/chigre/Picture_Capture/actions/runs/41437504042), **FAILURE** across all six Windows/macOS/Ubuntu × Python 3.10/3.13 jobs, exactly the two new \`test_stage_extrema_finds_two_close_turns_between_coarse_derivative_probes\` parameterizations. Ubuntu Python 3.13: **2 failed, 5419 passed, 3 skipped**; Risk-tier CI gate failure was expected and not treated as a release pass. OCR Smoke for the RED head was **3/3 SUCCESS**, independent of the geometry assertion failure.

## Minimal source correction

[\`1a7919e8e932a63ebcd4eea0b3fd498cd14634a0\`](https://github.com/chigre/Picture_Capture/commit/1a7919e8e932a63ebcd4eea0b3fd498cd14634a0) changes only \`src/picture_capture/preprocess/coordinate_mapping.py\`.

The existing bounded derivative-sign scan in \`_orthogonal_stage_extrema\` now uses 31 internal grid probes (\`i/32\`, \`i=1..31\`) plus \`0.001\` and \`0.999\` instead of only five probes. Observed derivative sign changes continue to be refined by the existing bounded bisection. Existing per-edge and total-sample budgets, crop half-open guards, stage-frame composition and approximate inverse remain intact.

This catches the demonstrated two-extrema interval without asserting mathematical completeness. Arbitrarily close pairs, pathological high-frequency fields, numerical cancellation and inverse solver limits are not certified. No wall-time, latency, memory or accuracy improvement is claimed without an authorized benchmark.

## Exact source/test gate results

| OS | Python 3.13 | Python 3.10 |
| --- | --- | --- |
| Ubuntu | 5421 passed / 3 skipped | 5421 passed / 3 skipped |
| macOS | 5422 passed / 2 skipped | 5422 passed / 2 skipped |
| Windows | 5421 passed / 3 skipped | 5422 passed / 2 skipped |

- [CI #41452328147](https://github.com/chigre/Picture_Capture/actions/runs/41452328147): **6/6 SUCCESS**; Risk tier **SUCCESS**, Risk-tier CI gate **SUCCESS**. Documentation architecture check **SKIPPED, not counted as a pass**.
- [OCR Platform Smoke #41452328062](https://github.com/chigre/Picture_Capture/actions/runs/41452328062): **3/3 SUCCESS**.
- [CodeQL PR #663 #41452320691](https://github.com/chigre/Picture_Capture/actions/runs/41452320691): **Analyze (python) SUCCESS; Analyze (actions) SUCCESS**.
- The documentation/checkpoint commit after this source SHA must independently pass its own exact-head gates; no prior run is attributed to the newer documentation SHA.

## Safety, limitations and recovery point

R7.3 stays **in_progress / synthetic E2 only**. No main write, merge/Ready transition, issue closure or second production PR. No PDIC/PPP/SECTION/Profile/OCR schema or writer, original image XY, scan, raster rendering or experimental default changed. No authentic dictionary scan or benchmark was run.

**NOT PERFORMED / DEFERRED:** Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, real dictionary scan/save-reopen, R6 real-label learning and R8 scanning. Synthetic CI is not human acceptance.

**Next bounded work:** examine adversarial intervals narrower than the fixed 1/32 probe spacing and numerical/solver unavailability as fail-closed conditions, but do not claim arbitrary-path certification or alter production raster/persistence. Continue safe R4.2 epoch/SECTION/crop/save synthetic-source contract regression where a concrete failure-first counterexample exists.
