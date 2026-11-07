# G3 R4.2 — scan-target and scan-epoch exact page owner (2026-11-03 SGT)

**Repository:** chigre/Picture_Capture. **Only development PR:** #663 Draft/Open/Unmerged; **main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`; **source/test HEAD:** `2315001597bceaee1ad686c0d948f98989ab14c2`.

## Concrete failure and observed RED

The focused scan target identity calculation and scan-epoch source witness recheck still used `int(target["page_index"])` and `int(page_index)`. Values such as `0.9` and `"0"` silently became page 0; `True` became page 1. An invalid target could inherit a *different real page's* valid PDIC/OCR/SECTION witness and be treated as confirmed. Incomplete scan epochs returned before even validating the populated witness map's key types.

[Test-only commit `35f84778`](https://github.com/chigre/Picture_Capture/commit/35f8477830e35a77532acf8f13f0d09ecdce80d4) creates 27 synthetic parameterized test cases with 8×8 disposable BMP, synthetic PDIC and OCR cache bytes, explicit source witnesses, no-witness compatibility, streaming/completed epochs, and positive integer controls. [RED CI #41614641957](https://github.com/chigre/Picture_Capture/actions/runs/41614641957) completed **FAILURE in all six Windows/macOS/Ubuntu × Python 3.10/3.13 jobs** on the expected 24 invalid-key cases. Ubuntu Python3.13: **24 failed/5477 passed/3 skipped**. RED Risk-tier CI gate **FAILURE**; a RED build is not accepted.

## Minimal source fix

[Source `23150015`](https://github.com/chigre/Picture_Capture/commit/2315001597bceaee1ad686c0d948f98989ab14c2) updates only `src/picture_capture/ui/focused_filter_workflow.py`:
- Imports existing `_source_page_index` from the focused crop source identity owner (strict `operator.index`, explicit boolean rejection).
- Validates scan target page identity *before* choosing missing/attested witness branches.
- Validates scan epoch's witness-map keys and bounds *before* the early incomplete-scan return. At completed scans the existing content witness check remains.
- During streaming this adds **only key-type/range validation**, not a full repeat of SHA-256 file hashing per repaint. Valid integer keys and legacy no-witness target callers continue working.

No cross-file transaction, lock/CAS, persisted format, pixel edit, OCR launch, save retry, source XY or experiment default has changed.

## Exact source/test HEAD gates

- [CI #41614879152](https://github.com/chigre/Picture_Capture/actions/runs/41614879152): **SUCCESS 6/6** Windows/macOS/Ubuntu Python3.10/3.13 and **Risk tier + Risk-tier CI gate SUCCESS**. Ubuntu3.13: **5501 passed/3 skipped**.
- [OCR #41614879182](https://github.com/chigre/Picture_Capture/actions/runs/41614879182): **3/3 SUCCESS**.
- [CodeQL #41614873974](https://github.com/chigre/Picture_Capture/actions/runs/41614873974): **Analyze Python/Actions 2/2 SUCCESS**.
- Documentation architecture check **SKIPPED, not PASS**. A later documentation-only HEAD must be independently checked.

## Evidence and non-claims

Synthetic E2 guards do not prove human Windows GUI E3, actual OCR fidelity, throughput, or multi-file atomicity. **NOT PERFORMED / DEFERRED:** #483 W1–W11; #503 real Undo/Redo; Windows R3 operator testing; actual dictionary page scans, PDIC/PPP/SECTION/Profile/OCR save-reopen; R6 real labels and R8 real scan benchmark. #503/#562/#483 stay open, sole #663 stays Draft/Open/Unmerged. No merge, Ready, force push or main write.
