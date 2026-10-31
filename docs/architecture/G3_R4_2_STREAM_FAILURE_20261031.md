# G3 R4.2 — Streaming remainder failure lifecycle audit (2026-10-31)

## Failure and threat boundary

A focused scan processes complete initial page batches and streams later pages. If a later `scan_page` raises (for example unreadable PDIC), the old `remaining_failed` callback only wrote the exception string to the status area. `_filter_scan_complete` remained false, so an operator could see a perpetual 'preparing next batch' cue without a terminal failure indication. The exception string might contain a private local project path.

## Safe correction

- Introduce an in-memory `_filter_scan_failed` per scan epoch (initially false, reinitialized on re-filter). On failure, require the original serial and an active focused mode before recording failure.
- Keep `_filter_scan_complete=False`: a failed stream is **not** a completed full scan. `_filter_available_target_count` continues to expose **only whole previously delivered batches**. Never publish the failed chunk.
- Do **not** clear the current row widgets, saved data, pending focused edits, or rendered crop when a remainder fails. Show a generic partial-result failure in the batch indicator and user status; a next-batch attempt must direct the operator to re-filter, not claim the worker is still preparing.
- A new valid filter request resets the failure flag and incremented scan serial. An old worker failure cannot alter the new scan or retry's UI. Do not echo `exc` / traceback paths to the status bar.
- Keep crop payload epoch, render serial and snapshot-signature checks intact. No change to default-OFF experimental toggles, data persistence, PDIC/PPP/SECTION, raw XY, manual override, OCR cache, or R3 transaction commits.

## Reproduction and limits

Red-first `tests/test_g3_r4_streaming_scan_failure_20261031.py` invokes actual `run_focused_filter` first/remaining callbacks with two synthetic page identities; second page raises `OSError`. CI #41161338739 reproduced one missing-terminal-state failure while the stale-epoch control passed. No private source pages or OCR data used. Re-run exact-head Windows/macOS/Ubuntu Python 3.10/3.13, OCR Smoke, Risk-tier, CodeQL Python/Actions and GUI smoke after source fix; no green or performance claim until observed.

Windows R3 E3, #483 W1–W11, #503 manual Undo, R4.2 real operator exercises, R6 human labels and R8 real scans: **NOT PERFORMED / DEFERRED**. Keep #663 Draft/Open/Unmerged and main unchanged.
