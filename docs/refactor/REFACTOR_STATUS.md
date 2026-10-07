# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 6 — dynamic facade/proxy compatibility cleanup is underway. Phase 6B replaces supervised import-time core mutation with explicit call hooks.**

Phase 4 controller decomposition and Phase 5 runtime-patch cleanup are complete. Phase 5 remains closed: all production `*_runtime.py` modules are gone and the zero-runtime-debt architecture ratchet remains active.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Final Phase 5 checkpoint — Phase 5AA
- precondition/help-contract repair PR: **#287 — repair illustration-mask checkbox help contract**
- Phase 5AA production PR: **#288 — remove final illustration-mask runtime seam**
- Phase 5AA production base: `72bd7d22fd84c7e8f30c1a57616aaace681ed8d2`
- production head: `a5ab7206840bfc01fde66863adf5b3a8cba5bf15`
- validated/merged production tree: `def12146459e5a82d924b58fed56add116ce356f`
- production merge / current architecture main: `9ec52afe99647e74ffd5d2d62f1bbe8d3dc7d7e6`

### Pre-Phase-5AA help-contract repair
Read-only preparation for the final runtime deletion found that the native/static Settings schema had the illustration-mask label/help text needed for the final move, but the dedicated checkbox help contract needed an explicit regression before deleting the runtime source.

PR #287 was deliberately narrow:
- add the dedicated `CHECK_HELP["layout_mask_illustrations"]` contract using the same wording already owned by the runtime seam;
- add focused regression coverage;
- do not change checkbox order, cache key, masking behavior, settings persistence, or runtime ownership.

PR #287 gates:
- CI run **2119**: passed;
- CodeQL run **2100** Actions/Python: passed;
- Advanced Security run **1852**: passed.

PR #287 merged as `72bd7d22fd84c7e8f30c1a57616aaace681ed8d2`.

Post-repair main verification:
- CI run **2120**: passed;
- CodeQL run **2101** Actions/Python: passed.

### Final static illustration-mask Settings/cache ownership
Phase 5AA removed the last production runtime module, `layout_illustration_mask_runtime.py`.

The final static ownership is:
- `AppSettings.layout_mask_illustrations`: native dataclass setting/default/persistence;
- Settings Center checkbox ordering: static `ui/settings/schema.py`, immediately after `ordinary_auto_layout`;
- Settings Center label/help: static settings schema/help metadata;
- illustration detector: static `processing_core.detect_illustration_regions_from_image(...)`;
- mask policy/diagnostics: non-runtime `layout_illustration_mask.py`;
- Page Understanding masking/fail-open/lifetime: static `processing._understand_page_current(...)`;
- training-export masking: static `layout_illustration_mask.mask_large_illustrations_for_layout(...)`;
- Layout visualization invalidation: static `layout_visualization_ui._layout_cache_key(app)`, preserving the historical setting-name + boolean tuple contribution;
- GUI bootstrap no longer imports/calls an illustration-mask runtime installer.

Phase 5AA intentionally did not change masking thresholds, detector behavior, PPP/crop formats, settings persistence, Page Understanding routing, training export, or GUI wording.

### Phase 5AA production gate
PR #288 publication shape:
- **1 commit / 6 changed paths**;
- runtime file deleted;
- architecture guard ratcheted runtime debt to zero;
- review submissions: none;
- review threads: none;
- PR comments: none.

Fixed-head PR #288 gates:
- CI run **2121** Ubuntu/Windows/macOS: passed, including pytest, platform GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL run **2102** Actions/Python: passed;
- Advanced Security run **1853**: passed.

PR #288 merged as `9ec52afe99647e74ffd5d2d62f1bbe8d3dc7d7e6`, retaining production tree `def12146459e5a82d924b58fed56add116ce356f`.

### Phase 5AA post-merge verification
On `main@9ec52afe99647e74ffd5d2d62f1bbe8d3dc7d7e6`:
- push CI run **2122**: passed;
- CodeQL run **2103** Actions/Python: passed;
- merge tree exactly matches `def12146459e5a82d924b58fed56add116ce356f`.

Structural Phase 5 completion proof:
- recursive `main` tree contains **zero** `src/picture_capture/**/*_runtime.py` files;
- `scripts/architecture_guard.py` now has `LEGACY_RUNTIME_FILES: set[str] = set()`;
- future production `*_runtime.py` additions therefore fail the architecture ratchet.

## Completed Phase 5 ownership milestones
- Phase 5A–5K: earlier runtime/controller compatibility slices completed; details remain in checkpoint history.
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native settings + static UI/rendering ownership.
- Phase 5P: illustration fill opacity became native settings + static UI/rendering ownership.
- Phase 5Q: long-band logical row recovery became static.
- Phase 5R: character-height fallback became static.
- Phase 5S: column-drift remeasurement became static.
- Phase 5T: identity-only spawn-layout wrapper was removed.
- Phase 5U: spawn-safe ordinary worker became static `processing.detect_entries_job`.
- Phase 5V: guarded oversized-head detection and row/fusion authorization became static.
- Phase 5W: unlined physical-row fast worker became static.
- Phase 5X: Layout-entry classification and existing-marker crop/OCR became static processing ownership.
- Phase 5Y: illustration-mask setting became native and shared detector ownership became static.
- Phase 5Z: illustration masking policy/diagnostics and Page Understanding preprocessing became static.
- Phase 5AA: Settings Center metadata and Layout cache invalidation became static; the final runtime module was deleted.

