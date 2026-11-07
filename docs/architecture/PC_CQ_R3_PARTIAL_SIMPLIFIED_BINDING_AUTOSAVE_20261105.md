# PC-CQ R3 — ordinary autosave must prove simplified row ownership

Date: 2026-11-05. Scope: sole Draft PR #663 on `refactor/562-retire-root-image-utils-20261024`; main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged. Synthetic E2 only.

## Actual boundary
`review_page_lifecycle.autosave_commit` already rejects stale original-row owners. However its simplified dirty probe `_has_unreported_simplified_input` returns `False` if `_owned_rendered_simplified_rows` cannot establish complete row provenance. During a partially rebound simplified Tk column, unchanged original text plus no dirty flag could thus be misclassified as clean, clearing `_r3_autosave_unconfirmed` without committing human simplified text. A later independent PPP write could report an unqualified "已自动保存".

## Invalid hypothesis explicitly withdrawn
The initial test-only `d6ec9f7bc43b3a97f6ea66a57640ab41ba0c0788` used an impossible `processing`/inactive-batch state. `batch_workflow._foreground_batch_state` needs an active foreground batch, and the main autosave skips worker-owned pages before PPP writes. Although CI was RED, this fixture does not establish a production defect and was replaced before production modification.

## Real RED → minimal fix → exact-source GREEN
- Corrected synthetic test-only: `fe3bc0b58caabf2738621fe6b76ff7f749dec51a`, `tests/test_r3_processing_review_autosave_truth_20261105.py`. [RED CI #42037267952](https://github.com/chigre/PictureCapture/actions/runs/42037267952): Ubuntu Python3.13 1 intended failed / 5730 passed / 3 skipped; macOS Python3.10 1 intended failed / 5731 passed / 2 skipped. Positive fully-bound no-op control passed.
- Minimal source: `b9c2cc17f7c7a5049318ba6d2d79bb0d065ba29b` modifies only `src/picture_capture/ui/review_page_lifecycle.py`. When original rows are present and the simplified column exists, it uses the established strict `_owned_rendered_simplified_rows` verifier before treating the page as a no-op. On failure: mark unconfirmed, preserve input, emit actionable status, block main fallback PDIC write; on fully-bound clean row: unchanged success semantics.
- [GREEN CI #42037758677](https://github.com/chigre/PictureCapture/actions/runs/42037758677): six Windows/macOS/Ubuntu × Python3.10/3.13 SUCCESS, Risk tier + gate SUCCESS, Ubuntu3.13 5731 passed / 3 skipped. [OCR #42037758732](https://github.com/chigre/PictureCapture/actions/runs/42037758732) 3/3 SUCCESS. [CodeQL #42037751783](https://github.com/chigre/PictureCapture/actions/runs/42037751783) Python/Actions 2/2 SUCCESS. Documentation architecture check SKIPPED, NOT PASS.

## Safety boundaries and follow-on
No user files, dictionary, real OCR, real operator GUI, durable format/schema, source XY, experiment opt-in or existing R3 authorization protocol was changed. A diagnostic status is not a persistence acknowledgment. Synthetic tests do not prove Windows E3 or actual save/reopen. Do not claim filesystem CAS, cross-file OS transactions, or accuracy/performance gains. Current docs commit must receive an independent exact-head gate.

Next: check LIVE #663/new docs SHA, complete six-matrix + Risk/gate + OCR + dynamic CodeQL jobs, and only then pursue a NEW synthetic R3 ordinary save/partial-redraw or R4.2 asynchronous epoch/worker/SECTION/crop-save owner counterexample. Old corrected PDIC image/SECTION final witness is historical GREEN unless a new counterexample exists. Human Windows E3, #483 W1–W11, #503 Undo/Redo, real scan/save-reopen, R6/R8 remain NOT PERFORMED/DEFERRED.
