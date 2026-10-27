# Round 141 — PDIC / PPP shared atomic writer: retain both failures

## Scope and rationale

Issue #562 / Draft PR #663; canonical owner
`src/picture_capture/io/formats.py:write_text_atomic`.

PDIC, PPP and related text sidecars share `write_text_atomic` through
`write_text_if_changed`. Staging is done in the destination directory,
followed by flush/fsync and `os.replace`. Before this change, its
`except Exception` block deleted the staging file without protecting the
original exception: when the write, fsync or replace *and* the cleanup unlink
both failed, the cleanup `OSError` replaced the actual publication failure
as the only surfaced exception.

## Behavioral change

When both publication and best-effort staging cleanup fail, the writer raises
a descriptive `RuntimeError` with the exact original
`publication_error` and `cleanup_error` attached, and the original write
error set as the explicit `__cause__`. This deliberately reports an
indeterminate on-disk state, including any leftover hidden `.tmp` file.
No subsequent writer/retry/rollback is attempted.

When cleanup succeeds, the **same original publication exception** still
propagates (unchanged type/object). On the successful path, serialization,
fsync, atomic replacement, file mode, newline handling and
`note_page_artifact_edit` are unchanged. A replace that physically succeeds
but raises afterward still propagates its original exception; callers are
responsible for checking committed bytes, not assuming the file is old.

## Regression

`tests/test_issue562_atomic_sidecar_cleanup_round141_20261027.py` covers
PDIC/PPP at the shared writer boundary:

- Failed fsync or failed replace **and** failed temporary unlink (4 fault
  combinations), exact primary/cleanup exception identities and leftover
  staging path, no target overwrite.
- Failed replace but successful temporary cleanup (2 cases), exact original
  exception identity and no `.tmp`.
- Replace executes then raises (2 cases): detect applied bytes, retain the
  error and avoid a second destructive operation.
- Normal PDIC/PPP roundtrip, retained original-pixel PDIC X/Y and saved PPP
  geometry (1 case).

## Remaining limits and manual acceptance

This does not implement cross-process atomic compare-and-swap,
two-sidecar PDIC/OCRed crash consistency, durability of directory entries
across power loss, nor automatic reconciliation of indeterminate outcomes.
It makes failures diagnosable while preserving the original byte formats.

The real scanned dictionary-page GUI acceptance gate remains
**OPEN / NOT PASSED** (ordinary/OCR/combined detection, source-pixel
coordinates, PPP/SECTION/PDIC editing and save/reopen, crop/export parity).
CI and synthetic tests are necessary but do not replace that human check.
Keep PR #663 **Draft / Open / Unmerged**. Check latest exact-head CI and OCR
Platform Smoke before declaring any platform passed.
