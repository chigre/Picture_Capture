# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before new production writes, revalidate `main`, open PRs, relevant callers/import order, and tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5L are complete.**

Phase 4 controller decomposition is complete. Phase 5 has already retired runtime ownership from ordinary drawing, selected-scope single-line crop, unlined export, training export, helper-only ordinary-action debt, LayoutRows visualization capture, local-indent replacement, role-provenance decoration, indent-visibility decoration, and the helper-only Windows GPU module name.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5L
- PR: **#254 — rename Windows GPU helper**
- validated production commit: `440b8ecd2ccea73c8b20eb68f3b6447af7c73e65`
- validated/merged production tree: `fb334f1367939aba49f906415a77c43b4479c409`
- architecture merge: `c78d1217fe8fa82ee85100a6409b58a09ee68d1a`
- previous Phase 5K merge: `2bfedcb17e9058d1b4fd2f8749a6db9690f95592`
- previous Phase 5J merge: `d56456047c51f97e2a2f929dfdab8c77df3db43c`
- Phase 5I #248, 5H #246, 5G #244, 5F #242, 5E #240, 5D #238, 5C #236, 5B #234, 5A #232 are complete.

### Current Windows/Paddle helper ownership
`src/picture_capture/windows_gpu.py` is now an ordinary non-runtime helper. The old `windows_gpu_runtime.py` path is retired.

`configure_windows_nvidia_dlls()` is behavior-identical to the old helper:
- non-Windows: no-op returning `[]`;
- Windows: discovers `site-packages/nvidia/*/bin`, prepends DLL directories to `PATH`, and retains `os.add_dll_directory(...)` handles.

The helper remains deliberately call-time and immediately before Paddle/PaddleOCR imports in:
- `ocr_channel.py`;
- `paddle_headwords_core.py`;
- `document_unwarping.py`;
- `layout_detection_legacy.py`.

Do not centralize this call or move it earlier/later without a separate architecture decision: the import timing is part of the Windows native-runtime contract.

`scripts/verify_ocr_environment.py`, OCR source-contract tests, and `docs/ocr-install.md` use the new path. `windows_gpu_runtime.py` is removed from `LEGACY_RUNTIME_FILES`; do not add `windows_gpu.py` there because it is not runtime-patch debt.

## Phase 5L validation history
The slice was fail-closed throughout.

Initial migration passed diff-shape, architecture guard, and focused tests, but full suite reported **1268 passed / 2 failed**. Both failures were omitted old-path references, not behavior failures:
1. `paddle_headwords_core.py` still imported `.windows_gpu_runtime`;
2. a `test_core.py` source-contract assertion still opened the old file path.
No production tree was published from that run.

After fixing those references, isolated validation passed. A manual architecture review then caught that a mechanical string replacement had incorrectly changed the guard entry to `windows_gpu.py` instead of deleting runtime debt. The guard was corrected and revalidated. A later final-shape gate initially rejected an intentionally historical mention in this checkpoint file; the zero-old-path gate was narrowed to live `src/`, `scripts/`, and `docs/ocr-install.md` surfaces.

Final isolated validation on the actual PR tree:
- final shape / legacy-reference gate: passed;
- architecture guard: passed, with runtime baseline reduced by one;
- focused: **8 passed**;
- full: **1270 passed, 2 existing Pillow deprecation warnings**;
- compileall: passed;
- Ruff F821: passed;
- temporary migration/workflow assets removed before publication.

PR #254 gate on fixed head `440b8ecd2ccea73c8b20eb68f3b6447af7c73e65`:
- Ubuntu CI: passed, including Linux GUI smoke;
- Windows CI: passed, including Windows GUI smoke;
- macOS CI: passed, including macOS GUI smoke;
- compatibility runner, compile, F821, wheel: passed;
- **OCR Platform Smoke passed on Ubuntu, Windows, and macOS**, including real CPU OCR runtime verification;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- GitHub CodeQL aggregate: no new alerts;
- no review threads or review objections.

