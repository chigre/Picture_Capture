# PC-CQ existing-route closeout — five retained root owners (read-only inventory)

**2026-11-04 JST** · [#562](https://github.com/chigre/PictureCapture/issues/562) · sole Draft [PR #663](https://github.com/chigre/PictureCapture/pull/663), source `252808dc724e243938f63df7d9fcc858d42e607d` · main `ec20989ea8c026cca5337293e67850b6b6df30f2`.

This is **not** a replacement P0–P4 roadmap and is **not** a merge authorization. Exact GitHub repository contents show the main branch has **15** direct Python modules under `src/picture_capture/`, while the Draft PR now has **5**, a physical reduction of ten. Both counts include `__init__.py` and `__main__.py` and reflect different branch snapshots; no root-compatibility duplicates may be added.

| Current Draft root Python owner | Reason to retain until a separately verified compatibility migration |
|---|---|
| `__init__.py` (113 B) | Import-light package metadata; naked `import picture_capture` must not start OCR/Tk/Paddle |
| `__main__.py` (159 B) | Python module application entry wrapper |
| `app.py` (152,823 B) | Historical Tk application/callback surface; substantial code has already moved into `ui/`, but this remains a large compatibility/controller owner |
| `models.py` (7,842 B) | Public model and pickle identity for `AppSettings`, `Entry`, `PolygonRegion`, `ProjectState` |
| `ocr_channel.py` (11,793 B) | Public OCR channel and pickle ownership for `OcrTextChoice`, `OcrChannelPlan` |

The existing `scripts/architecture_guard.py` enforces **at most five** root Python modules, limits newly oversized production modules to **100,000 bytes**, and prevents retired shim paths from returning. Those checks must remain monotonic. A future reduction of `app.py`, `models.py` or `ocr_channel.py` cannot be counted as successful if it silently changes module/pickle identity, GUI patch points, user settings, imports or persisted schemas.

## Original-plan closure gates still outstanding

- **Engineering:** preserve one Draft PR until exact HEAD CI, Python3.10/3.13 × Windows/macOS/Ubuntu, Tk native smokes, wheel, OCR 3-OS, CodeQL Python+Actions, architecture and package guard are verified. `#562` P10 root ownership rationalization is engineering-progress only while PR remains unmerged; after any approved merge, verify main-push CI separately.
- **R3 / #503:** manual candidate-linked compound Undo/Redo and Windows operator E3 cannot be inferred from Tk synthetic tests.
- **R2 / #483:** Windows interactive W1–W11, durable arbitrary moved XY ownership, multi-page and save-reopen remain NOT PERFORMED.
- **R4:** bound scan/crop/SECTION/PDIC provenance, retries, UI source session, and intermittent macOS native Tk in-flight reversion conflict require continuous fail-closed engineering validation. The present work item is detailed in `G3_R4_2_EXACT_SAVE_CALLBACK_OWNER_20261104.md`.
- **R5/R7:** retain previously proven synthetic score/geometry parity; do not mark real OCR outcomes as verified.
- **R6/R8:** real labels, training and actual scans remain deferred pending user authorization. No private images, source dictionaries or labels are uploaded automatically.

The final audit after the *existing* PC-CQ route stabilizes can then plan a separate next optimization phase. Until then do not expand to the supplied alternative P0–P4 algorithm proposal, switch OCR defaults, or weaken default-OFF safeguards.
