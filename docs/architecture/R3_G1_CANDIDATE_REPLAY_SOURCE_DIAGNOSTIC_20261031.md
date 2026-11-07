# PC-CQ R3 / #503 — OCR candidate replay source diagnostics, synthetic E2

Date: 2026-10-31. Active work remains in sole [Draft #663](https://github.com/chigre/Picture_Capture/pull/663), without changing `main@ec20989ea8c026cca5337293e67850b6b6df30f2`.

## Safety boundary

`CandidateReviewHistory._apply` is responsible for source-owned candidate-deletion Undo/Redo (PDIC + manual override + simplified sidecar). Unlike the ordinary `ReviewSessionHistory`, its diagnostic branch when `snapshot_review(review) is None` previously directly read image, PDIC, simplified, manual and OCR sources without handling `OSError`. Denied access could escape the human Tk callback, potentially including private source-path text. This diagnostic branch also omitted SECTION and Profile bytes, permitting stale history to survive a known changed source while Tk bindings were temporarily unavailable.

**The safe distinction:** transient Tk rebind + every saved source unchanged → return `False` while retaining history for explicit retry; any known source drift or unreadable source → return `False`, invalidate both history stacks and all candidate replay frames, and never modify persisted or visible data.

## Test-first coverage and bounded production fix

- Test-only `b7a0b669ae663b3c6a15f17de248418cf8b7b5fa` extends `tests/test_b3_candidate_history_20261015.py` with deterministic synthetic source failures: candidate Undo/Redo × image, PDIC, simplified, manual, OCR, SECTION, Profile unreadability (14 cases); changed SECTION/Profile during a temporary Tk rebind (4 cases); and unchanged sources retaining retryable history (2 controls).
- Source `cc0f101a510ce4abd6ca7d6b20fcb80284fba719` makes the diagnostic source check exception-safe (OSError/ValueError/TypeError → stale/fail closed), and checks exact SECTION and Profile bytes in addition to the original source owners. It does not alter the persisted writer, candidate matching rules, source coordinates, Undo/Redo transaction format, OCR, Profile, settings or R2 learning policy.
- Test-first CI [#41188708454](https://github.com/chigre/Picture_Capture/actions/runs/41188708454) was running at documentation authoring; do not infer exact red count without logs.
- Corrected source CI [#41188770945](https://github.com/chigre/Picture_Capture/actions/runs/41188770945), [OCR #41188770981](https://github.com/chigre/Picture_Capture/actions/runs/41188770981), [CodeQL #41188767775](https://github.com/chigre/Picture_Capture/actions/runs/41188767775) were pending at documentation authoring. **The final documentation HEAD itself must be checked again.**

## No premature acceptance

Complete automated E2 requires the exact final HEAD Windows/macOS/Ubuntu × Python3.10/3.13 **6/6**, Risk tier and its CI gate, OCR **3/3**, CodeQL Python/Actions **2/2**, Draft/Open/Unmerged #663 and zero unresolved review threads; the conditional Documentation architecture check may be skipped (not a pass). These checks do not establish Windows real-device operator E3.

Still **NOT PERFORMED**: #483 W1–W11, #503 full compound candidate/Undo/Redo human workflows, real dictionary pages & image/SECTION/PDIC save-reopen, real large-image performance, R6 real verified training labels, R8 real scans. No merge, Ready, issue closure or private scan upload.
