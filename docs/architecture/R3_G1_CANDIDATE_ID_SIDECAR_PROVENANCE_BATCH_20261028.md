# G1 / #503 — R3 candidate-owned deletion provenance & replay batch (2026-10-28)

## Evidence and owner

Scope: `proofreading/candidate_delete.py:prepare_candidate_delete` builds three-file
PDIC/manual_selection/simplified deletion bytes; `ui/review_candidate_delete_actions.py`
commits before updating live Entry, candidate `selected`, Tk checkbox and
word-count UI; `proofreading/candidate_history.py` replays only proved
candidate-owned deletes through `transactions.publish_owned_review_bundle`.
This batch preserves that existing ordered transaction protocol; it does
**not** add a new persistent Undo history, training path or file format.

### Newly identified failure modes

1. **Two live entries claiming one candidate_id.** Snapshot `owner_ids`
   was made into a dict and only the selected Entry's ID was checked.
   Another Entry could reuse the same OCR candidate_id; deleting one
   wrote `manual_selection.overrides[cid].selected=False` for **both**
   apparent owners, even though the other Entry remained in PDIC.
   Subsequent Undo history refused the ambiguous pair, but that was too
   late: the destructive delete had already committed.
2. **Unrelated simplified record reusing the same source coordinates.**
   Simplified lookup chose the record solely by `x,y`, without requiring
   its `source_word` to identify the selected PDIC headword. A manually
   edited/stale companion could be silently removed despite belonging
   to a different word.
3. **Untrusted simplified document provenance.** The delete path
   accepted any JSON dict containing an `entries` list, ignoring
   `format`, `format_version` and `page`. A companion belonging to
   another page/schema could be modified and marked successfully saved.
4. **Preexisting manual selection contradictory to the intended delete.**
   An existing override for the same candidate_id was rejected only
   when `selected=False`; a malformed, unselected/unknown or
   differently-worded record could otherwise be replaced with the
   batch's `selected=False` deletion decision.

### Changed behavior

- Require an unambiguous frozen snapshot: no duplicate entry object
  IDs in owner fingerprints; target cid must belong to **exactly one**
  frozen Entry. Independently maintain unique OCR candidate evidence.
- For an already present manual override on this cid, require an
  explicit boolean `selected is True` and, if it declares a word,
  that exact word must match the selected Entry. Missing manual file
  remains a supported legacy creation case.
- A present simplified JSON document must match its expected format,
  version 1 and current page stem. Every record must have readable
  coordinates; if it shares the candidate's exact coordinates, its
  `source_word` must exactly match the selected Entry before removal.
  Duplicate coordinates continue to fail closed. No matching record
  remains a valid optional-companion case; other unrelated simplified
  text/manual flags are preserved, including translated words not
  equal to the headword.
- Every refusal occurs **before** any R3 journal stage, disk write,
  Entry/Tk checkbox mutation or Undo frame creation. The caller keeps
  the existing benign status message and returns without side effects.

### Targeted regression matrix (19 new parameterized/normal cases)

`tests/test_b3_candidate_owned_deletion_20261015.py` gains:

- 2 frozen-owner collision scenarios (another live Entry shares cid;
  duplicated identity fingerprint);
- 7 simplified conflicts (stale `source_word`, wrong page, format,
  version, omitted version, duplicate coordinates, malformed other row);
- 5 stale/malformed existing manual override cases;
- 3 valid compatibility cases (matching existing manual overrides,
  unrelated translated simplified record, existing simplified sidecar
  without a candidate record);
- 2 end-to-end history cases (full-byte PDIC/manual/simplified
  Delete→Undo→Redo with surviving unrelated human override; refused
  stale simplified does not create undo history).

The previous R3 tests for absent legacy selected flag, empty PDIC,
failed fsync/atomic publication, recovery marker quarantine and Tk
post-commit ordering remain in place. Windows/macOS/Ubuntu + Py3.10,
R3 GUI synthetic smoke and OCR smoke must be verified on the **exact
post-batch HEAD** before declaring CI success.

### Explicit remaining boundaries

This is a **safe refusal**, not a repair of stale/manual data; do not
delete or rewrite a human's conflicting override to make tests green.
An OCR candidate cache, source image or SECTION can still change between
snapshots and disk publication; transient R3 `O_EXCL` plus optimistic
before/after checks do not create cross-file OS-level atomic CAS or a
durable power-loss journal. No claim of improved OCR precision/speed.

**Real Windows dictionary-page G1 acceptance remains NOT PERFORMED**:
20× Undo/Redo, deleted candidate selection/checkbox, manual overrides,
source coordinates, FocusOut, close/reopen, mixed page edits and real
PDIC/PPP/SECTION/crop/export must be verified by an operator. R2 #483
W1–W11 and user-deferred R8 PR-B remain separate OPEN gates.
PR #663 stays Draft/Open/Unmerged.
