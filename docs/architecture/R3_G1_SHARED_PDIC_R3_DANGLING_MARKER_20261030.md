# PC-CQ v1.3.0 G1 — shared PDIC writer and dangling R3 marker (2026-10-30)

## Why the shared writer still needed a guard
The prior filtered restore-writer fix checks the real PDIC target journal
before staging and immediately before replacement. Ordinary UI, deferred,
batch and other callers also use the shared `io.formats.write_pdic()`,
whose R3 guard used `marker.exists()`. Python follows a symlink for
`exists()`; a symlink in the recovery-marker slot that points to a
missing file therefore appears absent and allows the PDIC write.
Unreadable marker metadata must also stop the write.

## Fail-first test and minimal correction
Test-only commit `21b75ab731b6001ff2c28e8a5bf35db5509ee344`,
`tests/test_g1_shared_pdic_r3_dangling_marker_20261030.py`:
- Dangling recovery marker symlink blocks ordinary `write_pdic`;
  preserve the original PDIC and symlink.
- Simulated denied recovery marker `lstat` fails closed without PDIC
  mutation (rather than treating unreadable state as absent).
- Normal unresolved marker still blocks.
- Absent marker allows valid PDIC serialization and no-op unchanged save.

The production change is limited to
`src/picture_capture/io/formats.py::write_pdic`. Replace
`marker.exists()` with `marker.lstat()` and interpret **only
`FileNotFoundError`** as a genuinely absent directory entry.
Existing files and symlinks, including dangling ones, remain blocked;
unreadable status propagates. The public API, PDIC/PPP/SECTION format,
all image coordinates, OCR and serializer remain unchanged.
The behavior intentionally matches
`proofreading.transactions._marker_present` without importing a
proofreading domain module into the lower-level I/O module.

## Limitations and acceptance
This checks the marker before the shared writer begins. It is not
an OS-level multiprocess atomic CAS, a lock on the marker directory,
or a power-loss multi-file transaction; a concurrently created marker
after this check remains outside the guarantee.
Native Windows scanned-dictionary E3 (IME/paste, FocusOut, Undo×20,
Redo×20, PDIC/PPP/SECTION save-reopen, source X/Y and crop parity)
and #483 W1–W11 remain NOT PERFORMED. PR #663 stays Draft/Open
and Unmerged, main stays unchanged, #503/#562/#483 remain open.
