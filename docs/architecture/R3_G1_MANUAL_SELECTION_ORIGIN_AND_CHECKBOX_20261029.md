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

## G1 checkbox → delayed PDIC/manual publication boundary (2026-10-29)

A new source-derived failure matrix found that `deferred_save.flush_deferred_page_save`
wrote PDIC before checking the queued manual-selection bytes. A foreign human
manual edit could therefore reject sidecar publication *after* PDIC had landed,
with the queued snapshot already cleared. A PDIC writer that replaced data
then raised could also leave a retryable stale snapshot. The regular
`save_pdic` route had the same post-PDIC manual failure ambiguity.

The UI owner now freezes the first checkbox's PDIC source bytes and retains
that pin across coalesced clicks. Both regular and timer save preflight the
pending human source before PDIC. Deferred writes reject stale PDIC bytes,
preserve the queue on prepublication failure, and quarantine any write-then-
raise or PDIC-committed/manual-failed state as `_deferred_save_uncertain`.
Derived page-row metadata is refreshed only after both files commit.
Existing PDIC/manual JSON formats and the Tk callback surface are unchanged.
Targeted tests cover external PDIC/manual edits, post-replace exceptions,
pre-replace retry, subsequent refusal, normal coalesced save and direct-save
preflight/quarantine. This is an **optimistic** check, not OS CAS nor a
power-loss / cross-file atomic transaction. Human E3 is still NOT PERFORMED.

## G1 candidate choice + position-switch grouped source ownership (2026-10-29)

One R3 UI owner `ui/review_selection_workflow.py`, no new persistence
protocol or root facades. **Fail-first** regression HEAD
`b036c68ef1c6cb9ba8c918c98210e6962e9e6e3b`:
[CI #40750612646](https://github.com/chigre/Picture_Capture/actions/runs/40750612646)
Ubuntu Python 3.13 reports **7 new failures, 4,722 passed, 3 skipped**
(invalid OCR confidence/y/score, choice manual-first then PDIC disk full,
sibling override writer fault, foreign human sidecar between siblings,
timer failure). These were executable failures, not extrapolated from source.

Prior `apply_candidate_choice` immediately committed manual_selection
before parsing alternative OCR numeric fields and before PDIC could save.
A malformed OCR choice or PDIC failure left a manual-only persisted decision.
The position-switch callback mutated sibling Entry, selected flag and checkbox
before its second manual override could fail; a source race could leave
a partial in-memory switch. The first staged implementation encountered a
legacy V2.8.18 fixture failure because approximate OCR entry lookup tried to
use the original sibling Entry as the target *before* sibling removal,
which is a genuine ownership ambiguity, not a reason to relax the guard.

The owner now pre-validates alternatives; stages candidate/sibling human
decisions together only in memory; requires a unique candidate_id and a
strictly candidate_id-owned Entry (no nearby X/Y ownership guessing), and
rejects foreign/anonymous rows occupying the candidate's exact source X/Y.
Only then can it update the shared candidate/Entry/checkbox state. Staging
failure restores the prior queued human decisions/evidence without modifying
third-party saved bytes. A deferred timer/widget failure restores the old
membership and forbids stale retries. Immediate candidate choice defers
manual_selection until the existing guarded PDIC save. Before-PDIC failure
restores the prior UI decision and pending state; PDIC-committed/manual-failed
or postreplace uncertainty remains quarantined and needs human reconciliation.
No OS-level cross-file CAS, three-file atomicity or power-loss durability
is claimed. The **actual source-pixel X/Y** is used; no visual-neighbor
lookup is authorized for candidate-owned mutation.

`tests/test_g1_candidate_choice_position_switch_transaction_20261029.py`
exercises input failures, writer injection, external manual race,
position-switch staging/scheduler failures, neighboring-owner ambiguity,
normal choice/position switch, postreplace quarantine, and pending
ReviewWindow Undo refusal. Historical original-Y switch contract in
`tests/test_core.py` is preserved with a more informative assertion
on failures. This is E2 synthetic only; real Windows dictionary
checkbox/20-step Undo/Redo, FocusOut, source crop, PDIC/PPP/SECTION and
R2 W1-W11 remain **NOT PERFORMED**. Keep #503/#562 Open, #663 Draft.
