# PC-CQ R3 / #503 — compound replay Tk row ownership, source-path witness and destroyed UI

Date: 2026-10-31. Implemented exclusively in the sole open, unmerged [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663); baseline `main@ec20989ea8c026cca5337293e67850b6b6df30f2`. Every image is only a synthetic local byte placeholder; no user or third-party scans, manual E3, or permanent Undo database was used.

## 1. Why this is an owned transaction boundary

A safe R3 ordinary delete and an OCR-owned candidate delete have different durable file scopes:
- An ordinary one-row deletion or saved text edit is an *explicit unlinked Entry* PDIC/simplified-sidecar transaction, with a short-lived recoverable marker.
- An OCR-owned delete must prove the candidate identity and selected state, and commit PDIC + human manual-selection override + optionally simplified-sidecar as one recoverable bundle. It is **not** a guess based on nearby OCR text/coordinates.

Both can be undone/redone in a session only when every active Entry, candidate and persisted source still matches its frozen exact snapshot. A new mixed-history operation must not rebind a different Entry to a previous editor, replay an obsolete sidecar after a path switch, or turn a successful disk commit into an exception that leaves history on the wrong stack.

## 2. Genuine test-first red and exact reproductions

- Test-only `f1338c181e3590aa7c780b6cea22f153ca4fd693`: [CI #41195919532](https://github.com/chigre/Picture_Capture/actions/runs/41195919532) Ubuntu Python 3.13 **22 failed / 5,128 passed / 3 skipped**. The new negatives reproduced old UI mispairing on both ordinary/candidate Undo and Redo, private-path-bearing `RuntimeError` after successful committed presentation, and history incorrectly retained after manual/OCR/SECTION/Profile **source path** changed while byte-identical old files still existed. The unchanged-source retry controls are intentional positives.
- Test-only `094b885fb34ecc6a1c46dec160bc9d5cb2a241da`: [CI #41196070214](https://github.com/chigre/Picture_Capture/actions/runs/41196070214) Ubuntu Python3.13 **30 failed / 5,130 passed / 3 skipped**; additional negatives exercise destroyed `StringVar.get` and old row binding getter during a prepublication Tk check. Mixed candidate/ordinary history replay in both sequential directions and unchanged-source controls are positive checks, not newly unowned operations.
- Further tests `7c2a960ce2986ea19e12ec03e9753be6cc388240` exercise eight cases of the **real** `snapshot_review` with a killed row resolver raising either `RuntimeError` or `tkinter.TclError`. These tests demand refusal with no private traceback, unchanged committed files, and a retryable history if the backing source remained identical.

The red-only SHAs are **not** gate passes. Do not substitute a skipped/queued/failing run as acceptance.

## 3. Product corrections (bounded to replay)

- `src/picture_capture/proofreading/transactions.py` `_live_source_bindings_match`: an unavailable Tk snapshot is retryable only while the app's currently resolved manual-selection, OCR, SECTION and Profile **paths**, as well as old image/PDIC/simplified/manual/OCR/SECTION/Profile **bytes**, remain frozen and identical. Changing an active resolver to another path with identical bytes invalidates old Undo/Redo state. Resolver failures fail closed with no exception detail leaked to status or stdout. This predicate is shared by plain and candidate replay.
- Plain `ReviewSessionHistory._apply` and OCR `CandidateReviewHistory._apply` capture a **tuple of precommit rendered Entries and StringVars** after the source check and before the durable writer. After an owned deletion is undone/redone, newly added/removed Entry membership must *not* cause the old StringVar at list index zero to receive another row's text. Only still-existing objects in their original precommit binding are updated; the UI coordinator then requests a full render.
- A destroyed old Tk variable's `set` cannot make a completed disk transaction appear failed or prevent its Undo/Redo frame from advancing. Presentation-only callback errors are contained after the authoritative PDIC/manual/simplified + Entry/candidate state has committed. A destroyed `get` or row resolver **before** commit returns False and preserves disk/history; the read-only `snapshot_review` catches native Tk teardown exceptions and returns `None` instead of propagating a private path.
- Existing `tests/test_b3_review_session_transactions_20261015.py::test_two_saved_edits_replay_without_row_index_matching` previously assumed that a restored row order would silently reassign old widgets by index and allow a second Undo without repaint. This is unsafe. The test was **strengthened**, not dropped: verifies old vars remain tied to old Entries, the second immediate replay refuses without losing history, then simulates the ReviewWindow's explicit `_request_render_rows` rebind and proves both Undo and both Redo still succeed. No ability to replay valid multi-step history is abandoned.
- The synthetic provenance fixture in `tests/test_r3_plain_history_missing_sidecar_provenance_20261031.py` was made to expose explicit, matching manual/OCR/SECTION/Profile path resolvers; an absent resolver is not proof of stable ownership.

## 4. Scope of new automatic tests

`tests/test_r3_mixed_replay_membership_and_path_binding_20261031.py`: **46 parametrized cases**:
- 4 cases: ordinary/candidate × Undo/Redo old rendered row membership/Entry identity
- 4 cases: ordinary/candidate × Undo/Redo successful disk replay with a destroyed Tk variable setter
- 16 cases: two history kinds × Undo/Redo × 4 same-byte sidecar path rebindings during transient Tk snapshot unavailability
- 4 positives: two kinds × Undo/Redo with unchanged source bindings, still explicitly retryable
- 8 cases: destroyed precommit `StringVar.get` / row-reader, two kinds × Undo/Redo, disk unchanged and old frame retained
- 2 mixed-history integrations: candidate delete → ordinary text save → Undo×2 → Redo×2, and ordinary save → candidate delete → Undo×2 → Redo×2, with real synthetic PDIC/manual bytes and candidate checkbox state checked
- 8 cases: native `snapshot_review` row getter throws RuntimeError/TclError (two kinds × Undo/Redo), no disk or UI changes

The first 38 use genuine `write_pdic`, `commit_candidate_delete`, `publish_owned_review_bundle`, `snapshot_review` and replay on disposable generated files, except explicitly monkeypatched snapshot-unavailable/controlled-preflight cases. This is **automated E2**, not a Windows human E3 or evidence of full actual scanned page acceptance.

## 5. Required verification and open limitations

Final code/docs HEAD must independently show:
- Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 exact-head CI success**, plus Risk-tier CI gate
- OCR Platform Smoke **3/3**, CodeQL Analyze Python/Actions **2/2**
- Real Tk/synthetic-fixture smoke three OS passes; no unresolved review threads, one open Draft #663, main SHA unchanged
- Conditional Documentation architecture job SKIPPED is **not** counted passed

At audit authoring, source/test CI was still running; obtain actual final result in a PR comment **after** all gates complete, without new commit that invalidates that evidence.

**Still not performed**: genuine Windows human R3 E3; [#483](https://github.com/chigre/Picture_Capture/issues/483) W1–W11; full [#503](https://github.com/chigre/Picture_Capture/issues/503) compound simultaneous dirty original/simplified/candidate operations outside this owned sequential path; real dictionary page with source OCR/PDIC/PPP/SECTION/Profile save-reopen and large-image time; R6 independently checked human truth labels; R8 actual scans (deferred). This patch is an in-process UI/replay safety increment, not cross-process CAS, general-purpose Undo for arbitrary OCR or a multi-file OS atomicity guarantee. Keep #663 Draft/Open/Unmerged, do not Ready/merge/close issues, bypass gates or upload private images.
