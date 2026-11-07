# G3 R4.2 — successful N+1 crop prefetch: source and callback ownership

Date: 2026-10-31. Only Draft PR #663. This is **synthetic E2** work, not Windows E3 or a real dictionary benchmark.

## Baseline and observed RED

Previously verified green: `8ce6d807914cef24456862a3492806a5bb3e38a1`; [six-platform CI](https://github.com/chigre/Picture_Capture/actions/runs/41205116868) 6/6 + Risk tier, [OCR](https://github.com/chigre/Picture_Capture/actions/runs/41205116875) 3/3, [CodeQL](https://github.com/chigre/Picture_Capture/actions/runs/41205112460) Python/Actions 2/2.

The prior fix only handled **failed** prefetch callbacks. The **success** callback cached a payload before attesting current image/PDIC/SECTION source, and could apply it even when a newer prefetch key owned that epoch or when outstanding human edits existed. The worker could also build a payload while its initial source bytes changed.

Test-only `e45c92e44b3ab2ad4e3714455096b59a807c10ae` [CI #41211306832](https://github.com/chigre/Picture_Capture/actions/runs/41211306832) observed macOS Python3.13 **6 targeted FAILED / 5185 passed / 2 skipped**: (1–3) image, PDIC and SECTION drift even with restored mtime / matching length, (4) old success callback under a newer prefetch key, (5) pending human edit and (6) PDIC mutation during worker crop preparation. These are intentionally RED; not evidence of passed gates.

## Minimal production correction

Source commit `7637eedb7bc2eb5db8048a1ea690dc5d67bfa190` modifies only `src/picture_capture/ui/focused_filter_workflow.py`:

1. After preparing the N+1 crop off the Tk thread, compute `focused_crop_source_witness(local_pages, local_targets)` again. If the image/PDIC/SECTION content witness differs from the cache key captured before scheduling, reject the worker result rather than publish it under a stale key.
2. Tk `done` requires **both** current scan epoch and active prefetch-key ownership. It re-computes the current batch snapshot before inserting a cache entry. A stale/undecidable result is never cached or applied; when this is the visible batch and no human edit or save is pending, clear its waiting placeholder with a generic request to refilter.
3. Even when source is unchanged, do not repaint the visible rows if focused human changes or a save worker remain outstanding. The human source is authoritative; no background crop may silently erase it.

Synthetic fixture correction `cd01446db23801a2f04e9e9397134089562dc65a`: a completed worker payload is captured **before** modifying disk bytes, and its delayed `done` callback is then invoked. The strict assertions remain intact. Other tests continue to cover prior failed-prefetch one-retry, stale epoch, stable source and pending-edit paths.

## Safety, nonclaims and remaining boundary

- The crop witness includes resolved image, PDIC and active SECTION paths plus sha256 content; a same-size/mtime external mutation remains visible at the next witness read. This is **not** a multi-file OS-level compare-and-swap: external changes between the final hash and actual canvas update remain an inherent race. A full source provenance guarantee needs separate owned-storage integration, not a silent claim.
- No changes to original-image XY, candidate ownership, PDIC/PPP/SECTION/Profile/manual-selection formats, persistence writer, OCR engine, opt-in defaults, actual operator records or local-only data boundaries. No uploads of real dictionary/profile/OCR contents.
- Additional deterministic synthetic tests and workflow gates must pass on the **final code+docs HEAD**, not on this red-only commit, intermediate source commit or an earlier green SHA. At documentation commit creation, final exact-head CI 6/6 + Risk-tier, OCR 3/3 and CodeQL Python/Actions 2/2 are **PENDING**. Record independently verified terminal results by a PR comment, rather than creating a further unverified doc-only commit.
- **NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 real manual Undo/Redo, full real dictionary scan, real image/PDIC/SECTION/Profile save-reopen, latency or accuracy benchmark. **DEFERRED:** R6 verified-label learning; R8 real scans. #663 remains Draft/Open/Unmerged, main unchanged, Issues #503/#562/#483 open.

## Next check

Review the direct-render success callback for matching provenance and stale-cache ownership. Any further change requires new red-first tests and the same exact-head safety gates. Never convert automated E2 into E3 evidence.

## Intermediate source CI and legacy fixture correction

At source-fix SHA `7637eedb7bc2eb5db8048a1ea690dc5d67bfa190`, [CI #41211513690](https://github.com/chigre/Picture_Capture/actions/runs/41211513690) Ubuntu Python3.13 reported **5 failed / 5,185 passed / 3 skipped**. Three new tests originally called the worker *after* mutating the source, so the stricter post-worker guard correctly raised before a success callback could be simulated; `cd01446d` corrected their timing to precompute a payload, mutate source, then deliver `done`. Two historical source-less epoch-smoke tests injected a bare `("sig",)` key, inconsistent with the already-required real content-witness cache contract; `a5a25dc53ae9be4b2e8729ecf4b8e71ad51b3458` now constructs an empty-target witness with the actual `focused_crop_source_witness([], [])` function and still asserts cross-epoch isolation and exactly one valid current-epoch cache publication. No production source guard was removed, tests were not skipped, and red intermediate CI remains red. These are synthetic fixture fidelity corrections, **not** evidence of real-device acceptance.
