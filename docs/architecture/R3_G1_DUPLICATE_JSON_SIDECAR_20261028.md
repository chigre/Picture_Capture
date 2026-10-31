# G1 / #503 — Reject ambiguous human proofreading JSON before candidate delete (2026-10-28)

## Evidence and affected owner

Owner: `src/picture_capture/proofreading/candidate_delete.py`. Candidate-owned deletion
reads existing `*_manual_selection.json` and the simplified-review sidecar,
changes one proven candidate, then serializes the entire JSON document. Python's
default `json.loads` accepts duplicate object members and NaN/Infinity. For
example, `{"word":"human A","word":"human B"}` becomes one field. Rewriting
the document would irreversibly discard a distinct human-authored value even
when the duplicated member belongs to **another** candidate or simplified row.
This is a deterministic parser behavior, not a claim of a witnessed user incident.

## Repair / failure-injection contract

- Parse both human-editable sidecars with a recursive duplicate-member rejecting
  object-pairs hook and a non-finite JSON constant veto. This is local to the
  candidate-delete preparation boundary; it does not migrate any JSON schema.
- Any duplicate member (top-level, selected candidate, unrelated human override,
  selected or unrelated simplified record) or non-standard numeric constant
  rejects the entire delete **before staging a recovery marker**.
- Preserve exact PDIC, manual-selection and simplified bytes; candidate.selected,
  checkbox, Entry membership and Tk redraw stay unchanged on refusal.
- Retain valid historical sidecar handling, including absent manual file,
  matching preexisting override, valid simplified record and candidate Undo/Redo.

## Focused regression

`tests/test_b3_candidate_owned_deletion_20261015.py` adds eight parameterized
failure cases: manual duplicate root/target/unrelated, manual NaN, simplified
duplicate root/target/unrelated, simplified NaN. The existing success/Undo/Redo
tests remain. The prior parser would accept these malformed documents and
rewrite them; the new tests demand byte-exact refusal.

## Limitations

This does not provide cross-file OS atomicity, process-wide locking or real
Windows user acceptance. The existing R3 marker, source fingerprint and
publication safeguards are unchanged. #503/#562 remain open, PR #663 remains
Draft/Open/Unmerged, and R2 W1–W11 and all real scanned-page E3 tests remain
NOT PERFORMED.
