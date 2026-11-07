# PC-CQ v1.3.0 · G1 source-word / original-pixel manual owner and history reload
2026-10-28 · Issue #503 / #562 · sole Draft PR #663.

## Evidence and destructive association

ReviewWindow had retained simplified manual `{x,y,source_word,text,manual}`
records, but its actual render path selected a saved correction using only
the pixel key `(x,y)`. If another OCR/manual step replaced the PDIC word
at that coordinate, the prior human simplified correction was displayed as
if it were attached to the replacement. The earlier raw-byte freshness and
JSON-losslessness contracts do not detect this semantic misassociation:
the sidecar and PDIC can each be stable, parseable and individually authentic
while no longer belonging to each other.

## One provenance boundary through disk and UI

`simplified_review.source_word_conflicts` detects exact headword mismatch
for any saved row at an occupied original PDIC pixel. Historical sidecar
coordinates without a corresponding live PDIC row are preserved rather
than being guessed/migrated. `validate_source_word_binding` rejects a mismatch
for standard human sidecar documents without modifying bytes.

`review_bundle.commit_review_bundle` uses the frozen pre-edit snapshot's
word/X/Y identity to validate the *original* source sidecar, then validates
the preview against the *post-edit* Entry word/X/Y identities before any PDIC
or sidecar publication. Legitimate pending headword edits can update the
proposed `source_word`; stale ones cannot be silently reattached.

The independent protected simplified writer snapshots source PDIC bytes,
validates old and proposed sidecar words against original PDIC entries,
then rechecks original PDIC bytes before proposal, after staging and after
publishing. R3 O_EXCL recovery/rollback still owns uncertain disk writes.
This remains optimistic provenance checking, **not** atomic filesystem CAS.

On ReviewWindow render a conflicting saved row is replaced visually by a
clear source-identity warning and that simplified editor is disabled.
Saved human bytes remain untouched. KeyRelease, FocusOut, automatic refresh
and forced all-page regeneration refuse overwriting such a record. The user
can inspect or deliberately resolve an original-word mismatch separately;
this packet does not autoconvert manual edits into another headword.

For normal and OCR-candidate Undo/Redo, successful restored-file publication
invalidates the cached simplified row dictionary **and** its byte-provenance
pin. Next render must load/pin the current restored disk version afresh,
rather than retaining a pre-Undo provenance token.

## Synthetic failure and compatibility matrix

`tests/test_b3_sidecar_source_word_identity_20261028.py` covers same original
XY with renamed PDIC headword, sidecar with mismatching source_word, pending
legitimate rename versus incomplete target proposal, a historical orphan
coordinate that must not be discarded, independent sidecar writes where PDIC
changes during preview or just after sidecar publication, wrong-target
source_word, and obsolete FocusOut/KeyRelease/all-page regeneration.
Two existing history suites add plain/candidate Undo/Redo stale pin
invalidation while keeping same Entry object identity.

No real Windows dictionary/scan was used. E3 candidate checkbox, 20 Undo/Redo
steps, manual_selection/PDIC/PPP/SECTION reopen, source crop/X/Y pixel tests and
R2 #483 W1–W11 remain **OPEN / NOT PERFORMED**. No cross-process CAS, power-loss
durability or performance/recognition accuracy claim. PR #663 remains
Draft/Open/Unmerged; #503/#562 Open; PR-B scans deferred.

## Initial CI test-contract failure and repair

The implementation HEAD `e7d3a5def11ec41c31a9314d648a2a275b1c92b0` first CI
[#40705467706](https://github.com/chigre/Picture_Capture/actions/runs/40705467706)
exposed five focused failures in Ubuntu and macOS defaults, not a general
pytest skip: two older regeneration fault tests used human rows missing
`source_word`; two older core mocks omitted the rendered Entry's `word`;
the new after-publish race expected to reach its interception but a stricter
early PDIC guard had already refused it. These are preserved in the first
red CI evidence.

The repair gives existing synthetic rows the current real source-word/Entry
identity so the intended UI rollback path remains exercised, and injects
the PDIC race immediately **after** the real exclusive R3 journal is staged
but **before** canonical sidecar publication. Both source-byte and original
pixel ownership protections remain untouched. A new exact-head workflow
must finish successfully before this engineering packet is marked green.

## Second exact-head CI: phase-accurate fault injection

At intermediate HEAD `be76035cb363017ad8497e53869e983c14ea8046`, [CI #40706851786](https://github.com/chigre/Picture_Capture/actions/runs/40706851786)
returned 4,676 passing Ubuntu tests and one failed synthetic assertion.
The old `after_journal_stage` test injected through a marker-stage hook
that was never reached because the existing PDIC fail-closed check already
refused. Human sidecar bytes were not overwritten; nonetheless, the claimed
injection phase was unproved.

The same packet corrects its second fault case to inject PDIC changes on
the exact **post-preview PDIC readback** and explicitly requires the injected
callback to have run. A new positive control requires healthy
`guarded_write_records` to call the real R3 journal stage and commit a
new human simplified text while keeping an orphan source-coordinate row.
This retains the original preview-writer injection and prevents a mere
blanket refusal from masquerading as coverage. No production guard was
disabled. Recheck all CI on a new exact head; do not report this red
attempt as green.
