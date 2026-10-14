# PC-CQ/B2 — Human proofreading evidence (work in progress)

This PR is **draft** until the integration gate below is implemented and verified. Local event primitives and conservative read-only linking do **not** constitute an activated human feedback loop.

## Source-of-truth chain

1. OCR proposal: page OCR cache / candidate manual-selection sidecar
2. Persisted automatic decision: `ocr_final_decisions.py` sidecar, valid only when its OCR signature and saved PDIC snapshot match
3. Human correction: current actual PDIC, plus proposed `proofreading_events.py` append-only logical journal

**Do not** use row index after sorting, classify an arbitrary human click as a verified true/false label, or synthesize candidate IDs for unmatched Layout-only lines.

## Implemented foundations (not yet connected to UI writes)

- A versioned local JSON event journal with `operation_id`, independent stable `entry_id` supplied by caller, source stage, action, before/after fields, candidate ID, OCR/final fingerprints and post-save PDIC SHA256. Default status is `explicit_action_unverified_page`.
- Atomic journal updates; source PDIC is never written/changed. If journal is malformed or actual PDIC differs from the event's post-save snapshot, writing fails closed.
- Read-only candidate linkage to `ocr_final_decisions`: unique ID required, stale OCR signatures and PDIC snapshot cause unmatched results; ambiguous IDs never guessed.
- Audit counts by status and linkage; **always exports zero training labels** pending independent verification and R2.2 data consent.
- Two test modules with synthetic data, no dictionary scans.


## Additional implemented opt-in slice (pending CI)

- `AppSettings.proofreading_event_capture` is **OFF by default**, exposed in Settings Center under “校对时主界面”; prior projects without this key load with recording OFF.
- `ReviewWindow.delete_review_entry` captures the prior persisted PDIC before editing and requests logging only **after** `save_pdic(..., sync_editors=False)` returns. The recorder accepts only one unambiguous deleted row whose text/original XY precisely match the on-disk before/after diff; co-saved renames, duplicated rows, unresolvable candidates and untouched PDIC produce no deletion event.
- Project identity is a local, explicitly created UUID sidecar under `ProofreadingEvidence` on the first consented, provable deletion; page ID uses its relative path and project identity. A unique OCR candidate ID yields a stable namespaced entity ID; an unlinked or duplicated candidate is left without an entry ID rather than guessed.
- Source image bytes are fingerprinted (SHA-256), and event schema records original-image XY. Existing PDIC bytes and manual override files are not modified by journaling. Journal failure is reflected in the user's status while the already saved PDIC remains authoritative.
- `scripts/export_proofreading_quality.py` explicitly accepts local journal, saved PDIC, image (optional), project identity, license declaration and output; it writes **only aggregate counts**, source digest and license, without page images, raw words, filesystem paths or labels. Missing source image fingerprints and changed PDICs are stale. Export never runs automatically.
- `proofreading_evidence.link_event_to_final` now refuses OCR candidate linkage when either OCR signature or final-PDIC fingerprint is missing, avoiding unwarranted linkage from a later OCR run. Current delete events without such source-fingerprint proof are intentionally reported as **unknown**, not as verified labels.

**Incomplete**: rename/move/add/select/deselect/verify event capture; durable entry ID map for manually inserted/renamed records across app sessions; full rollback test of candidate override writes; SECTION grouping from actual project annotations; explicit positive/negative labels verified by user; integrated UI export. **Do not merge the draft PR based on green tests alone.**

## Required before claiming B2 complete or merging this PR

- Trace ReviewWindow/main-canvas edits and candidate toggles. Record events ONLY after a successfully committed PDIC and manual-override update; never journal an unsaved edit as completed.
- Decide and test a locally controlled settings option/default to enable evidence capture, including legacy JSON migration and UI visibility if needed. No network telemetry.
- Support rename, add, delete, move, select/deselect and verify with stable Entry identity. Events covering changes to multiple rows need a shared operation_id.
- Cover crash/retry, delete, autosave, FocusOut, SECTION reorder, page navigation, manual override rollback, snapshot invalidation and cross-platform UI smoke.
- Ensure raw scan text/paths are not sent to GitHub; project data stays local. Export only explicitly requested, minimal metadata with authorization.
- Complete R2.1/R2.2/R2.3 individually with evidence; 3-platform full CI and post-merge main CI required. PR-B real scan benchmarking remains deferred.

## Commands (once integration is ready)

```bash
uv run --locked pytest -q tests/test_proofreading_events_20261014.py tests/test_proofreading_evidence_20261014.py tests/test_proofreading_capture_20261014.py tests/test_proofreading_quality_export_20261014.py
uv run --locked python scripts/architecture_guard.py
uv run --locked python scripts/change_architecture_guard.py --base origin/main
uv run --locked pytest
```

### Additional R2.1 text-edit capture (pending CI)

`ReviewWindow.save` and `autosave_commit` now inspect prior PDIC bytes only if recording was explicitly enabled. They invoke `capture_saved_review_rename` strictly **after the PDIC write succeeded**. The journal accepts just one unique XY-preserving word edit; multiword saves, XY moves, duplicates and no-change saves generate no event. Namespaced UUID5 keyed to project/page/original XY is stable across text changes and reordered review rows; this does **not** establish a reliable identity for moved or coincident entries. Logging errors never override the successful PDIC save. This remains a draft; no claims about other edit actions, UI integration smoke or verified labels.

### Additional R2.1 checkbox capture (pending CI)

OCR candidate checkbox select/deselect is now captured only when a *single* pre-save PDIC entry addition/removal matches the selected candidate and the corresponding `*_manual_selection.json` file confirms the **same** manually selected state, word and candidate ID **after both files are saved**. Rapid coalesced candidate clicks explicitly invalidate attribution and skip event creation. A failed/interrupted save cannot create a journal record. Same-column alternate-Y swaps involving multiple entries remain unknown, not labeled. The option is OFF unless explicitly enabled. Tests use synthetic rows and local files only.

### Additional R2.1 main-canvas manual addition (pending CI)

A real canvas click now stages a pre-save PDIC snapshot and canonical-to-original-source XY. **Only** after a successful full PDIC save (and manual overrides flush) can it log an `add` event, requiring exactly one new row at the clicked XY, no unrelated rename/delete/move, no duplicated coordinate and no coalesced second insertion. Row text may be entered before saving. A missing/stale page, old project with option OFF, or background OCR save without a prior click generates no evidence. This change never rewrites existing PDIC for telemetry. Identity is stable by page+XY only for non-moving distinct entries; coordinate moves remain unlinked.

### Narrow OCR candidate position-switch move (pending CI)

Choosing a candidate's original/anchor versus refined-Y alternative uses a physical `position_group_id`. After the deferred PDIC and manual-selection override files **both** commit, a `move` event is allowed only if the prior and saved PDIC differ by exactly one removed and one added identical word at different source XY, both candidate IDs are unique and same-group, and the old/new override records unambiguously show `position_switch` and `manual_checkbox`. Stable identity is derived from the explicit group ID. Any text change, duplicate candidates, simultaneous edits, failed sidecar write or missing group link remains unknown. This is **not** unrestricted visual marker dragging support.

### R2.2 verified pre-human OCR decision ancestry (pending CI)

OCR source lineage is copied into an event only if `load_current_final_decisions` verifies the original OCR cache signature and the exact untouched saved-PDIC snapshot **before the user edit**. The UI queues this pair at the beginning of a click/review save, then only persists it after the PDIC/manual override commit succeeds. A stale cache, modified PDIC or missing final snapshot leaves ancestry unknown. Even linked events are not training labels.
