# PC-CQ v1.3.0 G1 — full filtered PDIC row readback (2026-10-29)

## Reason
The existing filtered PDIC writer already refuses stale original words
and changed source bytes, then reads back the committed file. Previously
the readback only checked total row count and the requested page/X/Y
words. A foreign update to an unrelated word, source coordinate, or
record order could survive that narrow check and be misreported as a
successful save.

## Fail-first regression
The test-only commit `fd9f9d8c03fd39c94caef884ff82f543bf0122dc`
adds `tests/test_g1_focused_pdic_full_readback_20261029.py`.
Four actual writer/readback cases: unchanged intended write succeeds;
foreign modification of an **unmodified** row word, of an unmodified
row source coordinate, and record reordering each must fail closed.
A raised verification exception preserves the foreign published bytes;
the asynchronous UI failure callback retains human pending edits.
Do not automatically write an old rollback snapshot onto the PDIC.

## Bounded change
Only `proofreading/focused_pdic_updates.py` changes: after disk
readback, compare the **complete ordered sequence of (word, x, y)**
against the intended working rows. Keep the prior explicit count and
requested coordinate verification and all original-word/source-byte
prepublication guards. This catches otherwise unnoticed postpublish
damage to other headwords or original-image positions. The public
writer function, existing tests, PDIC schema, and OCR pipeline remain.

The source-byte guard and postpublication readback are optimistic;
they are NOT atomic across processes and cannot promise power-loss
atomicity. Full row-level verification does not validate arbitrary
PDIC metadata fields nor rule out a writer modifying the file after
the readback. Native Windows scanned-dictionary E3, CJK IME/FocusOut,
20× Undo/Redo, PDIC/PPP/SECTION reopening and pixel/crop parity plus
#483 W1–W11 are NOT PERFORMED. Keep #663 Draft/Open/Unmerged.
