# G1 / #503 — All-page simplified regeneration failure rollback

2026-10-28. Single owner: `src/picture_capture/ui/review_simplified_workflow.py`.

## Root cause and exact user-data risk

Before this packet, `regenerate_simplified_current_page` first modified the
entire page's Tk simplified text, derived actual text, per-row manual and
auto-refresh flags, source-X/Y cache records, and dirty status. Only **after**
those changes did it invoke the already source-pinned
`_persist_simplified_page`. If another proofreader had modified the human
simplified JSON since cache load, that call correctly refused to overwrite the
foreign bytes, but the ReviewWindow could still display newly computed OpenCC
values and show the manual flags cleared. That was an incomplete in-memory
transaction after a refused disk commit.

## Cohesive recovery behavior

After validating complete live row identity and page and evaluating all OpenCC
values, freeze each affected row's display, actual text, manual and automatic
flags, exact cache record, and pre-existing dirty status. Build the proposal
for all rows. Apply it and call the canonical protected persistence entry point.
On any error *before persistence returns*, restore only the values and records
still equal to this regeneration's own proposed state; preserve synchronous
newer human edits made from callbacks and retain a dirty flag when rollback is
not provably complete. Re-raise the failure; never show the success banner or
emit a committed-save history record for a refused operation. Successful
commits continue to set OpenCC values, clear manual flags, persist the
simplified sidecar using source pinned R3 journaling and update the status.

The rollback does not attempt to write old bytes to disk itself; the existing
R3 writer owns publish/failure/marker quarantine. This separation prevents
an in-memory fallback from overwriting another proofreader's saved bytes.

## Synthesized behavior and fault tests

`tests/test_b3_simplified_rendered_owner_20261028.py` expands successful
and negative cases: failure during protected persist, preexisting dirty state,
a failure mid-page Tk widget update, and a newer synchronous human callback
modifying a widget and the same cached record. Existing stale page/Entry/
coordinate tests remain.

`tests/test_b3_simplified_sidecar_source_pin_20261028.py` exercises the
real simplified-review serializer/path with source fingerprints and a fresh
cache: another human changes the same row, adds an unrelated row, or deletes
the sidecar; protected save rejects the stale proposal while preserving exact
foreign bytes and restoring original Tk values, manual/automatic flags,
sidecar cache rows and dirty state. A healthy disk commit confirms actual,
display, source row, provenance advancement and status consistency.

No real scanned dictionary is loaded and no performance, accuracy, or
human-acceptance claim is implied. This is still optimistic version checking
rather than OS atomic CAS, and not proof of crash/power-loss durable multi-file
transactions. True Windows dictionary E3 candidate/checkbox, Undo/Redo ×20,
PDIC/PPP/SECTION save/reopen, original X/Y/crop, and #483 W1–W11 remain
OPEN / NOT PERFORMED. #663 remains Draft/Open/Unmerged and #503/#562 open.
