# G1 / #503 — R3 recovery intent snapshot coherence (2026-10-28)

## Exact owner and reproducible data-integrity gap

Owner: `src/picture_capture/proofreading/transactions.py`.
The recovery decoder first validated the R3 journal and returned a file-role
list, but `recover_pending_for_page` opened the same marker again to read
`rollback_required`. A concurrent replacement between those reads could
switch the recovery policy while retaining a **different** list of original
PDIC/manual/simplified bytes. With a complete after-state and the original
policy requiring rollback, a flipped policy could cause recovery to silently
keep the after-state and unlink the journal instead of restoring before-state.
The failed-live-publication path likewise separately re-read the marker;
journal replacement after initial parse could lead to stale rollback and
deletion of a peer's recovery intent.

## Cohesive owner repair and compatibility

- Decode each journal **once**, returning the exact raw bytes and parsed
  `rollback_required` along with its validated file-role list. Retain
  existing v1/v2, `None` (absent file), and explicit false-policy semantics.
- Require the recovery marker to remain a regular file with **identical raw
  bytes** before rollback/publication, between sequential file rollbacks,
  after each write, and before cleanup. On mismatch, refuse the remainder
  and retain the marker instead of unlinking unknown peer intent. Use the
  same rule in restart recovery and failed-live-publication rollback.
- When an older false-policy marker must be upgraded to rollback-required,
  check its original bytes before the rewrite and adopt the new written
  exact bytes as the remainder of the transaction's expected journal.
- No new persistent Undo journal, PDIC/PPP/SECTION/manual JSON schema,
  candidate ownership inference, or GUI/Entry mutation.

## Regression matrix

`tests/test_b3_review_session_transactions_20261015.py` adds
**9 synthetic cases**: restart recovery vs live failure rollback; each
intercepted after initial verified parse, replacing either rollback policy
or owned file intent (4 cases); the same replacement during first PDIC
rollback before the simplified companion (4 cases); and successful unchanged
false-policy single-file recovery (1 case). The conflicting journal and
unresolved companion must be left in place, including when an earlier
owned-file write already landed.

## Limitations and gates

Byte checks are optimistic, not an OS atomic compare-and-swap; a peer
may still race in the last check-to-unlink window. They do not prove
cross-process lock coordination, cross-filesystem atomicity, or power-loss
durability. Real Windows dictionary-page GUI, candidate checkbox and
20-step Undo/Redo, FocusOut, PDIC/PPP/SECTION save/reopen, original X/Y,
crop/export, and R2 W1–W11 remain **OPEN / NOT PERFORMED**.
Keep #663 Draft/Open/Unmerged and #503/#562 open.
