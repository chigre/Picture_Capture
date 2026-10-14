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

## Required before claiming B2 complete or merging this PR

- Trace ReviewWindow/main-canvas edits and candidate toggles. Record events ONLY after a successfully committed PDIC and manual-override update; never journal an unsaved edit as completed.
- Decide and test a locally controlled settings option/default to enable evidence capture, including legacy JSON migration and UI visibility if needed. No network telemetry.
- Support rename, add, delete, move, select/deselect and verify with stable Entry identity. Events covering changes to multiple rows need a shared operation_id.
- Cover crash/retry, delete, autosave, FocusOut, SECTION reorder, page navigation, manual override rollback, snapshot invalidation and cross-platform UI smoke.
- Ensure raw scan text/paths are not sent to GitHub; project data stays local. Export only explicitly requested, minimal metadata with authorization.
- Complete R2.1/R2.2/R2.3 individually with evidence; 3-platform full CI and post-merge main CI required. PR-B real scan benchmarking remains deferred.

## Commands (once integration is ready)

```bash
uv run --locked pytest -q tests/test_proofreading_events_20261014.py tests/test_proofreading_evidence_20261014.py
uv run --locked python scripts/architecture_guard.py
uv run --locked python scripts/change_architecture_guard.py --base origin/main
uv run --locked pytest
```
