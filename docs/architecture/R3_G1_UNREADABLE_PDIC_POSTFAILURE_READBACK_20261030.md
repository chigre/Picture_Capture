# PC-CQ v1.3.0 G1 — failure-after-failure readback quarantine (2026-10-30)

## Problem

Both `proofreading.save_safety.protect_app_pdic_commit` and
`protect_review_pdic_commit` preserve original `Entry` / canvas /
simplified review state and attempt to roll back speculative in-memory
mutations only when *exact original PDIC bytes* are still on disk.

In their exception handler they performed
`_bytes_or_absent(path) == before` directly. When the primary
PDIC write raises `OSError("disk full")` and a second
readback raises another `OSError` (permissions, transient offline
volume, device failure), the diagnostic exception escapes:
- the original write failure traceback is masked,
- the guard never sets `_deferred_save_uncertain`, and
- the UI may retry with a stale deferred snapshot whose true
  publication state was never established.

## Fail-first test and bounded fix

Regression file
`tests/test_g1_save_safety_unreadable_postfailure_readback_20261030.py`,
tests-only commit `dba7b81dd82c4794a46281540e904bae62cbeaeb`:
- one failure-then-unreadable case for main canvas, one for ReviewWindow;
- both must propagate the *primary* write failure, quarantine retries,
  preserve human word/sidecar edits and untouched known fixture bytes;
- both ordinary proven-unchanged rollback controls must continue
  restoring speculative in-memory state.

Shared private `_verified_same_disk_snapshot` safely verifies
the byte snapshot only on the same page. An `OSError` from this
diagnostic read means **unverified**, not unchanged; the existing
exception branch sets the uncertain-write bit and raises the
original exception. Both contexts share the same helper. No
normal successful save flow, GUI public signature, persistence
format, source X/Y, OCR selection or candidate history changes.

## Scope and limits

This is a conservative error-path quarantine, not cross-process CAS
or a proof that no writer can change the PDIC after successful
readback. It does not resolve a PDIC publication that already
occurred; explicit reconciliation is still necessary.
The real Windows scanned-dictionary E3 tests (IME/paste,
FocusOut/autosave, 20× Undo/Redo, PDIC/PPP/SECTION reopen and
original-source pixel/crop parity) and #483 W1–W11 remain
NOT PERFORMED. Keep PR #663 Draft/Open/Unmerged.
