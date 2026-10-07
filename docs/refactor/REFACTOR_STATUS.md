# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup is complete. Phase 5A through Phase 5AA are closed.**

Phase 4 controller decomposition is complete. Phase 5 has removed all production `*_runtime.py` compatibility modules and moved their behavior into explicit/static owners while preserving tested behavior.

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

## Recommended next phase — Phase 6 planning
**Do not begin proxy deletion as an implicit continuation of Phase 5. First define the compatibility contract for dynamic facades.**

Safest Phase 6 planning questions:
1. Which facade/private names are intentionally public or used by external plugins/tooling versus tests only?
2. Which monkeypatch assignments must continue to propagate into the historical core module?
3. Can those seams be replaced by explicit dependency injection / test hooks / public adapters without changing external behavior?
4. Which facade is the smallest independently removable proxy after characterization?

Initial read-only assessment:
- `paddle_headwords.py` is the smallest file but not necessarily the safest first write because its historical public module path is exactly where monkeypatch compatibility is expected.
- `evidence_fusion.py` has a more bounded core-mutation surface (supervised OCR decision refinements) but contains substantial behavior and shares the proxy class with `paddle_headwords`.
- `processing.py` has the broadest compatibility surface and should not be first.

Therefore the next step should be a **read-only Phase 6A compatibility inventory**, not immediate production deletion. A production Phase 6A slice should be chosen only after that inventory proves a bounded contract.

## Standing continuation authorization
The user's standing authorization covered continuation of Phase 5 runtime-patch cleanup without stopping at normal ownership decision points. Phase 5 is now complete.

Crossing into Phase 6 changes the debt class from runtime installers to historical module-proxy/public monkeypatch compatibility. Production writes should begin only after the Phase 6 compatibility inventory establishes a bounded slice. Read-only assessment may continue immediately.

Stop production writes for unexplained behavior/test/CI failure, public/file-format compatibility uncertainty, concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
