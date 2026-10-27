# G1 / #503 — Post-stage R3 source race and inter-file publication guard (2026-10-28)

## Reproduced risk and single owner

Owner: `src/picture_capture/proofreading/transactions.py`. Ordinary
`_publish_restored_snapshot` previously checked PDIC/manual/OCR/SECTION/Profile
only **before** writing the transient recovery marker. The marker's disk I/O
creates a deterministic gap: a second writer can change an owned PDIC or a
read-only source after preflight, then Undo publishes a stale PDIC version.
The candidate-owned `publish_owned_review_bundle` already rechecked sources
immediately after staging, but not between its ordered PDIC/manual/simplified
replacements; a third-party manual edit after PDIC publication could be
overwritten by the next replacement. This is a source-level failure scenario,
not a claim of having reproduced it on a real dictionary.

## Changes

- Centralize exact source checks in `_snapshot_sources_match`. Frozen
  `SavedSnapshot` supplies image SHA, PDIC/manual/simplified bytes, OCR,
  SECTION path+bytes and Profile bytes. Only roles already published by this
  operation may match their target bytes; all other roles must remain at the
  frozen original bytes.
- Ordinary Undo/Redo checks after marker staging, before each replacement,
  and after the last replacement. Candidate-owned delete/Undo/Redo retains
  its pre/post-stage check and gains checks between replacements and after
  the final write. No new sidecar schema, candidate ownership inference,
  persistent Undo journal, or GUI/checkbox mutation is introduced.
- Any detected drift aborts and attempts the existing before-state rollback.
  If a third-party owned-file version is neither staged before nor after,
  the marker remains to quarantine the page instead of overwriting that
  person's bytes. Unchanged rollback still clears the marker. The caller
  does not mutate live Entry/checkbox on failed publication.

## Deterministic regression and compatibility

Seven new fault-injection cases in
`tests/test_b3_review_session_transactions_20261015.py`:
five source types (PDIC, manual_selection, OCR, SECTION, Profile) changed
*during* journal staging; a human simplified edit between ordinary PDIC and
simplified writes; a human manual override between candidate PDIC and manual
writes. The latter two assert exact third-party bytes, no Entry mutation,
and a retained quarantine marker. Existing normal Undo/Redo, 20-step
history, candidate Delete→Undo→Redo, failure rollback, Windows/Tk and OCR
smoke remain mandatory.

## Boundary / release gates

Checks are optimistic and leave a final check-to-replace race on non-locking
or non-cooperating writers. No cross-process/OS cross-file atomic CAS,
power-loss durability, or true Windows human verification is claimed.
Real dictionary candidate checkbox, 20× Undo/Redo, FocusOut/autosave,
PDIC/PPP/SECTION/crop/source X/Y, close/reopen and #483 W1–W11 are
**NOT PERFORMED**. #663 remains Draft/Open/Unmerged; R8 remains deferred.
