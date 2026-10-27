# Issue #503 — fail-closed R3 recovery marker entry types (2026-10-28)

## Why this is needed

The R3 proofreading undo/redo and candidate-owned deletion transaction use the
per-PDIC `.<PDIC>.r3-inflight.json` marker as a short-lived recovery journal.
A marker may be left by a failed or interrupted save; it is not a persistent
user undo-history file.

Before this fix, `_verified_recovery` used `Path.is_file()`. A directory
or a dangling symlink returned False and was interpreted as **no pending
transaction**. Additional R3 snapshot and staging checks used `Path.exists()`,
which also returns False for dangling links. This could let a new edit/Undo
proceed despite an occupied, untrusted journal pathname.

## Implementation and ownership

Canonical source: `src/picture_capture/proofreading/transactions.py`.

- `_marker_present(marker)` checks `lstat` rather than following links.
  Any directory entry (ordinary file, directory, symlink including dangling)
  counts as occupied. Only `FileNotFoundError` at that path is absence;
  permission errors are propagated instead of treated as no journal.
- `_verified_recovery` reads a journal only if its **lstat** file type is
  regular. Unexpected types raise `ValueError` before any recovery writes,
  rather than following an attacker-controlled symlink or allowing a page
  load to continue as if no R3 transaction existed.
- Existing R3 staging, snapshot, Undo/Redo and post-unlink checks reuse the
  same marker presence policy, preventing a dangling marker or unsuccessful
  unlink from being accepted as absent.
- A valid regular recovery journal retains the current version 1/2 schema,
  exact byte checking and mixed-state restoration behavior. There are no
  changes to PDIC, manual_selection, simplified files, candidate identity,
  source-image geometry, or Tk shortcuts.

## Regression gate

`tests/test_issue503_r3_nonregular_recovery_marker_20261028.py` tests
directories, symlinks to external files, dangling symlinks, deterministic
symlink-like lstat for Windows machines without symlink privileges, denied
lstat, no-op marker unlink, and a legitimate absent/regular recovery path.
All unsafe cases preserve PDIC bytes and retain quarantine. Real symlink
tests are skipped only on hosts that prohibit symlink creation; the
cross-platform simulated-lstat test remains required.

## Security and crash limits

This checks the entry type **when observed**, not an OS-level atomic
file-descriptor lock. An adversarial writer can swap marker entries between
`lstat` and the subsequent open. This change does not implement
cross-process CAS, cross-file durable transactions, or protection from power
loss. Such design requires a separate, carefully reviewed filesystem
protocol, not silent relaxation of recovery ownership.

## Status and acceptance

This #503 patch is intentionally a separate small Draft PR based on `main`,
so the ongoing #562 Draft PR #663 can remain unmerged without being replaced
or force-pushed. Do not confuse CI with operator acceptance. R3/#503 real
Windows dictionary-page manual edit, candidate checkbox, Undo×N/Redo×N,
FocusOut, close/reopen and recovery testing remain **NOT PERFORMED**.
R2/#483 W1–W11 also remain pending. Never merge / mark Ready automatically
without resolving the applicable gates.
