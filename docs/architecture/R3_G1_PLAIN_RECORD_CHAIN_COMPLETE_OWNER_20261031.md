# PC-CQ R3 / #503 — ordinary saved-edit Undo chain full source ownership

Date: 2026-10-31. Only [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) is active, open and unmerged; `main@ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged. All test assets are disposable generated data, no private scans.

## Issue and why a valid new saved edit alone is not enough

A `ReviewSessionHistory.record(before, after)` may accept a new saved-text edit while the previous saved frame was committed under a **different source binding**. The prior implementation chained the two snapshots by checking some bytes and owner identifiers only; it did not compare `page`, `manual_path`, `ocr_path`, `section_path` or `profile_path`. Two project roots or page paths may have byte-identical PDIC/sidecar contents while referring to different owners, and prior Undo history must not cross that boundary. The new save is independently valid; only **retention of the old frame** is unsafe. This is the same complete-state rule already used by `CandidateReviewHistory.record_candidate_delete`.

## Actual test-first red and small fix

- Test-only `95b91b183fe416c5cf287593c49d3853484dc179` introduced `tests/test_r3_plain_record_chain_ownership_20261031.py` with five negative frozen-snapshot path/page continuity cases and three positive same-source multi-step controls.
- [Red CI #41193829573](https://github.com/chigre/Picture_Capture/actions/runs/41193829573) Ubuntu Python3.13 **5 failed, 5,114 passed, 3 skipped**, macOS Python3.13 **5 failed, 5,115 passed, 2 skipped**. Each failure was one of the five new negative cases asserting that a stale old Undo frame must be discarded, while the positive same-owner chain tests passed. The red test-only SHA is **not** an accepted gate.
- Production `259f5f15a3b57948ed1c7d1c6659b90ed868cd41` replaces the incomplete handwritten field subset in `ReviewSessionHistory.record` with the already-existing `_same_live_state(previous.after, before)` helper. On a mismatch it invalidates old Undo and Redo state before appending only the new independently valid save. Exact current page, source paths and byte/Entry identity must agree for multi-step history.
- Integration `318641056c69a5370bf03bdf68cd33ed560722e2` additionally tests actual `write_pdic`, `snapshot_review` and `record` when the app changes its manual selection binding, OCR cache binding, or Profile project root between two legitimate saves. This supplements synthetic frozen-snapshot cases with real project-local PDIC reads; it is still automated synthetic E2, not a real scanned image or a Windows human E3.
- Existing valid same-page sequential text edits and mixed candidate ordinary-save replay behavior must remain green.

## Limits and exact-head acceptance

This packet does not change actual PDIC/simplified/manual transaction publication, Undo application, source XY, OCR candidate assignment, Tk widget repaint, Settings/Profile serialization, or recovery marker storage; it only stops in-memory history from crossing different source owners. No cross-process CAS, permanent Undo log, on-disk atomic multi-page transaction or OS-wide lock is claimed.

Intermediate fixed-source [CI #41193980514](https://github.com/chigre/Picture_Capture/actions/runs/41193980514), [OCR #41193980507](https://github.com/chigre/Picture_Capture/actions/runs/41193980507) and three additional real-snapshot test [CI #41194015447](https://github.com/chigre/Picture_Capture/actions/runs/41194015447) were not yet fully completed at authorship. The final docs/code HEAD after STATE and RESUME must pass **6/6 Windows/macOS/Ubuntu × Python3.10/3.13 CI, Risk-tier CI gate, 3/3 OCR and 2/2 CodeQL (Python and Actions)**. Documentation architecture check may be conditional SKIPPED and must not be described as passed. Preserve the sole open Draft PR, unchanged main and no unresolved review threads.

Still **NOT PERFORMED / DEFERRED**: Windows operator E3, [#483](https://github.com/chigre/Picture_Capture/issues/483) W1–W11, [#503](https://github.com/chigre/Picture_Capture/issues/503) full candidate/plain/simplified compound Undo/Redo and human acceptance, actual dictionary scan/OCR/PDIC/PPP/SECTION/Profile save-and-reopen and large-image benchmark, R6 verified human labels and R8 real scans. Do not merge/mark Ready, close blockers, upload real private images, or relax failing gates.
