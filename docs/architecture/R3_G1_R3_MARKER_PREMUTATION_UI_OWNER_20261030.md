# PC-CQ v1.3.0 G1 — fail-closed R3 marker before UI mutation (2026-10-30)

## Issue

The lower-level shared PDIC writer now rejects even dangling R3 journal
symlinks by `Path.lstat`. Yet three *callers* checked
`_recovery_path(page).exists()` before performing other work:

1. Main page `save_pdic` calls pending-manual-source verification and
   can reconcile Tk editor values / sort `Entry` objects before
   the shared writer finally rejects the target.
2. Deferred checkbox `flush_deferred_page_save` calls manual source
   verification before ultimately reaching the shared writer.
3. ReviewWindow `commit_proofread_entries` writes `Entry.word`,
   captures simplified edits, and reconciles the main canvas; its
   direct caller need not immediately publish PDIC.

A **dangling symlink** at the real R3 recovery-journal pathname satisfies
`Path.exists() == False`, while the unresolved journal pathname remains
owned. A late disk-writer rejection is insufficient to protect in-memory
human edits or sidecar state.

## Reproduction and bounded change

Fail-first tests-only commit `2382f8a12f3ccce4a66a93df7e92d225262f54d6`
adds `tests/test_g1_r3_dangling_marker_editor_preflight_20261030.py`:
three early-fail scenarios across the main page, deferred checkbox
and ReviewWindow editor; existing regular-marker negative control;
unmarked ReviewWindow positive control.

At each of the **three existing preflights** replace
`_recovery_path(page).exists()` with the established shared
`transactions._marker_present(_recovery_path(page))`. This uses
`lstat` to detect dangling symlinks and propagates an unreadable
marker error. A regular marker and a healthy marker-free edit
retain existing semantics. No shared PDIC serializer, page/X/Y
ownership, OCR arbitration, persistence schema, UI signature or
remaining callback behavior is changed.

## Safety and E3 limits

These guards are immediately before their own work, not an OS-wide
atomic lock/CAS across processes or a multi-file power-loss guarantee.
A separate writer can still race after the preflight, which later
IO/transaction checks must handle independently.

Real Windows scanned dictionary E3 (IME/paste/FocusOut, Undo/Redo×20,
PDIC/PPP/SECTION reopen and original-source pixel/crop parity) plus
#483 W1–W11 are NOT PERFORMED. Maintain sole PR #663 Draft/Open
and Unmerged, #503/#562/#483 open and main unchanged.