## Current architecture ratchets
Runtime-installer/module debt is now zero.

The next explicit compatibility debt category in `architecture_guard.py` is dynamic module proxy/namespace mirroring:
- `processing.py`;
- `evidence_fusion.py`;
- `paddle_headwords.py`.

These facades are not equivalent to the retired runtime seams. They preserve a long-standing monkeypatch/debug compatibility contract where assignments to facade/private names are mirrored into historical core modules. Removing the proxy class or namespace copying without first defining that compatibility contract could break tests, plugins, debugging workflows, or external tooling even if normal application execution remains green.

Current approximate facade sizes on final Phase 5 main:
- `paddle_headwords.py`: ~2.9 KB, but its module-class proxy is inherited from `evidence_fusion` and protects the public historical import path;
- `evidence_fusion.py`: ~18.2 KB and also patches supervised decision functions into `paddle_headwords_core`;
- `processing.py`: ~23.3 KB and mirrors many historical `processing_core` symbols while owning current detection behavior.

## Phase 6A bounded contract
Read-only inventory separated two previously conflated behaviors: import-time core mutation and public assignment mirroring.

Observed compatibility contract on the Phase 5 completion baseline:
- direct monkeypatch/integration usage targets the historical public `paddle_headwords` path, including `get_paddle_engine`, `run_paddle_band`, and `refine_separator_y`;
- no direct assignment-mirroring dependency was found for the implementation module `evidence_fusion`;
- existing supervised-fusion regression explicitly requires `filter_headword_records` and `_annotate_peer_typography_matches` to remain patched into `paddle_headwords_core` at import time;
- `processing.py` still has the broadest namespace/proxy surface and remains out of scope for the first Phase 6 write.

Phase 6A therefore narrows, rather than deletes, compatibility behavior:
- `evidence_fusion` returns to ordinary module assignment semantics;
- the module-class proxy is owned directly by the historical public `paddle_headwords` facade;
- assignments on `paddle_headwords` still mirror to an existing same-named core attribute;
- the supervised import-time core patches remain unchanged;
- namespace copying from `paddle_headwords_core` remains unchanged;
- architecture guard now ratchets namespace copying and module-class proxying as separate debt categories.

This removes one dynamic module-class proxy instance without changing OCR decision behavior, supervised rescue behavior, public import paths, or the established public monkeypatch contract.

## Phase 6B explicit supervised-hook contract
Phase 6B removes the two default import-time assignments from `evidence_fusion` into `paddle_headwords_core`:
- `_core.filter_headword_records = filter_headword_records`;
- `_core._annotate_peer_typography_matches = _annotate_peer_typography_matches`.

The mature core now exposes two optional call hooks without changing existing callers:
- `filter_headword_records(..., peer_typography_annotator=None)` defaults to the native core annotator;
- `detect_paddle_headwords(..., record_filter=None)` defaults to the native core filter and uses the selected filter consistently for Paddle, Tesseract, and Lens.

`evidence_fusion` explicitly injects the supervised annotator into its filter wrapper and explicitly injects the supervised filter into its detector wrapper. Historical public monkeypatch behavior remains authoritative: if the public facade has mirrored a different same-named core callable, the wrapper preserves that override instead of replacing it.

This is a behavior-preserving ownership change:
- importing `evidence_fusion` no longer mutates either supervised core symbol;
- direct core callers retain native behavior by default;
- the public OCR boundary path still receives the supervised behavior;
- the `paddle_headwords` assignment-mirroring contract remains unchanged;
- `processing.py` remains untouched.

Because `paddle_headwords_core.py` had only eight bytes of growth headroom under the oversized-module ratchet, the hook change also trims redundant detector documentation so the core shrinks rather than grows. The architecture guard now forbids the two retired evidence-fusion assignment forms from returning.

## Recommended next slice — Phase 6C
Characterize the remaining `evidence_fusion` namespace copy (`vars(_core).items()`) and replace it only if an explicit export surface can preserve all historical private/public imports. Keep `processing.py` out of scope until the narrower Paddle/evidence facade debt is exhausted.

## Standing continuation authorization
The user has authorized faster continuous progression through confirmed-safe Phase 6 slices without stopping for a checkpoint after every small change. Phase 6A compatibility inventory established the first bounded production slice.

Continue across related low-risk changes once contracts and focused tests are clear. Use checkpoints at phase milestones, material compatibility-boundary changes, plan changes, merge/finalization boundaries, or when recovery state would otherwise become ambiguous.

Stop production writes for unexplained behavior/test/CI failure, public/file-format compatibility uncertainty, concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
