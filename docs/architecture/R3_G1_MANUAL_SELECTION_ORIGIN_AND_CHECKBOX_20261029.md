# G1 / #503 + #562 — manual_selection and checkbox source ownership
2026-10-29. Single UI owner: `src/picture_capture/ui/review_selection_workflow.py`. Candidate destructive owner: `proofreading/candidate_delete.py`.

## Reproduced byte-loss root

Previously `_read_manual_overrides` treated every malformed human
`*_manual_selection.json` as *no saved choices*, then `_write_manual_override`
could rewrite that empty payload and erase existing human selection data.
Likewise the delayed candidate checkbox queue stored a mutable payload but
no fingerprint for the exact source bytes, so a different proofreader's
same-page correction arriving between checkbox click and deferred flush
could be silently overwritten. When a candidate-owned delete found an
already selected override with arbitrary extra human annotations, it
replaced that dict with three standard keys and discarded the unknown
human annotation.

## Fail-closed owner behavior

`_validated_manual_selection` strictly parses raw disk bytes using the
already present unambiguous JSON decoder (reject duplicate members and
nonfinite constants), validates page/version/overrides and does NOT
convert parse errors to an empty human table. Missing file remains a
valid *new* project source.

An ordinary candidate checkbox update retains the exact page and raw
source version `_pending_manual_override_origin` while coalescing further
same-page changes. Every preflight/flush requires the same raw bytes;
cross-page navigation flushes the old page using its frozen page name
instead of the currently selected page. A safe single-file temporary
replacement avoids truncating existing human bytes on I/O failure.
Unknown existing fields on the specific candidate's override, or a
different saved headword owner, cause an explicit refusal before
normal checkbox/position-switch/choice model mutation. Candidate delete
uses the same conservative ownership rule for unknown prior human fields.

Sibling preflight runs before any position-group toggle changes Entry,
Tk checkbox, candidate selection, or pending evidence; a corrupt source
cannot be hidden by an empty fallback. The existing standalone owner
facades/API signatures and PDIC coordinate/PPP/SECTION/OCR formats are
not changed.

## Synthetic matrix and limits

`test_b3_manual_selection_source_pin_20261029.py` checks malformed
bytes, duplicate JSON keys, NaN, wrong source page/version, unknown
human-owned fields, foreign same/other candidate edits and deletion/
creation during pending flush, multiple valid same-page checkbox changes,
page-switch flush, before-replace disk failure and UI preflight
failures. Candidate deletion tests assert a prior unknown annotation
does not disappear. Old test expecting malformed sidecar->empty is
replaced by explicit fail-closed and unchanged byte assertions.

**Important:** Version readback plus same-filesystem atomic replacement is
*optimistic*, not an atomic compare-and-swap. Existing main app PDIC
deferred save may reach disk before manual_selection flush refuses, so
this is a source-preservation improvement, not a three-file durable
transaction or power-loss proof. User must reload and reconcile any
uncertain post-PDIC state. Real Windows dictionary E3, 20-step Undo/Redo,
PDIC/PPP/SECTION save/reopen, source pixel/crop and R2 #483 W1–W11
remain OPEN / NOT PERFORMED. Single Draft PR #663 Open/Unmerged,
Issues #503/#562 Open, old #664 Closed/Unmerged.

## First new-head CI and no-weakening contract repair

Source HEAD `f0bbd51949520cb8c23af2f68f0ffa3fc14a602d` [CI #40731357381](https://github.com/chigre/Picture_Capture/actions/runs/40731357381)
reported one shared failure across all six OS/Python pytest jobs, while
~4700 other tests in each job passed. The failing historical V2.8.18
single-click original-Y switch test constructed a real app subclass with
`PictureCaptureApp.__new__` but omitted `project` and `current_page`.
Before this packet, that invalid owner could still change an Entry;
mandatory manual_selection source preflight correctly refused, so the
legacy fixture's success assertion became impossible.

The test now supplies a temporary project root and synthetic current page,
retains all original mutually-exclusive candidate and object/XY assertions,
and exercises the original click path under a legitimate source owner.
Production fail-closed preflight is not relaxed; the first CI failure is
preserved. A different final commit HEAD must pass its **own** six-platform
Risk-tier, OCR Smoke and CodeQL gates before the packet is considered
engineering-verified.


## 2026-10-28 G1 / candidate-delete whole-page provenance closure

`prepare_candidate_delete` formerly checked only the simplified row at the deleted X/Y and accepted coercible coordinates in unrelated human rows; it could reserialize a sidecar with string/float/bool coordinates, unknown human metadata, or a different source word for another live PDIC row. The candidate's manual-selection document also accepted an explicit unsupported `version` and rewrote it. The owner now reuses the existing `simplified_review.validate_source_word_binding` contract for the **entire** saved simplified document against frozen PDIC entries (strict coordinate types, no unknown fields/duplicates, exact source-word provenance), and rejects explicit non-v1 manual schema while retaining legacy version-absent input. These are pre-publication fail-closed checks: PDIC/manual/simplified bytes, Entry identity, checkbox and undo history stay untouched on rejection. Tests cover malformed and healthy legacy data. This is not an OS-level CAS, genuine Windows human acceptance, or a claim of cross-file atomicity.
