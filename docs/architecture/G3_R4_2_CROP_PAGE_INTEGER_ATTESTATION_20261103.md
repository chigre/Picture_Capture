# G3 R4.2 — Crop prefetch source-witness integer page identity

**Date:** 2026-11-03 SGT. **Sole PR:** #663 Draft/Open/Unmerged, main `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Source/test HEAD:** `8b2ac2cd8b16db1891e50acb50577c7578f39680`.

## RED-first finding

Page identity was used as a source-ownership key but coerced using `int()` in three connected paths: `focused_crop_source_witness` target-page collection, `focused_save_source_from_crop_witness` selection and the Tk crop-publish call site. Fractional page 0.9 silently became page 0, page 1.9 became 1, booleans became 0/1 and text '0'/'1' could be accepted. These invalid tokens could claim a real other page's source attestation rather than fail closed.

[Test-only `650684ea`](https://github.com/chigre/Picture_Capture/commit/650684ea2e74121d57954be22d8e3b10cea8538d) adds 14 isolated assertions using disposable 8x8 BMPs and synthetic PDIC bytes: six malformed crop input page ids, six malformed extracted-save ids, the UI call-site raw-owner requirement, and a valid integer positive control. [RED CI #41612103458](https://github.com/chigre/Picture_Capture/actions/runs/41612103458) failed all six OS/Python matrix jobs on intended tests, Ubuntu Python3.10 **13 failed, 5461 passed, 3 skipped**. RED Risk-tier gate failed. These failures are *proof of the old gap*, not accepted release checks.

## Minimal fix and exact source-head evidence

[Source fix `8b2ac2cd`](https://github.com/chigre/Picture_Capture/commit/8b2ac2cd8b16db1891e50acb50577c7578f39680) uses `operator.index` and rejects booleans. Both crop witness creation and saved-crop attestation require a true integral page identity; malformed selections fail or return None. UI forwards the original `target["page_index"]` to validation rather than coercing it first.

- [CI #41612191423](https://github.com/chigre/Picture_Capture/actions/runs/41612191423): Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, Risk tier and Risk-tier gate **SUCCESS**. Ubuntu3.13 **5474 passed/3 skipped**.
- [OCR #41612191427](https://github.com/chigre/Picture_Capture/actions/runs/41612191427): **3/3 SUCCESS**.
- [CodeQL #41612184011](https://github.com/chigre/Picture_Capture/actions/runs/41612184011): Python/Actions **2/2 SUCCESS**.
- Documentation architecture check **SKIPPED, not PASS**; documentation checkpoint HEAD requires its own checks.

## Safety boundaries / outstanding evidence

Only internal owner-key validation and the Tk argument handoff change. No source image editing, OCR rerun, coordinate/pixel conversion, project data mutation, PDIC/PPP/SECTION/Profile schema modification, new telemetry, model access or save retry. This remains synthetic E2, not actual operator workflow E3.

Windows R3 E3, #483 W1–W11, #503 human Undo/Redo, real dictionary scan/save-reopen, R6 and R8 real-data validation are NOT PERFORMED/DEFERRED. Keep PR #663 Draft/Open/Unmerged and Issues #503/#562/#483 open. No merge or Ready transition.
