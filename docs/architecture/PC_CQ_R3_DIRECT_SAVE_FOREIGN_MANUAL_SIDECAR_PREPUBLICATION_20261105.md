# PC-CQ / R3 — unwired direct-save prepublication foreign HUMAN sidecar race (2026-11-05)

## Source / context
Single Open Draft Unmerged PR [#663](https://github.com/chigre/PictureCapture/pull/663); main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged. The direct writer `proofreading/direct_review_save.py` was introduced alongside an alternative #665 save design but the currently guarded ordinary ReviewWindow **does not dispatch to it**. Its safety must be proved independently; do not use it to bypass pre-existing R3 requirements. This is pure software-owned synthetic E2.

## Concrete failure and independent controls
Prior direct saver did `read_records(sidecar)` before snapshotting `old_sidecar`. A newer foreign manual record inserted after the parser's return but before snapshot could become the assumed baseline while `records` remained stale. Separately, a human record inserted after the direct saver published PDIC but before it published the sidecar was not checked. Both permitted stale proposal publication over newer foreign sidecar content; neither proves actual private user data loss.

Test-only [`e3facaa118adea36b3dc3f7c78029af3de635716`](https://github.com/chigre/PictureCapture/commit/e3facaa118adea36b3dc3f7c78029af3de635716) adds two independent injection cases to `tests/test_r3_direct_review_save_20261105.py`: one at `read_records` return, one after the controlled PDIC write. The assertions demand an explicit refusal, exact external HUMAN sidecar bytes, old PDIC bytes if this attempt's PDIC is reversible, unchanged `Entry.word`, and preserved visible original/simplified inputs. Existing direct-save success, equal-word "√", simplified-only edit, injected second-file error/rollback and stale-row rejection tests remain active. [RED CI #42017424683](https://github.com/chigre/PictureCapture/actions/runs/42017424683): all six OS/Python matrix jobs failed exactly on the new parameterized assertions (macOS Python3.10: **2 failed / 5716 passed / 2 skipped**); gate failure is expected, not an acceptance.

## Minimal source repair
[`fdbcf742f83328be85cff126ed3fa9e6c232d282`](https://github.com/chigre/PictureCapture/commit/fdbcf742f83328be85cff126ed3fa9e6c232d282) changes only `src/picture_capture/proofreading/direct_review_save.py` (net +15 lines). It freezes old PDIC/sidecar bytes **before** any sidecar parse, compares both baseline bytes before the first owned write, rechecks each destination against its own old bytes immediately before publishing, and tracks only `attempted` destinations for guarded on-error recovery. In the post-PDIC injection, the direct saver rolls back only its confirmed own PDIC version and never treats the unattempted foreign sidecar as an owned rollback target. No schema, original XY, user records, active R3 control flow or test assertions changed.

## Exact-head proof
Source+tests HEAD `fdbcf742f83328be85cff126ed3fa9e6c232d282`:
- [CI #42017896292](https://github.com/chigre/PictureCapture/actions/runs/42017896292) six jobs Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, Risk tier and Risk-tier CI gate **SUCCESS**. Ubuntu3.13 **5717 passed / 3 skipped**, macOS3.13 and Windows3.13 **5718 passed / 2 skipped**; architecture source guard and wheel build run in their jobs.
- [OCR #42017896228](https://github.com/chigre/PictureCapture/actions/runs/42017896228) Windows/macOS/Ubuntu 3/3 **SUCCESS**.
- [CodeQL #42017887281](https://github.com/chigre/PictureCapture/actions/runs/42017887281) Python and Actions 2/2 **SUCCESS**.
- Documentation architecture check **SKIPPED** (not PASS). The subsequent docs checkpoint commit is a new SHA that requires **its own** gate verification.

## Boundaries and next step
These are byte-level checks in user space, **not** an OS atomic compare-and-swap, no exclusion of writes in the final check-to-publish interval, no all-file atomic transaction or rollback of committed unrelated data. The direct saver remains **unwired**; real R3 Windows E3 / #503 manual Undo-Redo, #483 W1–W11, dictionary PDIC/PPP/SECTION/Profile/OCR actual scan + save-reopen and R6/R8 real workloads are **NOT PERFORMED / DEFERRED**. No private files uploaded, no background learning enabled, no scientific benchmark claim.

On resumption, fetch live #663 HEAD first and verify the **new docs HEAD** CI/OCR/Risk/CodeQL; then pursue NEW synthetic RED-first active R3 autosave/readback or R4.2 worker/callback/SECTION/crop/save owner defect. Keep main untouched and PR Draft.
