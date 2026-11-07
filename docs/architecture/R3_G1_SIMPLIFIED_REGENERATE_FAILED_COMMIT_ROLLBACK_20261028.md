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

## Exact-head CI failure: hosted Tcl path vs pure quick-state contract

At source HEAD `4371c027f8781e288b60bb63bbea025ea6caf0b3`, CI [#40692254312](https://github.com/chigre/Picture_Capture/actions/runs/40692254312) attempts 1 and 2 repeatedly failed
Windows Python 3.13's `test_state_initialization_requires_no_visual_widgets_and_binds_traces_once`
before executing its trace-ownership assertions: the runner could not read
its installed Tcl `init.tcl`. 4637 other tests passed; the other five test
jobs and OCR/CodeQL succeeded. This history is **not** treated as a pass.

The affected test is a pure quick-state variable/binding contract. Replace
only its dependence on a real Tcl interpreter with a test variable that
explicitly implements and validates `get`, `set`, `trace_add` and callback
count; its assertions about once-only traces and parameter routing remain.
Dedicated real Tk Windows/macOS GUI creation and managed PDIC/PPP,
proofreading, R3 candidate Tk smokes **remain active in the same CI workflow**.
If a real Tk smoke fails, the job must remain red; it must not be marked as
a user dictionary-page or Power-loss E3 acceptance pass.
