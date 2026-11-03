## 2026-11-03 SGT｜G3 R4.2 tail scan failure must revalidate prior ready-prefix sources — RED → GREEN

- **Live source authority:** `main@ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged; only PR #663 `refactor/562-retire-root-image-utils-20261024` Draft/Open/Unmerged at source/test `6c6ab74ae7970ed7061b60dd52945d006a3f67f6`. Issues #503/#562/#483 Open, zero unresolved review threads. No Ready/merge/main/force/issue closure.
- **New distinct defect:** after an early batch had been scanned and rendered, `remaining_failed` unconditionally preserved its partial results when a later chunk failed. It did **not reverify the original scanned prefix**. A PDIC/OCR/SECTION mutation of an already-scanned page, or replacement ProjectState with identical root/pages, could leave the old batch considered a safe partial scan despite stale provenance. This is a synthetic defensive interleaving, not an observed real OCR incident.
- **RED-first:** [test-only `779031b3`](https://github.com/chigre/Picture_Capture/commit/779031b3c003343e5cc616e01b3f06bd00a69452) adds 4 synthetic first-page source mutations/project identity cases to `tests/test_g3_r4_streaming_scan_failure_20261031.py`, explicitly preserving pending human edit and source-warning confidentiality. Existing `test_remainder_error_is_explicitly_terminal_without_losing_first_batch` stays the unchanged positive control. [RED CI #41651036164](https://github.com/chigre/Picture_Capture/actions/runs/41651036164) six Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 FAILURE**, exactly four new intended assertions/job, no unrelated failures (Ubuntu3.13 4 failed/5538 passed/3 skipped; Windows3.10 4 failed/5539 passed/2 skipped). RED Risk-tier CI gate FAILURE, not passing.
- **Minimal fix:** [`6c6ab74a`](https://github.com/chigre/Picture_Capture/commit/6c6ab74ae7970ed7061b60dd52945d006a3f67f6) modifies **one** UI source module by **+7 lines only**: once a tail failure callback has claimed its dispatch, call the existing `verify_scan_epoch_sources(start_position)` on the **completed prefix**; on failure call `_reject_active_filter_scan_epoch` and return before generic partial-result status. Valid prefix retains original partial-batch behavior. No additional hashes on successful normal scan, new filesystem watcher, PDIC writer/schema or pixel crop changes.
- **Exact source GREEN:** [CI #41652027345](https://github.com/chigre/Picture_Capture/actions/runs/41652027345) six matrix **6/6 SUCCESS**, architecture guard and Risk-tier/gate **SUCCESS**, Ubuntu3.13 5542 passed/3 skipped, Windows3.13 5543 passed/2 skipped; [OCR #41652027478](https://github.com/chigre/Picture_Capture/actions/runs/41652027478) **3/3 SUCCESS**; [CodeQL #41652019610](https://github.com/chigre/Picture_Capture/actions/runs/41652019610) Python/Actions **2/2 SUCCESS**. Documentation architecture check **SKIPPED (not PASS)**. This docs HEAD must pass its own checks separately.
- **Safety / deferred:** Synthetic E2 only. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, real dictionary/PDIC/PPP/SECTION/Profile/OCR scans and save-reopen NOT PERFORMED; R6/R8 real-data DEFERRED. This is a readback guard, not OS CAS or cross-file atomic transaction, foreign data rollback, model training, operator usability or speed claim.
- **Next:** verify docs exact-head gates, then bounded fresh scan callback/source audit; require a new RED-first executable counterexample, not speculative rewrites. Keep only #663 Draft/Open/Unmerged.

---

## 2026-11-03 SGT｜G3 R4.2 save-session and async crop ProjectState owners — two complete RED → GREEN packages

- **Live authority at source checkpoint:** `main@ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged; sole PR #663 `refactor/562-retire-root-image-utils-20261024` at source/test `5d8765124149515402a537316c553453d830bd97`, Draft/Open/Unmerged, #503/#562/#483 Open, unresolved review threads 0. No main write, force push, merge, Ready, issue closure or parallel PR.
- **Package 1 (focused save ProjectState owner):** [RED test-only `3c3ceb40`](https://github.com/chigre/Picture_Capture/commit/3c3ceb4075f168efcf032bfd31f1e1f1ee430407) adds four synthetic ProjectState-replacement/valid-control cases. [RED CI #41639594396](https://github.com/chigre/Picture_Capture/actions/runs/41639594396) all six OS × Python matrix jobs FAILURE on exactly 3 new expected owner assertions/job (Ubuntu3.13 3 failed/5529 passed/3 skipped; Windows3.10 3 failed/5530 passed/2 skipped), RED gate FAILURE. [Minimal correction `71e49785`](https://github.com/chigre/Picture_Capture/commit/71e49785dc12bdff5b096b1a4e67f0604fd9a81e) binds live human-edit save launch, worker preflight, each page before writer dispatch, and Tk completion to the scan's exact ProjectState and scan serial/root/page list. The ambiguous post-publication foreign-session callback retains correction and marks the page uncertain; no automatic replay/foreign UI reconciliation. [GREEN CI #41640032284](https://github.com/chigre/Picture_Capture/actions/runs/41640032284) 6/6 SUCCESS + Risk-tier/gate, [OCR #41640032317](https://github.com/chigre/Picture_Capture/actions/runs/41640032317) 3/3 SUCCESS, CodeQL Python/Actions 2/2 SUCCESS. Existing project-open UI already refuses a live ReviewWindow; this is an additional synthetic defense, not a claim of naturally occurring cross-project writes.
- **Package 2 (prefetch + direct render callback owner):** [RED test-only `d262da23`](https://github.com/chigre/Picture_Capture/commit/d262da23826a1981a79d02c04156949b74938507) adds four stale-session callbacks and two valid-controls using synthetic equal-root/equal-page/equal-byte ProjectState objects. [RED CI #41641142156](https://github.com/chigre/Picture_Capture/actions/runs/41641142156) all six matrix FAILURE on exactly four new intended assertions/job (Ubuntu3.13 4 failed/5534 passed/3 skipped; Windows3.10 4 failed/5535 passed/2 skipped); RED gate FAILURE. Initial [`1a935971`](https://github.com/chigre/Picture_Capture/commit/1a935971804dd4512c5ab86c76832e1f92c3654a) **FAILED** architecture cap: `focused_filter_workflow.py` 101,022 bytes > 100,000. Extraction [`075348a9`](https://github.com/chigre/Picture_Capture/commit/075348a9e27c8834f4afaee4ec9aac3171ef2a96) cleared size guard but **FAILED** an existing scan-epoch invalidation regression, so was not accepted. Final [`5d876512`](https://github.com/chigre/Picture_Capture/commit/5d8765124149515402a537316c553453d830bd97) extracts tiny, read-only `ui/focused_crop_session_owner.py` and `ui/focused_scan_source_owner.py`, keeps `focused_filter_workflow.py` below cap with existing scan helper ABI, and rejects/invalidate-epoch old prefetch/direct-render terminals before cache/UI publication. Updated synthetic test expects the established fail-closed epoch invalidation and source warning rather than incorrectly demanding silence.
- **Exact final source/test GREEN:** [CI #41643198831](https://github.com/chigre/Picture_Capture/actions/runs/41643198831) Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, architecture guard SUCCESS, Risk-tier/gate SUCCESS; [OCR #41643198671](https://github.com/chigre/Picture_Capture/actions/runs/41643198671) 3/3 SUCCESS; CodeQL Python/Actions **2/2 SUCCESS** at exact source SHA. Documentation architecture check **SKIPPED (not PASS)**. This new docs checkpoint must pass independent exact-head gates before it can be called final.
- **Boundaries:** Synthetic E2 only. No actual dictionary/medical data, OCR scan, real human operation, save/reopen, pixel or text accuracy benchmarking; no PDIC/PPP/SECTION/Profile schema mutation, filesystem CAS, cross-file atomic publication, foreign-data rollback, or speculative performance claim. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, actual scans/PDIC/PPP/SECTION/Profile/OCR save-reopen **NOT PERFORMED/DEFERRED**. R6 and R8 real-data DEFERRED.
- **Next:** verify docs HEAD gate; then bounded scan owner invalidation/reentrant terminal/cross-page save setup audit. Require new synthetic RED-first failure before any further code edit. Preserve sole #663 Draft/Open/Unmerged.

---

## 2026-11-03 SGT｜G3 R4.2 crop-batch cache + off-thread source XY owner — six-platform RED → GREEN

- **Live authority at source checkpoint:** main `ec20989ea8c026cca5337293e67850b6b6df30f2`; sole PR #663 on `refactor/562-retire-root-image-utils-20261024` Draft/Open/Unmerged; #503/#562/#483 Open, 0 review threads. The prior queue guard did not protect cache/prefetch source-XY matching.
- **New independent RED-first synthetic tests:** [`dbda31eb`](https://github.com/chigre/Picture_Capture/commit/dbda31ebbd3f8bda4362ee09946c0de3c0ab5d23) adds `tests/test_g3_r4_crop_batch_exact_xy_identity_20261103.py` with 6 malformed XY crop-cache snapshot cases, 10 invalid page/XY off-thread crop worker cases, and an unchanged valid integer positive control. Sources are disposable 8×8 BMP and synthetic PDIC; no real dictionary/OCR/operator data. Old snapshot normalized fractional/text/bool XY into a potentially identical cache signature; the worker likewise aliased page/XY including Python -1 page lookup. [RED CI #41631995853](https://github.com/chigre/Picture_Capture/actions/runs/41631995853) **6/6 OS/Python matrix FAILURE on exactly 16 new assertions per job** (Ubuntu Python3.13: 16 failed/5512 passed/3 skipped; Windows Python3.10: 16 failed/5513 passed/2 skipped). RED Risk-tier CI gate **FAILURE**, not accepted.
- **Minimal source fix:** [`929d65d5`](https://github.com/chigre/Picture_Capture/commit/929d65d5beb0d32795bb5ac4cd3bd90e488f1dd0) changes only `src/picture_capture/ui/focused_filter_workflow.py` (+26/-17). In `_filter_batch_snapshot`, construct identity and source signature under one fail-closed try with strict `_source_page_index` and `_exact_page_coordinate`, returning no cache snapshot for malformed targets. In `_prepare_filter_batch_payload`, reject noninteger or out-of-range page and invalid original-image XY before page cache lookup or crop, then match rows against the validated integers. Valid source-XY/pixel geometry and crop zoom stay unchanged.
- **Exact source/test GREEN:** [CI #41632643807](https://github.com/chigre/Picture_Capture/actions/runs/41632643807) six Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, Risk tier and Risk-tier CI gate **SUCCESS**, macOS Python3.13 **5529 passed/2 skipped**; [OCR #41632643864](https://github.com/chigre/Picture_Capture/actions/runs/41632643864) **3/3 SUCCESS**; [CodeQL #41632639670](https://github.com/chigre/Picture_Capture/actions/runs/41632639670) Python/Actions **2/2 SUCCESS**. Documentation architecture check **SKIPPED (not PASS)**. New documentation checkpoint HEAD requires separate verification.
- **Safety boundaries and non-claims:** source reads remain volatile, not OS CAS or cross-file atomic transaction. No PDIC/PPP/SECTION/Profile/OCR schema or original XY mutation; no data upload, model training, empirical accuracy/speed claim, automatic replay or rollback over foreign bytes. Synthetic E2 only. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, real dictionary/OCR/PDIC/PPP/SECTION/Profile scans and save-reopen **NOT PERFORMED/DEFERRED**; R6/R8 real data DEFERRED.
- **Next:** verify this docs HEAD's own CI/OCR/Risk-tier/CodeQL; then continue bounded async render/prefetch owner/epoch and SECTION source review. No merge, Ready, issue closure, parallel production PR or forced branch update.

---

## 2026-11-03 SGT｜G3 R4.2 focused UI edit-queue exact page/XY ownership — verified RED → GREEN

- **Authority at source/test checkpoint:** main `ec20989ea8c026cca5337293e67850b6b6df30f2`; sole PR #663 `refactor/562-retire-root-image-utils-20261024` Draft/Open/Unmerged, issues #503/#562/#483 Open, review threads 0.
- **New source-grounded interleaving risk:** `_queue_focused_change` silently applied `int()` to target page index and original-image XY. Although the downstream `apply_focused_review_page_updates` now rejects malformed *received* coordinates, the UI had already normalized a fractional, string or boolean input into a different valid marker before dispatch. Synthetic invalid target values are not proof of naturally occurring OCR corruption.
- **RED-first test-only:** [`a40c7b7f`](https://github.com/chigre/Picture_Capture/commit/a40c7b7f5f1db6f5e9fd7869813c7b2bdf5c6e84) adds nine deliberately malformed page/XY cases and one valid integer control to `tests/test_g3_r4_focused_queue_exact_source_identity_20261103.py`. [RED CI #41628494277](https://github.com/chigre/Picture_Capture/actions/runs/41628494277) **all 6 OS/Python matrix jobs FAILURE** on exactly nine new assertions per job; Ubuntu3.13 9 failed / 5502 passed / 3 skipped, Windows3.10 9 failed / 5503 passed / 2 skipped. RED Risk-tier CI gate FAILURE is not a passing gate. Isolated transcription probe independently gave 9 RED/1 positive control.
- **Minimal source fix:** [`00167584`](https://github.com/chigre/Picture_Capture/commit/00167584d552dbb58c5c341af3cf5661e1e55a1e) changes only `src/picture_capture/ui/focused_filter_workflow.py` (15 additions / 2 deletions), reuses strict `_source_page_index` and `_exact_page_coordinate`, and declines to mutate editor target or enqueue debounce save when source identity is invalid. Valid integer edits keep the existing 160-ms queue behavior; no persistence schema, PDIC writer, original source XY, crop raster, or worker scheduler change.
- **Exact source/test GREEN:** [CI #41629160886](https://github.com/chigre/Picture_Capture/actions/runs/41629160886) **6/6 SUCCESS**, Risk tier + Risk-tier CI gate **SUCCESS**; [OCR #41629160918](https://github.com/chigre/Picture_Capture/actions/runs/41629160918) **3/3 SUCCESS**; [CodeQL #41629155015](https://github.com/chigre/Picture_Capture/actions/runs/41629155015) Analyze Python/Actions **2/2 SUCCESS**. macOS Python3.13 5512 passed/2 skipped. Documentation architecture check **SKIPPED, not PASS**. The *documentation-only* HEAD is a distinct SHA and requires its own checks.
- **Safety and limits:** test uses no private scans, dictionary, PDIC, PPP, OCR or training records; no learning/telemetry/model invocation, benchmark claim, rollback promise or cross-file OS CAS. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, actual dictionary/OCR/PDIC/PPP/SECTION/Profile scan and save-reopen remain **NOT PERFORMED/DEFERRED**; R6/R8 real-data work DEFERRED.
- **Next:** independently verify this docs HEAD gates; then examine crop/render target XY identity and stale async owner provenance via new isolated RED-first tests. Do not repeat or weaken this E2 work, merge, mark Ready, close issues or add parallel production PRs.

---

## 2026-11-03 SGT｜G3 R4.2 scan-target + epoch-source exact page ownership — six-platform RED → GREEN

- **Live authority before documentation:** main `ec20989ea8c026cca5337293e67850b6b6df30f2`; only development PR #663 on `refactor/562-retire-root-image-utils-20261024` **Draft/Open/Unmerged**; #503/#562/#483 Open, no inline review threads. Prior final docs HEAD `b27db452` exact-head CI/OCR/CodeQL succeeded.
- **New fail-first test:** [`35f84778`](https://github.com/chigre/Picture_Capture/commit/35f8477830e35a77532acf8f13f0d09ecdce80d4) adds **27 synthetic cases**: 12 invalid scan-target page keys with/without witness, 12 invalid scan-epoch witness-map keys during incomplete/completed scan, 2 valid complete/streaming epochs and 1 valid witnessed/legacy-no-witness scan-target test. Fractional, boolean and text indexes previously became 0/1 through `int()`, potentially binding a different page's PDIC/OCR/SECTION source while reporting success. [RED CI #41614641957](https://github.com/chigre/Picture_Capture/actions/runs/41614641957) completed **FAILURE** on all six OS/Python matrix jobs; Ubuntu3.13 **24 intended failed/5477 passed/3 skipped**; RED Risk-tier CI gate **FAILED**. RED is not release acceptance.
- **Minimal fix:** [`23150015`](https://github.com/chigre/Picture_Capture/commit/2315001597bceaee1ad686c0d948f98989ab14c2) changes only `src/picture_capture/ui/focused_filter_workflow.py`. Reuse strict `_source_page_index` integer owner validator for target scan witnesses and epoch-map keys; reject malformed map keys even when scan is streaming. This checks keys only: **no extra PDIC/OCR/SECTION hashing per render**, worker scheduling/pixels/saved files unchanged; legacy no-witness positive case preserved.
- **Exact source/test HEAD E2:** [CI #41614879152](https://github.com/chigre/Picture_Capture/actions/runs/41614879152) **6/6 SUCCESS**, Risk tier and Risk-tier CI gate **SUCCESS**, Ubuntu3.13 **5501 passed/3 skipped**; [OCR #41614879182](https://github.com/chigre/Picture_Capture/actions/runs/41614879182) **3/3 SUCCESS**; [CodeQL #41614873974](https://github.com/chigre/Picture_Capture/actions/runs/41614873974) Python/Actions **2/2 SUCCESS**. Documentation architecture check **SKIPPED (not PASS)**. This later documentation checkpoint requires separate exact-head verification.
- **Unchanged limits:** no persisted PDIC/PPP/SECTION/Profile/OCR schema or source XY changes, source image write, training, model access, automatic replay, OS CAS, forced branch update or main merge. Synthetic E2 only. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, actual dictionary/OCR/save-reopen and R6/R8 real-data work remain **NOT PERFORMED/DEFERRED**.
- **Next:** verify final docs HEAD gates; then scan remaining bounded R4.2 source ownership. Windows thumbnail intermittent root cause remains unconfirmed. Architecture audit: `docs/architecture/G3_R4_2_SCAN_EPOCH_EXACT_PAGE_OWNER_20261103.md`.

---

## 2026-11-03 SGT｜G3 R4.2 crop source page-index truncation and UI witness binding — six-platform RED → GREEN

- **Live authority before docs checkpoint:** main `ec20989ea8c026cca5337293e67850b6b6df30f2`, sole PR #663 on `refactor/562-retire-root-image-utils-20261024` **Draft/Open/Unmerged**, #503/#562/#483 Open, unresolved review threads 0. Previous docs HEAD `66d64b8d` exact CI/OCR/CodeQL all succeeded; documentation architecture check SKIPPED.
- **Concrete RED:** `focused_crop_source_witness` used `int(target["page_index"])`, and `focused_save_source_from_crop_witness` used `int(page_index)`; fractional, boolean and text identifiers could inherit a different page's source witness. The real UI's crop publication also preconverted the page index, erasing the invalid type before verification. [Test-only `650684ea`](https://github.com/chigre/Picture_Capture/commit/650684ea2e74121d57954be22d8e3b10cea8538d) added 14 synthetic cases (13 negative/identity and 1 positive). [RED CI #41612103458](https://github.com/chigre/Picture_Capture/actions/runs/41612103458): **six matrix jobs failed** on intended regressions; Ubuntu Python3.10 **13 failed/5461 passed/3 skipped**; RED Risk-tier gate failed and was never treated as PASS.
- **Fix [`8b2ac2cd`](https://github.com/chigre/Picture_Capture/commit/8b2ac2cd8b16db1891e50acb50577c7578f39680):** add `operator.index` strict page owner validation, reject bool and noninteger page IDs during both crop attestation and save-witness selection, and pass the raw target page identity from `focused_filter_workflow.py`. No pixel, OCR, data serialization or worker scheduling changes; valid integer page indexes retain behavior.
- **Exact source/test HEAD:** [CI #41612191423](https://github.com/chigre/Picture_Capture/actions/runs/41612191423) **6/6 SUCCESS** plus Risk-tier/gate SUCCESS; Ubuntu3.13 **5474 passed/3 skipped**. [OCR #41612191427](https://github.com/chigre/Picture_Capture/actions/runs/41612191427) **3/3 SUCCESS**. [CodeQL #41612184011](https://github.com/chigre/Picture_Capture/actions/runs/41612184011) Python/Actions **2/2 SUCCESS**. Documentation architecture check **SKIPPED, not PASS**. The new documentation HEAD must be checked independently.
- **NOT PERFORMED / DEFERRED:** Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, real dictionary scans and OCR/PDIC/PPP/SECTION/Profile save-reopen, R6 real labels, R8 scans. No training, upload, telemetry, auto-merge, Ready transition or forced branch update. Only synthetic E2 evidence.
- **Next:** verify this documentation SHA's exact gates, then continue narrow source-based safety audits. Windows thumbnail intermittent root cause remains unconfirmed.

---

## 2026-11-03 SGT｜G3 R4.2 focused PDIC exact integer XY / page owner / empty-batch refusal — six-platform RED → GREEN

- **Live baseline before documentation:** main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged; only PR #663 remains **Draft/Open/Unmerged** on `refactor/562-retire-root-image-utils-20261024`; #503/#562/#483 remain Open, no resolved human acceptance implied.
- **Concrete RED:** `focused_pdic_updates.py` used `int(change["x"])`/`int(change["y"])`, so fractional/text coordinates could alias an existing exact PDIC marker. It also accepted mismatched page identities and republished an unedited PDIC when `changes=[]`. Test-only [`e68d0559`](https://github.com/chigre/Picture_Capture/commit/e68d055972d0d493ca8e2655c7d57ecc30dcdbda) added 11 synthetic cases, including the valid integer-positive control. [CI #41610202553](https://github.com/chigre/Picture_Capture/actions/runs/41610202553) **six OS/Python jobs FAILURE on 10 intended tests**, Ubuntu3.13 10 failed/5450 passed/3 skipped; Risk-tier gate FAILED (RED is not acceptance).
- **Minimal source fix:** [`b4ed2bad`](https://github.com/chigre/Picture_Capture/commit/b4ed2bad40c39e00732c55ba25323104444660de) requires true integer pixel coordinates via `operator.index` (rejecting bool, float, text), checks page/index and per-change page ownership before any disk access, and makes the empty batch a true no-op. Valid integer XY and ordinary UI-sourced page saves remain supported.
- **Exact source/test HEAD E2 GREEN:** [CI #41610298182](https://github.com/chigre/Picture_Capture/actions/runs/41610298182) **6/6 SUCCESS** plus Risk tier and Risk-tier CI gate **SUCCESS**; Ubuntu3.13 **5,460 passed / 3 skipped**; [OCR #41610298176](https://github.com/chigre/Picture_Capture/actions/runs/41610298176) **3/3 SUCCESS**; [CodeQL #41610293695](https://github.com/chigre/Picture_Capture/actions/runs/41610293695) Python/Actions **2/2 SUCCESS**. Documentation architecture check **SKIPPED, not PASS**.
- **Boundaries:** no PDIC/PPP/SECTION/Profile serialization or original-image XY mutation; no rollback, automatic retry or multi-file CAS; default-OFF proofing/telemetry remains unchanged. Synthetic E2 only. **NOT PERFORMED/DEFERRED:** Windows R3 E3; #483 W1–W11; #503 human Undo/Redo; real dictionary scans, OCR and PDIC/PPP/SECTION/Profile save/reopen; R6/R8 real data. Maintain PR #663 Draft/Open/Unmerged, never merge/Ready under incomplete gates.
- **Next:** check this new documentation SHA's own CI/OCR/CodeQL. Continue bounded R4.2 async source ownership audits; Windows thumbnail intermittent cause remains unconfirmed. Audit: `docs/architecture/G3_R4_2_EXACT_XY_PAGE_OWNER_FAIL_CLOSED_20261103.md`.

---

## 2026-11-03 SGT｜G3 R4.2 final focused-save image/SECTION readback witness — six-platform RED → GREEN

- **Live baseline:** main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged; sole PR #663 remains Draft/Open/Unmerged, source/test HEAD `8a0259b9a5175b8f760838862963530e01f2b1db`; #503/#562/#483 Open, no unresolved review threads.
- **Proven RED:** test-only `636351b14e805d4f05ac347b054e64ad413687a8` adds four synthetic readback-period source-drift cases (SECTION replaced/removed/created; image replaced) and two stable-source positive controls. [CI #41602730257](https://github.com/chigre/Picture_Capture/actions/runs/41602730257) failed **all six** platform/Python matrix jobs on exactly the four expected `DID NOT RAISE RuntimeError` cases; Ubuntu3.13 4 failed/5442 passed/3 skipped; Windows3.10 4 failed/5443 passed/2 skipped. RED gate is not PASS.
- **Minimal fix:** `8a0259b9a5175b8f760838862963530e01f2b1db` adds a final `verify_focused_save_source` only after complete PDIC readback and serialized-field/XY comparisons; no writer rollback or schema change.
- **Exact source/test HEAD:** [CI #41603256021](https://github.com/chigre/Picture_Capture/actions/runs/41603256021) **6/6 SUCCESS**, Risk-tier/gate SUCCESS; [OCR #41603256004](https://github.com/chigre/Picture_Capture/actions/runs/41603256004) **3/3 SUCCESS**; [CodeQL #41603250733](https://github.com/chigre/Picture_Capture/actions/runs/41603250733) Python/Actions **2/2 SUCCESS**. Documentation architecture check SKIPPED, not PASS. Documentation HEAD gates must be checked independently.
- **Audit:** `docs/architecture/G3_R4_2_FINAL_POSTREADBACK_SOURCE_WITNESS_20261103.md`. Byte-witness checks are discrete, **not cross-file OS CAS**; a prior PDIC publication is not rolled back and uncertain edits remain pending for explicit inspection.
- **NOT PERFORMED/DEFERRED:** Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, real dictionary scans/PDIC/PPP/SECTION/Profile/OCR save-reopen, human acceptance, R6 real-label learning, R8 real scans. Synthetic E2 only; no real benchmark or acceleration/accuracy claim.
- **Next:** verify final docs HEAD, then continue R4.2 bounded async epoch/SECTION/crop prefetch/save ownership. Windows thumbnail intermittent root cause remains UNCONFIRMED.

---

## 2026-11-03 SGT｜G3 R4.2 streaming session identity + epoch serial binding — RED → GREEN, exact source/test HEAD verified

- **Live baseline:** `main@ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged; sole PR #663 remains **Draft / Open / Unmerged** at source/test HEAD `2fc347e3f806c5e2e961127fb2c5d83d191bf1df`. Issues #503/#562/#483 remain Open; no unresolved inline review threads.
- **Streaming ProjectState identity:** source commit [`b2b4aa9b`](https://github.com/chigre/Picture_Capture/commit/b2b4aa9b4a40a012fcbe0f7d560d6c80ecb3b878) moves the exact ProjectState identity/root/page-list guard before the incomplete-scan early return. Streaming render publication now refuses a replaced session; full byte-witness hashing remains at chunk terminals and actual publication boundaries, not every repaint.
- **RED-first epoch serial binding:** test-only [`fc30ef6a`](https://github.com/chigre/Picture_Capture/commit/fc30ef6a3ae5522985d538758ffdf9a45b8e0cb0) added missing-serial and stale-serial cases plus a legacy no-witness positive control. [CI #41504813347](https://github.com/chigre/Picture_Capture/actions/runs/41504813347) completed with both intended failures in all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs. Ubuntu3.13 2 failed/5438 passed/3 skipped; macOS3.13 2/5439/2; Windows3.13 2/5439/2; Ubuntu3.10 2/5438/3; macOS3.10 2/5439/2; Windows3.10 2/5438/3.
- **Minimal fix:** [`2fc347e3`](https://github.com/chigre/Picture_Capture/commit/2fc347e3f806c5e2e961127fb2c5d83d191bf1df) changes only `src/picture_capture/ui/focused_filter_workflow.py` (4 additions, 1 deletion): a populated epoch witness map with missing/mismatched owner serial now fails closed. Legacy no-witness helper compatibility remains unchanged.
- **Exact source/test HEAD gates:** [CI #41505337297](https://github.com/chigre/Picture_Capture/actions/runs/41505337297) **6/6 SUCCESS**; Risk tier and Risk-tier CI gate SUCCESS. Counts: Ubuntu3.13 5440/3 skipped; macOS3.13 5441/2; Windows3.13 5441/2; Ubuntu3.10 5440/3; macOS3.10 5441/2; Windows3.10 5441/2. [OCR #41505337406](https://github.com/chigre/Picture_Capture/actions/runs/41505337406) **3/3 SUCCESS**; [CodeQL #41505327430](https://github.com/chigre/Picture_Capture/actions/runs/41505327430) Analyze Python/Actions **2/2 SUCCESS**. Documentation architecture check **SKIPPED**, not PASS.
- **Windows native smoke:** exact source/test HEAD passed Windows3.13 thumbnail controls and scroll/sort smoke, plus G3 native Tk focused refusal/retry/in-flight-reversion and close/source-drift refusal checks. Windows3.10 passed the thumbnail pixel/sort smoke. Historical first-attempt thumbnail failure remains preserved; root cause **UNCONFIRMED**.
- **Audit:** see `docs/architecture/G3_R4_2_EPOCH_SERIAL_BINDING_FAIL_CLOSED_20261103.md`. Synthetic E2 only. No persistence schema, PDIC/PPP/SECTION format, OCR behavior, crop geometry, save writer, original XY, or experiment defaults changed. No real benchmark or accuracy claim.
- **NOT PERFORMED / DEFERRED:** Windows R3 E3; #483 W1–W11; #503 human Undo/Redo; real dictionary scan and PDIC/PPP/SECTION/Profile/OCR save-reopen; human operator acceptance; R6 real-label learning; R8 real scans.
- **Next recovery point:** read-only audit of remaining SECTION/crop-to-save source-witness handoff; add another RED-first regression only if a concrete stale-owner/source-drift counterexample is found. Continue preserving the Windows thumbnail intermittent-failure audit without widening timeouts or weakening assertions.

## 2026-11-03 SGT｜G3 R4.2 project/ReviewWindow session lifecycle guards — RED → GREEN, exact source/test HEAD verified

- **Live baseline:** `main@ec20989ea8c026cca5337293e67850b6b6df30f2`; sole PR #663 remains **Draft / Open / Unmerged** at source/test HEAD `25d5cb46c38af10a831a31f7c8abc63eddc7bcb0`. Issues #503/#562/#483 remain Open; no unresolved inline review threads.
- **Project switch while proofreading is open — RED first:** test-only `49d3401f` added `test_project_switch_is_refused_while_review_window_is_alive`; [CI #41469931769](https://github.com/chigre/Picture_Capture/actions/runs/41469931769) failed all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs on the intended assertion that project loading began while a live `ReviewWindow` still owned the old session. Ubuntu3.13: 1 failed / 5432 passed / 3 skipped. Minimal fix `9a608895` checks the existing non-modal review window before deferred save flush, timer cancellation, persistence or new worker dispatch. It does not auto-close or trigger a save; same-project reopen remains a no-op.
- **Reverse ordering — RED first:** test-only `bfc2412d` added `test_open_review_is_refused_while_project_load_worker_is_active`; [CI #41472574845](https://github.com/chigre/Picture_Capture/actions/runs/41472574845) failed all six matrix jobs on the intended assertion that a new ReviewWindow opened while project loading was already active. Minimal fix `5f2f5b00` refuses before editor synchronization, settings mutation or window construction. A subsequent wording-only assertion mismatch (expected substring omitted “后台”) was corrected in test-only commit `25d5cb46`; no production change in that correction.
- **Exact source/test HEAD gates:** [CI #41473874028](https://github.com/chigre/Picture_Capture/actions/runs/41473874028) **6/6 SUCCESS**, Risk tier and Risk-tier CI gate SUCCESS. Ubuntu3.13 5435 passed/3 skipped; macOS3.13 5436/2; Windows3.13 5435/3; Ubuntu3.10 5435/3; macOS3.10 5436/2; Windows3.10 5436/2. [OCR #41473873904](https://github.com/chigre/Picture_Capture/actions/runs/41473873904) **3/3 SUCCESS**; [CodeQL #41473865458](https://github.com/chigre/Picture_Capture/actions/runs/41473865458) Analyze Python/Actions **2/2 SUCCESS**. Native Tk thumbnail pixel/sort smoke passed in all six regression jobs. Documentation architecture check was **SKIPPED**, not counted as PASS. The following documentation checkpoint must independently pass its exact-head gates.
- **Windows thumbnail intermittent-smoke audit:** historical [CI #41458526317](https://github.com/chigre/Picture_Capture/actions/runs/41458526317) attempt 1 failed only Windows Python3.10 after 5427 passed/2 skipped with `Real thumbnails never loaded into native first-column cells`; unchanged-head attempt 2 passed (job 125324407177, 5426 passed/3 skipped). Latest exact source/test HEAD #41473874028 passed the same native thumbnail pixel/sort checks on Windows Python3.10 and 3.13. The smoke uses a 1.8-second first-thumbnail wait and the controller has bounded viewport retries; these are plausible timing contributors, **not a confirmed root cause**. No timeout widening, assertion weakening, skip, or production thumbnail change was made. If it recurs, capture Treeview mapping/visible iids, controller generation, pending tickets, failures, task active count and poll state before changing code.
- **Boundaries:** no PDIC/PPP/SECTION format, source XY, OCR behavior, persistence writer or experimental default changed. Synthetic E2 only. Windows R3 E3, #483 W1–W11, #503 human Undo/Redo and real dictionary scan/save-reopen remain NOT PERFORMED; R6/R8 remain DEFERRED.
- **Next:** continue bounded R4.2 SECTION/crop/source/save ownership with a concrete RED-first counterexample. Keep the thumbnail timing risk explicitly unresolved unless reproduced.

---

## 2026-11-02｜B7b R7.3 cross-owner source XY + orthogonal replay fail-closed + multi-pass raster parity

- **Live baseline before this docs checkpoint:** `main@ec20989ea8c026cca5337293e67850b6b6df30f2`; sole PR #663 Draft/Open/Unmerged on `refactor/562-retire-root-image-utils-20261024`; branch code/test HEAD `0b1aeff27e96f9753c4af786e2c3e19ae22a94dd`. #503/#562/#483 remain Open; inline review threads 0.
- **Cross-owner source-XY integration:** [test commit `2e5cdbef`](https://github.com/chigre/Picture_Capture/commit/2e5cdbef44c06fff7b8d3370890966cbf03d812e) checks PDIC marker, PPP polygon and SECTION v2 under identity/mirror/90-degree layouts, homography, crop and centered canvas. Actual Pillow pixel agrees with the projected coordinate; inverse points/polygons round-trip; source image and PDIC/PPP/SECTION bytes are unchanged. Exact-head CI #41332835127 6/6 + Risk-tier/gate SUCCESS; OCR #41332835149 3/3; CodeQL #41332832231 Python/Actions 2/2.
- **Orthogonal replay RED-first:** [test-only `3a4d4672`](https://github.com/chigre/Picture_Capture/commit/3a4d467297daef3ac3131ad431cac6230ac80850), [CI #41333587702](https://github.com/chigre/Picture_Capture/actions/runs/41333587702), all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs failed exactly three intended assertions: missing modern step, empty step, incomplete legacy knots were silently accepted despite `orthogonal_applied=True`. Ubuntu3.13 3 failed / 5323 passed / 3 skipped.
- **Minimal fix:** [`59edbb0b`](https://github.com/chigre/Picture_Capture/commit/59edbb0b6affff39dc6c1c2a9a7503a263c925ef) validates finite/increasing legacy knots, separator array pairing, row-grid dimensions/lengths and decoder output. Applied orthogonal stages without usable replay geometry now fail closed; valid legacy row geometry and separator-only geometry remain supported. Exact source-head CI #41333905956 6/6 + Risk-tier/gate SUCCESS; OCR #41333906027 3/3; CodeQL #41333902165 Python/Actions 2/2.
- **Multi-pass raster parity:** [test commit `0b1aeff2`](https://github.com/chigre/Picture_Capture/commit/0b1aeff27e96f9753c4af786e2c3e19ae22a94dd) adds two sequential separator shifts (2px then 1px) with perspective, crop, canvas and all four canonical layouts. The actual Pillow-rendered pixel matches the map; inverse point/polygon mappings round-trip; original image and PDIC/PPP/SECTION bytes remain unchanged.
- **Final exact code/test HEAD gates:** [CI #41334461268](https://github.com/chigre/Picture_Capture/actions/runs/41334461268) **SUCCESS 6/6**, Risk-tier and Risk-tier CI gate SUCCESS; [OCR #41334461089](https://github.com/chigre/Picture_Capture/actions/runs/41334461089) **SUCCESS 3/3**; [CodeQL #41334459114](https://github.com/chigre/Picture_Capture/actions/runs/41334459114) Analyze Python/Actions **2/2 SUCCESS**. Ubuntu Python3.13/3.10 each 5328 passed/3 skipped; Windows and macOS Python3.13/3.10 each 5329 passed/2 skipped. Documentation architecture check SKIPPED, not PASS.
- **State:** R7.3 remains `in_progress`; active/next batch B7b. B7a/R7.1-R7.2 blocked pending authorized representative profiling; R6 blocked pending verified human labels; R8 user-deferred.
- **NOT PERFORMED:** Windows R3 E3, #483 W1-W11, #503 human Undo/Redo, real dictionary scan, real PDIC/PPP/SECTION/Profile/OCR save/reopen. Synthetic E2 is not human acceptance.
- **Next:** adversarial nonlinear orthogonal ROI/crop edge behavior, source-size/EXIF snapshot consistency and malformed preprocessing snapshot contracts. Do not wire this read-only mapper into persistence writers without a separate review.

---

## 2026-11-02｜B7b R7.3 projective point-horizon guard — RED-first + source fix, synthetic E2 source HEAD verified

- **Live baseline before docs checkpoint:** `main@ec20989ea8c026cca5337293e67850b6b6df30f2`; sole #663 Draft/Open/Unmerged branch `refactor/562-retire-root-image-utils-20261024`. Source fix HEAD `17c4507be204a84660e76b76e07629612edcae6d`; #503/#562/#483 remain Open; no review threads.
- **Historical 92afa verification:** test-only `92afa633b86d05158cab695bdb05dd14b2719d1e` [CI #41098513706](https://github.com/chigre/Picture_Capture/actions/runs/41098513706) completed FAILURE: native Tk opt-out rescan timed out on Windows/macOS/Ubuntu Python3.13 after status showed auto-saved but no batch active/progress. [OCR #41098513714](https://github.com/chigre/Picture_Capture/actions/runs/41098513714) 3/3 SUCCESS; [CodeQL #41098508919](https://github.com/chigre/Picture_Capture/actions/runs/41098508919) Python/Actions 2/2 SUCCESS. The issue was later corrected in `24e78710`; its [CI #41309027670](https://github.com/chigre/Picture_Capture/actions/runs/41309027670) 6/6, [OCR #41309027659](https://github.com/chigre/Picture_Capture/actions/runs/41309027659) 3/3, and [CodeQL #41309024720](https://github.com/chigre/Picture_Capture/actions/runs/41309024720) 2/2 completed SUCCESS. The historical RED is retained, not rewritten as green.
- **New point-mapping RED:** test-only `1d881ba0` [CI #41329969235](https://github.com/chigre/Picture_Capture/actions/runs/41329969235) completed FAILURE across all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs. Both new assertions failed everywhere: near-horizon forward source point was fabricated as an in-crop coordinate; exact inverse-horizon output point was fabricated as a source coordinate. Ubuntu3.13: 2 failed / 5304 passed / 3 skipped.
- **Minimal source fix:** `17c4507b` uses a relative denominator cancellation test (`abs(w) <= 1e-12 * sum(abs(g*x),abs(h*y),abs(i))`) with `math.fsum`, applied consistently to forward points, inverse points and polygon horizon checks. This is local to the read-only coordinate map; the shared general homography helper and raster writer remain unchanged. Homogeneous scale tests at 1e-14, 1 and 1e14 pass.
- **Exact source-head gates:** [CI #41330338708](https://github.com/chigre/Picture_Capture/actions/runs/41330338708) **SUCCESS 6/6**, Risk-tier and Risk-tier CI gate SUCCESS; [OCR #41330338796](https://github.com/chigre/Picture_Capture/actions/runs/41330338796) **SUCCESS 3/3**; [CodeQL #41330336171](https://github.com/chigre/Picture_Capture/actions/runs/41330336171) Analyze Python/Actions **2/2 SUCCESS**. Documentation architecture check SKIPPED, not PASS. This checkpoint adds positive controls for zero forward H[2,2] fallback and all four canonical LayoutTransform point/polygon round-trips; final docs/test HEAD must run its own exact-head gates.
- **Architecture audit:** [R7.3 scale-relative point-horizon guard](../architecture/R7_3_SCALE_RELATIVE_PROJECTIVE_POINT_HORIZON_20261102.md). No PDIC/PPP/SECTION/Profile/OCR schema, original source XY, real writer, raster algorithm or experiment default changed.
- **NOT PERFORMED:** Windows R3 E3; #483 W1–W11; #503 human Undo/Redo; real dictionary scan and real PDIC/PPP/SECTION/Profile/OCR save/reopen. **DEFERRED:** R6 verified-label learning and R8 real scan. Synthetic E2 is not human acceptance.
- **Next:** verify the final docs/test HEAD's six-platform CI, Risk-tier gate, OCR 3OS and CodeQL; then continue B7b/R7.3 read-only SECTION/PDIC/PPP/ROI/crop contracts. B7a profiling remains blocked pending authorized representative benchmark data.

---

## 2026-11-01｜G3 R4.2 不确定保存的重新筛选 / 批次导航旁路：失败先行 + 源码修复

- **实时代码基线：** 源码提交 `eff2b7c8e269bb4f6ecec414cffdff059e9dabdb`；唯一 #663 Draft/Open/Unmerged；main `ec20989ea8c026cca5337293e67850b6b6df30f2` 不变，#503/#562/#483 仍 Open。
- **失败先行：** `d8b65be7` [CI #41311186833](https://github.com/chigre/Picture_Capture/actions/runs/41311186833) Ubuntu Python3.13 2 targeted FAILED / 5302 passed / 3 skipped；`ae1f21ed` [CI #41311282890](https://github.com/chigre/Picture_Capture/actions/runs/41311282890) Ubuntu Python3.13 3 targeted FAILED / 5301 passed / 3 skipped。前者暴露 empty pending queue 仍允许重新筛选覆盖 source epoch；后者暴露 Next batch 经 `_flush_focused_changes_now` 自动赋予显式重试权限。
- **最小修复：** `eff2b7c8` 拦截尚未确认的 save/launch 状态，禁止重新筛选和导航隐式保存；保留人工 edit、PDIC 检查后显式 retry 和无异常的正常扫描/切批行为。回归含可恢复正向控制。
- **门禁：** 源码 HEAD [CI #41311452549](https://github.com/chigre/Picture_Capture/actions/runs/41311452549)、[OCR #41311452557](https://github.com/chigre/Picture_Capture/actions/runs/41311452557)、CodeQL Python/Actions 均须读取终态，不以当前排队 / 运行态当 SUCCESS；此文档提交后仍需检查文档 HEAD 的 exact-head 门禁。Documentation architecture check 的 SKIPPED 不计 PASS。
- **架构审计：** [G3 R4.2 不确定保存导航保护](../architecture/G3_R4_2_UNCERTAIN_SAVE_REFILTER_NAVIGATION_20261101.md)。未改变持久化 schema、writer、原图 XY 或实验开关，未声称原子跨文件事务。
- **NOT PERFORMED：** Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典扫描与真实 PDIC/PPP/SECTION/Profile/OCR 保存重开。**DEFERRED：** R6 真实标签学习、R8 真实扫描；自动 E2 不等于人工通过。
- **下一恢复点：** 先核最终 HEAD 六平台/Risk-tier/OCR/CodeQL，失败先修复；再推进异步 epoch / SECTION / crop prefetch / save 一致性反例。保持主干不变、唯一 PR #663 Draft，不合并。

---

## 2026-11-01｜B7b R7.3 polygon-horizon & G3 R4.2 uncertain focused-save, synthetic E2 verified

- **实时代码基线：** PR #663 的最后源码 HEAD `023432f6f8f0a742743eb5b33c68379c38cf1d4c`；main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。#663 Draft/Open/Unmerged；#503/#562/#483 保持 Open。任何新的文档/测试 commit 需重新确认当前 HEAD。
- **R7.3 反例与修复：** 多边形四角都在图内不代表边可投影。source polygon 跨单应性分母极点时必须拒绝，安全同侧多边形仍正常。RED [CI #41307611949](https://github.com/chigre/Picture_Capture/actions/runs/41307611949)；修复 `afbc42a1` 的 [CI #41307851367](https://github.com/chigre/Picture_Capture/actions/runs/41307851367) 6/6，OCR #41307851371 3/3，CodeQL #41307849472 2/2 SUCCESS。
- **G3 反例与修复：** scheduler 可能先运行 writer 后报告启动失败；本批全部标 UNCERTAIN，保留人工改动，关闭窗口与防抖不能隐式重试，只有核对 PDIC 后的显式 retry 可启动。RED #41308310346/#41308530086。原生 Tk GUI smoke 中间 RED #41308743285 已修正测试交互并在 [CI #41309027670](https://github.com/chigre/Picture_Capture/actions/runs/41309027670) 六平台通过。显式 retry 若 source preflight 失败必须保留历史 UNCERTAIN，RED #41309554723 → 修复 `023432f6`，其 [CI #41309765324](https://github.com/chigre/Picture_Capture/actions/runs/41309765324) 6/6 + Risk-tier/gate、OCR #41309765320 3/3、CodeQL #41309762501 2/2 SUCCESS。
- **架构审计：** `docs/architecture/R7_3_HOMOGRAPHY_RASTER_REPLAY_GUARD_20261101.md` 和 `docs/architecture/G3_R4_2_FOCUSED_SAVE_LAUNCH_AND_PREFLIGHT_20261101.md`。仅 transient UI / read-only geometry + synthetic tests，未更改 PDIC/PPP/SECTION/Profile/OCR 持久化 schema、原图坐标、实际 writer 或实验默认值。Documentation architecture check 的 SKIPPED 不计成功。最终文档/测试 HEAD 须独立复检门禁。
- **后续：** 保持 B7b 几何合同与 G3 async epoch/SECTION/crop prefetch/save 一致性回归的自动审计；风险恢复时先查实时 main/PR HEAD 和最新 PR 评论、CI/OCR/CodeQL。B6/R6 缺真实核验标签，B7a 缺真实 profiler，R8 缺授权数据时不得执行或声称性能提升。
- **NOT PERFORMED：** Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典扫描与真实 PDIC/PPP/SECTION/Profile/OCR 保存重开。**DEFERRED：** R6 学习、R8 扫描；synthetic E2 不等于人工验收。

---

## 2026-11-01｜G3 R4.2 B4 收口，进入 R7.3 独立坐标合同审计

- **实时 HEAD：** `fd4f46b717de23c96014661ae28cedef51434788`；main `ec20989ea8c026cca5337293e67850b6b6df30f2` 不变；唯一 PR #663 仍 Draft/Open/Unmerged；当前 open PR 列表仅 #663。
- **Exact-head 门禁：** [CI #41298152181](https://github.com/chigre/Picture_Capture/actions/runs/41298152181) 六平台/Python 6/6 + Risk-tier + gate SUCCESS；[OCR #41298152176](https://github.com/chigre/Picture_Capture/actions/runs/41298152176) 3/3 SUCCESS；[CodeQL #41298149721](https://github.com/chigre/Picture_Capture/actions/runs/41298149721) Python/Actions 2/2 SUCCESS。Documentation architecture check SKIPPED，不计 PASS。
- **B4/R4.2 完成：** no-hit page 的 PDIC/OCR/SECTION witness 在 scan terminal 后仍保留，并在实际 batch publication 前复核；在途 crop stale payload 被拒绝。多页保存若任一已派发 writer 抛错，则整批人工修改保留、页面标为 UNCERTAIN、关闭与自动重试停止，必须人工核对后显式重试；不回滚已可能发布的文件。
- **RED 与修复记录：** no-hit 在途 crop RED #41295513470，优化后 post-terminal 三来源回归 #41295775912；partial-save RED #41296691853；保守状态更新 RED #41297732941（28 failures，包括 recovered 未定义、旧 helper mock 缺字段和错误提示断言）。最终修复提交 `fd4f46b717de23c96014661ae28cedef51434788`，当前 exact-head gates 全绿。
- **批次状态：** B4 verified（synthetic E2）；B5 R5.1/R5.2 synthetic E2 verified；B6 blocked（缺少人工核验来源一致标签）；B7a R7.1/R7.2 blocked（无授权真实 profiling，不声称加速）；B7b R7.3 作为不依赖人工标签的独立工作包开始。
- **下一步：** 只读审计 source→canonical→transformed 坐标 owner，制定版本化正/逆映射合同，并以 synthetic tests 覆盖 SECTION、PDIC、PPP、ROI polygon、crop round-trip。禁止改持久化 schema、原图坐标或写入流程。
- **始终 NOT PERFORMED：** Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典扫描及真实 PDIC/PPP/SECTION/Profile/OCR 保存重开。**DEFERRED：** R6 真实标签学习、R8 真实扫描。自动 E2 不等于人工验收。

---

## 2026-11-01｜final docs checkpoint acab2b8321 exact-head gates green

- [CI #41290656126](https://github.com/chigre/Picture_Capture/actions/runs/41290656126): **6/6 SUCCESS**, Risk-tier and Risk-tier CI gate SUCCESS. [OCR #41290656141](https://github.com/chigre/Picture_Capture/actions/runs/41290656141): **3/3 SUCCESS**. [CodeQL #41290653408](https://github.com/chigre/Picture_Capture/actions/runs/41290653408): Analyze Python/Actions **2/2 SUCCESS**. Documentation architecture check was SKIPPED and is not counted as PASS.
- B4 remains active for post-terminal no-hit source drift and focused-save partial publication/reconciliation. B5/R5.1+R5.2 is synthetic E2 complete on source HEAD `3b06e89034cc8c5b93db3613fd0d10fe811bdc70`. B6 is blocked pending reliable human-verified source-consistent labels and independent dictionary/project partitions.
- The `implementation_pr.units` field is a scope index only; per-unit status is recorded in the B4/B5/B6 batch records and dedicated evidence objects. R7.1/R7.3 are not yet verified; human R3 acceptance remains deferred/not performed.
- Next: fail-first test to bound the cost of no-hit epoch revalidation (avoid repeated full-prefix hashing on every intermediate chunk), then continue focused-save partial publication/reconciliation. Preserve one Draft PR #663 and all human/real-data deferrals.

---

## 2026-11-01｜docs checkpoint 10a23f40 and B5 R5 parity recheck

- **Docs checkpoint exact HEAD:** `10a23f40f7751d51f66b34790fa12ec5efe25690`; [CI #41290109140](https://github.com/chigre/Picture_Capture/actions/runs/41290109140) 6/6 Windows/macOS/Ubuntu × Python3.10/3.13 + Risk-tier + Risk-tier CI gate SUCCESS; [OCR #41290109157](https://github.com/chigre/Picture_Capture/actions/runs/41290109157) 3/3 SUCCESS; [CodeQL #41290105787](https://github.com/chigre/Picture_Capture/actions/runs/41290105787) Python/Actions 2/2 SUCCESS. Documentation architecture check SKIPPED and not counted as PASS.
- **B5 R5.1/R5.2 current source recheck:** exact source HEAD `3b06e89034cc8c5b93db3613fd0d10fe811bdc70`; [CI #41289630397](https://github.com/chigre/Picture_Capture/actions/runs/41289630397) 6/6 SUCCESS, [OCR #41289630408](https://github.com/chigre/Picture_Capture/actions/runs/41289630408) 3/3 SUCCESS, [CodeQL #41289628415](https://github.com/chigre/Picture_Capture/actions/runs/41289628415) 2/2 SUCCESS. Dedicated candidate-score and engine-q parity tests both passed in all six full-suite jobs. R5.1 covers 4,096 boolean vectors; R5.2 covers 512 direct q comparisons plus full-arbitration differential cases. No weights/thresholds/decision rules changed; synthetic E2 only.
- **Batch state:** B4 remains active for the residual post-terminal no-hit source drift and focused-save partial publication/reconciliation audit. B5 R5.1/R5.2 is now marked synthetic E2 complete. B6 is blocked pending reliable human-verified, source-consistent labels and independent dictionary/project partition; no model training or shadow deployment.
- **Boundaries:** R3 E3, #483 W1-W11, #503 manual Undo/Redo and real PDIC/PPP/SECTION/Profile/OCR save/reopen remain NOT PERFORMED. R6 training/shadow, R7 real performance claims and R8 real scan remain gated/deferred.
- **Next:** fail-first test post-terminal no-hit page drift with a bounded/performance-aware design, then continue focused-save partial publication/reconciliation. Preserve one Draft PR #663; do not merge or mark Ready.

---

## 2026-11-01｜G3 R4.2 no-hit page source retention across async scan epochs：source HEAD synthetic E2 verified

- **Live baseline:** source/test HEAD `3b06e89034cc8c5b93db3613fd0d10fe811bdc70`; main `ec20989ea8c026cca5337293e67850b6b6df30f2`; sole PR #663 remains Draft/Open/Unmerged; #503/#562/#483 remain Open.
- **RED-first:** test-only `1a3e19e2595fb6355b87e185305228994c54e00a`; [CI #41289415491](https://github.com/chigre/Picture_Capture/actions/runs/41289415491) all six Windows/macOS/Ubuntu × Python3.10/3.13 jobs failed the three intended no-hit source drift cases (PDIC, OCR JSON, SECTION). Ubuntu3.13 and Ubuntu3.10 logs: 3 failed / 5280 passed / 3 skipped.
- **Production fix:** `3b06e89034cc8c5b93db3613fd0d10fe811bdc70` retains a scan-epoch-local page-index→source-witness map for every scanned page, including no-hit pages; rejects repeated page index with a changed witness; revalidates the scanned prefix at the first batch and every subsequent chunk terminal before publishing or marking complete.
- **Exact source-head E2:** [CI #41289630397](https://github.com/chigre/Picture_Capture/actions/runs/41289630397) **6/6 SUCCESS**, Risk-tier and Risk-tier CI gate SUCCESS; [OCR #41289630408](https://github.com/chigre/Picture_Capture/actions/runs/41289630408) **3/3 SUCCESS**; [CodeQL #41289628415](https://github.com/chigre/Picture_Capture/actions/runs/41289628415) Python/Actions **2/2 SUCCESS**. Ubuntu3.13 5283/3; macOS3.13 5284/2; Windows3.13 5284/2; Ubuntu3.10 5283/3; macOS3.10 5284/2; Windows3.10 5284/2. Documentation architecture check **SKIPPED**, not PASS.
- **Limitations:** witness map is volatile and rechecked at chunk terminals; later no-hit-page drift after terminal is not continuously rechecked on every navigation. SHA-256 readback is not OS-level CAS/lock. No save writer or persistence schema changed; no cross-page transaction claimed.
- **NOT PERFORMED:** Windows R3 E3, #483 W1–W11, #503 manual Undo/Redo, real dictionary scan, real PDIC/PPP/SECTION/Profile/OCR save/reopen, operator acceptance. **DEFERRED:** R6 real-label learning, R8 real scan.
- **Next:** commit synchronized docs checkpoint and re-run exact docs-head gates; then fail-first focused-save partial publication/reconciliation and post-terminal no-hit source drift.

---

## 2026-11-01｜G3 R4.2 异步筛选 PDIC/OCR/SECTION 来源绑定：source HEAD synthetic E2 已验证

- **实时基线与边界：** source/test HEAD `4458faa953fccc1bb247e3209dba400139c10a68`；main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未变；唯一 PR #663 仍 Draft/Open/Unmerged；#503/#562/#483 仍 Open。无 inline review comments / submitted reviews。
- **RED-first：** 测试提交 `36e917d27e98615413ad770c138cdba2f294ede4`，[CI #41286614069](https://github.com/chigre/Picture_Capture/actions/runs/41286614069) 六平台/Python regression jobs 均因四个新来源断言失败而 FAILURE：PDIC、OCR JSON、SECTION 在 scan 读取期间变化未拒绝，以及 target 缺少 scan witness；Ubuntu Python3.13 为 4 failed / 5,276 passed / 3 skipped，macOS Python3.13 为 4 failed / 5,277 passed / 2 skipped。
- **源码修复：** `035b50631b46a1ec1b6474736cc354c9a2214d77` 新增 `focused_scan_source_witness` / `verify_focused_scan_source`，对 required PDIC、optional OCR cache、active SECTION sidecar 记录 path/presence/SHA-256；scan_page 前后校验并将 witness 绑定到每个 target；batch snapshot 将其纳入 cache key；prefetch/direct crop worker 完成后再校验，Tk completion/apply 前再次 snapshot。
- **中间回归修复：** 首个 source CI 发现旧 streaming fixture 没有磁盘 PDIC，且部分旧 crop mock 没有 `parent.project`。新四个目标测试已通过，但 Ubuntu Python3.13 full suite 报 25 个旧夹具失败。提交 `4458faa953fccc1bb247e3209dba400139c10a68` 仅补 synthetic PDIC fixture，并使 legacy mock 的 project-root capture 安全；未削弱生产来源校验。
- **source exact-head gates：** [CI #41287049195](https://github.com/chigre/Picture_Capture/actions/runs/41287049195) **6/6 SUCCESS**，Risk-tier 与 Risk-tier CI gate SUCCESS；[OCR #41287049231](https://github.com/chigre/Picture_Capture/actions/runs/41287049231) **3/3 SUCCESS**；[CodeQL #41287046391](https://github.com/chigre/Picture_Capture/actions/runs/41287046391) Analyze Python/Actions **2/2 SUCCESS**。Ubuntu3.13 5280/3；macOS/Windows3.13 各5281/2；Ubuntu3.10 5280/3；macOS/Windows3.10 各5281/2。Documentation architecture check **SKIPPED**，不计 PASS。
- **限制与未完成：** 当前 target witness 绑定可见命中页，但 scan_page 返回后未命中的页面 witness 尚未保存在 epoch-wide map；此前扫描过的 no-hit page 在 scan terminal 前变化，仍需专门失败先行测试。SHA-256 readback 不是 OS-level CAS/文件锁。save writer 未改，未声称跨页原子事务。
- **NOT PERFORMED：** Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典扫描及真实 PDIC/PPP/SECTION/Profile/OCR 保存重开、真人验收。**DEFERRED：** R6 真实标签学习、R8 真实扫描。无真实 benchmark，不声称加速或准确性。
- **本次文档 checkpoint：** 以下架构审计、STATE、RESUME 与计划状态将提交到现有 Draft 分支；提交后必须对新的 docs HEAD 重新核验六平台 CI/Risk gate、OCR 3OS、CodeQL Python/Actions。下一恢复点为 no-hit page epoch-wide source witness，再继续 save publication consistency。

---

## 2026-11-01｜G3 R4.2 recurring Tk poll / durable close retry：源码修复完成，source HEAD E2 门禁通过

- 实时 main `ec20989ea8c026cca5337293e67850b6b6df30f2`；唯一 PR #663 保持 Draft/Open/Unmerged；#503/#562/#483 均 Open。
- **RED-first 链**：`923aa075` 首轮新增 7 个调度失败测试；发现 close-path fake 缺少 `_poll_ui_worker_queue` 后，在 `11db385d` 补齐 mock 并同步更新严格 leaf-owner inventory。随后 `57be8123` 的 corrected fixture RED 在 Ubuntu/macOS Python3.13 各复现 5 个失败，涉及关闭意图丢失、retry 后重新隐藏、idle fallback latch 与显式重试。
- **源码修复**：最终 source commit `1f338a368726c0cfd3c188f4bef1a0dec95b09ec`。轮询周期性 `after()` 失败时最多尝试一次 `after_idle()` fallback，避免 idle-spin；两种调度器均失败时保留 active/close-wait 和关闭意图，重新显示窗口以供显式重试；关闭重试重新开放一次 fallback，成功注册观察者后再隐藏，不重复 invalidation；若 worker 已完成但 `after_idle(on_close)` 注册失败，则在同一 Tk 线程直接完成关闭。
- **Source exact-head gates**：CI [#41284201872](https://github.com/chigre/Picture_Capture/actions/runs/41284201872) 六平台/Python 组合 6/6 SUCCESS，Risk tier 与 Risk-tier CI gate SUCCESS；OCR [#41284201873](https://github.com/chigre/Picture_Capture/actions/runs/41284201873) 3/3 SUCCESS；CodeQL [#41284199187](https://github.com/chigre/Picture_Capture/actions/runs/41284199187) Python/Actions 2/2 SUCCESS。macOS Python3.13 原生 GUI smoke 首次出现一次 synthetic in-flight PDIC conflict；同一 HEAD 的同一 job 重跑 `124783274918` 后 SUCCESS，5,277 passed/2 skipped，All checks passed。保留此瞬时异常记录，不宣称它未发生。Documentation architecture check 为 **SKIPPED**，不计为通过。
- 以上为 source HEAD 证据；本次路线图/架构 checkpoint commit 后仍须对新的 docs HEAD 重新验证全部 exact-head gates。此轮为 synthetic E2；不等于人工 E3 或真实项目文件耐久性验收。
- **NOT PERFORMED**：Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典扫描、真实 PDIC/PPP/SECTION/Profile/OCR 保存重开、性能 benchmark。**DEFERRED**：R6 真实标签学习、R8 真实扫描。PR 保持 Draft/Open/Unmerged，main 不变。
- 下一工作包：异步 SECTION/source epoch、crop prefetch 与 save 一致性 fail-first audit。


---

## 2026-11-01｜G3 R4.2 首次 Tk poll 注册失败：先注册轮询，再启动 worker

- 实时基线：main `ec20989ea8c026cca5337293e67850b6b6df30f2`；唯一 PR #663 保持 Draft/Open/Unmerged；#503/#562/#483 Open；无 inline review threads。
- **失败先行：** 测试提交 `30a52c095a85a3d3d21f8e5bae9eba9b2969c6da`，[CI #41281091863](https://github.com/chigre/Picture_Capture/actions/runs/41281091863) 最终 FAILURE。四个参数化反例覆盖有/无同 key 旧 worker × 普通/持久化 wait-on-close worker；在首次 `after()` 抛错时，旧实现已构造并启动新 worker，随后抛出调度异常，无法保证该 worker 有 Tk completion/close-wait observer。Windows Python3.10 日志为 **4 failed / 5263 passed / 2 skipped**；Ubuntu/macOS 的 Python3.10/3.13 jobs 也观察到四个目标失败。该 RED run 不作为通过门禁。
- **最小修复：** `c3e5c0e3aa937784715f5ece16ce82adb8173da7`。在 `ui/background_job_runtime.py::start_ui_worker` 中，先成功注册首个 Tk poll，再构造/启动 Thread；若 `after()` 抛错，回滚本次 generation、handler、active、close-wait，并恢复旧同 key handler/generation，因此不会启动无轮询观察者的线程。若 poll 已注册后 Thread constructor/start 失败，保留该 poll，让它能处理恢复的旧 worker，或在无旧任务时空轮询一次。未改持久化 schema、真实文件写入、OCR、原图坐标或实验开关。
- 回归：`tests/test_g3_r4_ui_worker_after_failure_20261101.py` 覆盖首次调度失败与已有 poll 复用；`tests/test_g3_r4_ui_worker_failed_start_20261101.py` 更新 constructor/start 失败后保留已接受 poll 的契约。
- **Source exact-head 自动验收：** [CI #41281480946](https://github.com/chigre/Picture_Capture/actions/runs/41281480946) Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**，Risk tier 与 Risk-tier CI gate SUCCESS；Documentation architecture check SKIPPED。Ubuntu Python3.13 5266 passed/3 skipped；macOS/Windows Python3.13 各 5267 passed/2 skipped；Python3.10 三平台均 SUCCESS。 [OCR #41281480909](https://github.com/chigre/Picture_Capture/actions/runs/41281480909) **3/3 SUCCESS**；[CodeQL #41281477946](https://github.com/chigre/Picture_Capture/actions/runs/41281477946) Analyze Python/Actions **2/2 SUCCESS**。
- 以上为 source HEAD `c3e5c0e3` 证据；本次审计/路线图文档 checkpoint 提交后，仍必须重新核对其自身 exact-head 六平台 CI/Risk、OCR 3OS、CodeQL Python/Actions。**残余边界：** `poll_ui_worker_queue` 后续周期性 `after()` re-arm 与 close 路径 `after_idle()` 在 worker 已活动后的调度异常尚未覆盖，需另立失败先行测试；不宣称该范围已修复。
- **NOT PERFORMED：** Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典扫描、真实 PDIC/PPP/SECTION/Profile/OCR、人工保存重开及性能 benchmark。**DEFERRED：** R6 真实标签学习、R8 真实扫描。自动 E2 不等于人工通过。保持 main 不动、PR #663 Draft/Open/Unmerged，不合并、不改 Ready、不关闭 Issues。

## 2026-11-01｜G3 R4.2 大批次：预取/直接裁剪 worker 启动确认 + Tk 线程启动失败所有权回滚（失败先行）

- GitHub 复核 main `ec20989ea8c`、仅 Draft/Open/Unmerged PR #663、#503/#562/#483 Open、0 review threads；起点 `f9d2f807` [CI #41238054379](https://github.com/chigre/Picture_Capture/actions/runs/41238054379) 六平台+Risk SUCCESS、[OCR #41238054368](https://github.com/chigre/Picture_Capture/actions/runs/41238054368) 3OS SUCCESS、[CodeQL #41238051230](https://github.com/chigre/Picture_Capture/actions/runs/41238051230) Python/Actions 2/2 SUCCESS。
- **第一组真实 RED：** 测试提交 `d83e05d833cc281be778c84fb5d6f00f1e3cde36` [CI #41240906808](https://github.com/chigre/Picture_Capture/actions/runs/41240906808) macOS Python3.13 **8 targeted FAILED / 5242 passed / 2 skipped**。预取/直接裁剪各 2×2 个拒绝启动场景（同步 done/failed，然后 -1/raise）暴露未确认启动即发布缓存、编辑界面和重入新渲染；另 2 个正常返回正控。
- **第二组真实 RED：** 叠加测试提交 `465943db85e84aab1c3e0ea406511645949133b6` [CI #41241036808](https://github.com/chigre/Picture_Capture/actions/runs/41241036808) macOS Python3.10 **16 targeted FAILED（8 crop + 8 scheduler）/5246 passed/2 skipped**。Tk 后台线程 constructor/start 抛错时未清理新 handler/active/close-wait；尝试替换同名旧任务时还抹去了旧 handler。另有成功启动及 shutdown -1 正控。
- **修复 ①/②：** `abc0f34316b23199c705663ec4c786c58c0d6fcf` 新建责任明确的 `ui/readonly_worker_launch.py`，并仅调整 `focused_filter_workflow.py` 两处裁剪调度入口。先缓冲最早完成/失败 callback，实际正常返回才允许发布；-1/异常则拒绝已缓存回调并走原有 generic failed。保留同步正常返回 `None` 的测试兼容 ABI、不放松来源/epoch/人工保存保护。
- **修复 ③：** `116cc02dcbbbc336624926f97d99e1921fcef9f3` 最小修改 `ui/background_job_runtime.py`：Thread 构造或 start 抛错时撤销本代 handler/active/close-wait、恢复仍运行的同名旧任务 handler 和 generation，避免错误的窗口关闭阻塞或丢失旧完成确认。
- 审计：[G3_R4_2_UI_WORKER_LAUNCH_OWNERSHIP_20261101.md](../architecture/G3_R4_2_UI_WORKER_LAUNCH_OWNERSHIP_20261101.md)。**最终代码+文档 exact HEAD 六平台 CI/Risk、OCR 3OS、CodeQL Python/Actions 必须独立核实，暂记 PENDING。** Tk `after()` 在 Thread 成功启动后失败的情况不在本批证据内；无持久化 schema 或实际 PDIC 写入流程修改。Windows R3 E3、#483 W1–W11、#503 人工 Undo、真词典/PDIC/PPP/SECTION/Profile/OCR/裁剪/性能 **NOT PERFORMED**；R6/R8 DEFERRED。保持 PR Draft，main 不动。


## 2026-11-01｜G3 R4.2 重点筛选人工保存 worker 关闭拒绝 -1：6 个真实失败先行用例，最小修复已提交

- 实时来源：main `ec20989ea8c`，唯一 Draft PR #663，#503/#562/#483 Open；先前 `8af813ad` [CI #41228910802](https://github.com/chigre/Picture_Capture/actions/runs/41228910802) 六 OS/Python＋Risk gate SUCCESS、[OCR #41228910853](https://github.com/chigre/Picture_Capture/actions/runs/41228910853) 3/3 SUCCESS，CodeQL 在此 SHA 未独立核实。
- `ui/background_job_runtime.py::start_ui_worker` 在关闭时直接返回 `-1` 且不会登记 worker/callback；`focused_filter_workflow.py` 人工编辑保存入口仍忽略此返回码，可能清空等待保存的队列却将保存状态永久视为运行。
- **真实测试先红** `36ad0b2e866a4d9ab7a7385ed89ca2ca363fc7d0`，[CI #41237742113](https://github.com/chigre/Picture_Capture/actions/runs/41237742113) Ubuntu 3.13 实际 **6 targeted FAILED / 5233 passed / 3 skipped**；用例组合为关闭意图 false/true × 无回调/同步 done/同步 failed（拒绝启动返回 -1），并检测晚到回调、敏感路径和人工修改保存。
- **最小产品修复** `5c7727413997aa9e010c703844e915ef1f345c01`：保存调度遇 `-1` 进入已有 launch-rejected fail-closed 处理，恢复排队编辑、取消自动关闭、拒绝未确认的提前/晚到回调；不修改落盘格式/worker runtime。独立审计：[G3_R4_2_FOCUSED_SAVE_WORKER_REFUSAL_20261101.md](../architecture/G3_R4_2_FOCUSED_SAVE_WORKER_REFUSAL_20261101.md)。
- 本轮**最终 code+tests+docs HEAD** 的六 OS/Python CI＋Risk、OCR 3 OS、CodeQL Python/Actions 仍须独立检查，暂记 **PENDING**，不能借用其它 SHA 通过证明。Windows R3 E3、#483 W1–W11、#503 实际人工、真实词典/PDIC/PPP/SECTION/Profile/OCR/裁剪验收 **NOT PERFORMED**，R6/R8 DEFERRED；继续保持 Draft、不合并、不关 Issue。

## 2026-11-01｜G3 R4.2 真实 worker 关闭拒绝（返回 -1）后的 prefetch 和直接裁剪状态释放（失败先行，最终门禁待核）

- GitHub 实时基线：`main@ec20989ea8c026cca5337293e67850b6b6df30f2`；唯一 Draft/Open/Unmerged PR #663，#503/#562/#483 Open，Review Threads 0；之前绿色 HEAD `18be51852eeb39179219fd4ac72738a451b18846` 已重新核对 [CI #41226272640](https://github.com/chigre/Picture_Capture/actions/runs/41226272640) 六平台＋Risk gate、[OCR #41226272559](https://github.com/chigre/Picture_Capture/actions/runs/41226272559) 3/3、[CodeQL #41226269712](https://github.com/chigre/Picture_Capture/actions/runs/41226269712) Python/Actions 2/2，全部 SUCCESS。
- 从 `ui/background_job_runtime.py::start_ui_worker` 查明实际关闭/停止调度返回 **-1**，不建立线程回调。旧 `focused_filter_workflow.py` 的 prefetch / direct render 调度忽略返回值，可能永久占有预取 key 或停留加载提示。**真实测试先红：** `f12778e0478bf68208ba54be1dd08c76e503506e`，[CI #41227343838](https://github.com/chigre/Picture_Capture/actions/runs/41227343838) Ubuntu Python3.13 观察 **2 targeted FAILED / 5227 passed / 3 skipped**，均为这两条新反例。
- **最小修复** `d54dc5c895e00c5ff678ed0cea0219e2c12e3860` 仅修改 prefetch 和直接裁剪的启动点：`_start_ui_worker` 抛异常或返回 `-1`，交由现有 epoch/key/serial/人工保存 guard 的 generic failed 回调处理；prefetch 释放 key，直接裁剪清除无穷加载提示；不披露任何内部异常/原图路径。补充 `03ebd57b41c6a1ca189df6cbe3122a38e8fcf970` 两项启动直接抛异常的 E2 测试。
- 审计：[G3_R4_2_CROP_WORKER_CLOSE_REFUSAL_20261101.md](../architecture/G3_R4_2_CROP_WORKER_CLOSE_REFUSAL_20261101.md)。**最终代码+文档 HEAD** 的 CI 六平台＋Risk、OCR 3/3 和 CodeQL Python/Actions 2/2 均需独立核实，此快照记 **PENDING**。Windows R3 E3、#483 W1–W11、#503 人工 Undo/真实词典/性能 **NOT PERFORMED**；R6 真标签学习、R8 实扫 **DEFERRED**。保留唯一 Draft PR #663，main 不动。

## 2026-11-01｜G3 R4.2 初始/分段扫描 worker 启动确认屏障（测试先红，最终 exact-head 门禁待核）

- GitHub 基线：`2599eddb1360b0ae72c0a51c11961020008fbc49` 的 [CI #41223273971](https://github.com/chigre/Picture_Capture/actions/runs/41223273971) 六平台＋Risk gate、[OCR #41223274149](https://github.com/chigre/Picture_Capture/actions/runs/41223274149) 3/3、[CodeQL #41223270845](https://github.com/chigre/Picture_Capture/actions/runs/41223270845) Python/Actions 2/2 全部成功。main `ec20989e` 不变，唯一 Draft PR #663、#503/#562/#483 Open、无 Review Threads。
- **测试先红：** 仅测试提交 `bcaee25f61b4b998ee251a9b4b106d013cd5b5a7`，[CI #41225930839](https://github.com/chigre/Picture_Capture/actions/runs/41225930839) macOS Python 3.13 **4 targeted FAILED / 5220 passed / 2 skipped**。首次或后续扫描的 `_start_ui_worker` 同步执行 done/failed 后再抛启动异常，会暴露私有异常并把未确认的扫描结果或失败发布到 UI；四项反例均红灯。
- 产品最小修复 `1790fe84c5196dcdbe40fdcb5c709b4886344203` 仅更新 `ui/focused_filter_workflow.py`：局部 `dispatch_scan_after_ack` 为首批和每次分段扫描缓冲启动期间最早 terminal，正常返回才派发；若启动抛异常则废弃早期结果、阻断迟到回调、以既有通用 failed 文案 fail-closed（不回显异常）。既有 scan epoch 和单次终结 guard 不变。
- 测试补充 `a83fc88fa848af394ef67f83f67d4e2e14fbb998`：扩展无 callback 直接启动异常的失败安全检查，并新增首批/分段同步成功且已确认启动的正控。上述测试结果需以最终 code+docs HEAD 完成 CI 为准。
- 架构审计：[G3_R4_2_SCAN_LAUNCH_ACK_20261101.md](../architecture/G3_R4_2_SCAN_LAUNCH_ACK_20261101.md)。最终 exact-head 六平台 CI＋Risk、OCR3/3、CodeQL Python/Actions 2/2 均暂记 **PENDING**，不借用前一 SHA。Windows R3 E3、#483 W1–W11、#503 人工 Undo、真实词典与性能 **NOT PERFORMED**，R6 标签学习及 R8 真实扫描 **DEFERRED**。保持唯一 Draft/Open/Unmerged PR #663，main 不动。

## 2026-11-01｜G3 R4.2 首批与分段 scan 的重复/矛盾终结回调（7 项红灯，新增计数断言，最终门禁待核）

- 上一基准 `97cabc347c28085b0e970947e347a7fc376f8782` GitHub exact-head CI [#41219251436](https://github.com/chigre/Picture_Capture/actions/runs/41219251436) 六组合及 Risk-tier gate、OCR [#41219251550](https://github.com/chigre/Picture_Capture/actions/runs/41219251550) 3/3、CodeQL [#41219246937](https://github.com/chigre/Picture_Capture/actions/runs/41219246937) Python/Actions 2/2 均成功；main `ec20989ea` 未动，唯一 Draft PR #663，Issues #503/#562/#483 全 Open。
- **真实测试先红：** `cd77a0aac4250adca5a2e2008e04e294ea1ffddc` 测试单独提交，[CI #41222862870](https://github.com/chigre/Picture_Capture/actions/runs/41222862870) Ubuntu Python 3.13 观察 **7 targeted FAILED / 5212 passed / 3 skipped**。首批重复 success/failed 会重置就绪结果或触发第二个 rest worker；分段重复 success 重复追加 targets，迟到 failed 可污染已完成扫描。测试 `41c92b63e80b786ff5b32147e355c5fb09e2e7e8` 增加 Var 状态写入次数断言，捕获“同文字的失败回调重复设置 UI”而不修改原有安全断言。[增强测试 CI #41223121982](https://github.com/chigre/Picture_Capture/actions/runs/41223121982) 独立记录，不将运行中作业视为通过。
- **最小修复** `405df1384e78a9658d3f1759e2a38ea0fd7abd8b` 仅 `ui/focused_filter_workflow.py`：首批一次性 `first_terminal_claimed`，每个分段派发独立 `remaining_terminal_claimed`；只有当前 scan epoch 且处于活跃筛选模式时认领首个 `done` 或 `failed`，认领先于 Tk 修改与启动下一批，旧回调绝不重复追加、清除或重派。既有隐私状态屏蔽、来源校验、安全写入逻辑保持不变。
- 架构审计 [G3_R4_2_STREAMING_SCAN_TERMINAL_20261101.md](../architecture/G3_R4_2_STREAMING_SCAN_TERMINAL_20261101.md)。**最终代码＋文档 HEAD** CI 六组合＋Risk gate、OCR3/3、CodeQL2/2 仍待核，提交文件内暂记 **PENDING**。Windows R3 E3、#483 W1–W11、#503 人工 Undo、真实词典/性能 **NOT PERFORMED**；R6 真标签学习及 R8 真实扫描 **DEFERRED**。仅 Draft/Open/Unmerged #663，main 不动。

## 2026-10-31｜G3 R4.2 prefetch 同 epoch 相同 key 重派后的旧终结回调隔离（测试先红，最终门禁待核）

- 上轮绿色基线 `8894d4cc4b781d811b429a051006d41d90ec46f9` 已重新核实：[CI #41216783408](https://github.com/chigre/Picture_Capture/actions/runs/41216783408) 六组合＋Risk-tier gate、[OCR #41216783393](https://github.com/chigre/Picture_Capture/actions/runs/41216783393) 三平台、[CodeQL #41216780401](https://github.com/chigre/Picture_Capture/actions/runs/41216780401) Python/Actions 全部 SUCCESS；main 不变，唯一 Draft PR #663 与 #503/#562/#483 Open。
- **真实失败先行**：测试单独提交 `e2c6b5c1c01c134557909c0f8ad2033c2d457bc0`，[CI #41218910472](https://github.com/chigre/Picture_Capture/actions/runs/41218910472) macOS Python 3.13 实际 **4 targeted FAILED / 5208 passed / 2 skipped**：旧 prefetch 第一次 done 或 failed 后，新一轮同 epoch 同源 key 被重派时，旧任务迟到的 done / failed 仍能覆盖新任务 key 或旧缓存。四种先后组合均红灯。
- **最小产品修复** `24d682ff4ffdd58f54b4e68762dee3017a819466` 仅改 `ui/focused_filter_workflow.py::_schedule_filter_next_batch_preload`：每次派发独立内存 `terminal_claimed`；核实原 scan epoch 及当前 key 后，首个有效 done/failed 认领终结，重复终结不能作用于同 key 重新派发的新任务。保留原图/PDIC/SECTION 字节 witness、人工编辑与保存防护和失败后仅一次直接渲染恢复。
- 架构审计：[G3_R4_2_PREFETCH_IDENTICAL_KEY_TERMINAL_20261031.md](../architecture/G3_R4_2_PREFETCH_IDENTICAL_KEY_TERMINAL_20261031.md)。产品＋文档最终 SHA 的 CI 六平台、Risk-tier、OCR 3/3、CodeQL 2/2 仍 **PENDING**；不得沿用旧 SHA。Windows R3 E3、#483 W1–W11、#503 人工 Undo、真实词典及性能 **NOT PERFORMED**；R6 真标签与 R8 真实扫描 **DEFERRED**。

## 2026-10-31｜G3 R4.2 直接渲染重复/矛盾终结回调单次所有权（测试先红，最终 HEAD 待验）

- 实时基准 `493877bead3e392d5e2b5bcdacffcc8ec2b97697` 已核：CI [#41213416632](https://github.com/chigre/Picture_Capture/actions/runs/41213416632) 六 OS/Python 组合＋Risk-tier gate SUCCESS；OCR [#41213416558](https://github.com/chigre/Picture_Capture/actions/runs/41213416558) 3/3、CodeQL [#41213413372](https://github.com/chigre/Picture_Capture/actions/runs/41213413372) Python/Actions 2/2 SUCCESS。main `ec20989e`、唯一 Draft #663，Issues #503/#562/#483 Open。
- **实际红灯：** 仅新增 6 项合成参数化反例 `0c7473e821e117a92b32c62c47509a89ad72d493`，[CI #41216502798](https://github.com/chigre/Picture_Capture/actions/runs/41216502798) macOS Python3.13 **6 targeted FAILED / 5202 passed / 2 skipped**。证实同一次直接裁剪的 done→failed、failed→done、重复 done/failed 会第二次改动缓存/编辑视图；此前因人工修改而忽略的终结事件在修改消失后仍可被重复回调重新激活。红灯 SHA 不计绿色门禁。
- **最小修复** `6c7088560334765f3fbc70d40d93edc32ea6a294` 仅在 `ui/focused_filter_workflow.py::_request_filter_batch_render` 回调闭包内增一次性 terminal claim：先核已有 serial、epoch、激活批次，再领用首个终结事件（包括因人工编辑/正在保存而不绘制的终结事件）；后续重复或矛盾回调严格无动作。保留此前来源哈希、安全写入以及未保存人工作业保护，不改变 PDIC/PPP/SECTION/Profile schema 和原图 XY。
- 审计 [G3_R4_2_DIRECT_RENDER_TERMINAL_ONCE_20261031.md](../architecture/G3_R4_2_DIRECT_RENDER_TERMINAL_ONCE_20261031.md)。最终代码+文档 HEAD 必须**另查** CI 6/6＋Risk、OCR 3/3、CodeQL Python/Actions 2/2；本次提交前尚为 **PENDING**。Windows R3 E3、#483 W1–W11、#503 人工 Undo、真实词典扫描及性能均 **NOT PERFORMED**；R6 真标签学习、R8 真实扫描 **DEFERRED**。唯一 Draft #663 保持 Open/Unmerged；main 不动。

## 2026-10-31｜G3 R4.2 直接裁剪 success/failure 回调的来源、SECTION 与 save 队列隔离（测试先红，最终门禁待核）

- 实时绿色基准 `6376d1a058bb634b8f09e18955cb80a9f4a67339` 已核：CI [#41212007134](https://github.com/chigre/Picture_Capture/actions/runs/41212007134) Windows/macOS/Ubuntu×Python3.10/3.13 六组合＋Risk gate 全成功；OCR [#41212007119](https://github.com/chigre/Picture_Capture/actions/runs/41212007119) 三平台成功；CodeQL [#41212004168](https://github.com/chigre/Picture_Capture/actions/runs/41212004168) Python/Actions 两项成功。唯一 Draft #663、main 不动、#503/#562/#483 Open。
- **真实测试先红**：仅加 synthetic test `13f4abbbb54f787ca0357ebde161f443ae105dda`，[CI #41213043690](https://github.com/chigre/Picture_Capture/actions/runs/41213043690) Ubuntu Python3.13 **9 targeted FAILED / 5192 passed / 3 skipped**。三类原图/PDIC/SECTION 同大小同 mtime 漂移可入旧 cache；直接裁剪 worker 过程来源漂移未拒绝；后到 done/failed 和缓存命中会覆盖未完成的编辑/保存。稳定来源和过期 serial 正控通过；本旧 SHA 是 RED，不计通过。
- 生产最小修复 `cc1d2d44289eb6b81f9f80adfaa2081567c5d40a` 仅 `ui/focused_filter_workflow.py`：direct worker 返回前复核 source witness；成功回调先验证 scan epoch、render serial、选中批次、当前图像/PDIC/SECTION 字节及无正在保存/未保存编辑，再允许缓存与重绘；失败回调不可清除被人工或保存占用的工作区；缓存命中路径同样尊重这些保护。无持久化变更、原图 XY 或实验默认值修改。
- 审计 [G3_R4_2_DIRECT_RENDER_SOURCE_SAVE_GUARDS_20261031.md](../architecture/G3_R4_2_DIRECT_RENDER_SOURCE_SAVE_GUARDS_20261031.md)。**本次代码及文档最终 HEAD** 必须另核 exact-head CI 六组合＋Risk、OCR 3/3、CodeQL Python/Actions 2/2，不能凭本说明或旧 SHA 推定成功。真实 Windows R3 E3、#483 W1–W11、#503 人工 Undo、真实词典/性能均 **NOT PERFORMED**；R6 真标签/R8 真实扫描 **DEFERRED**。

## 2026-10-31｜G3 success prefetch 中间测试夹具诊断补记（最终 docs HEAD 待验）

- 源修复 `7637eedb` [CI #41211513690](https://github.com/chigre/Picture_Capture/actions/runs/41211513690) Ubuntu Python3.13 **5 failed / 5185 passed / 3 skipped**：3 项是新测试应先取得 worker 成功载荷再模拟磁盘漂移，已由 `cd01446d` 校正；另 2 项是旧 epoch-smoke 假 key 没有真实 witness，已由 `a5a25dc5` 换成原有 source-witness API。未改产品检查，未跳过断言。最新代码+文档 HEAD 6/6 CI＋Risk、OCR3/3、CodeQL Python/Actions2/2 均须重新核实。真人 E3/W1–W11/人工 Undo/真实词典 **NOT PERFORMED**，R6/R8 **DEFERRED**。

## 2026-10-31｜G3 R4.2 成功 prefetch 的来源复核、跨 epoch/key 所有权与人工修改保护（red-first，最终 E2 待核）

- 绿色基准为 `8ce6d807914cef24456862a3492806a5bb3e38a1`：CI [#41205116868](https://github.com/chigre/Picture_Capture/actions/runs/41205116868) 6/6 + Risk-tier、OCR [#41205116875](https://github.com/chigre/Picture_Capture/actions/runs/41205116875) 3/3、CodeQL [#41205112460](https://github.com/chigre/Picture_Capture/actions/runs/41205112460) Python/Actions 2/2 成功，唯一 Draft #663。
- **红灯确实复现：** 仅新增合成测试提交 `e45c92e44b3ab2ad4e3714455096b59a807c10ae`，[CI #41211306832](https://github.com/chigre/Picture_Capture/actions/runs/41211306832) macOS Python3.13 **6 targeted FAILED / 5185 passed / 2 skipped**。涵盖同大小恢复 mtime 原图/PDIC/SECTION 修改后旧成功结果缓存、旧 key 回调覆盖新所有权、未保存人工编辑被重画、worker 读取过程变源没有被检测。该测试 SHA 不算绿色。
- 最小产品修复 `7637eedb7bc2eb5db8048a1ea690dc5d67bfa190` 只修改 `ui/focused_filter_workflow.py`：worker 裁剪后复核原图/PDIC/SECTION 的确切字节 witness，Tk success 在相同 scan epoch、活动 prefetch key 和当前批次完整 snapshot 匹配时才发布 cache；可见漂移清除等待占位并提示重新筛选；人工未保存编辑或保存任务存在时不覆盖展示。异常不泄露私有信息，非 OS CAS。
- 测试时序更正 `cd01446db23801a2f04e9e9397134089562dc65a` 明确 worker 先完成、随后发生磁盘漂移、最后才递送 Tk done；修正夹具模拟路径，没有跳过断言。详见 [G3_R4_2_SUCCESSFUL_PREFETCH_SOURCE_ATTESTATION_20261031.md](../architecture/G3_R4_2_SUCCESSFUL_PREFETCH_SOURCE_ATTESTATION_20261031.md)。
- **最终代码与文档 HEAD** 必须单独核验 CI 6/6＋Risk、OCR 3/3、CodeQL Python/Actions 2/2。Windows R3 E3、#483 W1–W11、#503 人工 Undo、真实词典与性能均 **NOT PERFORMED**，R6 真标签与 R8 真扫描 **DEFERRED**。保持 main 不变、#663 Draft/Open/Unmerged、不 Ready/merge/关闭 Issues。

## 2026-10-31｜G3 可见 prefetch 失败修复后的合成夹具补充（最终门禁待验）

- 产品修复初始 HEAD `5532774c42b5a0b23603b5da88ae9aca842f2adc` [CI #41204886134](https://github.com/chigre/Picture_Capture/actions/runs/41204886134) Ubuntu3.13 **1 failed / 5183 passed / 3 skipped**；唯一失败是新测试合成 ReviewWindow 缺少原有 `_cache_filter_batch_payload`，真实 direct-render done 回调因此 AttributeError，属于测试夹具遗漏，不是已经证明的生产源码故障。
- 本次仅在新测试文件增加指向真实 `workflow._cache_filter_batch_payload` 的 fixture 方法，仍核验失败 prefetch → 单次回退直接裁剪 → 成功确认/来源锁定。无产品代码改动，无跳过失败测试。最终 HEAD CI 6/6＋Risk、OCR 3/3、CodeQL 2/2 仍 **PENDING**。
- 详见 [G3_R4_2_VISIBLE_PREFETCH_FAILURE_RECOVERY_20261031.md](../architecture/G3_R4_2_VISIBLE_PREFETCH_FAILURE_RECOVERY_20261031.md)。真人 Windows R3 E3、#483 W1–W11、#503 人工 Undo、真扫描均 NOT PERFORMED；R6/R8 DEFERRED。唯一 #663 保持 Draft/Open/Unmerged、main 未变化。

## 2026-10-31｜G3 R4.2 N+1 裁剪 prefetch 失败后的可见批次保守恢复（red-first，最终 E2 待核）

- 上一严格绿色基线 `c9837923b0bcf5184ac16098688a4688600c68b6`：[CI #41197464856](https://github.com/chigre/Picture_Capture/actions/runs/41197464856) 六组合 6/6＋Risk-tier；[OCR #41197464869](https://github.com/chigre/Picture_Capture/actions/runs/41197464869) 3/3；[CodeQL #41197460973](https://github.com/chigre/Picture_Capture/actions/runs/41197460973) Python/Actions 2/2 通过。唯一 Draft #663；main 不变。
- 测试先行 `1166cd5e18c3bc13e67417b23ea8e3ca15db9491` 在 [CI #41204531136](https://github.com/chigre/Picture_Capture/actions/runs/41204531136) macOS Python3.13 **5 targeted FAILED / 5180 passed / 2 skipped**：切换到等待中的 N+1 后 prefetch 失败，旧代码清空 key 却不进行直接裁剪恢复；原图/PDIC/SECTION 同大小同 mtime 字节变更后未作明确重筛提示。红灯不算通过门禁。
- 最小产品修复限定 `ui/focused_filter_workflow.py` prefetch failed 回调：严格比对 scan epoch 与本次 prefetch key；无人工未保存编辑/后台写入、当前仍选中该批次时再核验原图+PDIC+SECTION 精确字节，未变才单次调度已有 direct render；变化/拒读则脱敏提示重新筛选并清除等待占位，不擅自读取新来源当成旧批次；重复或晚到回调不污染状态。修复 synthetic PDIC 的换行夹具，提高保真度。
- 审计 [G3_R4_2_VISIBLE_PREFETCH_FAILURE_RECOVERY_20261031.md](../architecture/G3_R4_2_VISIBLE_PREFETCH_FAILURE_RECOVERY_20261031.md)。**本次最终代码与文档 HEAD CI 6/6+Risk、OCR3/3、CodeQL Python/Actions2/2 尚需独立核实。** Windows R3 E3、#483 W1–W11、#503 人工 Undo、真词典与性能 NOT PERFORMED；R6 真标签/R8 真扫描 DEFERRED。#663 Draft/Open/Unmerged，不合并、不 Ready、不关闭 issues。

## 2026-10-31｜R3/#503 候选删除 Undo/Redo 已提交后的 Tk 状态刷新异常（红灯已实测，最终 HEAD 仍待验）

- 上一基线 `683b06bed6fe0750ec94f6b4f65f2b89adda075a` 的 Windows/macOS/Ubuntu × Python3.10/3.13 CI **6/6 + Risk-tier gate 成功**，OCR **3/3**、CodeQL Python/Actions **2/2** 成功；仅合成 E2。
- 新增测试提交 `8f528a4f4c991682833e85dda84840be5951f5ab`，在 [CI #41197223626](https://github.com/chigre/Picture_Capture/actions/runs/41197223626) Ubuntu Python3.13 **8 failed / 5168 passed / 3 skipped**、macOS Python3.13 **8 failed / 5169 passed / 2 skipped**；测试覆盖候选 Undo/Redo × 词条计数/页面行刷新 × RuntimeError/TclError。提交后 Tk 异常原可让已经写盘的重放帧未移动并暴露异常。红灯提交不等于验收。
- 产品最小修复：`proofreading/candidate_history.py` 在权威 PDIC/manual/simplified bundle 与 Entry/candidate 确认后先完成 history stack 转移，再对派生页面状态/原生 Tk 回调做提交后异常隔离；原有源检查、原图 XY、持久化事务和默认设置不动。审计见 [R3_G1_CANDIDATE_POSTCOMMIT_TK_REFRESH_20261031.md](../architecture/R3_G1_CANDIDATE_POSTCOMMIT_TK_REFRESH_20261031.md)。
- **最终代码/文档 HEAD 必须另核 exact-head CI 6/6＋Risk-tier、OCR 3/3、CodeQL Python/Actions 2/2。** 真人 Windows R3 E3、#483 W1–W11、#503 全复合 Undo/Redo、G3 真实扫描及性能均 NOT PERFORMED；R6 真标签、R8 真扫描 DEFERRED。唯一 #663 保持 Draft/Open/Unmerged，main 不动。

## 2026-10-31｜R3/#503 复合回放 Tk 行所有权 + 来源路径锁定 + 销毁控件 fail-closed（46 个自动化合成场景；最终 HEAD E2 待核）

- **基准已验收** `e7a721bf83fdd85c274cdd824e78a2505877259a`：[CI #41194141243](https://github.com/chigre/Picture_Capture/actions/runs/41194141243) Windows/macOS/Ubuntu × Python3.10/3.13 六组合 6/6＋Risk-tier CI gate、[OCR #41194141209](https://github.com/chigre/Picture_Capture/actions/runs/41194141209) 3/3、[CodeQL #41194138864](https://github.com/chigre/Picture_Capture/actions/runs/41194138864) 2/2。唯一 Draft #663，main `ec20989e` 未变。
- **真实红灯：** `f1338c181e3590aa7c780b6cea22f153ca4fd693` [CI #41195919532](https://github.com/chigre/Picture_Capture/actions/runs/41195919532) Ubuntu Python3.13 22 failed / 5128 passed / 3 skipped；扩充测试 `094b885fb34ecc6a1c46dec160bc9d5cb2a241da` [CI #41196070214](https://github.com/chigre/Picture_Capture/actions/runs/41196070214) Ubuntu Python3.13 30 failed / 5130 passed / 3 skipped。错误集中在复合 Undo/Redo 恢复/删除 Entry 后，用新行列表按位置修改旧 `StringVar`；持久化成功后 Tk setter 抛异常；Tk 临时无快照时只核旧路径字节，未核现用人工覆盖/OCR/SECTION/Profile **路径**；已销毁 Tk reader 的异常冒出校对按钮。红灯 SHA 绝不是通过证据。
- **产品修复：** `db16a6ee78eb0a7f12cff89f8baa5783bf80d3a2`、`ee90b3ed1e904a12ff9220d98c985a9d7cb5fb7a` 分别修复普通和 OCR 候选历史：`_live_source_bindings_match` 新增活动路径锁定；提交前冻结 `tuple(bound Entries)` + `tuple(StringVars)`，提交后只用旧 Entry 对应的旧变量，不按新行号猜测；销毁 Tk var.set 为已提交数据的展示层失败，不重复提交、不中断历史栈迁移。只读 `snapshot_review` 的原生 `RuntimeError/TclError` 通过 `1bdb41868e6f2d3ec6749c05e5f81e4681ed3999` 统一 fail-closed，绝不暴露私人异常内容。
- **测试：** `tests/test_r3_mixed_replay_membership_and_path_binding_20261031.py` 新增 46 个合成参数化场景：普通/候选 Undo/Redo、旧 Tk StringVar 归属、持久化后 UI setter 异常、4 来源路径重绑定、快照未就绪但来源未变允许重试、precommit get/row reader 故障、OCR 删除/普通编辑两序混合 Undo×2/Redo×2、真正 `snapshot_review` 原生 Tk reader RuntimeError/TclError。老测试 `test_two_saved_edits_replay_without_row_index_matching` 由安全旧控件断言 + 等显式重绘后多步 Undo/Redo 取代危险的隐式按新索引对齐，并非放弃多步撤销。旧合成来源固定夹具补明确的 path resolver。
- 详细审计 [R3_COMPOUND_REPLAY_TK_BINDING_AND_PROVENANCE_20261031.md](../architecture/R3_COMPOUND_REPLAY_TK_BINDING_AND_PROVENANCE_20261031.md)。只改变内存回放所有权、Tk 安全展示与只读来源诊断；不碰 PDIC/manual/SECTION/Profile/OCR 格式、图片原始数据、磁盘提交事务、永久 Undo。**本最终 docs HEAD 仍需另外证明 CI6/6＋Risk、OCR3/3、CodeQL2/2**，所有旧红灯保留。真人 Windows E3、#483 W1–W11、完整 #503 同时脏编辑、真词典/大图、R6/R8 仍 NOT PERFORMED/DEFERRED；唯一 Draft #663 不 Ready、不合并、不开新 PR、不关闭 Issue。

## 2026-10-31｜R3/#503 普通保存 Undo 历史的完整来源连续性（测试优先 5 个红灯已证，最终 E2 待核）

- 承接最终已验收 `e12ce5908a2c40a60a5fc6a1914160e42e0d8c94`：[CI #41192253305](https://github.com/chigre/Picture_Capture/actions/runs/41192253305) Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 + Risk-tier CI gate 通过**，[OCR #41192253252](https://github.com/chigre/Picture_Capture/actions/runs/41192253252) **3/3**，[CodeQL #41192249986](https://github.com/chigre/Picture_Capture/actions/runs/41192249986) **Python/Actions 2/2**；单 Draft PR #663，main 保持 `ec20989e`。
- 普通 `ReviewSessionHistory.record` 在新保存之前仅比较前次保存与本次保存的部分字节和 owner_id，漏掉 `page` 与 `manual_path/ocr_path/section_path/profile_path`。不同来源的文件即便字节碰巧相同，也不应把旧 Undo frame 继续串到本次合法保存上；此前候选删除历史已使用完整 `_same_live_state`。
- **真实红灯：** 测试先行 `95b91b183fe416c5cf287593c49d3853484dc179` [CI #41193829573](https://github.com/chigre/Picture_Capture/actions/runs/41193829573)：Ubuntu Python3.13 **5 failed / 5114 passed / 3 skipped**，macOS Python3.13 **5 failed / 5115 passed / 2 skipped**，五项失败均为旧 Undo frame 跨不同页面或来源路径未清除；同源连续多级历史正控通过。
- 最小修复 `259f5f15a3b57948ed1c7d1c6659b90ed868cd41`：普通 record 与候选历史共用 `_same_live_state(previous.after, before)`，来源路径、对象 ID、快照数据不一致时只丢弃旧历史，但仍记录新的独立合法保存。测试 `318641056c69a5370bf03bdf68cd33ed560722e2` 追加真实 `write_pdic` / `snapshot_review` 下人工覆盖路径、OCR 路径、Profile 项目根路径更换 3 项集成场景。详情见 [R3_G1_PLAIN_RECORD_CHAIN_COMPLETE_OWNER_20261031.md](../architecture/R3_G1_PLAIN_RECORD_CHAIN_COMPLETE_OWNER_20261031.md)。
- 只改内存 Undo 历史连续性，未修改磁盘事务/缓存写入、Entry XY、OCR/PDIC/SECTION/Profile 格式或门禁。**最终 docs HEAD 需独立证明 6/6 CI＋Risk、3/3 OCR、CodeQL Python/Actions 2/2**；真人 Windows E3、#483 W1–W11、#503 全复合事务、真实扫描及大图、R6/R8 均 NOT PERFORMED/DEFERRED；保留唯一 Draft #663，不 Ready、不 merge。

## 2026-10-31｜R3/#503 普通文字 Undo/Redo 全来源失效防护（测试优先红灯已证，E2 最终 HEAD 待核）

- **承接已验收 HEAD `2f303379fae26906ac2674ff152139bc97dbb499`**：[CI #41191029305](https://github.com/chigre/Picture_Capture/actions/runs/41191029305) 六 OS/Python 组合 6/6＋Risk-tier gate、[OCR #41191029324](https://github.com/chigre/Picture_Capture/actions/runs/41191029324) 3/3、[CodeQL #41191026786](https://github.com/chigre/Picture_Capture/actions/runs/41191026786) Python/Actions 2/2；实际源码与 ReviewWindow native Tk G3 合成 E2 均成功。唯一 #663 Draft/Open/Unmerged，main `ec20989e` 未变。
- **真实红灯：** 仅新增合成测试 `dc306c3613b342eccadf02c1adcc342ac6dc1b03`，[CI #41192052020](https://github.com/chigre/Picture_Capture/actions/runs/41192052020) Ubuntu Python3.13 **24 failed / 5087 passed / 3 skipped**，全部是普通 `ReviewSessionHistory` 在 Tk 快照暂失效时没有核对人工覆盖、OCR、SECTION、Profile 的修改/删除/拒读，导致旧 Undo/Redo 历史未作废；2 个来源完全不变的重试正控通过。绝不把测试先红 SHA 算作通过门禁。
- **最小代码修复 `20fb3dffd2b63cdd9de39f5633617f37146766ac`：** 只在 `snapshot_review=None` 的保守诊断补四类 sidecar 的精确字节复核，OSError/ValueError/TypeError 统一拒绝＋失效历史，绝不回滚或覆盖第三方改动，保留来源未变时显式重试。无实际 PDIC writer、XY、人工覆盖和 OCR 格式变更。
- 合成测试新增 26 个参数化场景；完整审计见 [R3_G1_PLAIN_HISTORY_FULL_PROVENANCE_20261031.md](../architecture/R3_G1_PLAIN_HISTORY_FULL_PROVENANCE_20261031.md)。本轮最终文档 HEAD 必须另查 CI Windows/macOS/Ubuntu × Python3.10/3.13 **6/6＋Risk gate**、OCR **3/3**、CodeQL **2/2**。真人 Windows E3、#483 W1–W11、#503 完整复合撤销、G3 真词典及大图、R6 人工标签、R8 真扫描依旧 NOT PERFORMED/DEFERRED；不 Ready、不合并、不关闭 issue。

## 2026-10-31｜G3/R3 native Tk 稳定物理读回验证：旧 macOS 失败保留，五次事件循环所有者一致性（E2 最终 HEAD 待验）

- 同步回调修复 `3ed584a5` 的源 CI [#41190137992](https://github.com/chigre/Picture_Capture/actions/runs/41190137992) 六组合 6/6 全通过。测试优先 `140d981d` 的 Ubuntu/macOS Python3.13 均有 **6 项真实目标失败**，证实未确认的 inline done/failed 能提前关闭／重复错误弹窗；后续产品回调确认屏障保留全部人工更正。
- 原生 Tk 扩展提交 `9408c31d` [CI #41190240419](https://github.com/chigre/Picture_Capture/actions/runs/41190240419) **attempt 1 macOS Python3.13 G3 最后多文件一致性断言失败**（pytest 5086 passed，2 skipped；其他 Tk smoke 通过），明确不得把该失败当成功。相同 SHA 该失败作业独立重跑 **attempt 2 成功**，证明间歇性；不认为这等同于真实人工 E3。逐项诊断 `149ea7bc` [CI #41190551568](https://github.com/chigre/Picture_Capture/actions/runs/41190551568) 六 OS/Python CI 6/6＋Risk、OCR3/3、CodeQL2/2 成功，没有任何数据所有权放宽。
- 纯测试等待修正 `1e89f4c15364eba071cf7bf9d5b76bc513714d50`：原 G3 native Tk 关闭后不再只等待窗口销毁，而是连续五次 Tk 事件循环确认实际 PDIC 全八字段/原始 XY、主 Entry、PPP、SECTION、settings、原图及 OCR 来源均满足原有等式，防止后台 UI 异步完成与测试采样竞态；永久不一致仍超时失败，不能以主窗口 `status_var` 文本替代权威状态。审计见 [G3_R4_2_SYNCHRONOUS_WORKER_CALLBACK_HANDOFF_20261031.md](../architecture/G3_R4_2_SYNCHRONOUS_WORKER_CALLBACK_HANDOFF_20261031.md)。
- **本最终文档 HEAD 仍需核实 exact SHA 六组合 CI 6/6＋Risk、OCR3/3、CodeQL Python/Actions2/2；旧绿灯不可替代最新 HEAD。** main `ec20989e` 保持不变，唯一 Draft #663 Open/Unmerged、0 unresolved reviews（需再核）。真人 Windows R3 E3、#483 W1–W11、#503 复合 Undo/Redo、真实词典扫描性能、R6 人工标签与 R8 真实扫描仍未做／延后；不 Ready、不合并、不关闭 issue。

## 2026-10-31｜G3/R3 调度器同步回调先于确认返回：单次结果所有权（合成 E2 最终 HEAD 待核）

- 基准 `1f6d85dd90ad3d9712033efdc7f3516a955bb2d1` 上已实际验证 [CI #41188843977](https://github.com/chigre/Picture_Capture/actions/runs/41188843977) 六组合 6/6 + Risk-tier CI gate、[OCR #41188843994](https://github.com/chigre/Picture_Capture/actions/runs/41188843994) 3/3、[CodeQL #41188841943](https://github.com/chigre/Picture_Capture/actions/runs/41188841943) Python/Actions 2/2，全绿；main `ec20989e` 不动，唯一 Draft PR #663。
- **新红灯已实际复现：** `140d981d48e227ca2a5ccd3a6c7d9bc31bf951ac` 的 [CI #41190094623](https://github.com/chigre/Picture_Capture/actions/runs/41190094623) Ubuntu Python3.13 **6 failed / 5079 passed / 3 skipped**，macOS Python3.13 **6 failed / 5080 passed / 2 skipped**。调度器在返回前先调用 done/failed，随后抛错时，旧逻辑可能提前消费成功结果并关闭窗口，或重复弹窗；同一已确认调度的矛盾终结回调也会重复处理。成功接受 inline 空结果的正控通过。红灯测试 SHA 不是通过的门禁。
- 修复 `3ed584a5d3c8dea7f938008f005ce4dc2e94248a` 在 `focused_filter_workflow._flush_focused_changes` 设置本地 pending/accepted/rejected 回调确认屏障：调度器未正常返回之前不消费任何终结回调；异常时保留人工修改/清除关闭意图/单一通用错误；正常返回后仅消费第一条终结回调。原有跨代递增 dispatch serial 保持不变。
- 合成原生 Tk 集成 `9408c31d620b97f561274b31be85db0397ae761e` 对真实 ReviewWindow StringVar 测试“inline done→raise”和“inline failed→raise”两种拒绝、精确待保存 XY、PDIC 字节不动与后续人工明确重试真正保存。审计 [G3_R4_2_SYNCHRONOUS_WORKER_CALLBACK_HANDOFF_20261031.md](../architecture/G3_R4_2_SYNCHRONOUS_WORKER_CALLBACK_HANDOFF_20261031.md)。
- **最后文档 HEAD 全部六 OS/Python CI＋Risk、OCR3、CodeQL2 必须再核验**，不得用中间源码 SHA 取代。真人 Windows R3 E3、#483 W1–W11、#503 复杂事务、G3 真实词典扫描/大图、R6 人工标签、R8 真实扫描均 NOT PERFORMED/DEFERRED；继续 #663 Draft、未合并，不 Ready，不降低失败门禁。

## 2026-10-31｜R3/G1 OCR 候选删除 Undo/Redo 来源不可读与 SECTION/Profile 漂移安全拒绝（最终 E2 待核）

- 承接上一轮最终 `19ffa6a955f74016aba2fef2502567974ec42a1c`： [CI #41187745842](https://github.com/chigre/Picture_Capture/actions/runs/41187745842) 六组合 6/6 + Risk-tier gate、[OCR #41187745851](https://github.com/chigre/Picture_Capture/actions/runs/41187745851) 3/3、[CodeQL #41187743372](https://github.com/chigre/Picture_Capture/actions/runs/41187743372) Python/Actions 2/2 **完整验收成功**。唯一 Draft PR #663 未合并、main 保持 `ec20989ea`。
- 本轮仅聚焦 OCR candidate-owned deletion 的 R3 Undo/Redo：与普通 Undo 不同，原 `CandidateReviewHistory._apply` 在 Tk 临时快照为 None 时来源诊断直接 `sha256_file/_bytes_or_absent`，缺少权限/磁盘异常处理，且漏检 SECTION 和 Profile 漂移。先测 `b7a0b669` 添加 20 个合成参数化案例（7 类来源不可读×Undo/Redo、SECTION/Profile 漂移×Undo/Redo、2 个未变来源的重试正控）；最小源修复 `cc0f101a` 异常安全拒绝＋校验 SECTION/Profile，不改变 PDIC/人工覆盖/撤销事务与历史格式。
- 详细审计 [R3_G1_CANDIDATE_REPLAY_SOURCE_DIAGNOSTIC_20261031.md](../architecture/R3_G1_CANDIDATE_REPLAY_SOURCE_DIAGNOSTIC_20261031.md)。测试优先 [CI #41188708454](https://github.com/chigre/Picture_Capture/actions/runs/41188708454) 及源修复 [CI #41188770945](https://github.com/chigre/Picture_Capture/actions/runs/41188770945) 在记录时执行中；**须按最终文档 HEAD 重新核对 6/6 CI＋Risk、3/3 OCR、CodeQL2/2，不把 pending 当 pass**。
- 人工 Windows E3、#483 W1–W11、#503 全套复合 Undo/Redo、真实词典 G3、R6 人工标签与 R8 真扫描均 NOT PERFORMED/DEFERRED；继续 Draft/Open/Unmerged，不 Ready、不 merge、不关闭 issue。

## 2026-10-31｜G3/R3 大批量：筛选保存调度失败、多页人工修改恢复与旧回调隔离（最终 E2 待核）

- 本批次直接承接已验证 `37bc755e2d9d04515b89a49c4f4abbee2aad265e`：[CI #41186645728](https://github.com/chigre/Picture_Capture/actions/runs/41186645728) 六组合 6/6＋Risk-tier gate、[OCR #41186645762](https://github.com/chigre/Picture_Capture/actions/runs/41186645762) 3/3、[CodeQL #41186643481](https://github.com/chigre/Picture_Capture/actions/runs/41186643481) Python/Actions 2/2 全成功；主分支 `ec20989e` 未变化、唯一 Draft #663。
- **实测红灯**：仅加测试的 `d928e65c` 在 [CI #41187323339](https://github.com/chigre/Picture_Capture/actions/runs/41187323339) Ubuntu Python3.13 **8 failed / 5046 passed / 3 skipped**，macOS Python3.13 **8 failed / 5047 passed / 2 skipped**。包含调度器异常外逸/隐私泄露、单页与多页人工作业丢失、较新编辑与主动撤回、页面读取失败已清队列、缺乏真实 worker 却遗留关闭意图。**这条旧测试 SHA 的失败不可归为绿色**。
- 同一主题源修复：`8e965bec` 在清空待保存修改前构造来源页面快照，异常调度时恢复未确认的人工修改、脱敏并停止自动关闭/重试；`50551093` 明确区分运行中、未开始和调度失败，不把未开始说成正在保存；`9f746b98` 加内存 dispatch serial，拒绝更早的不确定任务在新任务成功接管后通过迟到 done/failed 更改 Tk/队列/close 状态。
- 扩展测试：`81803283` 覆盖迟到回调与人工重试，`cc4177e4` 覆盖旧 done/failed 在新任务启动后的跨代污染；`44607281` 真实 Tk 控件＋临时合成项目，覆盖同步拒绝 → 保留编辑/PDIC 原字节 → 人工明确重试并验真后关闭。审计 [G3_R4_2_DISPATCH_FAILURE_RECOVERY_20261031.md](../architecture/G3_R4_2_DISPATCH_FAILURE_RECOVERY_20261031.md)。
- **最终文档 HEAD 的 6/6 CI＋Risk、OCR 3/3、CodeQL Python/Actions 2/2 尚须按最终 SHA 分别检查**。不把非最终 SHA 的结果冒充验收。仍是合成 E2，不等于真人 Windows E3、#483 W1–W11、#503 Undo/Redo、真实扫描/G3 大图性能、R6 人工标签或 R8 真实扫描；全部保持 NOT PERFORMED/DEFERRED。唯一 #663 继续 Draft/Open/Unmerged；不 Ready、不自动合并、不关闭 issue。

## 2026-10-31｜R3/G3 筛选校对关闭时同步触发保存异常，安全拒绝（E2 exact-head 待核）

- 此前最终 `f1d436be` 已**实际核实**：CI [#41185135896](https://github.com/chigre/Picture_Capture/actions/runs/41185135896) Windows/macOS/Ubuntu × Python3.10/3.13 **6/6**、Risk-tier gate SUCCESS，OCR [#41185135720](https://github.com/chigre/Picture_Capture/actions/runs/41185135720) **3/3**，CodeQL [#41185132099](https://github.com/chigre/Picture_Capture/actions/runs/41185132099) Python/Actions **2/2**。独立 Documentation architecture 作业 SKIPPED，不计成功。
- 新发现同步边界：普通 ReviewWindow 关闭已经捕获脱敏异常，但筛选模式 `_flush_focused_changes_now()` 的同步异常原本可从 Tk 关闭回调传播。新增先测 `f6626b6b`（两种旧 close intent），保护用户未保存文本、窗口继续开启、禁止私有路径/词条异常泄露；生产最小修复 `8761355f` 捕获异常、清除旧自动关闭意图、只显示通用失败状态和弹窗。**不清空待提交人工作业，也不假设后台提交已成功或可回滚。**
- 审计 `docs/architecture/G3_R4_2_SYNC_CLOSE_TRIGGER_FAIL_CLOSED_20261031.md`；红灯 [CI #41186527418](https://github.com/chigre/Picture_Capture/actions/runs/41186527418) 在撰写时进行中，需先实际核对而非声称已红。**本轮文档 HEAD 仍需核验 exact-head CI 6/6+Risk、OCR3/3、CodeQL2/2**，再可称自动化 E2 完成。
- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged，`main@ec20989e` 不动；真人 Windows R3 E3、#483 W1–W11、#503 复杂 Undo/Redo、G3 真扫描和大图性能均 NOT PERFORMED。R6 人工真值和 R8 实扫均 DEFERRED，不 Ready / merge。

## 2026-10-31｜R3/G3 native Tk 完整异步等待条件硬化（旧 macOS 失败保留，待 exact HEAD 核验）

- 生产关闭失败脱敏及未确认写入后取消旧 close intent：`fa2ec8377b9c118f7bb1a32d5aedc354dc8889b3` [CI #41183802964](https://github.com/chigre/Picture_Capture/actions/runs/41183802964) **6/6+Risk 已通过**；红灯 `7881848c` Ubuntu 4 targeted failed/5039 passed 是有效旧实现缺陷证明。
- 原生 Tk 合成关闭集成的旧源 `40524a44` [CI #41183879358](https://github.com/chigre/Picture_Capture/actions/runs/41183879358)、初次等待修正 `60187066` [CI #41184236154](https://github.com/chigre/Picture_Capture/actions/runs/41184236154)、docs `3082cc56` [CI #41184611929](https://github.com/chigre/Picture_Capture/actions/runs/41184611929) **macOS 均曾失败**：分别是新 SECTION 拒绝结束、新未确认写入结束、旧 SECTION 恢复后保存重试；三个 await 均误用会被主应用自动保存覆盖的全局 `app.status_var` 文本。均如实留档，不能当成全绿。
- `60187066`、`06b5e631` 已分别修正新关闭链路两个等待条件，`06b5e631` [CI #41184539224](https://github.com/chigre/Picture_Capture/actions/runs/41184539224) macOS **5044 passed/2 skipped** 且 native close OK。最新测试修正 `5b89b2ad` 将**此前遗留**的旧 SECTION 拒绝/正向保存两个等待改为 error callback+精确原始 XY 待保存内容、或 PDIC 物理字节变化+目标词条对齐；不降低写入保护。紧接 `1b632af3` 新增 AST 回归，禁止 G3 native Tk 的任何 `_pump_until` 依赖 `status_var`。
- 新源码 [CI #41185041953](https://github.com/chigre/Picture_Capture/actions/runs/41185041953)、[OCR #41185041949](https://github.com/chigre/Picture_Capture/actions/runs/41185041949)、[CodeQL #41185039598](https://github.com/chigre/Picture_Capture/actions/runs/41185039598) 在文档编写时待完成；本 docs 更新 HEAD **仍需另核六平台CI+Risk、OCR3、CodeQL2**。完整审计：[G3_R4_2_REVIEW_CLOSE_FAIL_CLOSED_20261031.md](../architecture/G3_R4_2_REVIEW_CLOSE_FAIL_CLOSED_20261031.md)。
- 唯一 Draft #663 Open/Unmerged，`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 不动，真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 真扫描与大图性能 NOT PERFORMED，R6/R8 真证据 DEFERRED。

## 2026-10-31｜R3/G3 关闭窗口 E2 跨平台 test oracle 修正（待最终 HEAD 核验）

- 已通过有效红灯证明 `7881848c` 的普通关闭异常文本泄露（3 种模拟私有信息）和无确认提交后过期 close intent（1 项），Ubuntu [CI #41183577244](https://github.com/chigre/Picture_Capture/actions/runs/41183577244) 4 targeted failed、5039 pass；最小生产修复 `fa2ec837` [CI #41183802964](https://github.com/chigre/Picture_Capture/actions/runs/41183802964) **6/6 + Risk-tier gate SUCCESS**。
- 后续原生 Tk 合成 close smoke 源 `40524a44` 的 [CI #41183879358](https://github.com/chigre/Picture_Capture/actions/runs/41183879358) **macOS 失败**，因测试把全局 `app.status_var` 瞬时“保存失败”用作 await 条件；主应用自动保存可将状态覆写为“已自动保存”。`60187066` 修正后 [CI #41184236154](https://github.com/chigre/Picture_Capture/actions/runs/41184236154) 又暴露**此前一段**等待“尚有未确认修改”文本的同类测试时序问题。两次失败须明确记录为 test oracle 不稳，不能算生产代码已通过／也不能证明它存在新故障。
- 最新纯测试修正 `06b5e631c124cd8afbcdaf26a5d62f438bb779fb`：两处完成等待条件均只检查真实后台 worker、`_filter_close_after_save`、精确待保存词条、错误回调和 live Tk 窗口；不撤销来源指纹、PDIC、关闭窗口门禁。源 [CI #41184539224](https://github.com/chigre/Picture_Capture/actions/runs/41184539224)、[OCR #41184539255](https://github.com/chigre/Picture_Capture/actions/runs/41184539255)、[CodeQL #41184536750](https://github.com/chigre/Picture_Capture/actions/runs/41184536750) 当时进行中。审计见 [G3_R4_2_REVIEW_CLOSE_FAIL_CLOSED_20261031.md](../architecture/G3_R4_2_REVIEW_CLOSE_FAIL_CLOSED_20261031.md)。
- 本 docs 会更新 HEAD，**必须重新核验 exact-head 六平台+Risk/OCR3/CodeQL2**。唯一 Draft #663 Open/Unmerged，`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 不动；真人 R3 E3/#483/#503 和真实词典性能 NOT PERFORMED，R6/R8 真证据延期。

## 2026-10-31｜R3/G3 校对关闭失败脱敏＋恢复未确认修改时取消自动关闭意图（E2 待 docs 最终 HEAD 核验）

- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) 仍 Open/Unmerged；`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未动。上一批多页成功保存／预检后 SECTION 漂移最终 `e1399dc1dd19ee540cdf5bbd208dfc2641f869af` [CI #41182460290](https://github.com/chigre/Picture_Capture/actions/runs/41182460290) **6/6 + Risk SUCCESS**、[OCR #41182460325](https://github.com/chigre/Picture_Capture/actions/runs/41182460325) **3/3**、[CodeQL #41182457382](https://github.com/chigre/Picture_Capture/actions/runs/41182457382) **2/2** 全部通过。
- 本次**真实红灯证明**：test-only `7881848c093bb1512b26bdc75c35d7490f1f541d` 的 [CI #41183577244](https://github.com/chigre/Picture_Capture/actions/runs/41183577244) Ubuntu Python3.13 **4 failed / 5039 passed / 3 skipped**；三个旧逻辑直接将模拟私有 Windows/Unix 路径和词条异常输出 Tk 状态/弹窗，另一个在后台“无确认提交→恢复未写修改”后遗留 `_filter_close_after_save=True`。均为目标断言，不是模拟夹具错误。
- 最小生产修复 `fa2ec8377b9c118f7bb1a32d5aedc354dc8889b3`：`review_close_actions` 捕获保存错误时只用**脱敏通用提示**，保持窗口打开；`focused_filter_workflow.done` 遇到 `recovered` 或 `conflicts` 均取消旧 close intent，恢复修改则提示`尚有未确认修改`。物理 PDIC/R3 事务/源指纹/八字段保持不变。
- 原生 Tk 合成测试 `40524a44d40fc217c5bfaa3dbddff642e7978521` 增真实 `_close_review()` 四路径：非筛选错误脱敏、后台无提交时窗口保持打开、保存中 SECTION 漂移后拒绝关闭/保留输入、原 SECTION 恢复后**真正保存 PDIC 才关闭**。源码 [CI #41183879358](https://github.com/chigre/Picture_Capture/actions/runs/41183879358) Ubuntu 5043 passed/3 skipped 且新 Tk close smoke OK，macOS/Windows 当时待完成；[OCR #41183879407](https://github.com/chigre/Picture_Capture/actions/runs/41183879407) 3/3、[CodeQL #41183876658](https://github.com/chigre/Picture_Capture/actions/runs/41183876658) 2/2 成功。详细审计：[G3_R4_2_REVIEW_CLOSE_FAIL_CLOSED_20261031.md](../architecture/G3_R4_2_REVIEW_CLOSE_FAIL_CLOSED_20261031.md)。
- 本 docs 还会更新 HEAD：必须重新核实**最终 HEAD 6/6 CI + Risk/OCR3/CodeQL2 + review threads**，不得借旧源 HEAD 绿灯。真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 真词典/大图性能仍 NOT PERFORMED；R6 人工标签、R8 真扫描 DEFERRED；不 Ready、不 merge、不关 issue。

## 2026-10-31｜G3 R4.2 多页成功保存＋预检后 SECTION 漂移的两组补测（合成 E2，待 docs 最终 HEAD 核验）

- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged、`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。上轮两页冲突／后续异常的最终 `cb640e2ed4ea09c5cfa5ca7c3d0254cd3f4a2d7a` [CI #41178796433](https://github.com/chigre/Picture_Capture/actions/runs/41178796433) **6/6+Risk**、[OCR #41178796384](https://github.com/chigre/Picture_Capture/actions/runs/41178796384) **3/3**、[CodeQL #41178793955](https://github.com/chigre/Picture_Capture/actions/runs/41178793955) **2/2** 全成功，仍是合成 E2。
- **预检后来源竞态**：`690d9047e541a9edb1ee3008eba5ebf7a01673ca` 四个组合（SECTION 在第一页写入后变更；或第二页 PDIC 发布后、来源复核前变更；各有／无第二页更新人工词条），均要失败保留两页未确认修改，保护较新输入、不回滚已发布 PDIC、不泄露私有异常；不等同跨页原子提交。[CI #41181859352](https://github.com/chigre/Picture_Capture/actions/runs/41181859352) **6/6+Risk SUCCESS**、[OCR #41181859280](https://github.com/chigre/Picture_Capture/actions/runs/41181859280) **3/3**、[CodeQL #41181856998](https://github.com/chigre/Picture_Capture/actions/runs/41181856998) **2/2**。
- **两页正常提交路径**：`1de457539d85f17564fe0dbee1668e39819cc3eb` 增两测：同时成功保存两页、验证 8 字段/原始 XY/主界面同步；第一轮完成前第二页又收到更新时，第二轮只写第二页，第一页 PDIC 字节不再改变。[CI #41182028698](https://github.com/chigre/Picture_Capture/actions/runs/41182028698) **6/6+Risk SUCCESS**、[OCR #41182028695](https://github.com/chigre/Picture_Capture/actions/runs/41182028695) **3/3**、[CodeQL #41182025709](https://github.com/chigre/Picture_Capture/actions/runs/41182025709) **2/2**。
- **夹具修正**：`7fddc8628c90e1809bccd8f7e04fe4f2b34041a3` 将第二页真实 stem 改为 `002`，使第一页 `001#@#002`、第二页 `002#001#@` 的元数据断言具可区分性；其 [CI #41182362350](https://github.com/chigre/Picture_Capture/actions/runs/41182362350) 等当时待完成。本 docs 仍会刷新 HEAD；必须重新核 exact-head 6/6 CI+Risk、OCR3/3、CodeQL2/2。审计：[G3_R4_2_MULTI_PAGE_CONFLICT_E2_20261031.md](../architecture/G3_R4_2_MULTI_PAGE_CONFLICT_E2_20261031.md)。上述全部 **test-only**，不更改生产保存逻辑。
- 真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 真实扫描保存／大图性能仍 **NOT PERFORMED**，R6 人工标签、R8 真实扫描 **DEFERRED**；不 Ready、不 merge、不关 issue。

## 2026-10-31｜G3 R4.2 多页 PDIC 冲突部分提交与写入中断后的不确定状态（E2 待最终 HEAD 核验）

- 唯一 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged，`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。上一批原生 Tk 并发撤回最终 HEAD `4ca7401012e4cbf747a2bf277c2f738517f31a88` [CI #41177650887](https://github.com/chigre/Picture_Capture/actions/runs/41177650887) 6/6 + Risk gate、[OCR #41177650896](https://github.com/chigre/Picture_Capture/actions/runs/41177650896) 3/3、[CodeQL #41177648830](https://github.com/chigre/Picture_Capture/actions/runs/41177648830) 2/2 全部成功；仍是合成 E2，非真人 E3。
- 纯测试提交 `f643404029a5428c2928781d56d430a8afd42a46` 新增两页 synthetic BMP/PDIC/SECTION 的两项真实 worker/done/failed 回调覆盖：① 两页原图/SECTION 指纹均有效，但第二页 PDIC 原词被外部改变：第一页恰好只发布一次、第二页保留 pending 且不覆盖外部原词；再次明确重试也不重新写第一页；② 第一页已发布、第二页发生受控 `OSError`：必须报告失败并保留**两页**待检查人工修改，不回滚可能已成功的第一页或泄露私有路径。只加强测试，不更改生产写入器/规则。
- 源 [CI #41178622263](https://github.com/chigre/Picture_Capture/actions/runs/41178622263)、[OCR #41178622249](https://github.com/chigre/Picture_Capture/actions/runs/41178622249)、[CodeQL #41178619392](https://github.com/chigre/Picture_Capture/actions/runs/41178619392) 在文档编写时运行中；本 docs 提交将更新 HEAD，**需重新核验最终 exact-head 六平台 CI + Risk/OCR/CodeQL**。专项审计：[G3_R4_2_MULTI_PAGE_CONFLICT_E2_20261031.md](../architecture/G3_R4_2_MULTI_PAGE_CONFLICT_E2_20261031.md)。
- 真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 真实扫描与原图性能均 NOT PERFORMED；R6 人工标签、R8 真实扫描 DEFERRED；保持 Draft、不 merge、不关 issues。

## 2026-10-31｜G3 R4.2 真实 Tk 输入框＋受控后台保存中的撤回测试（合成 E2 待最终 HEAD 核验）

- 继续唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)，`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未动。上一组异步撤回来源指纹修复最终 `ea66f9009815d322d7d29dced90dafc9596e4ce8` [CI #41177039367](https://github.com/chigre/Picture_Capture/actions/runs/41177039367) **6/6+Risk SUCCESS**、[OCR #41177039325](https://github.com/chigre/Picture_Capture/actions/runs/41177039325) **3/3 SUCCESS**、[CodeQL #41177036541](https://github.com/chigre/Picture_Capture/actions/runs/41177036541) **2/2 SUCCESS**（纯合成 E2）。
- 测试-only `1c45f308f29064161ea8d850af10825ff43d07ca` 在已成功的 G3 native Tk GUI smoke 中增加第二条**真实 Tk→后台 worker**链：第一笔 PDIC worker 在测试专用 Event 门控暂缓物理写入，前台 StringVar 撤回到原词，释放后验证后台实际连续进行了两笔写入；最终磁盘 PDIC 字节恢复初始状态，主界面词条与原始 X/Y、原图/PPP/SECTION/设置均不变。门控 30s 超时并有 `finally` 释放；不生成真实词典标签、不改生产任何代码。
- 源 [CI #41177444432](https://github.com/chigre/Picture_Capture/actions/runs/41177444432) macOS Python3.13 `5027 passed/2 skipped` 且新 native Tk in-flight reversion 实际输出 OK；其他 OS 和 Python3.10 当时待执行；[OCR #41177444434](https://github.com/chigre/Picture_Capture/actions/runs/41177444434) 3/3 SUCCESS；[CodeQL #41177440534](https://github.com/chigre/Picture_Capture/actions/runs/41177440534) 当时待终核。手册：[G3_R4_2_INFLIGHT_REVERSION_SOURCE_20261031.md](../architecture/G3_R4_2_INFLIGHT_REVERSION_SOURCE_20261031.md)。**docs HEAD 必须另核 exact-head CI/Risk/OCR/CodeQL**，不可将源 HEAD 绿灯转用于文档。
- 真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 实页/真实 TIFF 大图性能 **NOT PERFORMED**；R6 人工标签、R8 真实扫描 **DEFERRED**。不 Ready、不合并、不关 issue、不碰 main。

## 2026-10-31｜G3 R4.2 后台保存过程中撤回词条：来源指纹与二次保存归属（E2 待最终 HEAD 核验）

- 唯一 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged；`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未动。上轮「原生 Tk 拒绝→来源恢复→成功重试」最终 `65cdbb6a37f4416018fa90d3efe7af442edc2fcb` [CI #41175831057](https://github.com/chigre/Picture_Capture/actions/runs/41175831057) **6/6+Risk**、[OCR #41175831062](https://github.com/chigre/Picture_Capture/actions/runs/41175831062) **3/3**、[CodeQL #41175827419](https://github.com/chigre/Picture_Capture/actions/runs/41175827419) **2/2** 通过，仅合成 E2。
- 代码审查发现：旧异步 worker 保存 `edit-1` 时，用户把输入框撤回 `old`，成功回调会合成新待保存 `edit-1→old`，但未把**已显示裁剪的原图/SECTION SHA 指纹**带到新队列，下一次保存可能 fail-closed 卡住有效撤回。最小生产补丁 `a6c791ffc3c5e565dd5330865c76e42d8d6046b8` 仅在 `focused_filter_workflow.done` 的回撤补队列分支继承可用的原显示指纹；不在保存时凭磁盘创建证明，缺指纹仍拒绝，不改物理 PDIC writer/R3/OCR/格式。
- 新三组**合成** worker/callback 测试分别检验撤回后自动重写原词、SECTION 同大小同 mtime 改变时二次拒写且保留待保存修改、并发较新 `edit-2` 不被旧成功回调覆盖。需要严谨说明：test-only `4dd5b75ae20c5f0e40dc19bc54d5c3aa69a9b307` [CI #41176545296](https://github.com/chigre/Picture_Capture/actions/runs/41176545296) 的三次红灯均因**模拟 ReviewWindow 缺少回调**，并非有效 test-first 生产故障复现；`a99eeae5fff80872db47378ede438e7cbf0c9024` 和 `737a6f4dbee6b5d5ac7c98de3460e06bc679f060` 先后补齐真实保存回调绑定。源码 [CI #41176916072](https://github.com/chigre/Picture_Capture/actions/runs/41176916072) 当时进行中，不能把 red/green 结果提前标记成功。
- 审计：[G3_R4_2_INFLIGHT_REVERSION_SOURCE_20261031.md](../architecture/G3_R4_2_INFLIGHT_REVERSION_SOURCE_20261031.md)。**最终 docs HEAD 还需 exact-head 六平台+Risk/OCR/CodeQL 与 reviews 核验**。真人 Windows R3 E3/#483 W1–W11/#503 Undo、G3 真实词典及大图性能仍 **NOT PERFORMED**；R6 真标签、R8 真扫描延期。不 Ready、不 merge、不关闭 issue、不碰 main。

## 2026-10-31｜G3 R4.2 原生 Tk 先拒绝陈旧 SECTION、来源恢复后自动保存重试（E2 待最终 HEAD 核验）

- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) 保持 Open/Unmerged，`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 不动。前轮真实 Tk 合成负例最终 HEAD `a38815ea0146435b411dbf722c3bee5fcfeedd71` [CI #41173017802](https://github.com/chigre/Picture_Capture/actions/runs/41173017802) 6/6+Risk、[OCR #41173017850](https://github.com/chigre/Picture_Capture/actions/runs/41173017850) 3/3、[CodeQL #41173015058](https://github.com/chigre/Picture_Capture/actions/runs/41173015058) 2/2，全部成功但仅合成 E2。
- 新 source/test-only `7ae5443788aed84faa65868ef05db23e996536f3` 在 `scripts/gui_g3_focused_controls_smoke.py` 现有 native Tk 链路中追加正例：先通过真实 StringVar、显示来源快照、SECTION 外部漂移触发拒写，随后**恢复同一来源并由同一输入框重新输入**，等待 160ms 后台保存完成；对保存后 PDIC 两行**8 字段**逐字段核验，仅第一行词条改变，全部原始 X/Y、百分比、相邻页字段及第二行保持不变；主页面 Entry 与 Tk 输入同步；原图、PPP、设置、SECTION 均不改；不生成过期 OCR 证明，不改任何生产 writer/OCR/事务。
- 源 [CI #41175589069](https://github.com/chigre/Picture_Capture/actions/runs/41175589069) Ubuntu Python3.13 全量 `5023 passed / 3 skipped` 且 native Tk 输出 `refusal + successful retry: OK`；其余平台当时进行中。[OCR #41175589039](https://github.com/chigre/Picture_Capture/actions/runs/41175589039) **3/3 SUCCESS**、[CodeQL #41175586266](https://github.com/chigre/Picture_Capture/actions/runs/41175586266) **2/2 SUCCESS**。本 docs commit 还会刷新 HEAD：**必须核验最终 HEAD 六平台+Risk/OCR/CodeQL 才能声明 E2 完成**。审计：[G3_R4_2_NATIVE_TK_SAVE_SOURCE_E2_20261031.md](../architecture/G3_R4_2_NATIVE_TK_SAVE_SOURCE_E2_20261031.md)。
- Windows 真人 R3 E3、#483 W1–W11、#503 Undo/Redo、G3 真实词典保存重开/裁剪与 X/Y 目测、真实大图性能 **NOT PERFORMED**；R6 人工标签、R8 实际扫描 **DEFERRED**。不合并、不 Ready、不关闭 issue、不上传私有数据。

## 2026-10-31 | G3 R4.2 原生 Tk 合成 SECTION 漂移自动保存拒绝（E2 待最终 HEAD 核验）

- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged；`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。前轮只读性能探针最终 `a232c03a8796679cccc1a663b8647e60172bad21` [CI #41171508870](https://github.com/chigre/Picture_Capture/actions/runs/41171508870) **6/6 + Risk-tier SUCCESS**、[OCR #41171508849](https://github.com/chigre/Picture_Capture/actions/runs/41171508849) **3/3 SUCCESS**、[CodeQL #41171505801](https://github.com/chigre/Picture_Capture/actions/runs/41171505801) **2/2 SUCCESS**，仅 E2。
- 确认现有 G3 native Tk smoke 仅测选项与无效筛选，没有真正经过「已接受裁剪指纹→Tk 编辑→自动保存失败」的完整 GUI 路径。测试-only `931ac2284feb1727c1dad6081d1de9141b0363d3` 延伸 `scripts/gui_g3_focused_controls_smoke.py`：使用真实 `ReviewWindow` 渲染的原图 X/Y + `StringVar` 输入，随即**向临时合成项目新增 SECTION**，真实 160ms autosave 与 worker 应拒绝覆盖 PDIC、保留编辑/队列、原词/主界面 Entry 不变并取消关窗。最后恢复合成 SECTION；不需要真实词典、不触及任何生产写入代码。
- 首版 [CI #41172738534](https://github.com/chigre/Picture_Capture/actions/runs/41172738534) Ubuntu Python3.13 的全 pytest **5023 passed / 3 skipped**，且真实 native Tk G3 smoke `OK`。`c033cbeb1987e96abc1d3b0f779c343314d4819d` 进一步用 `getattr` 安全等候尚未创建的 Tk 变量（纯测试时序修正）。
- 此文档提交前，校正源码 [CI #41172814679](https://github.com/chigre/Picture_Capture/actions/runs/41172814679) 仍执行中；[OCR #41172814667](https://github.com/chigre/Picture_Capture/actions/runs/41172814667) 3/3 SUCCESS；[CodeQL #41172812918](https://github.com/chigre/Picture_Capture/actions/runs/41172812918) 当时执行中。**文档改 HEAD 后仍需 exact-head CI/Risk/OCR/CodeQL 全绿**。审计：[G3_R4_2_NATIVE_TK_SAVE_SOURCE_E2_20261031.md](../architecture/G3_R4_2_NATIVE_TK_SAVE_SOURCE_E2_20261031.md)。
- 真人 Windows R3 E3、#483 W1–W11、#503 复杂 Undo/Redo、G3 真实大页及真实词典 PDIC/PPP/SECTION/Profile 保存重开、性能测量均 **NOT PERFORMED**；R6 真人人工标签、R8 真实扫描 **DEFERRED**。不 Ready、不合并、不关闭 issues、不向 GitHub 上传私有文件。

## 2026-10-31 | G3 R4.2 Windows 原图/SECTION 来源指纹只读性能探针（E2 待最终 HEAD 核验）

- 唯一 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) 继续 Open/Unmerged，main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未改变。此前保存来源修复的最终 `b9493de123c6d1e7ae583df13215edd86c88cdaf` [CI #41170601208](https://github.com/chigre/Picture_Capture/actions/runs/41170601208) 六平台 **6/6+Risk-tier SUCCESS**、[OCR #41170601202](https://github.com/chigre/Picture_Capture/actions/runs/41170601202) **3/3 SUCCESS**、[CodeQL #41170598178](https://github.com/chigre/Picture_Capture/actions/runs/41170598178) **2/2 SUCCESS**，均仅合成 E2，不是人工 E3。
- 本包补足**可测而非臆测**的大图来源校验 I/O：test-only `a2c89e692cd199731174862cabd117c627a8dc01` 在 [red CI #41171166506](https://github.com/chigre/Picture_Capture/actions/runs/41171166506) Ubuntu Python3.13 **5 failed/5018 passed/3 skipped**（因工具不存在，**不是原生产代码出错**）；`d3dc69799adfd9ca50434c6f31287e25c6248275` 创建 `scripts/benchmark_g3_focused_source_guard.py`，复用真实 SHA-256 crop/image+PDIC+SECTION 与 save/image+SECTION 来源函数。读真实项目时只有只读 I/O，输出只有固定 numeric JSON（median/p95/max、MiB、SECTION 是否存在、源稳定及人检未执行），禁止打印项目路径/词条/SHA/异常；合成模式仅在 OS 临时目录建立伪图伪 PDIC/SECTION。测试增强 `9b60261f2c7e85daf67355034f56472c98adbb22` 强制校验预期错误提示，排除不存在脚本导致的假阳性拒绝。
- [源码 CI #41171197847](https://github.com/chigre/Picture_Capture/actions/runs/41171197847) Ubuntu Python3.13 **5023 passed/3 skipped**，macOS Python3.13 成功，其他当时仍执行中；[OCR #41171197791](https://github.com/chigre/Picture_Capture/actions/runs/41171197791) 3/3 成功。**文档最终 HEAD 需独立核验完整 CI/Risk/OCR/CodeQL；不可把 pending 算 pass。** 手册：[G3_R4_2_WINDOWS_SOURCE_PERF_RUNBOOK_20261031.md](../architecture/G3_R4_2_WINDOWS_SOURCE_PERF_RUNBOOK_20261031.md)，原 G3 操作步骤新增 17/18。
- **真实 Windows 授权词典副本上的性能、GUI 响应和人工 E3 均 NOT PERFORMED**，不存在可报告的真实大图耗时或速度优势。#483 W1–W11、#503 复杂 Undo/Redo、R3 E3 仍待真人；R6 人工标签、R8 真实扫描 DEFERRED。不 Ready、不合并、不关闭 issues、不向公共 GitHub 上传任何真实内容。

## 2026-10-31｜G3 R4.2 人工校对保存时的原图/SECTION 来源归属（test-first E2 待最终核验）

- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged；`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 不变。前轮裁剪来源保护的最终 `5a0fca316497508442a19b71ac8cbe1dbd04a459` [CI #41168544144](https://github.com/chigre/Picture_Capture/actions/runs/41168544144) 六平台 **6/6 SUCCESS + Risk-tier**、[OCR #41168544148](https://github.com/chigre/Picture_Capture/actions/runs/41168544148) **3/3 SUCCESS**、[CodeQL #41168541671](https://github.com/chigre/Picture_Capture/actions/runs/41168541671) Actions/Python **2/2 SUCCESS**，仅自动化 E2。
- 新 [Red-first CI #41170243020](https://github.com/chigre/Picture_Capture/actions/runs/41170243020)：测试-only `ee78e188667ee5967c99c4c479faa5f07e095898`；Ubuntu Python3.13 **9 expected failures/5005 pass/3 skip**、macOS Python3.10 **9 expected failures/5006 pass/2 skip**。确认已有裁剪可显示，但人工改字后原图/SECTION 改变时 PDIC 仍可能保存；原图同尺寸且原 mtime 恢复也能复现；缺来源不能 fail-closed；PDIC 读取后来源漂移无写前阻断。红灯是预期缺陷复现，不是通过门禁。
- 生产 `1c6ec22930ab64fef94023b05cf57abddcddfacb`：在已校验的裁剪行绑定**原图+活动 SECTION**字节指纹（PDIC 不作为编辑时指纹，因正常写入会更新 PDIC）；改字排队携带该来源；后台保存所有页面先验来源，再由 PDIC 物理写入器在读取后、发布前和发布后复检。真实 filter 缺失/不一致来源拒绝写入，保留人工修改/较新同坐标修改；原有 R3/PDIC 原词/XY/8字段校验不削弱。
- `5c0829f9d652f7f8072cc7bbc45e57ff8f43e8e6` 补充**第二页陈旧时第一页零写入**及**SECTION 原缺失→新增**两个合成负例。审计：[G3_R4_2_FOCUSED_SAVE_SOURCE_20261031.md](../architecture/G3_R4_2_FOCUSED_SAVE_SOURCE_20261031.md)。全部输入为合成 8×8 BMP + PDIC/SECTION，非真实词典。
- **门禁截至本次文档编写**：更新后源 [CI #41170460022](https://github.com/chigre/Picture_Capture/actions/runs/41170460022) 仍进行中；[OCR #41170460039](https://github.com/chigre/Picture_Capture/actions/runs/41170460039) 三平台 3/3 SUCCESS；[PR/CodeQL #41170456823](https://github.com/chigre/Picture_Capture/actions/runs/41170456823) 仍进行中。**本 docs commit 产生新 HEAD，全部必需 exact-head 门禁需另行核验，绝不把 pending 说成 passed。**
- 边界：按页面验证仅是文件字节快照乐观约束，不是跨页 OS 原子事务、无障碍全面安全保证；原图多次 SHA 读取增加 I/O，尚未真实大页性能测试。下一项是非破坏性的 Windows G3 操作验收准备/性能观察，不应再制造人工标签或扩大持久化格式。
- 真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 真实词典 GUI/PDIC/PPP/SECTION/Profile 验收仍全部 **NOT PERFORMED**；R6 人工标签、R8 真实扫描 **DEFERRED**。不 Ready、不合并、不关闭 issues、不触及 main。

## 2026-10-31｜G3 R4.2 异步裁剪缓存的原图/PDIC/SECTION 内容漂移（test-first E2 待核）

- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged；`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 不变。上个 checkpoint `659dcb90156c67701a71bc562f513b95b0c93d16` 的 [CI #41167212998](https://github.com/chigre/Picture_Capture/actions/runs/41167212998) 6/6 + Risk-tier、[OCR #41167213013](https://github.com/chigre/Picture_Capture/actions/runs/41167213013) 3/3、[CodeQL #41167207899](https://github.com/chigre/Picture_Capture/actions/runs/41167207899) Actions/Python 2/2 全部 SUCCESS，仅自动化 E2。
- 真实 red-first 测试修正版 `0426f197e8890a648a3ae15565b4deb048487fc0` 的 [CI #41168242309](https://github.com/chigre/Picture_Capture/actions/runs/41168242309) Ubuntu Python3.13 **7 failed/4997 passed/3 skipped**、macOS Python3.13 **7 failed/4998 passed/2 skipped**。源图同尺寸并恢复 mtime、PDIC/SECTION 变化或 SECTION 删除后，原 crop cache key 不变、过期预取被 `_apply` 接受；无变动时正例通过。测试只用极小合成 BMP/sidecar，无私有扫描。
- 生产 `7ac6fb024fb3fbb804a1da96acd40d1840cf13fe`（新增 `proofreading/focused_crop_source_fingerprint.py`）+ `746ddef47298e18c608e54e231d967a8fea88e3f`（`ui/focused_filter_workflow.py`）：按当前批次逐页 SHA-256 读取原图、PDIC、当前 SECTION 及路径/缺席状态，纳入内存裁剪缓存键；回调和缓存渲染时重新比较，来源变化不显示旧裁剪、不改人工编辑和持久化。不可读来源按 fail-closed 提示。独立审计：[G3_R4_2_CROP_SOURCE_DRIFT_20261031.md](../architecture/G3_R4_2_CROP_SOURCE_DRIFT_20261031.md)。
- **准确门禁状态**：源 [CI #41168312629](https://github.com/chigre/Picture_Capture/actions/runs/41168312629) 六平台当时仍运行，Risk-tier SUCCESS；[OCR #41168312628](https://github.com/chigre/Picture_Capture/actions/runs/41168312628) 三 OS 3/3 SUCCESS；[CodeQL #41168309968](https://github.com/chigre/Picture_Capture/actions/runs/41168309968) Python/Actions 2/2 SUCCESS。**文档提交产生新 HEAD，全部门禁必须重新核验；不把 pending 写成 success。**
- 当前代码只防**裁剪预览**复用，不冒充跨文件 OS 原子性，也未证明更晚的源图/SECTION 变化下 PDIC 保存拥有可信快照。下一唯一相关包：保存快照源归属+时间窗口故障注入，保留 R3 writer/人工编辑。图像哈希新增同步 I/O，未做真实大图延迟基准。
- 真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 操作及真实词典 GUI/PDIC/PPP/SECTION/Profile 全部 **NOT PERFORMED**；R6 人工标签、R8 真实扫描 **DEFERRED**。保持 #663 Draft/Open/Unmerged，不合并、不开 Ready、不关闭 issue、不碰 main。

## 2026-10-31｜G3 R4.2 异步校对保存失败：屏蔽异常中的私有路径（test-first / E2 待核）

- GitHub 实时基线 `main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未变，仅 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged；上一 exact HEAD `455c07eed7dde06916952a0bf30cba7bfb8f6e5c` 的 [CI #41165453150](https://github.com/chigre/Picture_Capture/actions/runs/41165453150) 六平台 6/6、Risk-tier， [OCR #41165453132](https://github.com/chigre/Picture_Capture/actions/runs/41165453132) 三 OS 3/3、[CodeQL #41165449850](https://github.com/chigre/Picture_Capture/actions/runs/41165449850) Python/Actions 2/2 全部成功；独立文档 job SKIPPED，不算成功。
- 新增真实 test-first `070bf0b6a84b2e1d7587d58aed09827b6bfd6e5f`，源 [CI #41166900396](https://github.com/chigre/Picture_Capture/actions/runs/41166900396) Ubuntu 3.13/macOS 3.13 **各 2 个预期失败**，日志明确显示 `_flush_focused_changes.failed` 向 Tk status、错误弹窗和 stdout 泄漏原始异常/traceback 哨兵；新测试前面的未保存编辑恢复、后到人工编辑归属、synthetic PDIC 字节不变断言均通过。
- 最小生产修复 `066fc62da163526dc5bd7ba4f4e3a8f49517f622` 禁止在保存失败回调显示异常字符串和 traceback，仅显示泛化重试提示；不改原 R3 事务、PDIC 读写或 pending 编辑恢复逻辑。测试：`tests/test_g3_r4_focused_save_failure_redaction_20261031.py`；审计：[G3_R4_2_FOCUSED_SAVE_FAILURE_20261031.md](../architecture/G3_R4_2_FOCUSED_SAVE_FAILURE_20261031.md)。
- **当前 E2 仍待最终 exact-head 核验**：源 [CI #41166937906](https://github.com/chigre/Picture_Capture/actions/runs/41166937906) 六平台执行中、Risk-tier 成功；源 [OCR #41166937853](https://github.com/chigre/Picture_Capture/actions/runs/41166937853) 3/3 SUCCESS；独立 [CodeQL #41166933385](https://github.com/chigre/Picture_Capture/actions/runs/41166933385) Actions SUCCESS、Python 尚在运行。此文档提交也会改变 HEAD，需重新检查全部最终 SHA 的门禁；不把旧 SHA 绿灯迁移到最新 SHA。
- **人工 NOT PERFORMED**：Windows R3 E3、#483 W1–W11、#503 复杂 Undo、G3 R4.2 Windows 操作以及实际词典页 GUI/PDIC/PPP/SECTION/Profile；R6 人工标签、R8 真实扫描继续延期。保持唯一 #663 Draft/Open/Unmerged，main 不动，不关闭 Issues、不自动合并或 Ready。

## 2026-10-31｜G3 R4.2 首批扫描/裁剪错误回调 epoch 与路径脱敏（源修复，最终门禁待核）

- 实时核对：仅有 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged，main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。上一轮 `e75747ecda54b0ee896b0a2e79d480908f56c4da` 的 [CI #41161659038](https://github.com/chigre/Picture_Capture/actions/runs/41161659038) 六平台 6/6 SUCCESS、[OCR #41161659989](https://github.com/chigre/Picture_Capture/actions/runs/41161659989) 三 OS 3/3 SUCCESS、[CodeQL #41161655346](https://github.com/chigre/Picture_Capture/actions/runs/41161655346) Python/Actions 2/2 SUCCESS、Risk-tier SUCCESS。Documentation architecture check SKIPPED，未记作通过。
- 反例先行 `85188655c43c7239471e9cc933934447c35732d8` 的 [CI #41165165064](https://github.com/chigre/Picture_Capture/actions/runs/41165165064) 在 Ubuntu 3.13 和 macOS 3.13 **各有 4 个真实失败**：首批 worker 失败误标已完成、模式退出后回调改写界面、旧 crop render 失败污染新 epoch、裁剪报错回显异常来源路径。其余该两平台用例分别 4,989/4,990 通过；这份红灯不是门禁成功。
- 生产修复 `901ad2ec2f96d6397eb39db73ffe0ce02b5a5b2d` 仅收紧 `ui/focused_filter_workflow.py` 当前 scan/render epoch + 活跃模式失败回调，首批失败保持 incomplete/failed、泛化显示信息；预取失败不输出异常路径并允许后续重试。后续扫描失败的显式批次提示继续保留，避免旧测试适配器 override 指示器时失去状态。新旧回调均不写入 PDIC/PPP/SECTION。
- 源修复固定 SHA 的 CI [#41165270089](https://github.com/chigre/Picture_Capture/actions/runs/41165270089) 在本次文档编辑时仍处于运行过程；最终本提交也必须单独检查 exact-head 六平台、OCR 三 OS、Risk-tier、CodeQL Python/Actions，不能复用上一 HEAD 成功结论。
- 审计：[G3_R4_2_INITIAL_CROP_FAILURE_20261031.md](../architecture/G3_R4_2_INITIAL_CROP_FAILURE_20261031.md)。**NOT PERFORMED / DEFERRED**：Windows R3 E3、#483 W1–W11、#503 人工 Undo、R4.2 真人操作、真实词典扫描、R6 人工标签和 R8 真实扫描；自动 E2 不是人工 E3。继续保持 #663 Draft/Open/Unmerged、main 不动、不关闭 Issues。
- 下一恢复：先核最终 HEAD exact CI 与 CodeQL，如失败检查测试/工作区回调路径并最小修正；若绿，继续 SECTION/裁剪预取在源文件改写和保存后的一致性合成负例，不引入新的持久化 schema 或真实数据。

## 2026-10-31｜G3 R4.2 后续页面异步扫描失败：明确中断、保留已就绪批次

- 实时起点：PR #663 Draft/Open/Unmerged `f2422e271d1d33dd3913942b4504633f47990477`；六平台 CI #41120989838 SUCCESS 6/6，OCR #41120989687 SUCCESS 3/3，Risk-tier 成功，独立 CodeQL #41120978327 Actions/Python 2/2 SUCCESS；架构文档 job SKIPPED（不计通过）。main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。
- 真实失败先行提交 `6182785af8bcaf0bf27c4cf700819c9d3e2556ee`，CI https://github.com/chigre/Picture_Capture/actions/runs/41161338739：Ubuntu 3.13 1 failed / 4988 passed / 3 skipped；macOS 3.10 1 failed / 4989 passed / 2 skipped。问题是后续 worker error 只设 status 字符串，没有终止态标志或批次指示，界面可能仍误显示后台扫描中；另一个旧 epoch 回调隔离测试通过。
- 最小修复：`ui/focused_filter_workflow.py` 仅增加**内存态** `_filter_scan_failed`，每次新扫描重置；在当前 epoch + 活跃模式的后续 worker 失败时标记**中断/未完成**，保留已显示词条与编辑；禁止将未扫描页视为完成，明确提示用户重筛，旧回调不能污染新 epoch。失败文案不回显包含私有路径的异常字符串。完整批次可继续处理，partial 尾部仍隐藏。
- 测试：`tests/test_g3_r4_streaming_scan_failure_20261031.py` 两个纯合成用例：部分扫描失败的显式终态/原批保留，以及跨 epoch 旧失败拒绝。本提交 CI/OCR/Risk-tier/CodeQL 的 exact-head 结论**待实时核实**；失败先行的 CI 红灯不当成生产通过。
- 审计：不改变源图 XY、PDIC/PPP/SECTION/manual_selection/OCR 缓存、Profile、原子写入和持久化 schema；不增加自动数据采集或 R6/R8 实验。Windows R3 E3、#483 W1–W11、#503 真人 Undo、R4.2 真人操作、真实词典扫描均 **NOT PERFORMED / DEFERRED**；自动 E2 不能代替。
- 恢复：确认本次修复最终 PR HEAD 的六平台 CI、三平台 OCR、Risk-tier、CodeQL Python/Actions，架构审计与 PR review；有红灯先检查日志并修复，勿合并/Ready/关闭 Issues。

---

## 2026-10-30｜G3 R4.2 真正 Tk 合成集成测出来的首屏 R3 来源竞态（最新恢复入口）

之前文档最终 HEAD `58a8108c461efae36cda3fc9c677bc85e249bb5b` 全部 CI 6/6、OCR 3/3、CodeQL 2/2、Risk-tier SUCCESS，仅自动化 E2。新 `c65f3fbbe7f3263b798d49846eb1e7a9a343816e` 把真实 Tk 校对窗口+三个默认 OFF 开关+「筛选」按钮的合成临时项目集成测试加进 `.github/workflows/ci.yml` Python 3.13 的 Windows/macOS/Linux 三平台。首次脚本将标签中带「筛选」的复选框误当按钮，`e952f5737346f576e38b2ec163a2d65e2f6174e7` 只修测试 selector。随后 Mac/Windows GUI smoke 通过，Ubuntu **真正暴露产品时序缺口**：异步首屏校对来源/词条尚未建立时单页保存被原有 R3 `commit_review_bundle` 正确拒绝，原筛选回调未捕捉，导致挂起/超时。

修复生产 `bd796fd73a2906d4e083fbd43ff83caacc57472d`：首次筛选前要求 `current_page.stem==_rendered_page_stem`；首屏未就绪显示提示并保持人工文字/设置；R3 保存 RuntimeError/OSError/ValueError 或明确 False 时停止，**不持久化新的风险/证据/计时选项，也不启动筛选**；只有 R3 保存成功才保存筛选设置并开始下一轮 worker serial。预先检验批次整数防止失败筛选误保存。在 `tests/test_g3_r4_rejected_scan_and_origin_race_20261030.py` 新增未渲染/来源保存异常/False return 三条回归；真实 Tk 集成 smoke 则覆盖主动模拟未就绪拒绝→等待真实首屏 bound→成功筛选→未保存人工编辑拒绝重筛。所有测试只用自动生成项目，不能替代真人 Windows E3。

**恢复动作：**核对源 [CI #41094402643](https://github.com/chigre/Picture_Capture/actions/runs/41094402643) 六平台 OS/Python (Ubuntu 3.13 **4987 passed 3 skipped，Xvfb real Tk G3 smoke OK**)、[OCR #41094402645](https://github.com/chigre/Picture_Capture/actions/runs/41094402645) 3 OS、CodeQL Python/Actions、Risk-tier；若失败查相应 job logs 修复。再核对最新文档 HEAD 的完整 exact CI，不以过去代码绿灯代替新 HEAD。R3 Windows真人 E3/#483 W1–W11/#503 人工 Undo 全部 NOT PERFORMED，R6 可信人工标签缺，R8 真实扫描延期。保留 #663 唯一 Draft/Open/Unmerged，main 不动，不合并不 Ready 不关事项。

---

## 2026-10-30｜G3 R4.2 后续：被拒绝筛选不写入设置 + 风险来源文件竞态防护（最新恢复入口）

已核验起点 `1611f7c60a5f3f93ca191e01b9ee7cc47248c493`：CI 6/6、OCR 3/3、CodeQL 2/2、Risk gate 全 SUCCESS，仅 E2。新 `12fa0cd4bc800ab740e0cb148d6874698924ad31` 负向测试复现非法 batch size 仍修改部分 AppSettings、OCR 风险来源 sidecar 被并发换字节后仍可排序的缺口；其中 4 个早期 guard 测试有缺漏的 mock deps，`3252a949d615af1a819441778db2bd6c3f4f84c7` 仅补齐测试依赖，无变更业务断言。修复源 `691bcee0da9adc3b8a108ac737a2216ac03a5a9c` 让 pending/saving 编辑拒绝点提前到任何设置写入之前；特定字符为空不保存改动；所有设置字段在 batch size 成功验证后才统一提交；风险快照开始与结束复读原 `*_risk_origin_v1.json` 字节，来源变化则保留原顺序并拒绝认证。

**接力下一步：**先查看 corrected-test [CI #41082255201](https://github.com/chigre/Picture_Capture/actions/runs/41082255201) 六平台 + Risk、[OCR #41082255256](https://github.com/chigre/Picture_Capture/actions/runs/41082255256) 三平台和 CodeQL Python/Actions 2/2；再核查最新文档 HEAD exact SHA 所有检查。红灯必须读 job log 修复，不因早期 mock 错误声称全部测试先行成功。已保留真实两类失败证据。默认风险优先/来源采集/匿名计时三个选项继续 OFF；不修改 PDIC/PPP/SECTION/OCR、不产生人工真值、不上传用户内容。

后续剩余真正门槛为人工 Windows R3 E3、#483 W1–W11 和 #503 Undo/Redo；准备好的 [R4.2 Windows 操作者 runbook](https://github.com/chigre/Picture_Capture/blob/1611f7c60a5f3f93ca191e01b9ee7cc47248c493/docs/architecture/G3_R4_2_OPERATOR_ACCEPTANCE_20261030.md) 尚未执行。R6 标签不齐，R8 真实扫描待用户决定。保持唯一 Draft #663 不合并，不开启 Ready，不改 main，不关闭 #483/#503/#562。

---

## 2026-10-30｜G3 R4.2 大批次：匿名计时、旧预取防串代次与 Windows 人工验收包（最新恢复入口）

GitHub verified previous exact baseline `efed96356e1bb69a490525d927a062f40d10ff09`: [CI 41074662522](https://github.com/chigre/Picture_Capture/actions/runs/41074662522) 6/6 + Risk, [OCR 41074662499](https://github.com/chigre/Picture_Capture/actions/runs/41074662499) 3/3, CodeQL Python/Actions 2/2 全绿。#663 保持 Draft/Open/unmerged，main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未改。

本轮测试先行 `a5414d69071a8c9fdb4e0d12fbb7f3939790f473` 缺 review_timing 模块 red；代码 `af797e858a2795e41eb51b7f9a435b9c0d096f7e` 新增 `ReviewTimingSession`：扫描/来源风险校验/预览生成/PDIC 保存的**本地内存**秒数和数量，仅包含聚合整数+浮点，无词条、原图、坐标、页面名、文件自动写入、网络上传；非人工主动校对时间，risk 含于 scan，不得相加宣称加速。第三个 GUI 默认 OFF 开关 `focused_review_timing_enabled=False`，只有点击「筛选」后新 epoch 采样；界面标签显示汇总。新增初始 worker invalidate、render serial advance、预取与渲染同时固定 scan epoch，旧扫描的迟到 done/failed 不能更新新一轮缓存或清除其 key；保存与人工修改仍用原可靠队列和源 X/Y。

源 [CI 41077510554](https://github.com/chigre/Picture_Capture/actions/runs/41077510554) Ubuntu py3.13 **4978 passed / 3 skipped**、Risk-tier、CodeQL 2/2 SUCCESS；[OCR 41077510565](https://github.com/chigre/Picture_Capture/actions/runs/41077510565) Ubuntu 成功，Windows job 在安装 setup-uv 的 GitHub 版本 API 报 Server Error、**测试未执行，不能视为通过**；macOS pending。其他 full OS/Python CI 仍 pending。**下一步先核对最新文档 HEAD 的全部 matrix 和安全门禁**；如果失败按日志修，非本地网络问题不改无关功能。Windows 操作者流程已写 `docs/architecture/G3_R4_2_OPERATOR_ACCEPTANCE_20261030.md`，全是 NOT PERFORMED，#483 W1–W11、R3 E3、#503 压力 Undo/Redo 仍另行验收。没有人工标签不启动 R6，R8 真实扫描延后。

---

## 2026-10-30｜G3 R4.2 重点筛选 Tk 可选队列：旧设置兼容修复（最新恢复入口）

#663 最新的选配 UI source `9ac248699e05b1524ca56cbe24a8b06f2729a18c` 完成 Tk 高风险优先与来源时证明采集两个默认 OFF 开关，但 CI 发现旧 `SimpleNamespace` 不具备两个新 Tk BooleanVar，导致旧测试 `test_focused_setting_write_validation_and_clamp` 抛 AttributeError。此失败是**真实回归，不是预期 RED**。已提交小修 `f7cba75de0dadb755b8eaa7505e39e31ce9f0f44`：缺少新控件时保留原设置或默认 False，真实窗口仍按 Checkbox 值保存。复测 [CI #41074003807](https://github.com/chigre/Picture_Capture/actions/runs/41074003807) Ubuntu py3.13 **4971 passed, 3 skipped**，OCR [#41074003632](https://github.com/chigre/Picture_Capture/actions/runs/41074003632) 3/3、Risk-tier、CodeQL Python/Actions 2/2 成功；其他 Python/OS 仍须读取 exact-head conclusion，不能预先宣布 E2 全部通过。

上一严格 SECTION `e60c59f9bb5a4a1656457f4e056c63986f5f39f6` 全绿自动化基线。默认 OFF 时筛选顺序、身份与 IO 不变；ON 时每页批量验证 OCR/PDIC/image/SECTION 与来源侧记录，只对已证明来源的诊断在同页连续 SECTION 内稳定排序，unknown 不冒充 normal；不能扫描未保存修改的可见批次，勾选变化需按「筛选」开启新 serial，不会中途重排编辑器。来源捕获仅下次批量 OCR/combined PDIC 成功落盘后才可选写文件。

**恢复动作：**先确认修复源 `f7cba75...` 六 CI 6/6、Risk、OCR 3OS、CodeQL 2/2；再确认最新文档 HEAD exact CI；若失败查日志修复，不推 merge。后续 local-only anonymous aggregate timing + GUI 工作者序列和 SECTION 人工 W1–W11 在获真实用户许可后进行。#663 Draft/Open/Unmerged、main 未修改；R3 E3、#483 W1–W11 仍 NOT PERFORMED；R6 人工标签缺失、R8 真实扫描 deferred。

---

## 2026-10-30｜G3 R4.2 可选风险优先队列已接入重点筛选（最新恢复入口）

前一 `e60c59f9bb5a4a1656457f4e056c63986f5f39f6` 已由 GitHub exact SHA 验证 CI 六平台 6/6、OCR 3/3、Risk-tier 与 CodeQL Python/Actions 2/2 全绿，SECTION 原图 XY 归属可作为来源快照基础；仍无人工真值。

本轮 `155727da9783178f8e9257e8e72a17682edb73df` 是 red-first（Ubuntu CI 41072980340 预期缺 review_risk_snapshot 模块），生产 `9ac248699e05b1524ca56cbe24a8b06f2729a18c` 把默认 **OFF** 的高风险优先选项实际接入 Tk「重点筛选」，并提供第二个默认 OFF 的「下次批量 OCR 记录来源证明」选项。仅在重新点击「筛选」后保存设置并捕获新 worker epoch，已经显示的编辑器不会被切换开关直接重排；尚未保存或仍在后台保存的编辑会阻止清空和重新筛选。每页合并读取来源 witness、OCR/PDIC/图像/SECTION、严格唯一源XY，并复检哈希；风险判定为 priority/normal/unknown，只在同页连续 SECTION 内稳定排序，缺少来源不能凭旧缓存认定高风险。默认 OFF 保留原列表和无额外页面读取。无需更改人工 PDIC、PPP、SECTION 或 OCR JSON。

**恢复动作：**核查生产 [CI #41073344700](https://github.com/chigre/Picture_Capture/actions/runs/41073344700) 六平台和 Risk、[OCR #41073344750](https://github.com/chigre/Picture_Capture/actions/runs/41073344750) 三平台、CodeQL 2/2 的 exact HEAD conclusion；有失败必须读对应 jobs logs 修复。**再**核对文档最终 HEAD 完整 CI。后续仅在自动化门禁绿时继续 R4.2 local-only aggregate timing / 明确 Windows E3 验收材料，不能凭 pytest 替代真实 GUI 操作与用户 W1–W11。#663 必须 Draft/Open/Unmerged、main 不动；R6 无可用人工核验标签，R8 真实扫描延后。

---

## 2026-10-30｜G3 R4.2 SECTION 原图几何严格归属（最新接力）

前一个 `b49d1ef181828f1699e2fc9e5304bac4cfb23d0c` 已由 GitHub 验证全部 CI 6/6 + Risk、OCR 3/3、CodeQL Python/Actions 2/2 SUCCESS。现仍唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)，main 不动。

本轮 test-first `cd7aa3f055515e0e3785c05ef8cedb36329dee66` 预期缺 `review_section_provenance`；源 `ffbe5ded4c8b4de6f8b47bc01a8045a259cd1332` 新增严格 SECTION v2 原图 X/Y 归属，不用历史 UI 的最近区域逻辑：核对原图 EXIF 后尺寸、四种 layout transform、每条 source segment 与真实区间、序号与无重叠，再确认点唯一落在半开区间内。不在区域、边界歧义、坏文件、跨SECTION 不能认领。来源时 witness 增加原图SHA、SECTION SHA、候选所属 `section-N`，读取时复检旧图/缓存/PDIC/SECTION；只写软件自有可选来源 sidecar，设置继续默认 OFF；**未接 Tk 队列**。4 种变换与恶意损坏/间隙/同尺寸换图均有合成测试。

**恢复动作：**查询源 [CI #41068586911](https://github.com/chigre/Picture_Capture/actions/runs/41068586911)、[OCR #41068587040](https://github.com/chigre/Picture_Capture/actions/runs/41068587040)、CodeQL Python/Actions 的所有 exact-SHA conclusion，并核验最终文档 HEAD 6+3+2+Risk；任何错误查 job logs 修正，不能因 Ubuntu py3.13 `4961 passed, 3 skipped` 和 OCR 已绿就提前宣布全部完成。源全绿后才考虑 R4.2 Tk 选配队列的每页快照与 worker serial/cancellation、安全定位和 local-only timing。Windows R3 E3、#483 W1–W11 NOT PERFORMED；无人工真值或真实基准，R6 blocked、R8 deferred；不合并、不开 Ready、不关闭 #503/#562/#483。

---

## 2026-10-30｜G3 R4.2 来源时 witness 只读选配提交（最新恢复入口）

上一 checkpoint `f8d2d48acb68df3f11b83445d7ef2f0155ff8e99` 已经由 GitHub exact SHA 验证六平台 CI 6/6、OCR 3 OS 3/3、Risk-tier 和 CodeQL Python/Actions 2/2 全绿，**只是无 Tk 接线的 R4.2 基础模块**。

本轮先发 red-first `a81075569ed32e2c4d4618cc1c4bfcf9d8e1ce66`，Ubuntu CI 41064417899 预期 ModuleNotFoundError；随后实现 `2985eb6610aa54f070bf07eb919bf792678b6f67`：新增 `proofreading/review_risk_witness_storage.py`，以及 settings 默认 **False** 的 `focused_review_risk_witness_capture`。批量 OCR/combined 的 PDIC 已经落盘后才可选地生成 OCR/PDIC SHA256 来源时 witness，只支持**无 SECTION sidecar**，有 SECTION 或无法唯一证明候选ID、原图XY、词文本归属时跳过。文件保存前后复验；按真实当前文件复核旧 witness。不会改写 OCR JSON/PDIC/PPP/SECTION，默认不生成 sidecar，界面仍未接高风险优先排序。

**恢复动作：**核对源 [CI 41064630984](https://github.com/chigre/Picture_Capture/actions/runs/41064630984) 六平台 + Risk、[OCR 41064630989](https://github.com/chigre/Picture_Capture/actions/runs/41064630989) 3OS、CodeQL Python/Actions，失败按日志修复；另核对最新文档 HEAD，不以旧提交成功替代。继续 R4.2 SECTION 几何严格归属和默认 OFF Tk 实际接线之前，不能称 UI 高风险优先功能完成，不能把此 witness 当 OCR 错误真值。main 不动，#663 Draft，不合并，Windows R3 E3/#483 W1–W11 仍 NOT PERFORMED。

---

## 2026-10-30｜G3 R4.2 只读来源证据与默认 OFF 的稳定队列（最新接力）

[Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) 当前以 `c6426614e112e0d8bc7a4d80aae941575e301b47` 全绿作为 R4.1 E2 基线：CI 六平台 6/6 + Risk-tier、OCR 3OS 3/3、CodeQL Python/Actions 2/2 成功。R4.1 不是人工真值分类。

本轮先提交测试 `c155a8dda3cf032b43e93ba396fcc2ba7b2d8dff`，Ubuntu 预期缺少模块导致 red；再提交生产 `898d90261727b3c5515cba43e5255b294e7135df`：新增 `proofreading/review_risk_queue.py`，只读检查 OCR/PDIC 实际 SHA-256、候选ID和原图X/Y唯一归属、SECTION sidecar 版本指纹与几何 SECTION 来源，同时提供只按原始页与连续 SECTION 段内稳定排序的函数，默认 OFF。缺少独立**来源时** witness 的老缓存一律 unknown；不能在校对时自行生成证据冒充来源。**尚未接线 Tk、尚未建立持久化来源证明，也不产生真实界面优先队列。** 保留原重点筛选、批次导航、Undo/Redo、用户所有文件与主分支不变。

**恢复动作：**源 [CI #41059425448](https://github.com/chigre/Picture_Capture/actions/runs/41059425448)、[OCR #41059425445](https://github.com/chigre/Picture_Capture/actions/runs/41059425445)、CodeQL Python/Actions 要确认 exact SHA 6+3+2+Risk 全绿；本段提交时源 Ubuntu py3.13、OCR 3/3、Risk 成功，其余 pending。再检查最新文档 HEAD 的全部 CI。随后单独研究可靠来源时 witness 的可选采集、SECTION geometry、界面明确 OFF 开关与 worker cancellation，不可直接对所有旧缓存排序。Windows R3 E3、#483 W1–W11 仍 NOT PERFORMED；R6 标签、R8 真实扫描 blocked；#663 仍 Draft 不合并。

---

## G3 R5.2 exact E2 + R4.1 fail-closed triage（2026-10-30）

R5.2 `11aa70a0a9327b7bac6080f863aa212da1af27de` 已核实 [CI 40968076780](https://github.com/chigre/Picture_Capture/actions/runs/40968076780) 六平台+Risk-tier、[OCR 40968076632](https://github.com/chigre/Picture_Capture/actions/runs/40968076632) 三平台、[CodeQL 40968072905](https://github.com/chigre/Picture_Capture/actions/runs/40968072905) Python/Actions 全部 SUCCESS，仅合成 E2。R4.1 红先行 `c3caec35` 预期 ModuleNotFoundError；源码 `460383db864663854905e7f8d2dd1abd665e26ca` 增加只读 `proofreading/review_risk.py`：需独立核验 OCR+PDIC SHA、project/page/SECTION、唯一 source XY，才输出 priority/normal，否则 unknown。源 [CI 40971810563](https://github.com/chigre/Picture_Capture/actions/runs/40971810563)、[OCR 40971810731](https://github.com/chigre/Picture_Capture/actions/runs/40971810731)、[CodeQL 40971805624](https://github.com/chigre/Picture_Capture/actions/runs/40971805624) 及最终文档 HEAD 必须核实结论。R4.2 UI 尚未接入，默认排序不变。详见 [R4 来源审计](../architecture/G3_R4_PROVENANCE_REVIEW_TRIAGE_20261030.md)。PR #663 唯一 Draft/Open/Unmerged；main 不变；Windows R3 E3、#483 W1–W11 **NOT PERFORMED**；无 R6 训练或真实扫描基准。

## 2026-10-30｜G3 R5.2 独立 OCR 仲裁 q 快照/纯函数（最新接力）

基线 R5.1 已在 `234870694bca285117deb6a863c11bd705f3891c` 确认六平台 CI #40965627205 6/6、Risk-tier、OCR #40965627204 3/3、CodeQL Python+Actions 2/2 全部成功。**仅为 E2 自动化，不等于真人 E3**。

本轮仍在唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)，先做 fail-first `5cd39dddc278553b10ded5d0efb57ff54f9375f3`（预期缺少 q 纯评分模块），再提交源代码 `e57346968a48372a0cb633cc63c6fce8fe0f0db9`：新增 `ocr/engine_quality_scoring.py` 的不可变、可 JSON 序列化的 11 字段快照及有序纯评分函数；`ocr/pairing_arbitration.py` 保持 pair/前缀转换及 monkeypatch 入口、三引擎投票逻辑、Lens diagnostic-only、并列 tie、门槛和原图坐标不变。新增 512 组纯 q 浮点逐项对比、异常值/边界值、P/T/L 及 15 个全量输出差分场景。

**唯一恢复动作：**检查源代码 [CI #40967756737](https://github.com/chigre/Picture_Capture/actions/runs/40967756737) 六平台、[OCR #40967756750](https://github.com/chigre/Picture_Capture/actions/runs/40967756750) 三平台及 CodeQL Python/Actions 的最终 conclusion；有失败立即查日志修本包，不能将 queued/in_progress 当 success。当前本节提交前 OCR 3/3 和 Risk-tier 已成功，完整源 CI 未完成。随后核对最新文档 HEAD 全套检查并将 R5.2 E2 标为 verified，方可启动 R4 priority/normal/unknown + 默认 OFF 队列。人工 E3、#483 W1–W11 仍 NOT PERFORMED，R6 标签阻塞，R8 真实扫描延后，不合并、不标 Ready、不关闭 #503/#562/#483。

---

## 2026-10-30｜G3 R5.1 candidate score immutable/pure checkpoint（历史完成证据）

同一 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) 中，基于 `50a913ef` 已完成 G2 全平台绿灯的基线，先提交 fail-first `9426de03`（缺模块导致预期 collection error），再在 `33fbef91` 将候选过滤器12项打分布尔特征抽为冻结可序列化快照和纯函数（精确保留原加法顺序，不改接受/拒绝/原图XY/保存逻辑），新增穷举4096组合、三个OCR来源及拉丁/CJK等合成差分用例。第一个 CI 暴露测试误以为所有 diagnostics 都是候选，实际另有合法页面级 meta；仅修正测试、绝不删改产品 meta，最新源和测试 HEAD `f63d8805d54100adafb802ed2bedd1ff91dd226f`。

**恢复动作：**核对该确切源 HEAD 的 [六平台 CI #40965305404](https://github.com/chigre/Picture_Capture/actions/runs/40965305404)、[OCR 3OS #40965305118](https://github.com/chigre/Picture_Capture/actions/runs/40965305118)、CodeQL Python+Actions；排队/运行中不是通过。有失败按真实日志修复；全绿后才能标记 R5.1 E2 完成，再启动 **R5.2 独立仲裁 q** 的纯函数/缺失值、边界强度、修复数、forced status及 Lens diagnostic-only 差分验证。**R4 默认 OFF，R6 未核标签 blocked，R3 Windows E3 / #483 W1–W11 NOT PERFORMED，PR 保持 Draft 不合并 main**。详细见 `docs/architecture/G3_R5_SCORE_Q_PARITY_AUDIT_20261030.md`。

---

## 2026-10-29｜G1 OCR candidate choice + 原图 Y 位置切换（此节为最新执行接力）

本次仅在 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) 内处理
`ui/review_selection_workflow.py` 一个 UI owner 的真实顺序错误：
人工 candidate choice 曾在 OCR 数值校验和 PDIC 保存前先落盘 manual_selection，
位置切换在兄弟候选完整暂存前就撤掉 Entry/checkbox。
先提交回归 HEAD `b036c68ef1c6cb9ba8c918c98210e6962e9e6e3b`，
[CI 40750612646](https://github.com/chigre/Picture_Capture/actions/runs/40750612646)
Ubuntu/Python3.13 **7 failed / 4722 passed / 3 skipped**，均为新故障注入反例。
随后修复为先校验、候选和兄弟人工作业内存批量暂存、严格
`candidate_id` 归属（禁止附近 X/Y 认领）、PDIC 优先持久化，
失败则依磁盘实际字节恢复 UI 或隔离不确定状态，**不擅自覆盖第三方人工字节**。
测试覆盖健康流程、写前/写后错误、外部人工竞争、旧版原始 Y 切换和
ReviewWindow 未提交时不准 Undo。详见
`docs/architecture/R3_G1_MANUAL_SELECTION_ORIGIN_AND_CHECKBOX_20261029.md`。

以 GitHub **最新 #663 HEAD 的 exact-head 六平台 CI/Risk、OCR 3 OS、
CodeQL Python/Actions** 为本包完成证据；queued、skipped、旧 SHA 通过均不可计入。
本节是新代码/测试提交记录，不能代替最新 CI 或 R3 真人 E3。
#663 保持 Draft/Open/Unmerged；#503/#562/#483 均不因合成测试关闭，
真实 Windows candidate/Undo/Redo×20/FocusOut、PDIC/PPP/SECTION、原图裁切
和 R2 W1–W11 **NOT PERFORMED**。先审查最终 CI，若失败只修本包。
若通过，下一安全包是剩余 FocusOut/自动保存和 ReviewWindow 历史
交叉边界；无复现实证则只读阻塞而非机械迁移。

---

## 2026-10-28｜v1.3.0 全库复审后唯一执行入口（取代以下旧接力状态）

**从现在起仅推进 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)**，同时跟踪 [#503](https://github.com/chigre/Picture_Capture/issues/503) R3 与 [#562](https://github.com/chigre/Picture_Capture/issues/562) 架构；旧 #664 关闭未合并，完整提交历史通过双父合并 HEAD `66ad88c276b6965c075eeb72583b42dd0aa7f3ac` 纳入 #663。旧文本中「新建 #503 实施 PR」「#542 仍当前 PR」「重新从 B0 启动」均为历史，不再作为可执行指令。

每次恢复**先**读取 `CORE_QUALITY_UPGRADE_PLAN.md` v1.3.0、`CORE_QUALITY_STATE.json` 中 `audit_20261028` 及 [全库复审](../audits/WHOLE_CODE_AND_ROADMAP_REAUDIT_20261028.md)，**再读取 GitHub 真实 PR HEAD 和 CI**（它们高于本文快照）。最近审计基线 `66ad88c276b6965c075eeb72583b42dd0aa7f3ac`：[#40559523622](https://github.com/chigre/Picture_Capture/actions/runs/40559523622) CI completed/success 6/6、[#40559523187](https://github.com/chigre/Picture_Capture/actions/runs/40559523187) OCR Smoke completed/success 3/3。只保证**该旧 HEAD**，不能直接用作下一次新提交证明。

**唯一下一主题 G1：#503 R3 候选归属、manual_selection/PDIC/simplified、Undo/Redo 和崩溃恢复的所有权/版本失败矩阵；**不重复已存在的 O_EXCL、非普通标记拒绝或多文件核验。其次 G2 `app.py`/大 owner 有限抽取、G3 R5 parity 与 R4 默认关闭可解释优先队列。禁止依赖源码行数声称性能提升；R6 没有经人工 verified 的标签保持 blocked；R8/真实扫描 PR-B 继续用户延后。

每个包：HEAD/CI/是否并发修改检查 → 责任 owner / 反例 → 源码、回归、架构文档 → 实际提交 → 新 HEAD 六平台 CI、OCR Smoke、按需 CodeQL 与人工门禁分别记录 → 两个 Issue 同步。**PR #663 维持 Draft/Open/Unmerged，不标 Ready，不合并 main**。真实 Windows 字典 R3 20-step Undo/Redo、候选checkbox、FocusOut、PDIC/PPP/SECTION/crop、source-image X/Y 人工验收 **NOT PERFORMED**；R2 #483 W1–W11 未验收。可因安全 blocker 停下，不可补造测试结论。

---

## 2026-10-17｜main postmerge CI 最终结果：成功（Windows runner 重试后）

- R3 #542 已合并主干 `e12a9db4cc9199069e93d2c3ef12df97fcafd403`。该 SHA [postmerge CI 39013602419](https://github.com/chigre/Picture_Capture/actions/runs/39013602419) 在第一次 Windows hosted Tcl `init.tcl` 初始化异常后，**attempt 2 重跑失败 Windows 作业成功，最终四平台 SUCCESS**；[main CodeQL 39013601837](https://github.com/chigre/Picture_Capture/actions/runs/39013601837) SUCCESS。首次失败不能冒充未发生；是已记录的运行器异常。
- 此份文档仍需 #548 纯文档 PR 的自身固定 SHA CI/CodeQL 与合并后 main CI，不从上述旧 main SHA 推断文档合并后的结果。R3 的人工 Windows 交互验收依用户明确授权暂不进行，不是已实际 PASS；#483、#503 不关闭。

## 2026-10-17｜R3 工程合并完成；人工验收暂缓；main CI Windows 运行器重试

- R3.1/R3.2 [#542](https://github.com/chigre/Picture_Capture/pull/542) 最终 HEAD `f80daf07d7421f5bd8d20cce0c86fce160813697` 经 [四平台 CI 39013417928](https://github.com/chigre/Picture_Capture/actions/runs/39013417928) **SUCCESS**，[CodeQL 39013415268](https://github.com/chigre/Picture_Capture/actions/runs/39013415268) **SUCCESS** 后 squash merge [main@e12a9db4](https://github.com/chigre/Picture_Capture/commit/e12a9db4cc9199069e93d2c3ef12df97fcafd403)。
- 交付：候选所有权约束 Undo/Redo、20 步同会话历史、严格源指纹、PDIC+简体 sidecar 可恢复提交与字节回读、失败回滚及隔离、窗口关闭拒绝、延迟快照防护；合成故障注入/架构检查通过；不改变人工 PDIC/SECTION/Profile/OCR、原格式、R2 默认 OFF，不混入精修功能。跨文件恢复 **不等于 OS 原子性**。
- 用户本日授权本次**不进行**真人 Windows 验收而放行工程合并；R3/#503 与 R2/#483 W1–W11 的实际验收均是 **NOT PERFORMED**，不得记录为实际 pass/verified；R2/B2 继续 `in_progress`，#483 开放。
- 合并后 [CodeQL 39013601837](https://github.com/chigre/Picture_Capture/actions/runs/39013601837) **SUCCESS**；首次 [main CI 39013602419](https://github.com/chigre/Picture_Capture/actions/runs/39013602419) Ubuntu/macOS/Python 3.10 通过，Windows 2847 tests passed、1 项 GitHub hosted Python3.13 `init.tcl` 环境加载失败；已发起 Windows failed-job 重试 attempt 2，记录时尚未最终绿灯。
- main 分支保护禁止直接提交，故以**独立纯文档 PR** 同步 STATE/RESUME/B3_RUNBOOK，不绕过保护或开启第二个生产 PR。后续须验证 main Windows 重试、文档 PR 固定 SHA CI/CodeQL、合并及 docs postmerge CI。

## 2026-10-17｜#542 R3 安全工程收口，人工验收本次明确豁免（未声称通过）

- 用户明确授权：真人 Windows R3/R2 验收当前均暂不进行；**仅作为本次工程合并决策的人工验收豁免，实际结果仍是 NOT PERFORMED**。R2/B2 仍 `in_progress`，#483 W1–W11 保持 open；R3/#503 真人验收仍未实际完成，不制造 verified 标签。
- #542 同一 Draft PR，最新工程 HEAD `94a464b34a0569f3fc136fc1c263cd148883abc7`。已复用 B3 事务历史/候选所有权、恢复标记、严格源指纹，补 ReviewWindow 失败时窗口不关闭、内存与磁盘保护，以及 PDIC+简体 sidecar 配对暂存/两文件提交/回读/失败回滚；原项目格式和 R2 证据默认 OFF 不变。该机制是可恢复、fail-closed，**不是跨文件 OS 原子性**。精修画线独立。
- 此文档检查点时 [工程 CI 39013316496](https://github.com/chigre/Picture_Capture/actions/runs/39013316496) 尚未确认最终结果；文档提交将生成新 SHA，**必须以最后 SHA 的 Windows/macOS/Ubuntu/Python3.10、架构与 CodeQL 全绿为合并条件**，若失败只修复不合并。
- 唯一下一动作：核最终固定 SHA 的 CI 与 diff，安全通过后按用户豁免合并 #542，复核 postmerge main CI，并在 main 同步 STATE/RESUME/RUNBOOK；如有 blocker 保持 Draft、下小时继续。

## 2026-10-17｜#542 分支落后修复（仅同步 main，R3 未验收）

- GitHub live main：`db746ec4a15b5cae33f04526ef2995e86a91fd19`；#542 同步前 HEAD：`41f14fe55b0bd4f465e86f6e7314f30910e85281`。经 GitHub 自动无冲突试合并树核对，以两个父提交创建分支合并 `0511b30a20be57ba79d378eded03d4a1f0f7c9bf`（PR HEAD first parent；main second parent），非 force push；当前比较 `main...#542` 为 **behind 0 / ahead 24**（本条文档提交前）。仅同步历史，不表示 R3 安全验收。
- 旧 PR HEAD [CI 39008787964](https://github.com/chigre/Picture_Capture/actions/runs/39008787964) success；**合并后的新 SHA 尚无完整 CI 结论**。此文档提交也将进一步改变 HEAD，必须按最终 HEAD 重新检查 Windows/macOS/Ubuntu/Python3.10 + 架构 + CodeQL。
- #542 保持唯一 Draft 生产 PR，**未合入 main**；#503 真人 Windows R3、#483 Windows W1–W11 均未验收，R3/B3、R2/B2 仍 `in_progress`。后续单一安全动作：先补 ReviewWindow 保存失败/关闭及延迟快照保留的故障注入和修复，再跑四平台，禁止把精修画线改动当本 PR 的功能任务。

## B3/R3 #542 固定 SHA CI 结果（2026-10-17，自动验证通过，真人待验收）

Draft [PR #542](https://github.com/chigre/Picture_Capture/pull/542) 源码与文档 head `eaad5dd41c8742261592454ed4838713b6ea7a37` 的 Windows/macOS/Ubuntu/Python3.10 [CI 38970243351](https://github.com/chigre/Picture_Capture/actions/runs/38970243351) **四项 SUCCESS**；[PR gate 38970237522](https://github.com/chigre/Picture_Capture/actions/runs/38970237522) SUCCESS。main@05d345f8 的既有 [CI 38966764059](https://github.com/chigre/Picture_Capture/actions/runs/38966764059) SUCCESS。但这不等于 R3 全范围实现的真人验收，不等于跨文件 OS 原子性保证。#503 要求的真人 Windows ReviewWindow FocusOut、autosave、删除、重复 Undo/Redo、关闭/跨页、异常中断等交互尚未验收，R2/B2 #483 Windows W1–W11 仍未做；两阶段保持 `in_progress`，PR **保持 Draft/开放不合并**。唯一下一动作：严格审查剩余源指纹及失败路径并完成 R3 真人 Windows 验收；若有代码变动重新四平台 CI，再评估合并及 main CI。本次仅同步文档会产生新的 PR CI，需按该文档提交新 SHA 重新确认。

## B3/R3 #542 PR 与真实 CI 接力（2026-10-17 05:34 +0800；未验收）

B3 v4–v8 已正式提交原 R3 分支（`16e00f2`、`ded1117`），[Draft PR #542](https://github.com/chigre/Picture_Capture/pull/542) 是**唯一活跃生产 PR**。已将 main@05d345f8 (#539 PDIC 批量保护及其他主干更新) 以双亲合并提交 `3d8c157` 整合；PR 后来变为可合并，main 自身四平台 [38966764059](https://github.com/chigre/Picture_Capture/actions/runs/38966764059) SUCCESS。初次 R3 CI [38969777363](https://github.com/chigre/Picture_Capture/actions/runs/38969777363) 暴露 app.py 原架构上限 784737 字节被突破；`8b2186b` 将延迟保存抽离为独立 `proofreading_deferred_save.py`，主模块降至 784233 字节，**未放宽 ratchet**。下一轮 R3 CI [38969942123](https://github.com/chigre/Picture_Capture/actions/runs/38969942123) 的 Ubuntu 架构守卫通过，pytest 2800 通过、2 项原有源码文本断言因抽离模块而失败；`162764a` 调整断言查找实际调用与被调模块，**仍继续要求 PDIC 先提交、人工覆盖后于 PDIC、证据最后写入**。新 CI 尚未验证；R3 不得合并或标记 verified。R2/B2 `in_progress`，#483 真人 Windows W1–W11 待做，R3/#503 真人 GUI 验收也待做，不可替代。下一唯一动作：检查最新 fixed-head PR CI、逐项修复失败，然后严格审查数据/GUI安全及 Windows 人工验收。

## B3/R3 v4–v8 实装检查点（2026-10-17，未验收）

原 R3 分支 `feat/pc-cq-b3-candidate-undo-redo-20261015` 已真实提交 **v4/v5** 事务 rollback-intent／marker readback、失败后单文件或跨文件强制回滚（`16e00f2`），以及 **v6/v7/v8** 普通保存、共享 PDIC writer、ReviewWindow 编辑提交隔离和 deferred-save 失败快照保留（`ded1117`）。新增合成故障注入测试，但**未运行项目 pytest、Tk smoke、架构守卫或 R3 四平台 CI**；不得据此声称跨文件 OS 原子性、Undo/Redo 彻底安全或 R3 verified。main@05d345f8 的 [CI 38966764059](https://github.com/chigre/Picture_Capture/actions/runs/38966764059) 第 2 次运行四平台 SUCCESS，不能替代 R3 分支验证。R2/B2 与 R3/B3 维持 `in_progress`，#483 W1–W11 真人 Windows、#503 R3 真人 GUI 验收待做；用户已授权越过 B2 验收门槛推进 B3，不关闭 #483。恢复动作：只开一个 R3 draft PR 以获得固定 head CI，处理差异并做跨平台及真实 GUI 验收后再决定 merge。

## B3/R3 #503 readback/rollback safety checkpoint (2026-10-16 17:13 +0800; unverified)

On branch `feat/pc-cq-b3-candidate-undo-redo-20261015` (parent `8b52b344d755`, main `8ed4dd04bce0`), add exact post-publication bytes verification for candidate PDIC/manual/simplified bundle and one-/multi-file Undo/Redo. A silent rollback failure retains the recovery marker and blocks page reopening until recoverable; **this does not provide OS-level cross-file atomicity**. Add negative tests for invalid row index, silent partial writes, silent rollback and silent single-file Undo. No pytest/Tk/architecture/four-platform R3 CI has run; R3 remains in_progress. Only open PR #536 (unrelated UI, CI https://github.com/chigre/Picture_Capture/actions/runs/38878591544 failed), so do not open a parallel R3 PR. main CI https://github.com/chigre/Picture_Capture/actions/runs/38876986096 passed. #483 W1–W11 and R3 human Windows acceptance remain pending; R2/B2 in_progress, R2 evidence OFF, no real scans/uploads/training. Next: execute focused tests and architecture/Tk checks, then wait for PR slot and run R3 four-platform CI.

## B3/R3 #519 最终结果（2026-10-15，已验证部分交付）

#519 [PR](https://github.com/chigre/Picture_Capture/pull/519) final head `16a6e8b28c983b31a11b23682777f9be2efaf882` 四平台（含 Python 3.10、Tk synthetic、架构、wheel）[PR CI 38703019216](https://github.com/chigre/Picture_Capture/actions/runs/38703019216) SUCCESS；CodeQL 成功。已 squash 合并 main@`6987a4a2eac37a6b3524e6c63ae87a1b60f5ad7a`，合并后 [main CI 38703692439](https://github.com/chigre/Picture_Capture/actions/runs/38703692439) 与 [Push 38703694285](https://github.com/chigre/Picture_Capture/actions/runs/38703694285) 均 SUCCESS。旧 Windows init.tcl 运行器错误重跑后消失；没有改弱测试/基线。

已支持安全的 OCR candidate-linked **删除提交**：PDIC、人工覆盖、简体的恢复式多文件写入成功后才更改 Entry/candidate/Tk checkbox。快照冻结 OCR owner，检查源文件与源指纹。**仍不支持此删除的 Undo/Redo**，操作后清历史并提示。唯一下一项：[#503](https://github.com/chigre/Picture_Capture/issues/503) 实现可逆 candidate 状态恢复、三文件逆向事务、重复多步/FocusOut/autosave/窗口关闭/跨页行为以及必要真人 Windows R3 验收；之后才可能标记 R3 完成。R2/B2 用户授权暂不验收，仍 `in_progress`，#483 W1–W11 保持 open。无 R4/PR-B。

# Picture_Capture 核心质量升级：跨会话恢复操作规程

**计划 ID：PC-CQ-20261014**。这是用户明确要求的持久任务交接合同。每次新的聊天 / Work / Codex 环境都必须将 GitHub 的实时状态视作真实进度；禁止因为没有聊天记忆而从头实施。

## 最新接力（2026-10-15）：B3/R3 #519 源归属防护；#503 继续未完成

实时 main 起点 e61fd0016da1da43e39dc30d44e66f4c7c60fdfb，合并后四平台 CI [38700426803](https://github.com/chigre/Picture_Capture/actions/runs/38700426803) 成功；启动时无开放 PR。审计发现原 SavedSnapshot 仅保留可变 Entry 对象，撤销判定事后读取 candidate_id，并且提交前未再次验证 OCR cache/manual override。旧候选删除是 manual override→PDIC→简体文件的非原子写入链。

单一在建生产 PR [#519](https://github.com/chigre/Picture_Capture/pull/519)，分支 feat/pc-cq-b3-r3-source-fingerprint-20261015。它复用旧 #503 分支的三条反例，从最新 main 重新组织安全代码：冻结候选 ownership，manual/OCR/SECTION/Profile 路径与字节级提交前核验，历史串链失效清栈，并补并发/外部修改反例。初始 CI [38701396654](https://github.com/chigre/Picture_Capture/actions/runs/38701396654) 在运行；文档提交后必须以最终 PR 头部 SHA 的 CI 为准。CI 未绿不得合并，main CI 未通过不得标记工作包验证。

唯一下一接力：核 #519 最新 CI（Windows/macOS/Ubuntu/Python3.10、架构与 Tk），失败优先修复；成功则审查→合并→postmerge main CI→同步 STATE。之后继续 [#503](https://github.com/chigre/Picture_Capture/issues/503) 的 OCR candidate-linked 删除/人工覆盖与 PDIC/简体多文件事务及 Undo/Redo/Tk 行为，不能仅凭 #519 宣称完成。R2/B2 始终 in_progress，#483 的真人 Windows W1–W11 未验收；R3 亦 in_progress。不碰 PR-B、训练、私人原图与格式迁移。

## B3/R3 当前额外交付范围（PR #519）

#519 当前已扩展为同一主题的一组安全工作：冻结 OCR owner/人工覆盖/OCR/SECTION/Profile 源指纹并于 Undo 最后一刻复核；对“已确认为唯一 candidate 的 ReviewWindow 删除”先生成精确 PDIC/manual_selection/简体三文件目标字节，再用短暂 v2 恢复标记事务写入，**持久化成功才更新 Entry/candidate/Tk checkbox**。跨页重新打开由可信项目 OCR 路径恢复未完成事务。详细见 `CORE_QUALITY_B3_RUNBOOK.md`。修复时同时移除了 app.py 内不可达的旧候选写入分支，未修改架构基线。新增反例、真实 Tk 合成 smoke + 三平台 CI 配置。

**不要误判 R3 完成**：上述 candidate 删除尚不能 Undo/Redo，当前故意清理历史并明确状态提醒；#503 仍包含候选状态恢复/重复复合事务/真人 Windows 操作检查。先看最新 PR #519 HEAD 和固定 SHA CI，不要根据聊天里的中间提交的红/绿灯直接合并。完成 PR/main CI 后，更新 STATE/RESUME/RUNBOOK 并继续 #503。R2 始终 in_progress，#483 W1–W11 保持等待，不开启 R4/PR-B。

## 新会话的一句启动指令（可原样复制）

请继续 chigre/Picture_Capture 的 PC-CQ-20261014 核心质量升级。首先通过 GitHub 读取 docs/roadmaps/CORE_QUALITY_UPGRADE_PLAN.md、docs/roadmaps/CORE_QUALITY_STATE.json、docs/roadmaps/CORE_QUALITY_RESUME.md，再核查实时 main SHA、open PR、最近提交、CI 与实际代码。若文件还在规划 PR 分支，请先定位规划 PR。按 STATE.active_batch 只推进一个主题 PR，可在该 PR 内完成约 2–4 个紧密关联子任务；每项独立验收，并在 PR/CI 状态变化后更新 checkpoint；不要重跑已完成工作。遵守 AGENTS.md/架构守卫，所有实验功能默认关闭，保留人工 PDIC 保护；真实扫描 PR-B 继续延后，不能冒充实测准确率。若发现冲突或并行工作，先只读报告 blocker。

## 强制恢复次序（实施前逐项执行）

1. 读取本规程、MASTER PLAN、STATE，确认 plan_id / plan_version 和 active_work_item。
2. 获取 GitHub 主分支实时 SHA、最近 merged PR、全部 open PR、当前/最近 CI 的明确结论。
3. 读取 AGENTS.md、docs/architecture/CHANGE_POLICY.md、docs/refactor/REFACTOR_STATUS.md 及相关源码/测试；不要把独立的 Phase13 重构状态写入本计划 state。
4. 比对 STATE 中记录的 active PR / SHA / status 与 GitHub。若 PR 已合并而 STATE 仍写 pr_open，先核 CI 与变更是否满足 DoD，必要时单独修正 state，不能重复开启 PR。
5. 检查是否有其他实例正在改同文件、是否存在未完成 CI、merge conflict、失效 checkpoint、权限或依赖阻塞。出现任何不确定，仅做只读检查，提供下一步建议，不并发修改。
6. 若具备写入条件，只推进 **一个 active_batch** 的一个可审查主题 PR；其中允许完成约 2–4 个具有相同测试边界的子任务。逐项记录测试/验收，先补回归反例，再实施并运行目标测试、架构守卫和完整 GitHub CI。超大/异质任务可经 STATE 明确记录后拆包；不同时开启第二个生产 PR。
7. 将实施证据登记到 STATE：before/after SHA、PR URL、CI URL+结论、目标测试、文件、是否已合并、下一步唯一编号、blocking_reason、work_in_progress。CI 正在跑时不得谎报完成。
8. 当 PR 已合并且最新 main CI 通过，才将该批次及其已验收子任务标记 verified；开始下一批次必须确认依赖、状态和用户限制未变。新阶段或目标改变应先更新 PLAN 版本。

## 当前执行（2026-10-15）：#502 已合并并通过 main CI；B3/R3 继续 #503

**[#502](https://github.com/chigre/Picture_Capture/pull/502) 已合并**，main `910b889898efab1ffc2975cdfa613eb675be70ef`；固定版本 [CI 38630143182](https://github.com/chigre/Picture_Capture/actions/runs/38630143182) 和合并后 [main CI 38630567897](https://github.com/chigre/Picture_Capture/actions/runs/38630567897) 均已通过 Windows、macOS、Ubuntu、Python 3.10（含 Tk smoke 和构建）。该工程工作包支持当前会话已保存文字、简体副本和无 OCR 关联单条删除的撤销/重做与中断恢复，**不是整项 R3 完成**。唯一下一工作包：[#503](https://github.com/chigre/Picture_Capture/issues/503) OCR-linked 删除、manual_selection 人工覆盖和复杂组合事务；只能在来源和提交原子性可证明时开放。R2/B2 继续 in_progress、#483 不关闭，真人 Windows W1–W11 未验收。无活跃代码 PR，R4 和真实扫描 PR-B 暂不开始。

### 历史执行记录（#502 开发期）

**一个生产代码 PR #502**：加入会话内保存后的撤销/重做，支持可证明的词名、简体配对副本和无 OCR 候选关联的单条删除；采用 Entry 对象 ID 与当前原图、PDIC、manual_selection、OCR 缓存指纹校验，PDIC+简体文件使用仅在提交时出现的本地崩溃恢复标记。用户未授权永久撤销日志，因此重启后不能继续 Undo。遇 OCR-linked 删除/人工 override 变更、同页其他未保存编辑、来源漂移时拒绝。源码与回归见 `src/picture_capture/proofreading_transactions.py`、`tests/test_b3_review_session_transactions_20261015.py`，详见 [B3 RUNBOOK](CORE_QUALITY_B3_RUNBOOK.md)。**当前 PR 最新 CI 尚待核验，不能冒充 R3 完成。** R2 仍不验收。

## 当前阶段授权（2026-10-15）：R2 暂不验收，立即进入 B3/R3

用户明确改变阶段门槛：**R2/B2 保持 in_progress、#483 与 Windows W1–W11 留待真人验收，允许开始 B3/R3；不得借此把 R2 标为 verified。** 规划升级为 v1.2.0，旧的「B2 不完成就绝对不得开始 R3」仅对此次用户指令豁免。R3 业务事务要先查 ReviewWindow 保存/候选覆盖/简体配对调用链，只有源指纹严格一致的 Undo/Redo 才可实际启用，不能用内存文本倒退冒充 PDIC 已回滚。当前独立工程分支 `feat/pc-cq-b3-review-session-transactions-20261015`，先查 GitHub 实时 PR/CI 再续接。原有真实扫描 PR-B 延后。
 
## 历史入口（2026-10-14）：#500 合并和 main CI 均成功；仅 #483 Windows 真人验收尚需完成

**[#500](https://github.com/chigre/Picture_Capture/pull/500) 已成功合并到 main@`3248882a40606069c9eb5b931c1a690bef87c422`：** 基于已通过四平台 CI 的 main@`8a95e37d592f421d823efbe338942333867ad15c`，一次打包 R2.1/R2.2/R2.3 的“右键词条序号、输入原图 X,Y”具体对象所有权移动操作、post-PDIC evidence、拒绝来源歧义/重合/不同步的边界测试。该功能是明确操作的坐标输入移动，**不是通用自由拖动**；已有 OCR 候选/简体配对/后台批量运行时拒绝。固定提交 [PR CI 38619428582](https://github.com/chigre/Picture_Capture/actions/runs/38619428582) 与 [合并后 main CI 38619848886](https://github.com/chigre/Picture_Capture/actions/runs/38619848886) 四平台均通过；Windows 真人 W1–W11 仍待完成，R2/B2 不标 verified，下一批仍是 B2/#483，不启动 B3 或 PR-B。\n\n## 当前入口（2026-10-14）：#498 已合并且 main CI 通过；B2 仍等待 #483 真人验收与任意移动归属

**#498 已合并到 main@`c1b16d0b8112367f2a5ad816018fe8fd771c91d4`：PR [CI 38616327415](https://github.com/chigre/Picture_Capture/actions/runs/38616327415)、合并后 main [CI 38616790068](https://github.com/chigre/Picture_Capture/actions/runs/38616790068) 均通过四平台；一次交付 R2.1–R2.3 的身份血缘、锁内前驱校验和跨页/旧证据拒绝。无开放生产代码 PR。B2 仍 in_progress：#483 尚需真实 Windows 人工 W1–W8 验收与“任意词条 XY 移动/混合编辑”的操作所有权设计（当前应用未有通用 Entry 拖动事务）。下一批次仍为 B2/#483，不启动 B3 或 PR-B。**

**B0 #479、B1 #481 已通过对应主分支验收。B2 基础记录 #482、真实 Tk 合成核验 #486、同次保存多条独立文字修改的原子证据 #489 也已合并。** 当前 main@`04c02286` 的 [CI 38553009540](https://github.com/chigre/Picture_Capture/actions/runs/38553009540) 与 [CodeQL 38553009318](https://github.com/chigre/Picture_Capture/actions/runs/38553009318) 成功，所有已完成增量均保持用户校对证据默认关闭。#488 双栏行首修复已合并，但未把过去的原图单独像素审计冒充新版本的完整画线基准。**B2 仍未全部验收：Issue #483 继续要求任意 XY 标记移动/混合编辑的操作所有权身份，以及真正由人执行的 Windows ReviewWindow FocusOut/自动保存/跨 SECTION/异常重开检查。** B2 的唯一下一步是 #483，B3 和真实扫描 PR-B 继续延后。

**关键核查位置**：

- src/picture_capture/ocr_page_resume.py — _algorithm_environment_key、input_fingerprint、validated_resume、write_page_resume
- src/picture_capture/app.py — _detect_pages 内的恢复入口及 PDIC 保存
- src/picture_capture/ink_safe_separator.py / separator_y_refinement.py
- src/picture_capture/ocr_tesseract_runner.py / ocr_lazy_secondary.py
- tests/test_ocr_page_resume_20261014.py / tests/test_ocr_engine_cache_lazy_20261014.py
- scripts/architecture_guard.py / .github/workflows/ci.yml

**不可绕过**：即使 Linux 单平台通过，也不能宣称 Windows/macOS 已通过；没有 OCR 环境就明确写出未测试范围；若主分支已修复该风险，记录现有修复证据，不重复提交新实现，然后继续 R0.2。

## 每次会话结束时填写的小结（必须有事实依据）

- plan_id / plan_version / active_work_item：
- 开始时 main SHA / 结束时 main SHA：
- 查到的 open PR / 并行修改信号：
- 本轮实际变更文件、提交 SHA 和 PR URL：
- 已执行的 focused tests + 架构检查：
- 三平台 CI 的 run URL、status 与 conclusion：
- 改动对 PDIC、manual_selection、SECTION、Project Profile、实验开关的影响：
- 完成状态：todo / in_progress / blocked / pr_open / merged / verified：
- 唯一可执行的下一个主题批次（及子任务）：
- 未验证内容 / blocker / 需要用户裁定的问题：

## 何时必须停下

- 计划与代码、PR、CI 不一致；并行工作；有 merge conflict 或不稳定测试；需要改持久化格式；需要用户授权真实扫描、数据上传或自动在线训练；需要调整架构基线；需要超出当前同主题批次范围的多模块设计抉择；发现可能损害人工校对/备份。停止时仍要尽量将可证实状态记入 STATE，**不创造虚假成功状态**。

## 规划文档在哪里

- 仓库：chigre/Picture_Capture
- 文件：docs/roadmaps/CORE_QUALITY_UPGRADE_PLAN.md
- 检查点：docs/roadmaps/CORE_QUALITY_STATE.json
- 本规程：docs/roadmaps/CORE_QUALITY_RESUME.md
- 如 main 暂无这三份文件，查找分支 docs/core-quality-upgrade-plan-20261014 和对应规划 PR；优先把规划文件经 review/CI 合入 main 后再开始实施。
- 规划正文是稳定目标；STATE 是会变化的执行事实；GitHub 实时状态优先于二者的旧状态快照。

## v1.1.0：多子任务主题 PR 规则

- 计划批次和子任务映射见 CORE_QUALITY_UPGRADE_PLAN.md 的“1.1 主题批次计划”；当前首次批次 B1，推荐 2–4 关联点/PR，**可分拆不可强捆**。一个 PR 可一轮完成多个子任务、一次 CI；不必在两个子任务之间等待一小时。
- STATE 必须保存 active_batch、batches[batch].units、batches[batch].status、各个 units 的完成证据以及同一 active PR。先检查旧 PR 和实时 CI，不能重做、不能并发另开第二个生产 PR。
- 文档修订 PR 不等于生产代码 PR。合并后先确认 main CI 通过才开始下一批次。用户特别要求：**简短状态报告、主要进度留在 GitHub，不增加聊天长度**。


## 2026-11-02｜B7b/R7.3 非线性 ROI knot preimage、Canvas/crop 与半开边界

- **唯一活跃生产 PR** 仍为 [#663](https://github.com/chigre/Picture_Capture/pull/663)，Draft/Open/Unmerged；main 仍为 `ec20989ea8c026cca5337293e67850b6b6df30f2`，#503/#562/#483 仍 Open，inline review threads 0。没有 main 写入、合并、force push、第二个生产 PR、issue 关闭或 Ready 转换。
- 新 RED 测试提交 `a59a904bdbc2c4d2895a77bbc74a7c8490ca326b`，[CI #41344061364](https://github.com/chigre/Picture_Capture/actions/runs/41344061364)：六平台/Python3.10/3.13 全部因三项 fractional/boolean crop_box 断言失败；Canvas+crop reverse knot 回归已通过，证明 stage-frame preimage 修复有效。
- 源码修复链：`4b2a1cb1` 将 knot root finding 移到每个 orthogonal stage 的真实输入坐标系；`d589e318` 加入 half-open crop 上边界的 (10^{-7}) px 数值 fail-closed guard；最终 `d87d83e3dc1dcf9b6ec8c39ff38041a438e90f9b` 严格拒绝 fractional/boolean crop_box 坐标，避免 `int()` 有损截断。
- 最终 exact-head [CI #41344312511](https://github.com/chigre/Picture_Capture/actions/runs/41344312511) **6/6 SUCCESS** + Risk-tier/Risk-tier CI gate SUCCESS。Ubuntu 3.13/3.10 各 5352 passed、3 skipped；macOS 3.13 5353/2、3.10 5353/2；Windows 3.13 5353/2、3.10 5352/3。[OCR #41344312514](https://github.com/chigre/Picture_Capture/actions/runs/41344312514) 3/3 SUCCESS；[CodeQL #41344308665](https://github.com/chigre/Picture_Capture/actions/runs/41344308665) Python/Actions 2/2 SUCCESS。Documentation architecture check **SKIPPED，不计为通过**。
- 详见 `docs/architecture/R7_3_NONLINEAR_ROI_KNOT_PREIMAGE_20261102.md`。R7.3 仍为 **in_progress / synthetic E2 only**；bounded root finding 仍未声称可证明任意病态多重/切触 crossing，orthogonal inverse 仍是近似逆。未改 PDIC/PPP/SECTION schema/writer、原图 XY、renderer 或实验默认值；未执行真实扫描、真人 E3 或人工验收。
- **唯一下一步**：对 tangential/non-monotonic knot contacts 做 fail-first 对抗测试，并校验 `OutputCanvasInfo` 尺寸/content_box 为严格整数 raster snapshot；同时审计实际 map construction callsite 的 raw-size/EXIF metadata 传递。继续保持 B7b/R7.3，不推进 B7a profiling、B6 labels 或用户暂缓的 B8。


## 2026-11-02｜R7.3 Canvas raster snapshot — RED-first → source CI/OCR GREEN

- 唯一生产分支仍是 PR [#663](https://github.com/chigre/Picture_Capture/pull/663)，**Draft/Open/Unmerged**；main 未写入，#503/#562/#483 保持 Open。提交前每步核对 PR HEAD，仅对现有分支正常非强制更新，没有新建并行 PR、合并或 Ready 转换。
- **RED:** 测试提交 [f3cb33bc](https://github.com/chigre/Picture_Capture/commit/f3cb33bce1980df6f57a25fccc4af038f034cc08) 在 [CI #41407303817](https://github.com/chigre/Picture_Capture/actions/runs/41407303817) 六个 Python/OS 回归 job 均出现预期失败；Ubuntu 3.13 为 16 failed、5355 passed、3 skipped。复现传入可变 content_box 修改导致已经构造的映射点 X 从 15 变为 25，以及 fractional/bool 非整型画布数据误通过。
- **SOURCE:** [1e7d0541](https://github.com/chigre/Picture_Capture/commit/1e7d054185dd76bad42475396941a6de7d0562d0) 仅修改 preprocess/coordinate_mapping.py：启用的 OutputCanvasInfo 严格校验整数 width/height/content_box，deepcopy + replace 规范化整数 tuple，防止外部内容改变 read-only mapping。测试 tests/test_r7_3_canvas_raster_snapshot_20261102.py 保留合法 canvas/output_canvas_info/NumPy 整数正向控件。
- **Exact SOURCE HEAD:** [CI #41407552831](https://github.com/chigre/Picture_Capture/actions/runs/41407552831) Windows/macOS/Ubuntu × 3.10/3.13 **6/6 SUCCESS**，Risk-tier 和 Risk-tier CI gate SUCCESS，Ubuntu py3.13 为 **5371 passed、3 skipped**；[OCR #41407552811](https://github.com/chigre/Picture_Capture/actions/runs/41407552811) **3/3 SUCCESS**。Documentation architecture check SKIPPED（非 PASS）；当前未独立获取相同 SHA 的 CodeQL Python/Actions 完整结论，不能假定成功。
- 证据与限制：docs/architecture/R7_3_STRICT_CANVAS_RASTER_SNAPSHOT_20261102.md。CORE_QUALITY_STATE.json 已更新，**最终文档 HEAD 会更新，必须重新核对该 HEAD 的 CI/OCR/CodeQL**。R7.3 仍 in_progress；下一步是 non-monotonic/tangential knot preimages、source-size/EXIF 生产调用点及异常变换 fail-closed 的 bounded synthetic regression。无真实性能/准确率基准。
- **NOT PERFORMED / DEFERRED**：Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典页面及实际 PDIC/PPP/SECTION/Profile/OCR save/reopen；R6 verified-label 学习和 R8 扫描均 DEFERRED。未修改人工记录、持久化 schema、原始 source XY、实盘 writer 或实验 OFF 默认。


## 2026-11-02｜B7b/R7.3 tangential knot、malformed transform 与 EXIF frame audit

- 唯一活跃生产 PR 仍为 [#663](https://github.com/chigre/Picture_Capture/pull/663)，Draft/Open/Unmerged；分支 \`refactor/562-retire-root-image-utils-20261024\`。最新 source/test HEAD \`39aaa983f858755f8d18ac0a4278c1d05d641f55\`。未合并、未修改 main、未新建并行生产 PR。
- **Tangential knot tests:** \`tests/test_r7_3_tangential_knot_preimages_20261102.py\` now covers two composed-stage cases: forward local-minimum tangency and reverse local-maximum tangency, each touching a saved knot between ordinary spatial samples without a value sign change. These are bounded synthetic counterexamples, not mathematical certification for arbitrary high-frequency/multiple-extremum warp fields.
- **Malformed LayoutTransform RED:** test-only commit \`04e2e8a6bfa4c735962e6506c616b32abc69c4fe\`, [CI #41433985246](https://github.com/chigre/Picture_Capture/actions/runs/41433985246): all six Windows/macOS/Ubuntu × Python3.10/3.13 matrix jobs failed on the two unhashable list/dict transform-kind inputs. Ubuntu3.10 and Ubuntu3.13 each reported 2 failed, 5417 passed, 3 skipped. Minimal source fix \`39aaa983\` checks string type before set membership; supported identity/mirror/quarter-turn transforms remain unchanged.
- **EXIF source-frame audit:** \`analyze_preprocess_page\` normalizes with \`normalize_page_rgb\` before analysis dimensions/geometry; \`ui.controllers.page\` normalizes the opened page before reading/displaying PDIC/PPP; \`persistence.page_sections\` uses \`ImageOps.exif_transpose\` dimensions for SECTION conversion. Therefore \`PreprocessCoordinateMap.source_size\` is EXIF-oriented. \`raw_source_size\` and \`exif_orientation\` validate metadata only; they do not transform raw annotation XY. No production \`PreprocessCoordinateMap\` construction callsite was found on this PR head, so production propagation and UI wiring are **not claimed**.
- **Exact source/test gates:** [CI #41434426536](https://github.com/chigre/Picture_Capture/actions/runs/41434426536) 6/6 SUCCESS, Risk-tier and Risk-tier CI gate SUCCESS; [OCR #41434426792](https://github.com/chigre/Picture_Capture/actions/runs/41434426792) 3/3 SUCCESS. Counts: Ubuntu3.13 5419 passed/3 skipped; macOS3.13 5420/2; Windows3.13 5420/2; Ubuntu3.10 5419/3; macOS3.10 5420/2; Windows3.10 5420/2. Documentation architecture check SKIPPED, not PASS. Exact-head CodeQL Python/Actions was not independently retrieved; do not infer a pass.
- **Boundary:** R7.3 remains \`in_progress / synthetic E2 only\`. No PDIC/PPP/SECTION schema or writer, original source XY, renderer, OCR policy or experiment default changed. No real dictionary scan, Windows operator E3, #483 W1–W11, #503 human Undo/Redo or real save/reopen was performed. R6 real-label learning and R8 real scan remain deferred.
- **唯一下一步：** continue bounded adversarial review of multiple extrema/rapid coordinate oscillations inside a single already-partitioned orthogonal-stage interval; unresolved paths must fail closed. Preserve EXIF-oriented source frame. Do not wire the map into UI/persistence until a real consumer and ownership semantics receive separate design review.


## 2026-11-02｜B7b/R7.3 单区间多极值失检修复（RED → GREEN）

- 唯一开发 PR [#663](https://github.com/chigre/Picture_Capture/pull/663) 仍 Draft/Open/Unmerged；main 保持 ec20989ea8c026cca5337293e67850b6b6df30f2。RED 测试 SHA `4c64678bc09a3968bf00afaab9b1c8413ca0af61`，[CI #41437504042](https://github.com/chigre/Picture_Capture/actions/runs/41437504042) 六个矩阵任务均按预期因两个 quartic 近邻极值反例失败（Ubuntu3.13 2 failed / 5419 passed / 3 skipped）。
- 最小修复 `1a7919e8e932a63ebcd4eea0b3fd498cd14634a0`：仅在 `preprocess/coordinate_mapping.py` 中将原五点导数探测换为 bounded 1/32 网格，保留原来的有限二分法、half-open crop/边缘样本预算。不能保证任意高频非线性场完全检测，也无真实 benchmark。
- **source/test exact-head** [CI #41452328147](https://github.com/chigre/Picture_Capture/actions/runs/41452328147) 六平台 × 3.10/3.13 **6/6 SUCCESS**、Risk-tier/gate SUCCESS；[OCR #41452328062](https://github.com/chigre/Picture_Capture/actions/runs/41452328062) **3/3 SUCCESS**；[CodeQL #41452320691](https://github.com/chigre/Picture_Capture/actions/runs/41452320691) **Python/Actions 2/2 SUCCESS**。Ubuntu 3.13/3.10 5421 passed/3 skipped；macOS 3.13/3.10 5422/2；Windows 3.13 5421/3、3.10 5422/2。Documentation architecture check SKIPPED（非 PASS）。详细反例与限制见 [R7.3 multi-extrema audit](../architecture/R7_3_BOUNDED_MULTIPLE_EXTREMA_20261102.md)。
- 当前仍为 **synthetic E2 / in_progress**。Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实词典扫描和 save-reopen 全部 **NOT PERFORMED / DEFERRED**，R6 真实标签学习和 R8 真实扫描 DEFERRED。未改原图 XY、PDIC/PPP/SECTION/Profile/OCR writer/schema、图像栅格算法和实验默认 OFF。
- **下一恢复点**：先检查本次文档 HEAD 的 exact-head CI/OCR/Risk-tier/CodeQL 状态；继续 R7.3 有界高频/数值 fail-closed 反例，并审查 R4.2 async epoch/SECTION/crop/save；不将 E2 当人工验收。

## 2026-11-02｜R7.3 多边形路径长度溢出 fail-closed（RED → source GREEN）

- 主干 `ec20989ea8c026cca5337293e67850b6b6df30f2` 未修改，唯一 Draft/Open/Unmerged PR #663 分支 `refactor/562-retire-root-image-utils-20261024`。#503/#562/#483 不关闭；未合并、不改 Ready、不 force、不另开 PR。
- 测试先行 `bf07d77fc3736c400ca8fd844785083f2b056564`：[CI #41456523292](https://github.com/chigre/Picture_Capture/actions/runs/41456523292) 六个 OS/Python job 均因新增四项 OverflowError 反例失败；正常有限 ROI 对照通过。RED 是预期失败，绝不作为绿灯。
- 最小修复 `020931bbedba4e8963c98cda39aef05a6287a58c`：仅 `preprocess/coordinate_mapping.py` 两处 isfinite 保护、8 新增行；遇到数学溢出的 ROI/阶段路径长度时明确拒绝，不再执行 ceil(inf)。
- **source/test HEAD** [CI #41457357693](https://github.com/chigre/Picture_Capture/actions/runs/41457357693) **6/6 SUCCESS**、Risk-tier/gate SUCCESS；[OCR #41457357678](https://github.com/chigre/Picture_Capture/actions/runs/41457357678) **3/3 SUCCESS**；[CodeQL #41457351160](https://github.com/chigre/Picture_Capture/actions/runs/41457351160) **Python/Actions 2/2 SUCCESS**。Ubuntu3.13 5426 passed/3 skipped；macOS/Windows3.13 各5427 passed/2 skipped。Documentation architecture check **SKIPPED（不是 PASS）**。
- 详见 `docs/architecture/R7_3_POLYGON_LENGTH_OVERFLOW_FAIL_CLOSED_20261102.md`。该文档/STATE/RESUME checkpoint HEAD 需重新读取自己独立的 CI/OCR/CodeQL，尚不能继承源码的绿灯。R7.3 保持 `in_progress / synthetic E2`。无实盘 benchmark/F1、无源图 XY/renderer/writer/schema/实验默认变动。
- **NOT PERFORMED / DEFERRED：** Windows R3 E3；#483 W1–W11；#503 人工 Undo/Redo；真实词典扫描与 PDIC/PPP/SECTION/Profile/OCR save-reopen；R6 实标签学习、R8 真实扫描。下一恢复优先核查文档 HEAD 的完整门禁，然后审计 R4.2 before-terminal prefetch 同键重派的 worker owner/epoch/SECTION/crop/save 反例。

## 2026-11-02｜G3 R4.2 首次 terminal 之前的同键 prefetch 重派所有权（RED → source GREEN）

- 实时确认唯一生产 PR #663 仍 Draft/Open/Unmerged，main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未修改；#503/#562/#483 均 Open，无并行生产 PR、force push、合并或 Ready。
- RED `482bd7ad2d10d0c8fa60e7eb6adc2e79c11ea40f`：[CI #41461342776](https://github.com/chigre/Picture_Capture/actions/runs/41461342776) 六个矩阵任务全部因四项 old terminal 抢占新 same-key worker 断言失败；Risk-tier CI gate 失败，不算通过。
- 最小修复 `9cee90ca10b51f860b5e51ae6fb77fc97cdf464e`：仅 `ui/focused_filter_workflow.py` 增加不持久化的每调度 object identity，旧 done/failed 需同时匹配 epoch/key/owner 才有清理或发布权限。
- **source/test HEAD** [CI #41462311384](https://github.com/chigre/Picture_Capture/actions/runs/41462311384) **6/6 SUCCESS** + Risk-tier/gate；[OCR #41462311678](https://github.com/chigre/Picture_Capture/actions/runs/41462311678) **3/3 SUCCESS**；[CodeQL #41462304534](https://github.com/chigre/Picture_Capture/actions/runs/41462304534) Python/Actions **2/2 SUCCESS**。Ubuntu 3.10/3.13 各5430 passed/3 skipped；macOS 3.10/3.13 及 Windows 3.10 各5431 passed/2 skipped；Windows 3.13 为5430 passed/3 skipped。文档架构检查 SKIPPED，不是 PASS。
- 架构审计 `docs/architecture/G3_R4_2_PRETERMINAL_PREFETCH_DISPATCH_OWNER_20261102.md`。本次文档 HEAD 将重新跑独立 CI/OCR/CodeQL，不能沿用源码 HEAD 的绿灯。没有修改真实文件、原图 XY、持久化 schema、实盘 writer、实验默认 OFF；仅 synthetic E2，非 Windows 人工 E3。
- **NOT PERFORMED / DEFERRED：** Windows R3 E3、#483 W1–W11、#503 人工 Undo/Redo、真实扫描词典及 PDIC/PPP/SECTION/Profile/OCR 保存重开；R6 实标签学习、R8 真实扫描。下一恢复优先查文档 HEAD 门禁，然后 R4.2 SECTION/crop/save 剩余所有权争用与既有 Windows 缩略图 smoke 时序风险，不为频率空提交。


## 2026-11-03 | G3 R4.2 focused PDIC final readback drift after last source witness (RED → GREEN)

- main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged; sole PR #663 remains Draft/Open/Unmerged. No merge, Ready transition, force push, parallel production PR or Issue closure.
- Test-first `5cec99d063afde915e0e2edeeb79ee56e02f6872`: [RED CI #41607004651](https://github.com/chigre/Picture_Capture/actions/runs/41607004651), six OS/Python jobs failed on two intended post-readback PDIC mutations; Risk-tier gate FAILURE. Ubuntu 3.13 2 failed/5447 passed/3 skipped.
- Minimal source `0a31856b36ff33b93a686a108b24ac69a9c82ea3`: snapshot exact eight-field PDIC readback bytes and recheck them after final image/SECTION source witness, rejecting new PDIC drift without rollback.
- Exact source [CI #41607380209](https://github.com/chigre/Picture_Capture/actions/runs/41607380209) six jobs SUCCESS, Risk-tier and gate SUCCESS (Ubuntu3.13 5449 passed/3 skipped); [OCR #41607380214](https://github.com/chigre/Picture_Capture/actions/runs/41607380214) 3/3 SUCCESS; [CodeQL #41607374344](https://github.com/chigre/Picture_Capture/actions/runs/41607374344) Python/Actions 2/2 SUCCESS. Documentation architecture check SKIPPED, not PASS.
- Audit: `docs/architecture/G3_R4_2_FINAL_PDIC_READBACK_WITNESS_20261103.md`. This documentation checkpoint requires separate exact-head checks. Cross-file atomicity is **not** claimed; committed bytes are not rolled back, and changes after last verification remain possible. No schema/source XY/real human record/default-OFF change.
- **NOT PERFORMED / DEFERRED:** Windows R3 E3; #483 W1–W11; #503 human Undo/Redo; actual dictionary scan + save/reopen; R6 real-label learning; R8 real scans. Continue allowed source-grounded epoch/SECTION/crop/save regressions; keep #663 Draft.
