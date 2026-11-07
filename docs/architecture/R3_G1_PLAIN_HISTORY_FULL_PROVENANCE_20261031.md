# PC-CQ R3 / #503 — Plain saved-text Undo/Redo full source-provenance refusal

Date: 2026-10-31. Only [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) is active and still not Ready/merged; main remains `ec20989ea8c026cca5337293e67850b6b6df30f2`. All fixtures here use generated text bytes, never private scans.

## Boundary proven by red-first CI

`proofreading/transactions.py::ReviewSessionHistory._apply` only reaches its fallback source diagnostic when `snapshot_review(review)` returned `None`, e.g. Tk rows have temporarily lost their binding during a redraw. To distinguish transient unbound widgets from changed authoritative files, that diagnostic checked the original page fingerprint and exact PDIC and simplified sidecar bytes, but **omitted** the original manual-selection, OCR, SECTION and Profile sources. When any of these changed externally, the old Undo/Redo stack was erroneously retained while Tk was not ready. A later full successful snapshot would ordinarily reject an actual drift; nonetheless the temporary diagnostic must not advertise unsafe retryability or keep stale ownership.

Test-first `dc306c3613b342eccadf02c1adcc342ac6dc1b03` added a self-contained `tests/test_r3_plain_history_missing_sidecar_provenance_20261031.py` with **24 negative cases** (four sources × Undo/Redo × foreign write, deleted file, denied read), plus **two positive controls** for unchanged source bytes and a temporary Tk rebind. [Red CI #41192052020](https://github.com/chigre/Picture_Capture/actions/runs/41192052020) Ubuntu Python3.13 actually finished **24 failed, 5,087 passed, 3 skipped**; all failures were in the added targeted source-drift suite, and both unchanged-source controls passed. The red test-only commit is **not** accepted as a passing gate.

## Minimal production correction

`20fb3dffd2b63cdd9de39f5633617f37146766ac` adds exact original `manual_bytes`, `ocr_bytes`, `section_bytes` and `profile_bytes` comparisons to `ReviewSessionHistory._apply`'s existing `snapshot_review is None` diagnostic; denied/invalid reads (`OSError`, `ValueError`, `TypeError`) fail closed without propagating exception details into Tk. The unchanged-source case still retains the single-window history for an explicit retry after row rebinding. The ordinary PDIC/simplified transactional writer, source XY, Entry membership, persisted manual selections, OCR candidates, Profile and Settings formats are entirely unchanged.

This is deliberately consistent with the stricter candidate-owned delete Undo/Redo diagnostic previously addressed in `candidate_history.py`. It does not prove complex mixed Undo/Redo or simultaneous user/foreign writer serialization, nor introduce permanent Undo storage.

## Required exact-final-head E2 and honest open gates

Fixed-source [CI #41192150071](https://github.com/chigre/Picture_Capture/actions/runs/41192150071), [OCR #41192150102](https://github.com/chigre/Picture_Capture/actions/runs/41192150102) and [CodeQL #41192147651](https://github.com/chigre/Picture_Capture/actions/runs/41192147651) were running when this audit was written; the **final documentation HEAD after this file and STATE/RESUME must itself** pass Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 plus Risk-tier CI gate**, OCR **3/3**, CodeQL Python/Actions **2/2**. Conditional Documentation architecture check SKIPPED does not count as a successful job. Never substitute the test-only red SHA or an intermediate source SHA for final E2.

Still **NOT PERFORMED/DEFERRED**: Windows operator R3 E3, [#483](https://github.com/chigre/Picture_Capture/issues/483) W1–W11, full [#503](https://github.com/chigre/Picture_Capture/issues/503) compound original/simplified/candidate Undo/Redo, real dictionary-page crop/OCR/PDIC/PPP/SECTION save-reopen, large-image performance, R6 independently checked manual truth labels, R8 real scans. No Ready, merge, issue closure, skipped red jobs, automation-only claims of human acceptance, or private data uploads.
