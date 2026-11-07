# PC-CQ v1.3.0 G1 — R3 target recovery-marker check in PDIC restore writer (2026-10-30)

## Root cause

Filtered proofreading calls `proofreading.pdic_restore.write_pdic_atomic`.
The existing routine writes a staging PDIC named
`.<target>.restore.tmp` using `io.formats.write_pdic` and then
`os.replace(temp, target)`. The shared `write_pdic` checks a
`.r3-inflight.json` marker relative to its *supplied path*, which is
the temp filename, **not the actual target PDIC**. Therefore a
non-finished R3 multi-file recovery transaction can coexist with a
separate filtered save which replaces the target PDIC.

## Fail-first test and constrained repair

Test-only commit `697ff2d7c881841c57c28280439deb658ee02a35`,
`tests/test_g1_filtered_r3_marker_actual_writer_20261030.py`,
uses the actual production `write_pdic_atomic` through the filter
page writer and separately as a direct writer:

- Existing unresolved marker at target PDIC: no mutation.
- Marker created after staging the temporary PDIC but before its
  `os.replace`: no mutation, staged file removed.
- Dangling symlink in marker slot: refuse when OS supports symlinks.
- Unmarked healthy write continues to succeed.

Repair reuses `transactions._marker_present`, including its
`lstat` semantics for dangling symlinks, and checks the **real target
marker** both before staging and immediately before replacing.
The public writer signature, existing fixed temp name, whole-file
replacement, source-image pixel coordinates and PDIC/PPP/SECTION
formats are unchanged.

## Explicit safety limits

This protects against markers already present at either check, not a
marker created between the final check and OS replace. It does **not**
supply OS-level cross-process atomic CAS, a filesystem lock, or a
multi-file power-loss atomic transaction. No synthetic CI test is a
substitute for real Windows scanned dictionary E3: CJK IME/paste,
20× Undo/Redo, PDIC/PPP/SECTION save-reopen, source pixel/crop
parity, #483 W1–W11 still NOT PERFORMED.
Keep #663 Draft/Open/Unmerged, main unchanged and #503/#562/#483 open.
