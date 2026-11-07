# G3 / R4.2 — final focused PDIC readback byte witness after image/SECTION verification

Date: 2026-11-03 (SGT). Sole production work branch: Draft/Open/Unmerged PR #663; source/test commit `0a31856b36ff33b93a686a108b24ac69a9c82ea3`. Main remains unchanged at `ec20989ea8c026cca5337293e67850b6b6df30f2`.

## RED-first (synthetic E2)

Test-only commit [5cec99d0](https://github.com/chigre/Picture_Capture/commit/5cec99d063afde915e0e2edeeb79ee56e02f6872) adds `tests/test_g3_r4_final_pdic_readback_witness_20261103.py`. Only disposable 8×8 BMP, synthetic eight-field PDIC, and a monkeypatched last image/SECTION source-witness callback are used.

While the fourth (last) source witness runs, a foreign writer can replace the headword or append another PDIC row. The original method had already validated ordered rows, eight fields and edited XY, so it returned confirmed success after the unrelated source check even though PDIC changed. An unchanged-source positive control must still succeed.

[RED CI #41607004651](https://github.com/chigre/Picture_Capture/actions/runs/41607004651): all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs completed **FAILURE** on the two expected new `DID NOT RAISE RuntimeError` cases; Ubuntu 3.13: **2 failed / 5447 passed / 3 skipped**. Risk-tier CI gate **FAILURE**. Documentation architecture check **SKIPPED**. A RED build is not a passing release gate.

## Minimal fix and exact source-head GREEN

[Production fix 0a31856b](https://github.com/chigre/Picture_Capture/commit/0a31856b36ff33b93a686a108b24ac69a9c82ea3) changes only `src/picture_capture/proofreading/focused_pdic_updates.py`:
- Keep the exact PDIC bytes used for post-write eight-field comparisons, decoding those same bytes rather than independently reading text.
- After the final image/SECTION witness, compare current PDIC disk bytes with the captured bytes; reject confirmation if different.
- Never rewrite or roll back foreign bytes after an uncertain publication.

At **exact source/test HEAD**:
- [CI #41607380209](https://github.com/chigre/Picture_Capture/actions/runs/41607380209): **6/6 SUCCESS**; Risk tier and Risk-tier CI gate **SUCCESS**; Ubuntu 3.13 **5449 passed / 3 skipped**.
- [OCR #41607380214](https://github.com/chigre/Picture_Capture/actions/runs/41607380214): **3/3 SUCCESS**.
- [CodeQL #41607374344](https://github.com/chigre/Picture_Capture/actions/runs/41607374344): Analyze Python/Actions **2/2 SUCCESS**.
- Documentation architecture check **SKIPPED** (not PASS).

The later documentation/checkpoint HEAD requires its **own** exact-head gate verification; source-head results do not automatically transfer.

## Safety and remaining limits

This is a bounded fail-closed post-write readback, **not** a filesystem cross-file lock, multi-file transaction, or operating-system CAS. PDIC may already be durably written when a subsequent foreign update is detected; there is no rollback or automatic retry. A modification after the last discrete check can still occur. Persistent PDIC/PPP/SECTION/Profile/OCR formats, original-image XY, the safe writer and experiment default-OFF settings are unchanged. No real data or benchmark were used.

**NOT PERFORMED / DEFERRED:** Windows R3 E3; #483 W1–W11; #503 human Undo/Redo; actual dictionary scanning and PDIC/PPP/SECTION/Profile/OCR save/reopen; R6 real-label learning; R8 real scans. Synthetic E2 is not human E3.

Next: verify final documentation SHA's six CI jobs, OCR three jobs, Risk-tier/gate and CodeQL Python/Actions. Continue source-grounded async epoch/SECTION/crop-prefetch/save ownership audits, and never claim absolute cross-file atomicity.
