# G3 R4.2 — asynchronous prefetch/direct-render ProjectState owner and scan invalidation

**Date:** 2026-11-03 (Asia/Taipei). **Sole PR:** #663, Draft/Open/Unmerged. **Baseline main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Final source/test SHA:** `5d8765124149515402a537316c553453d830bd97`.

## RED-first synthetic failure

Existing prefetch callbacks verified dispatch owner/key and scan serial; direct-render callbacks verified render serial/scan serial and row activity. These alone cannot prove that a new `ProjectState` with identical page paths, bytes and source key owns an old asynchronous callback. Prior to correction, old prefetch `done` could cache a crop for the replacement session, old prefetch `failed` could request a retry, old direct-render `done` could cache/apply, and old direct-render `failed` could clear/relabel the replacement workspace.

[`d262da23`](https://github.com/chigre/Picture_Capture/commit/d262da23826a1981a79d02c04156949b74938507) adds `tests/test_g3_r4_async_crop_project_owner_20261103.py`: four stale callback interleavings and two same-session positive controls, entirely synthetic 8×8 BMP/PDIC. [RED CI #41641142156](https://github.com/chigre/Picture_Capture/actions/runs/41641142156) six OS × Python jobs **FAILURE** on exactly 4 intended assertions/job; Windows3.10 4 failed/5535 passed/2 skipped; Risk-tier gate **FAILURE**. Real UI already prohibits ordinary ProjectState replacement with a living ReviewWindow; these prove an independent lower-level defensive requirement, not a real-world incident.

## Intermediate failures preserved; no gate bypass

[`1a935971`](https://github.com/chigre/Picture_Capture/commit/1a935971804dd4512c5ab86c76832e1f92c3654a): architecture guard **FAILURE**, because `ui/focused_filter_workflow.py` expanded to **101,022 bytes > 100,000-byte limit** ([CI #41641665464](https://github.com/chigre/Picture_Capture/actions/runs/41641665464)). No architecture limit override.

[`075348a9`](https://github.com/chigre/Picture_Capture/commit/075348a9e27c8834f4afaee4ec9aac3171ef2a96): extracted pure helper below module-size cap; architecture check SUCCESS but previous regression `test_inflight_render_rejects_replaced_project_object_before_scan_terminal` **FAILURE** because a silent ignore of an owned stale terminal did not invalidate its previous scan epoch ([CI #41642099256](https://github.com/chigre/Picture_Capture/actions/runs/41642099256)). Existing test retained, not ignored or skipped.

## Final minimal owner boundary

[`5d876512`](https://github.com/chigre/Picture_Capture/commit/5d8765124149515402a537316c553453d830bd97) keeps code architecture guard while preserving original scan invalidation. The new `ui/focused_crop_session_owner.py` contains the cheap ProjectState object/epoch/root/page identity guard and an `accept_crop_terminal` boundary invoking the established `_reject_active_filter_scan_epoch` on foreign ownership. The new `ui/focused_scan_source_owner.py` owns the extracted read-only scan target source signature helper, still imported/re-exported at the original UI patchpoint; no writer/schema changes. Four owned async terminals (prefetch done/failed, direct-render done/failed) perform guard before cache/UI side effects. Tests for replacement sessions now require the established scan-epoch invalidation and generic source-warning instead of wrongly demanding no UI invalidation.

- [Exact source CI #41643198831](https://github.com/chigre/Picture_Capture/actions/runs/41643198831): six Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, Risk-tier/gate **SUCCESS**, architecture size guard **SUCCESS**.
- [OCR #41643198671](https://github.com/chigre/Picture_Capture/actions/runs/41643198671): **3/3 SUCCESS**.
- CodeQL Python/Actions: **2/2 SUCCESS** for the exact source HEAD. Documentation architecture check **SKIPPED (not PASS)**.

**Limits:** Callback validation and source byte witnesses do not provide atomic cross-file snapshot/CAS semantics. Not an E3 human review, throughput experiment or real OCR validation. No private data, real scans, PDIC/PPP/SECTION/Profile schema edits, auto merges/Ready or issue closures.
