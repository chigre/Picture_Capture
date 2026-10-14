# PC-CQ/B2 — Human proofreading evidence (work in progress)

This PR is **draft**: limited opt-in UI capture now exists, but the full human-feedback contract remains incomplete. A green CI only validates tested slices, not a fully activated human-feedback loop.

## Source-of-truth chain

1. OCR proposal: page OCR cache / candidate manual-selection sidecar
2. Persisted automatic decision: `ocr_final_decisions.py` sidecar, valid only when its OCR signature and saved PDIC snapshot match
3. Human correction: current actual PDIC, plus proposed `proofreading_events.py` append-only logical journal

**Do not** use row index after sorting, classify an arbitrary human click as a verified true/false label, or synthesize candidate IDs for unmatched Layout-only lines.

## Implemented foundations and narrowly integrated opt-in UI slices

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

- Finish safe post-save capture for unsupported manual operations and verify no unsaved edits or coalesced changes can generate evidence. Implemented: single deletion, single rename, single canvas addition, candidate selection/deselection and strict original/refined Y switch.
- Decide and test a locally controlled settings option/default to enable evidence capture, including legacy JSON migration and UI visibility if needed. No network telemetry.
- Implement explicit human verification and durable Entry identity for arbitrary coordinate edits; narrowly supported actions use reliable original XY or named OCR position group identity. Co-edited multiple rows remain unclassified; general moving/edit grouping not complete.
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


### Explicit visual judgment (opt-in CLI; pending latest CI)

An explicit, user-invoked local command now records a separate `verify` event only after the operator has personally inspected the original scanned page, selected an existing `operation_id`, chosen `correct_headword` or `not_headword`, and supplied `--confirm-visual-review`. The source operation must have a stable entry identity and match the exact current on-disk PDIC SHA-256 and source-image SHA-256. An OCR-linked operation additionally requires the original matching `--ocr-cache` signature. The journal refuses duplicate verification, missing/changed source files, and stale actions; all writes remain atomic and local.

```bash
uv run --locked python scripts/verify_proofreading_action.py \
  --journal /project/ProofreadingEvidence/<page-id>.json \
  --pdic /project/page.pdic --image /project/page.png \
  --operation-id <actual-id-from-journal> \
  --judgment correct_headword --confirm-visual-review \
  --ocr-cache /project/path/to/original_ocr_cache.json
```

`--ocr-cache` is required only for OCR-linked events. These explicit judgments are *separate user confirmations*, not implied by a manual rename, checkbox click or a unique candidate link. Read-only aggregate export counts only fresh, referentially valid confirmed positive/negative judgments. **No raw words, OCR proposals, images, or training labels are exported and no model is trained.** The interface also has an explicit ReviewWindow button and original-scan preview; the CLI remains available for offline verification.

### SECTION provenance from original-image geometry (pending latest CI)

New post-save events resolve SECTION using the persisted `page_sections` original-image boundary segments, the saved page-layout transform and original image X/Y. Classification only succeeds when the point lies strictly within one SECTION; gap points and cross-SECTION moves are unknown, not assigned to the nearest segment. Each attribution includes the actual sidecar digest. Local aggregate export only counts an attribution if the source-image and SECTION sidecar digests still match; it reports unknown/stale counts for missing or changed SECTION data. Rotated pages, two-SECTION pages and a gap are covered by synthetic tests. The implementation reads only the image header/EXIF to avoid decoding large dictionary scans.

### Remaining acceptance gates

- Validate ReviewWindow's new opt-in visual verification UI with actual scanner/window smoke across platforms (headless contracts are already added)
- Improve durable identity for arbitrary marker movement outside explicitly grouped OCR position switches; support crash/reopen and multi-row transactions without guessing
- Add UI integration tests for save failure, manual override write failure, page navigation during active deferred saves, and SECTION/PDIC rollback
- Review local evidence-log privacy, malformed journal recovery and multi-process concurrent writers
- Confirm latest cross-platform PR CI + CodeQL and post-merge main CI; **do not merge a draft PR or mark B2 verified only from synthetic tests**

### In-app visual verification and concurrency lock (2026-10-14; latest CI pending)

With **记录本地校对操作证据** enabled in Settings, the proofreading toolbar now shows **核验记录**. The control first commits the current proofreading editor (blocking on pending/processing/filtered writes), then opens a separate local-only dialog. It reads only the existing local project identity/journal and lists operations which are currently on-disk, have stable identities, and have not already been verified. No event is selected by default. Selecting an event displays an original scanned-image crop with a red circle around its source XY coordinate, and the user must tick the visual-inspection confirmation checkbox and accept a final confirmation dialog before an independent positive/negative judgment is saved. Source PDIC/image/cache hashes are **revalidated at confirmation time** by `verify_saved_action`. No model training, uploads, screenshots or image changes occur.

Concurrent writers of the same local JSON journal now compete for a directory `<page-journal>.json.lock` created atomically. The second writer fails closed and does not overwrite the first writer's events. The lock is released even after a write/PDIC mismatch exception. **Crash recovery**: a process crash may leave an orphaned `.lock` directory; intentionally never auto-delete a lock while another application might own it. Close all Picture_Capture processes and inspect the journal before manually deleting a confirmed orphan. No silent journal truncation is allowed. This guard serializes a single journal, **not arbitrary simultaneous PDIC writes**.

Additional headless tests verify: dialog's read-only event lookup before confirmation; stale source images/PDIC and wrong OCR caches unavailable for verification; events disappear once verified; missing/corrupt project identity never creates a record; exclusive lock refuses overlapping writers without data loss; lock release after simulated write error. A real GUI smoke run with actual full-resolution dictionary scans remains a separate outstanding acceptance gate.

### Still outstanding

Arbitrary manual XY marker movement and per-row multi-edit identity across sessions remain unverified without an explicit stable entry ID; **do not infer them from proximity or row ordering**. Some scene interactions and focus/close/rollback require GUI smoke on a real Windows desktop. The draft PR must not be merged merely because unit CI is green.
