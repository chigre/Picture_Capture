# G1 / #503 — Noncandidate deletion paired PDIC/simplified commit

2026-10-28, one vertical behavior owner: `ui/review_entry_actions.py`
calling the existing paired persistence owner
`proofreading/review_bundle.py`.

## Demonstrated loss / partial-commit route

Prior `delete_review_entry` committed pending text and deleted an Entry from
the shared model, called `parent.save_pdic(..., sync_editors=False)`, and
only afterwards invoked `_persist_simplified_page` on the independent
simplified human JSON. If another proofreader had modified that JSON,
the source-pinned sidecar writer correctly refused, but PDIC deletion had
already landed. The UI had also removed the row before the second failure,
and the intended Undo history was not recorded.

## Reuse existing R3 bundle, not another format

The noncandidate branch now requires `capture_review_before` to return a
trusted current page, PDIC and Entry-object snapshot. It prepares editor text
and removes the selected Entry/cache row only inside
`protect_review_pdic_commit`; `commit_review_bundle` publishes both
PDIC and simplified through its existing exact-byte R3 recovery journal.
Only a complete commit may mutate presentation/highlighting, append
committed Undo history or produce an evidence-deletion observation.
The protective context recovers in-memory Entry/cache if the saved PDIC
remains the original version after a failed commit; if uncertainty persists,
the existing recovery marker quarantines later edits.

The paired writer now uses existing `transactions._snapshot_sources_match`
rather than a duplicate list of source checks, and tracks exactly the roles
it has published. It checks unchanged PDIC/simplified, manual_selection,
OCR, original image hash, SECTION path/bytes and Profile before each role
and after the last role. A third-party simplified edit that arrives
between PDIC and simplified is not silently overwritten. If rollback cannot
prove the old disk state, the marker stays: quarantine, never claim atomicity.
After successful commit the ReviewWindow's simplified source pin advances
to the committed bytes, avoiding its own next-save false stale alarm.

## Focused tests and remaining caveats

`tests/test_b3_plain_review_delete_bundle_20261028.py` covers normal
deletion, pending text of other rows, fault before/after both file publish
roles, foreign PDIC bytes at claim time, external simplified edit between
role writes (including exact foreign byte preservation + recovery marker),
and stale cross-page invocation. The existing optional capture ordering
assertion now requires `commit_review_bundle` before event capture;
source and UI contracts remain intact.

The R3 journal is recoverable *optimistic* file publication, not OS CAS,
not power-loss-durable cross-file atomicity or complete operator E3.
Real Windows dictionary pages, manual candidate checkboxes, 20 Undo/Redo
steps, FocusOut/PDIC/PPP/SECTION save/reopen, source-image XY/crop and
R2 #483 W1–W11 remain **OPEN / NOT PERFORMED**. PR #663 remains
Draft/Open/Unmerged, #503 and #562 remain open; PR-B real scans deferred.

## Initial exact-head CI feedback and repair

Source head `e3e3bee776d7d72cadac9c35dacd78c0bd84fd8d`: [CI #40696349131](https://github.com/chigre/Picture_Capture/actions/runs/40696349131) initially
reported 12 Ubuntu failures. Nine new behavioral test cases were blocked
before assertions by an incorrectly qualified module import
(`ui.review_bundle` rather than the existing
`proofreading.review_bundle`). Three legacy static tests expected the
obsolete sequential parent save, object-equality-based Entry removal, and
single-file-only readback condition. Correct the import; update the same
historical assertions to require paired R3 commit, strict Entry identity,
and per-role source rechecks. **No tests deleted and no production source
protection weakened.** Recheck all exact-head workflows; never count this
first CI as success.
