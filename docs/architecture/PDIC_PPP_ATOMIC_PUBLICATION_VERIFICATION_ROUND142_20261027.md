# Round 142 — verify PDIC/PPP atomic publication on disk

## Owner and motivation

Issue #562 / Draft PR #663. `src/picture_capture/io/formats.py:write_text_atomic`
is shared by PDIC, PPP, and other text sidecar writers.

Previous behavior trusted a normal return from `os.replace(staging, target)`.
A faulty/patched filesystem adapter can return successfully **without moving
the file**. Similarly, a separate proofreader can replace target bytes as
soon as the atomic operation returns. Previously the caller could report a
successful PDIC/PPP save and emit a page-artifact edit notification even though
the on-disk contents were not those published by this operation.

## Behavior now

After fully flushing/fsyncing the staging file, capture its *actual bytes*
from the staging path before replacement. That avoids constructing a second,
possibly platform-different encoding or CRLF representation.

After `os.replace` returns, require both:

1. The staging path no longer exists (the atomic move took place).
2. The target's current bytes exactly equal those staged.

If either proof fails, raise an explicit publication error; the existing
best-effort staging cleanup runs and the caller does not emit a success
notification. If reading the result itself raises an `OSError`, preserve the
identical error as `verification_error` and the explicit exception cause.
Do not retry the replacement or roll back external edits.

This is a post-operation *observation*, **not** an atomic compare-and-swap:
external writers can race after the final read. If a concurrent writer
changes the target, that newer content must not be overwritten by recovery.

No changes to normal PDIC/PPP bytes, image-pixel coordinates, serialized
schema, file naming, Windows/Tk interfaces, OCR workflow order, or public
function signatures.

## Regression

`tests/test_issue562_atomic_sidecar_publication_verification_round142_20261027.py`
adds eight parameterized scenarios covering both PDIC and PPP:

- Replace returns normally but does nothing: report failure, retain old bytes,
  clean staging file and suppress page-edit notification.
- Replace succeeds and an external editor writes new bytes before verification:
  detect conflict without overwriting the editor or retrying.
- Post-replace target read is denied: retain exact verification exception
  identity/cause, no false success, committed bytes remain.
- Ordinary successful saves: verify canonical PDIC text and original-pixel
  coordinates, PPP polygon coordinates and no temporary artifacts.

## Limits and acceptance

Crash/power-loss durability, directory fsync, cross-process atomic CAS,
and OCRed+PDIC two-file transaction recovery are unresolved. This check may
surface an indeterminate result after actual disk publication, but it never
attempts destructive guessing. The real-scanned dictionary-page GUI,
ordinary/OCR/combined workflow, PPP/SECTION/PDIC save/reopen,
source-pixel coordinates and crop/export manual acceptance remains
**OPEN / NOT PASSED**. Tests cannot replace that acceptance gate.

Keep PR #663 **Draft / Open / Unmerged**. Verify exact-head six-platform CI
and three-platform OCR Smoke independently before claiming completion.
