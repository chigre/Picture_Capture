# G1/G2 — ReviewWindow simplified editor row/pixel ownership (2026-10-28)

## Reproducible cause (source grounded, not a claimed observed incident)

`ui/review_simplified_workflow.py:on_simplified_key` used
`parent._ordered_entries_reading_order()[index]` to select a PDIC-associated
original-image X/Y coordinate even though the Tk editor was bound to an Entry
in `ReviewWindow.row_entries[index]` at the previous render. Sorting/SECTION
changes or deferred Tk redraw can change current index order before the
KeyRelease, causing an explicit human simplified edit to land under another
headword's coordinate. A separately queued clipboard callback captured only
the numeric index; whole-page regenerate used `min(len(...))`, silently
overwriting a subset of human simplified records on a partial redraw.

## Single UI owner repair

- Require page stem, rendered-row lengths, exactly matching **live Entry
  object identities**, and unambiguous source-pixel X/Y keys before changing
  any simplified model, dirty flag or saved record. Never use the current
  sorted order to guess a rendered editor owner. Reject stale page, partial
  rows, duplicate identities or duplicate source coordinates.
- KeyRelease: validate its actual emitting widget when supplied, keep the
  bound Entry through the claim step, and reject if its identity, text,
  simplified value or page changed during the claim.
- Clipboard after_idle: capture the Entry identity and page along with the
  row index, apply only if the old owner is still rendered there.
- Auto refresh: reject unowned rows before modifying their widget or cache.
  Explicit whole-page regenerate requires the complete trusted bound set;
  revalidate after automatic conversion and manual edit claim instead of
  truncating to the minimum length.

All changes stay in the canonical `ui/review_simplified_workflow.py`
owner; public ReviewWindow methods, monkeypatch dependency injection,
simplified/PDIC/PPP/SECTION storage schemas and original pixel coordinate
conventions remain unchanged. No new root facade or module migration.

## Regression and verification boundary

`tests/test_b3_simplified_rendered_owner_20261028.py`: synthetic reordered
rows, stale KeyRelease widget, delayed clipboard ABA, page change, dropped
or duplicated row identity, duplicated X/Y, partial render, claim-time races,
healthy auto refresh and complete page regenerate; no real scan data.

This is a **fail-closed UI ownership guard**, not a cross-process CAS, filesystem
transaction or proof that real Windows human edits are correct. R2 #483
W1–W11, R3 #503 candidate / 20-step Undo/Redo / FocusOut / reopen and
real PDIC/PPP/SECTION/crop source-pixel E3 operator gate stay
**OPEN / NOT PERFORMED**. #663 stays Draft/Open/Unmerged.
