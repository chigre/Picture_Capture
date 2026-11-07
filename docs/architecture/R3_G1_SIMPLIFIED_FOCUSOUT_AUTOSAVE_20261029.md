# PC-CQ v1.3.0 / #503 G1 — unreported simplified editor text (2026-10-29)

## Reproduction and boundary
The ReviewWindow simplified Tk Entry reports KeyRelease and <<Paste>>/<<Cut>>, but
native IME/text-service/manual widget edits can alter StringVar without either
callback. Before this packet, `autosave_commit` tests only word deltas and
`_simplified_dirty_pages`, so the changed visible simplified text could be
ignored. Pending-page explicit `save` can likewise treat it as untouched.
The test-only parent commit is recorded separately; its tests must fail before
this production patch. This is **E2 synthetic**, not Windows E3 acceptance.

## Scope of production fix
- `review_page_lifecycle._has_unreported_simplified_input` compares the current
  visible StringVar values against the *rendered, originally bound* per-row
  values, using the canonical owner/XY identity validator. It is read-only.
- Both shared autosave and pending-page explicit save use this detection, so
  existing `_commit_edits` -> `commit_review_bundle` source guards remain
  the only publication path.
- Simplified Entry adds FocusOut reconciliation. Leaving an unchanged saved
  manual value does not spuriously mark the entire page dirty.
- No new disk format, sidecar write path, nearest-XY fallback, OCR acceptance,
  UI singleton, model instance, or Undo/Redo claim.

## Gates and limits
Run exact-head focused pytest and Windows/macOS/Ubuntu Python 3.10/3.13 CI,
three-OS OCR Smoke and CodeQL. Record results only when actually completed.
Source checks are optimistic not OS-level multi-file CAS. A user must still
verify real Windows IME/menu/clipboard FocusOut, delayed autosave,
20-step Undo/Redo, page/reopen, PDIC/PPP/SECTION and original crop parity.
Do not merge or mark #663 Ready, do not close #503/#562/#483.
