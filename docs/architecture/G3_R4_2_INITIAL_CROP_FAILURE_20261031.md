# G3 R4.2 — Initial scan / crop-failure epoch safety audit (2026-10-31)

## Failure surface and ownership

The active owner is `src/picture_capture/ui/focused_filter_workflow.py` behind the existing `ReviewWindow` adapters. The first asynchronous page worker and the current batch crop worker have separate callbacks. Before this packet, **initial scan failure** set `_filter_scan_complete=True` despite no trustworthy batch; error text and traceback could reach local Tk widgets/stdout. A pending crop failure only compared its render serial, so a callback from an older **scan epoch** could erase a new workspace if the render serial had not changed. Current crop failures also surfaced the raw exception. Optional prefetch failure printed raw details. None of these failures authorizes any PDIC write.

## Red-first reproducible evidence

- Test-only `85188655c43c7239471e9cc933934447c35732d8`; [CI #41165165064](https://github.com/chigre/Picture_Capture/actions/runs/41165165064) confirmed on Ubuntu Python 3.13 **4 failed / 4,989 passed / 3 skipped**, macOS Python 3.13 **4 failed / 4,990 passed / 2 skipped**. The four failures are precisely the new initial-terminal, post-mode-exit, stale-crop-epoch and exception-redaction assertions, not inferred from the test source alone.
- Test file: `tests/test_g3_r4_streaming_scan_failure_20261031.py`. Fixture uses synthetic page identifiers, text and errors; no real dictionary, Profile, PDIC content, OCR results or physical scan.
- A fifth assertion covers safe optional crop prefetch failure: clear the pending prefetch key for retry without echoing private error details.

## Minimal fix and exact bounded guarantee

- Source fix `901ad2ec2f96d6397eb39db73ffe0ce02b5a5b2d`: a current, active first-worker error sets `_filter_scan_failed=True` and **keeps** `_filter_scan_complete=False`, publishes no targets, and displays generic failure/retry text. After mode exit or a newer scan serial, its callback is inert.
- Crop-render failure now checks **both** render serial and scan epoch plus active filter mode; current error gives a generic message, while a stale error leaves the new workspace untouched.
- Optional crop prefetch failures clear only their own prefetch key and avoid raw exception printing. On a later explicit render/navigation, the prefetch may be retried; it is not silently considered a successful crop.
- Previously fixed later-page failures retain the completed source batches and their terminal indicator; the focused test fixture has an intentionally stubbed indicator helper, so the explicit later-failure status assignment is retained.
- No original image, source XY, geometry, SECTION mapping, PDIC/PPP/manual-selection/OCR schema, cached provenance, persistent setting, R3 commit, or default-OFF toggle is changed. This is **in-memory asynchronous failure handling**, not OS-level file atomicity or a cure for external modification between crop snapshots.

## Acceptance and remaining risk

Require the **final exact PR HEAD** full Windows/macOS/Ubuntu × Python 3.10/3.13 regression, Tk smoke and wheel, OCR three OS, Risk-tier gate, CodeQL Python/Actions. The red-first run is not a passing gate; source checks in progress or queued are not an acceptance result. Review the final diff and unresolved threads. Existing manual safeguards remain in force: Windows R3 E3, #483 W1–W11, #503 complex Undo and G3 R4.2 operator steps **NOT PERFORMED / DEFERRED**; R6 human labels and R8 real scans not authorized. Do not merge or mark Ready.
