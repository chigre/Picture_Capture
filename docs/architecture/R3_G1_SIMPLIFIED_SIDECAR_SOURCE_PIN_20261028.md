# G1 / #503 — Simplified sidecar external-source preservation (2026-10-28)

## Destructive path demonstrated by code

ReviewWindow cached per-page simplified human-edit rows, then its independent
`_persist_simplified_page` wrote those cached records without checking if the
underlying file had changed since the cache was read. A second proofreader could
edit or add unrelated rows in the interval; saving the old cache rewrote and
discarded those exact bytes. Main-window row deletion also swallowed guarded
ReviewWindow persistence failure and used unguarded read/write as fallback.

## Single-owner source pin and shared recovery writer

`proofreading/simplified_review.py:guarded_write_records` accepts an explicit
original-byte expectation, refuses mismatched/malformed/ambiguous source JSON,
previews through the canonical writer, rechecks disk bytes, creates an O_EXCL
R3 transient recovery journal for its one `simplified` role, publishes,
read-verifies and removes the marker after successful commit only. On errors,
attempt the existing R3 rollback, quarantine on unresolved external writes,
and never overwrite a foreign version.

`ui/review_simplified_workflow.py` pins the source bytes (and resolved path)
on the first cache read, checks again after parsing, demands the same source
on save and advances the snapshot only after successful commit. Stale
FocusOut or asynchronous Tk row callbacks may not change cache entries for
a different page or incomplete rendered Entry set.

`ui/main_entry_actions.py` now refuses the deletion rather than re-writing
unprotected bytes when ReviewWindow's guarded persistence fails. It restores
unsaved in-memory simplified cache entries on refusal. Its no-ReviewWindow
case also uses the same source-checked writer.

## Focused regression and remaining gate

`tests/test_b3_simplified_sidecar_source_pin_20261028.py` covers normal
save/source advance, unrelated and same-row external human edits, external
deletion, corrupt file, missing provenance, publication fault before/after
os.replace, third-party replacement during publish, preview race, stale
cross-page FocusOut and both main-window delete paths. Existing SECTION
and lexical mocked fixtures are adapted to the stable rendered Entry contract.
No user-provided scanned files are used.

This is optimistic source verification plus a fail-closed journal, **not**
an OS-level atomic compare-and-swap, durable cross-filesystem transaction,
or proof of real Windows user acceptance. Real dictionary operations,
20 Undo/Redo steps, PDIC/PPP/SECTION save-reopen, original crop X/Y and
R2 #483 W1–W11 remain OPEN / NOT PERFORMED. #663 stays Draft/Open/Unmerged;
#503 and #562 remain open.
