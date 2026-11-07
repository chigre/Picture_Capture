# PC-CQ v1.3.0 G1 — R3 Undo/Redo unreadable diagnostic source (2026-10-30)

## Failure mode

`snapshot_review()` returns `None` if a ReviewWindow cannot establish its
fresh disk/UI ownership snapshot. `ReviewSessionHistory._apply()` then
performs a *second* PDIC/simplified byte readback to decide if the failure was
only a transient Tk rebind, in which case the in-memory Undo/Redo frame can
safely remain available for a later retry.

Before this patch, an inaccessible PDIC or simplified sidecar at the second
readback raised `OSError` out of the human Undo/Redo path; that error was not
a controlled `False` refusal and left history ownership unresolved.

## Contract and bounded change

Fail-first synthetic regression commit
`5ee9d06e15e8276886fde9c838b182d985e45688` adds
`tests/test_g1_r3_undo_redo_unreadable_diagnostic_20261030.py`:
- If a PDIC readback raises `PermissionError` after snapshot failure,
  Undo must return False, invalidate both history stacks, and leave source
  PDIC and simplified bytes untouched.
- A failed simplified readback does the same for Redo.
- If source image/PDIC/simplified bytes are verifiably unchanged and only the
  live widget snapshot is temporarily unavailable, Undo returns False but
  *retains* its saved history frame for rebind/retry.
- Actual foreign PDIC or simplified source drift invalidates history and
  does not write to either file.

Only the `current is None` diagnostic branch in
`src/picture_capture/proofreading/transactions.py` changes.
`OSError` from diagnostic source checks means source ownership **cannot be
verified** and is treated as stale for history retention. No persistence
publication, R3 marker schema, PDIC/PPP/SECTION data, ownership
fingerprints, Tk bindings or normal Undo/Redo transaction rules change.

## Governance and limits

This is synthetic E2 failure safety, not an OS-level atomic CAS or
multi-file power-loss atomicity claim. Real Windows dictionary R3 E3 and
#483 W1–W11 were explicitly postponed by the user and remain
**NOT PERFORMED**, not PASSED. R2/B2 and full R3 human acceptance remain
in progress. Work stays in sole Draft PR #663; main unchanged and issues open.
