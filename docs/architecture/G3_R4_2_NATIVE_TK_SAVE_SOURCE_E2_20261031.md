# G3 R4.2 — native Tk synthetic failed focused-save source ownership (2026-10-31)

## Previously missing physical GUI integration check

The unit-level [focused-save source-ownership package](G3_R4_2_FOCUSED_SAVE_SOURCE_20261031.md) tests stale image/SECTION bytes and queued human edits with fake review/window callbacks. The pre-existing `scripts/gui_g3_focused_controls_smoke.py` instead exercised the **real Tk controls** and real project loader but stopped before a human-edited *source-attested* filtered row was actually autosaved. A bug between widget `StringVar`, target witness, pending queue, 160-ms timer, background PDIC writer and failure callback could therefore escape either slice.

This packet extends the existing real-Tk script, **without changing production source, persistence schemas, PDIC/PPP/SECTION writer, OCR, or settings defaults**, to cross that boundary in an isolated temporary synthetic managed project. The native smoke already runs in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) on **Windows, macOS and Linux under Python 3.13**; no new workflow or external dictionary download was added.

## Exact synthetic scenario and invariant

1. Load the existing two-page synthetic project using the actual app loader and `ReviewWindow`. Execute the existing default-OFF/opt-in/opt-out and invalid-filter checks; accept the first focused crop **only after it is rendered with its source witness**.
2. Assert visible target retains original image source XY `(80,76)`, and invoke actual `review.filter_vars[0].set("synthetic-native-edit")`. This triggers a real `trace_add("write")` and the pending edit with the exact **accepted crop** source witness. The synthetic literal is not a real dictionary word.
3. **Before the scheduled 160-ms save fires**, add or modify the active disposable SECTION sidecar. Do not write a new witness at save time. Permit real background save dispatch; the preflight must fail closed on SECTION byte/path/presence drift.
4. Wait for the real Tk failure callback. Confirm the synthetic PDIC remains byte-exact; parent `Entry` word/source XY is unchanged; text remains in the Tk editor and pending save queue; `target["original_word"]` stays original; close-on-save cleared. Error dialog is generic and does not echo the unsaved human text.
5. Restore/erase only the **disposable synthetic** SECTION mutation and abandon the intentionally unsaved synthetic edit before the original GUI smoke's ordinary final assertions. The test cannot write to a real user project or set R6 OCR truth labels.

The first test-only patch `931ac2284feb1727c1dad6081d1de9141b0363d3` already passed the **real native G3 Tk smoke** on Ubuntu Python 3.13 in [CI #41172738534](https://github.com/chigre/Picture_Capture/actions/runs/41172738534), with `5,023 passed / 3 skipped` in full pytest. The second test-only patch `c033cbeb1987e96abc1d3b0f779c343314d4819d` uses a safe optional-widget readiness check while waiting for Tk to create the transient `filter_vars` attribute; this is test hardening, **not** a production bypass or a new R3 save policy.

## Validation, limits and operator gate

At authoring, corrected source [CI #41172814679](https://github.com/chigre/Picture_Capture/actions/runs/41172814679) remained running. [OCR #41172814667](https://github.com/chigre/Picture_Capture/actions/runs/41172814667) passed all 3 OS, and [PR/CodeQL #41172812918](https://github.com/chigre/Picture_Capture/actions/runs/41172812918) was still running. This documentation checkpoint creates **another HEAD** requiring its own exact-head CI six Python/OS jobs, Risk-tier, OCR 3 OS, CodeQL Python/Actions and review verification before declaring E2 successful; never inherit a prior HEAD green result.

This is **synthetic automated E2 only**. It cannot establish human crop correctness, Chinese IME behavior on an authorized real dictionary, any real Windows installation E3, device-specific timings, external concurrent OS atomicity, #483 W1–W11, or #503 complex Undo/Redo. All human Windows R3 E3, G3 real-source GUI/PDIC/PPP/SECTION/Profile and save-reopen acceptance remain **NOT PERFORMED**; [real-image source hash timing runbook](G3_R4_2_WINDOWS_SOURCE_PERF_RUNBOOK_20261031.md) awaits a real authorized operator. R6 human labels and R8 real scans remain **DEFERRED**. Sole [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) remains Open/Unmerged, main unchanged; do not mark Ready, merge or close issues.
