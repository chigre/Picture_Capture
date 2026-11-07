# G3 R4.2 — preterminal same-key crop-prefetch dispatch ownership

Date: 2026-11-02. PR [#663](https://github.com/chigre/Picture_Capture/pull/663) must remain Draft/Open/Unmerged; main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged. Synthetic E2 only, no real scanned dictionary or operator run.

## Concrete failure-first counterexample

`_schedule_filter_next_batch_preload` already used `terminal_claimed` to ignore **post-terminal** duplicate callbacks. But the acceptance test identified another race: a controller can invalidate the original background prefetch *before its first terminal*, clear `_filter_prefetch_key` and launch another worker with an **identical crop key and scan epoch**. The cancelled worker's first late `done` or `failed` still has `terminal_claimed=False` and matches the new worker's key and epoch, so it can clear the new owner's key; `done` may publish stale pixels and `failed` may trigger an unowned direct-render retry.

Test-only [`482bd7ad`](https://github.com/chigre/Picture_Capture/commit/482bd7ad2d10d0c8fa60e7eb6adc2e79c11ea40f) adds four parameterized cases (old done/failed × visible/not-visible next batch) to `tests/test_g3_r4_prefetch_visible_failure_recovery_20261031.py`. It uses disposable synthetic 8×8 BMP/PDIC/SECTION witnesses, the existing fake Tk scheduler and an explicit preterminal key release. Old first callbacks are delivered *after* new same-key ownership, followed by the new worker's positive completion and late old contradictory callbacks. [CI #41461342776](https://github.com/chigre/Picture_Capture/actions/runs/41461342776) **COMPLETED FAILURE in all six** OS/Python jobs **on exactly those four new assertions** (Ubuntu 3.13 4 failed / 5426 passed / 3 skipped; Windows/macOS Python3.13 each 4 failed / 5427 passed / 2 skipped). Risk-tier CI gate failed. RED is not a passing release gate.

## Minimal implementation and protected invariants

[`9cee90ca`](https://github.com/chigre/Picture_Capture/commit/9cee90ca10b51f860b5e51ae6fb77fc97cdf464e) changes only `src/picture_capture/ui/focused_filter_workflow.py`. Each scheduled prefetch owns an opaque `dispatch_owner = object()` distinct from the content/source key and scan serial. Both `done` and `failed` require **epoch + key + exact owner identity** before claiming the first terminal and clearing their own owner/key. Old callbacks that arrive before or after the new worker's completion are ignored even under identical source witnesses. The initial prefetch, failed-worker visible retry, source-byte drift fail-closed, pending human editors, save-running gates and post-terminal duplicate protections remain intact.

No actual PDIC/PPP/SECTION/Profile/OCR format or writer, original source-image XY, crop coordinates, OCR engine, worker scheduling identifier, on-disk cache format, human evidence record or opt-in default was altered. The new owner is volatile UI memory, not a durable cross-file CAS transaction.

## Exact source/test gates

At source commit `9cee90ca10b51f860b5e51ae6fb77fc97cdf464e`:

| OS | Python 3.13 | Python 3.10 |
| --- | --- | --- |
| Ubuntu | 5430 passed / 3 skipped | 5430 passed / 3 skipped |
| macOS | 5431 passed / 2 skipped | 5431 passed / 2 skipped |
| Windows | 5430 passed / 3 skipped | 5431 passed / 2 skipped |

- [CI #41462311384](https://github.com/chigre/Picture_Capture/actions/runs/41462311384): **COMPLETED SUCCESS**, 6/6 Windows/macOS/Ubuntu × Python3.10/3.13, Risk-tier and Risk-tier CI gate SUCCESS.
- [OCR #41462311678](https://github.com/chigre/Picture_Capture/actions/runs/41462311678): **COMPLETED SUCCESS 3/3**.
- [CodeQL #41462304534](https://github.com/chigre/Picture_Capture/actions/runs/41462304534): Analyze Python and Actions **2/2 SUCCESS**.
- Documentation architecture check **SKIPPED**, not PASS.
- This documentation/STATE/RESUME commit must independently pass **its own exact HEAD** CI/OCR/CodeQL/Risk-tier before declaring the final checkpoint verified.

## Residual risks and next owner

Synthetic preterminal key release is an adversarial test of the callback contract, not a certified real-world Tk cancellation path. Per-source SHA readback is not an atomic multi-file filesystem transaction. Windows native thumbnail GUI smoke showed an intermittent fixed-head timeout on the previous R7 docs commit; its one-job rerun passed, but the root cause was not fixed. Continue bounded R4.2 epoch/SECTION/crop/save source ownership and native Tk regression only with actual material RED-first cases. Do not claim benchmark speedup or OCR accuracy.

**NOT PERFORMED / DEFERRED:** Windows R3 E3; #483 W1–W11; #503 human Undo/Redo; real dictionary scan and PDIC/PPP/SECTION/Profile/OCR save-reopen; R6 verified-label learning; R8 scanning. E2 is not human E3.
