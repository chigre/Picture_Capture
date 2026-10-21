# Issue #562: Entry descriptor helper ownership (2026-10-21)

Candidate based on main `710b92c1766f318d9303e9ee71ad0ee7abd64817`.

- Physical move: `src/picture_capture/entry_classification_fields.py` → `src/picture_capture/proofreading/entry_classification_fields.py`. No root shim.
- All eight lazy `models.Entry` property delegations now resolve the proofreading owner. The registry in `entry_classification.py` remains root-owned pending independent cycle and serialization review. `proofreading/__init__.py` remains import-light.
- Recycled-object-ID detection, manual scale override, auto-source and height semantics remain unchanged; no PDIC/PPP/SECTION/Profile, GUI, GPU, Windows spawn or Y-refinement algorithms changed.
- Source ownership guard and focused test prevent accidental root restoration. Independent complete-tree count: 49 → 48 root Python modules (887 total Git tree entries, not truncated).
- Exact-head tri-OS × Python3.10/3.13, GUI smoke, wheel, CodeQL, review and postmerge main checks must pass before accepting this candidate. Real scanned-page/native Windows GUI/GPU parity is not yet verified.
- Provisional remaining roots: public/entry 11, persistence/review 8, UI compatibility 3, layout 7, OCR/GPU/runtime 9, refinement 2, image 2, evidence 2, crop export 2, training compatibility 2 = 48. Root reduction is not the fraction of eligible modules completed.

This supplemental checkpoint is intentionally separate from the main ownership roadmap; updating the roadmap in place is still pending because the GitHub connector blocked replacement of its large existing content. The authoritative cross-run checkpoint is Issue #562.

## Rebase checkpoint 2026-10-22

Prepared as a clean tree overlay on merged main `19fdcddaf6190de35dfcc8f071dded92a4cc9dbe`, retaining the separate #596 proofreading guard. Base now 47 root Python files, candidate target 46; exact candidate CI, review and merge are not yet complete. The former 49→48 numbers above refer only to the original staged predecessor branch.
