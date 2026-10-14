# PC-CQ/B2 — Human proofreading evidence (partial merge; remaining acceptance underway)

**2026-10-14 B2 已合并 [#500](https://github.com/chigre/Picture_Capture/pull/500)：** 新增指定词条序号右键按原图坐标移动的明确对象操作与可选 post-save 证据；与用户编辑文字保留同一行所有权，不按列表序号/最近坐标猜测。禁止同页其他未保存编辑、坐标冲突、OCR 候选、已有简体配对、正在批处理、跨 SECTION/Profile 不可写区域。新步骤 W9–W11 见真人验收表。此功能不是自由拖动，PR [CI 38619428582](https://github.com/chigre/Picture_Capture/actions/runs/38619428582)、合并后 main [CI 38619848886](https://github.com/chigre/Picture_Capture/actions/runs/38619848886) 全部通过。Windows 真人 W1–W11 与受限操作场景的用户验收尚缺，B2 仍 in_progress。

**2026-10-14 B2 增量 [#498](https://github.com/chigre/Picture_Capture/pull/498) 已合并：** 已增加连续 PDIC 指纹血缘的 Entry ID 延续（已有明确操作所有权的 move → 不相关保存改名 → 再次改名/重开）、写入锁内前驱 SHA 校验、跨页/来源漂移防伪和 synthetic 回归。合并 SHA `c1b16d0b8112367f2a5ad816018fe8fd771c91d4`；PR [CI 38616327415](https://github.com/chigre/Picture_Capture/actions/runs/38616327415) 和合并后 main [CI 38616790068](https://github.com/chigre/Picture_Capture/actions/runs/38616790068) 均已成功。**仍不可声称支持通用词条 XY 拖拽**，[#483](https://github.com/chigre/Picture_Capture/issues/483) 的真实 Windows W1–W8 操作者验收也尚未做；无生产代码 PR，B2 保持 in_progress，B3 不启动。

**Live status (2026-10-14):** Default-OFF local evidence [#482](https://github.com/chigre/Picture_Capture/pull/482), cross-platform real-Tk synthetic evidence tests [#486](https://github.com/chigre/Picture_Capture/pull/486) and atomic multiple unique-XY text-only rename capture [#489](https://github.com/chigre/Picture_Capture/pull/489) are merged. Latest main `04c02286` passed [CI 38553009540](https://github.com/chigre/Picture_Capture/actions/runs/38553009540) and [CodeQL 38553009318](https://github.com/chigre/Picture_Capture/actions/runs/38553009318). **B2 is STILL IN PROGRESS**, because arbitrary moved/compound Entry identity and human-run Windows ReviewWindow end-to-end acceptance remain open in [#483](https://github.com/chigre/Picture_Capture/issues/483). The historical paragraphs below describe older draft slices, not today's live status.

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


### Source-consent commit and unsaved-editor boundary (additional B2 safeguards)

Two additional headless regressions address narrow evidence corruption risks without changing the PDIC schema or journal schema:

- **Post-consent source drift**: An image or linked OCR cache may be replaced after the user visually confirms it but before the append-only journal is published. The explicit verification path now carries SHA-256 checks for both files into the existing exclusive per-journal lock. It validates them before and immediately prior to the atomic journal publication, in addition to the saved PDIC digest. If any source differs, no verification event is written. This narrows, but cannot eliminate, filesystem TOCTOU without cross-file transactions.
- **Uncommitted editor state**: ReviewWindow.save may legitimately refuse to claim a pending OCR page and return without raising. Before opening the visual-verification dialog, the UI now requires rendered-entry identity bindings to agree in number and text with the live edit controls, requires no pending simplified edits, and rechecks pending/processing batch state. If these preconditions cannot be shown, it displays a save-first message and does not show the confirmation UI.

Tests simulate an image/OCR cache change between the preflight check and the append call, preservation of the existing journal on rejection, a no-op save with dirty text, mismatched row bindings, and a normal committed save. The new source validation applies to independent human verification events only; ordinary unverified action logging retains the previous contract.

**Remaining gates unchanged**: arbitrary marker movement requires actual stable Entry identity beyond geometric proximity; Windows real-GUI FocusOut/navigation/reopen/crop smoke remains outstanding. Do not treat green CI as evidence of these unperformed tests. The PR stays Draft; no remote submission of local images or patient/dictionary content.


### Incremental Tk interaction gate — PR #486 (2026-10-14)

The previous `scripts/gui_smoke.py` verifies only application-window construction; mocked widget unit tests also cannot establish that Tk selection events, cropped pixels, button enablement and journal writes are wired correctly. `scripts/gui_proofreading_evidence_smoke.py` exercises actual Tk widgets on a fully synthetic page in CI (Windows/macOS GUI sessions and Linux Xvfb). It checks initial disabled/no-selection state, rendering actual PNG crop after Treeview selection, explicit checkbutton, cancellation without byte changes, positive and negative human-*simulated* judgments, stale-source rejection between preview and acceptance, and re-opening the verification dialog without repeated actionable events. Both synthetic input PNG and PDIC are generated into disposable private temp storage; only generic code is committed. This is **not** a user-operated Windows acceptance or a real dictionary-scanner test.

**Remaining #483:** interactive FocusOut/autosave/navigation/SECTION/crash-reopen with a real operator; durable identity across arbitrary marker drag and multi-row transactions without row index/proximity inference. Keep B2 in progress, do not start B3 from synthetic CI alone. For current SHA/CI check `CORE_QUALITY_STATE.json` and GitHub, not historical pending paragraphs above.


### R2/B2 incremental closure — #489 (merged 2026-10-14)

`ReviewWindow.save` and `autosave_commit` already route through the same post-saved-PDIC capture hook; #489 now accepts more than one simultaneous text-only rename **only when** the entire saved before/after PDIC has the same number of rows and the same unique source-image XY keys. Mapping uses each unchanged original XY rather than rendered/sorted row order; these same-position IDs survive SECTION reordering and reopened sessions. Candidate lineage stays unknown unless separately established.

The events for one multi-edit save are appended in one atomic journal publication under the existing exclusive lock. Simulated disk failure must leave the source PDIC and any existing journal bytes unchanged, with no orphan lock. Changed XY, mixed add/delete, duplicate coordinates, stale PDIC, mixed pages and duplicate IDs fail closed; no fabricated inference or supervised training label is generated. The existing `proofreading_event_capture=False` default and persistent PDIC/manual_selection/SECTION/Profile schemas are unchanged. Exact fixed-head and postmerge CI links are in `CORE_QUALITY_STATE.json`.

**Open #483:** the XY-based ID is **not** valid after arbitrary movement, and combined move/rename transactions are not audited; a future design must use the explicit UI operation as identity provenance and never guess by row index or coordinate proximity. Actual Windows operator FocusOut/autosave/page navigation/SECTION/crash/reopen acceptance is still required. Do not begin B3 or claim B2 fully verified based on #489.
