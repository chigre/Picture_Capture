# G3 R4.2 — direct-render one-shot terminal callback ownership

Date: 2026-10-31. Sole Draft PR #663. main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged.

## Problem and independently observed RED

The predecessor `493877bead3e392d5e2b5bcdacffcc8ec2b97697` had independently completed [CI #41213416632](https://github.com/chigre/Picture_Capture/actions/runs/41213416632) Windows/macOS/Ubuntu × Python3.10/3.13 6/6 + Risk-tier, [OCR #41213416558](https://github.com/chigre/Picture_Capture/actions/runs/41213416558) 3/3 and [CodeQL #41213413372](https://github.com/chigre/Picture_Capture/actions/runs/41213413372) Python/Actions 2/2. That green baseline does not cover this new packet.

Direct rendering correctly guarded source/SECTION/PDIC hash, save progress, scan epoch and render serial, but its `done` and `failed` closures had no per-dispatch **terminal claim**. Thus the same completed worker could call done twice or deliver contradictory done→failed / failed→done and repaint/clear an already accepted UI. A terminal callback initially ignored because of pending human edits could become active again when those edits cleared, despite being the same old task.

Test-only `0c7473e821e117a92b32c62c47509a89ad72d493` added six deterministic synthetic 8×8 image/PDIC/SECTION cases, including first-terminal outcome snapshots and private exception suppression. [CI #41216502798](https://github.com/chigre/Picture_Capture/actions/runs/41216502798) macOS Python3.13 actually observed **6 targeted FAILED / 5,202 passed / 2 skipped**. All six new failures reflect this duplicate/contradictory callback exposure; **do not treat the RED SHA as passed CI**.

## Minimal implementation

Commit `6c7088560334765f3fbc70d40d93edc32ea6a294` modifies only `src/picture_capture/ui/focused_filter_workflow.py::_request_filter_batch_render`:

- Keep a per-dispatch in-memory `terminal_claimed` cell in the direct-render callback closure. Reject duplicate or contradictory callback **before** doing any UI/cache work.
- Match existing render serial, scan epoch, active focused workspace and selected batch *before* claiming the first terminal event. Claims for stale tasks cannot mutate the new epoch.
- Claim the first owned terminal delivery even if the GUI cannot render because human edits or an uncertain save still exist. An old task must never reactivate when the pending flag clears later. Preserve all existing source hash, failure anonymization and safe-save checks.

No new shared state, persistence field, permanent Undo log, disk writer, or OCR sidecar migration. The proof is synthetic E2: local temporary image and sidecar bytes only. Source hashes are volatile readbacks, **not** an OS multi-file CAS. No real latency or accuracy improvement is claimed.

## Acceptance and exclusions

The final **code+docs SHA** must independently obtain completed Windows/macOS/Ubuntu × Python3.10/3.13 CI **6/6 plus Risk-tier gate**, OCR Smoke 3/3, and CodeQL Python/Actions 2/2. All remain **PENDING at this documentation commit**, not inferred from old SHA or intermediate source CI. The terminal result should be recorded in an immutable PR comment after exact-head verification, rather than creating a new unchecked commit.

**NOT PERFORMED:** Windows R3 E3; #483 W1–W11; #503 full operator Undo/Redo; real dictionary OCR/PDIC/PPP/SECTION/Profile GUI crop/save-reopen; real source XY and big-image benchmark. Automated E2 is **not** human E3.

**DEFERRED:** R6 learning from true labels, R8 real dictionary scans. No private contents uploaded. Keep #663 Draft/Open/Unmerged, main unchanged and Issues #503/#562/#483 open.

Next: inspect remaining async *prefetch* duplicate success/failure, mid-callback re-entrancy and SECTION/navigation under saved-source changes. Do not duplicate this now-covered direct-render packet.
