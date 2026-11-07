# Round 139 — Pre-PDIC ownership-read failure identity (2026-10-27)

## Scope

The existing-marker OCR publication flow exports OCRed first and writes PDIC
only after ownership and optional SECTION/source-image checks. If a filesystem
read fails at any of four **post-export, pre-PDIC** checkpoints, the disk pair
is indeterminate: do not write PDIC and do not roll back OCRed alone.

This change preserves that established fail-closed policy and attaches the
*exact* caught `OSError` instance to `RuntimeError.verification_error`, while
retaining `__cause__ is verification_error`. It covers:

1. Reading OCRed immediately after its exporter returns.
2. Reading PDIC after OCRed export.
3. Re-reading PDIC after the final page-context validator.
4. Re-reading OCRed after the final page-context validator.

## Regression contract

`tests/test_issue562_pre_pdic_verification_identity_round139_20261027.py`
injects a `PermissionError` separately at all four checkpoints. Each case
asserts exception identity, no PDIC writer invocation, unchanged PDIC bytes,
preserved exported OCRed bytes and no rollback staging artifacts.

This is diagnostic consistency only; no changes to publication order,
transaction guarantees, PDIC/PPP/SECTION format, original-pixel coordinates,
Tk behavior, or Windows spawn behavior. Filesystem CAS and cross-file atomicity
remain unavailable; manual real-dictionary scan acceptance is **OPEN /
NOT PASSED**. Synthetic fault-injection tests do not close that gate.