The separate `github-advanced-security` Copilot/agentic review job failed before reviewing code because GitHub returned **HTTP 402 monthly quota exceeded**. This was an external service-quota failure, not a code/security finding. Do not claim this job passed; use the successful CodeQL Actions/Python and aggregate no-new-alert result as the recorded security evidence for this PR.

Architecture merge `c78d1217fe8fa82ee85100a6409b58a09ee68d1a` retained exactly validated tree `fb334f1367939aba49f906415a77c43b4479c409`.

Post-merge verification on that same tree:
- Ubuntu / Windows / macOS CI: passed;
- GUI smoke: passed on all applicable platforms;
- compatibility / compile / F821 / wheel: passed;
- OCR Platform Smoke: passed on Ubuntu / Windows / macOS;
- CodeQL Actions: passed;
- CodeQL Python: passed.

## Current explicit Phase 5 ownership
- Ordinary drawing: app wrapper → `DetectionController`; OCR-independent quick-setting helper is `ordinary_quick_settings.py`.
- Selected-scope single-line / unlined export: app wrapper → `CropController` → app-owned shared parallel batch runner.
- Training package: app wrapper → `ExportController`; bootstrap no longer replaces the method.
- Layout visualization: LayoutRows capture, corrected indent geometry, provenance, visible indent drawing, and prepared-count diagnostics are all non-runtime/static ownership.
- `unlined_fast_path_runtime.py` remains intentionally because CropController resolves its worker at action time and the fast worker is still an import-order/performance seam.

## Recommended next slice — Phase 5M
**Retire `unicode_nonbmp_input_runtime.py` method monkey-patching by making the Windows/Tk bridge an explicit `PictureCaptureApp` lifecycle dependency.**

Fresh read-only inspection after Phase 5L shows:
- the module owns the Windows/Tk 8.6 non-BMP repair algorithm and native hooks, which should remain behavior-identical;
- its dynamic debt is narrow: `install_nonbmp_unicode_input(app_module)` wraps only `PictureCaptureApp.__init__` and `PictureCaptureApp.destroy`;
- the installer has one production caller in GUI bootstrap;
- dedicated tests already cover the repair planner and bootstrap installation ordering.

Safest Phase 5M architecture:
1. rename/move the algorithm + `_WindowsNonBmpBridge` to non-runtime `unicode_nonbmp_input.py`;
2. expose small explicit attach/close helpers (or equivalent lifecycle functions) without changing native-hook logic;
3. have `PictureCaptureApp` initialize the bridge at the same point currently reached after its original `__init__` completes, and close it before normal destroy completes;
4. remove only the GUI bootstrap installer import/call;
5. ratchet `unicode_nonbmp_input_runtime.py` out of `LEGACY_RUNTIME_FILES`;
6. add lifecycle regressions proving non-Windows/Tk9 remain no-op, Windows/Tk8 attaches once, and destroy closes the bridge;
7. preserve all existing planner/native-hook tests and run Windows GUI smoke as a hard gate.

Do not combine 5M with overlay opacity/anchor, layout detection/recovery, spawn workers, ordinary-large-head, or unlined fast-path work.

## Remaining runtime seams after Phase 5L
Treat these as real compatibility/algorithm/performance seams until individually proven:
- `entry_classification_runtime.py`;
- `illustration_fill_opacity_runtime.py`;
- `layout_character_height_runtime.py`;
- `layout_column_drift_runtime.py`;
- `layout_illustration_mask_runtime.py`;
- `layout_row_recovery_runtime.py`;
- `ordinary_large_head_runtime.py`;
- `overlay_line_anchor_runtime.py`;
- `overlay_opacity_runtime.py`;
- `spawn_detection_runtime.py` / `spawn_layout_runtime.py`;
- `unicode_nonbmp_input_runtime.py` (recommended Phase 5M);
- `unlined_fast_path_runtime.py`.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
