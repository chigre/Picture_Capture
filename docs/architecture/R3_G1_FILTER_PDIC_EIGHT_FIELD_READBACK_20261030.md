# PC-CQ v1.3.0 / G1 — exact eight-field PDIC readback (2026-10-30)

## Problem and test-only proof
The filtered PDIC writer already validates original words and exact
source bytes before publication, then checks all resulting words,
original-image pixel coordinates, and row order after publication.
However the on-disk PDIC record carries eight fields:

`word#x#y#x_percent#y_percent#current_page#previous_page#next_page`

Its percentage coordinates and navigation references were not verified.
A foreign or faulty writer could alter one of those sidecar metadata
fields while leaving every word, pixel coordinate and row position
unchanged. The old writer would incorrectly report success.

Fail-first test-only commit:
`84e6c4f64cff6df6466da07d3e8073047374febf`
`tests/test_g1_filtered_pdic_metadata_readback_20261030.py`.
Tests use actual `write_pdic` and `read_pdic`, including a successful
eight-field control and separately corrupting percent-X, percent-Y,
current-page, previous-page, and next-page fields.

## Bounded correction
Inside `proofreading/focused_pdic_updates.py` after successful
existing readback, reconstruct the canonical eight fields for **every**
intended PDIC row using the same UTF-8 and 2-decimal `:g` percentage
representation as `io/formats.write_pdic`, and compare them to the
actual freshly published records in row order. Mismatch raises without
a blind rollback over a possibly foreign publication. The public
writer interface, source pixel-coordinate ownership, existing
serial-worker callback, OCR and PDIC format remain unchanged.

## Explicit limits
Post-write verification and the existing prepublication byte check are
optimistic data-integrity checks, NOT cross-process OS atomic compare-
and-swap, multi-file power-loss atomicity, or assurance against a
change *after* the check. Native Windows E3 (CJK IME/FocusOut,
20× Undo/Redo, PDIC/PPP/SECTION reopen, original-source pixel/crop
parity) and #483 W1–W11 remain NOT PERFORMED. Keep #663 Draft,
Open and Unmerged; #503/#562/#483 open.
