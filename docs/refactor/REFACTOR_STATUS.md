# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub live state is authoritative: revalidate `main`, open PRs, and the relevant source paths before writing production code. Historical SHAs below are checkpoints, not assumptions about the future live HEAD.

## Current milestone
Modular architecture refactor

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A is complete.**

Phase 4 controller decomposition is complete through the approved Detection batch-processing boundary. Phase 5A retired the first runtime method monkey-patch, `ordinary_action_runtime.install_ordinary_action_runtime(...)`.

## Architecture checkpoint
- Last completed architecture PR: **#232 — Phase 5A: retire ordinary action runtime monkey patch**
- Phase 5A architecture merge commit: `5f4bf0707fe32a52ab1af1f39a64652d8fcc9874`
- Previous Phase 4Y architecture PR: #230 — `auto_detect_current(...)` routed through `DetectionController`
- Phase 4Y merge commit: `6b5af293232039102fddcf90bb51c6a2373023e7`
- Phase 4X PR: #229 — `batch_ocr()` routed through `DetectionController`
- Phase 4X merge commit: `704936dfe90c5132f130475a2ff199cd4bc3d9ab`
- Previous headword-fill PR: #227 — source selection / fill routed through `HeadwordController`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none after the Phase 5A checkpoint is merged
- Work in progress: false

## Current controller structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

`DetectionController` now owns the complete user-facing detection action-entry set plus the approved batch/current-page orchestration:
- ordinary OCR-independent drawing: `run_normal_draw_action()`
- current Paddle setup: `paddle_detect_current()`
- selected-scope combined/OCR draw entry actions
- scoped OCR draw routing
- full-project `batch_auto_detect()` routing
- full-project `batch_ocr()` worker/persistence orchestration
- current-page `auto_detect_current(...)` worker/batch bridge, including clicked-column replacement and combined-mode blank-text rescue

`PictureCaptureApp.run_normal_draw_action()` is now an explicit compatibility wrapper and delegates to `DetectionController.run_normal_draw_action()`; GUI bootstrap no longer replaces that method dynamically.

The app still owns the generic `_start_batch_task(...)` runner, `_detect_pages(...)` multi-page detection pipeline, transformed-geometry guard, page tuple generation, shared page/review/quality refresh helpers, and broader UI/persistence infrastructure. Phase 5A deliberately did not extract these.

`ExportController`, `HeadwordController`, and `ReviewController` retain the ownership recorded in the Phase 4 checkpoints. `pdic_restore.py` remains the deterministic low-level PDIC restore/publication boundary.

## Completed Phase 5A seam — ordinary drawing runtime patch
Before Phase 5A, three layers coexisted:
1. `PictureCaptureApp` already contained a legacy `run_normal_draw_action()` body using the normal quick-settings validator;
2. `ordinary_action_runtime.install_ordinary_action_runtime(...)` replaced that method at GUI bootstrap time;
3. the runtime replacement supplied the important OCR-independent validation behavior needed when all visible OCR engines were disabled.

Phase 5A made that ownership explicit without changing the user-facing behavior:
- the app-body legacy implementation was reduced to a compatibility wrapper;
- the real action orchestration moved into `DetectionController.run_normal_draw_action()`;
- `DetectionController` continues to perform: project guard → OCR-independent quick-setting validation → selected-page resolution → set `detection_method="left_edge"` → save settings → app-owned `_detect_pages(..., method="left_edge", force_refresh=False)`;
- `install_ordinary_action_runtime(...)` was removed;
- GUI bootstrap no longer imports or invokes that installer;
- `ordinary_action_runtime.py` intentionally remains as a helper module for `_apply_quick_settings_for_ordinary(...)` because `postproduction_single_line_runtime` still imports and reuses the same OCR-independent validation helper.

The helper preserves the critical all-OCR-off behavior exactly:
- if Paddle/Tesseract/Lens is already effectively selected, normal quick-setting validation runs normally;
- if all visible OCR engines are off, it temporarily satisfies only the legacy OCR-presence check;
- immediately afterward it restores the user's original visible OCR selections and corresponding settings values before ordinary drawing proceeds;
- it keeps the existing safe fallback when an unusual caller lacks the normal Paddle quick-setting variable.

Phase 5A did **not** rename/delete the helper module merely to remove the word `runtime`; doing so would unnecessarily couple this slice to the still-runtime-owned single-line postproduction path.

## Phase 5A validation history
Live revalidation started from the Phase 4Y checkpoint `1ec608807332ce8609bd6b5b760b8d3f86698a83`, with no open PR or competing architecture work.

The first isolated Phase 5A run intentionally failed closed:
- focused suite: **205 passed / 1 failed** out of 206;
- the only failure was an ownership/source-shape assertion showing that `app.py` already contained a legacy `run_normal_draw_action()` body beneath the runtime override;
- the first migration helper had incorrectly treated the presence of the method as evidence that no app-body replacement was needed;
- no behavioral test failed;
- the workflow stopped before publishing a production commit, so no partially validated Phase 5A tree was promoted.

The migration was corrected to replace that exact legacy app method body with the controller wrapper. Final isolated validation then passed:
- focused runtime/controller suite: **206 passed**
- full suite: **1248 passed, 2 existing Pillow deprecation warnings**
- `git diff --check`: passed
- compileall: passed
- Ruff F821: passed
- validated production commit: `cb6b4a4122bdb8ffef4f886589f33e25fc74315a`
- same-tree user-authored PR CI trigger head: `827a47b2bcc835b45f5bc91e553c1aabb40f34e0`
- final production tree: `bb5477d4bac407af5b0c5d505ceed6e284e1d616`
- final net diff contained exactly 6 expected files:
  - `src/picture_capture/app.py`
  - `src/picture_capture/bootstrap/gui.py`
  - `src/picture_capture/ordinary_action_runtime.py`
  - `src/picture_capture/ui/controllers/detection.py`
  - `tests/test_runtime_entry_path_guards.py`
  - `tests/test_ui_detection_controller.py`
- temporary migration scripts/workflow were removed before the validated production commit.

PR #232 final-head verification:
- Ubuntu CI: passed
- Windows CI: passed
- macOS CI: passed
- pytest, GUI smoke, compatibility runner, compile, F821, and wheel build all passed on their applicable platforms
- CodeQL Actions: passed
- CodeQL Python: passed
- Advanced Security AI findings: passed
- no review threads or review objections were present before merge

Post-merge verification on architecture merge `5f4bf0707fe32a52ab1af1f39a64652d8fcc9874`:
- Ubuntu CI: passed
- Windows CI: passed
- macOS CI: passed
- CodeQL Actions: passed
- CodeQL Python: passed

## Remaining runtime-owned seams
Phase 5A removes only the ordinary-action method replacement. It is **not** permission to flatten the entire GUI bootstrap installer chain mechanically.

### `postproduction_single_line_runtime`
Still runtime-owned and materially wider than Phase 5A. It currently:
- injects `split_single_lines_selected_scope` onto `PictureCaptureApp`;
- wraps `PictureCaptureApp.__init__`;
- locates the main postproduction `词条切图` button at runtime and inserts `单行切图` relative to it;
- owns dedicated background-thread / event-queue / polling behavior;
- owns private runtime state fields for active job, token, thread, and button state;
- reuses `_apply_quick_settings_for_ordinary(...)` from `ordinary_action_runtime.py` so single-line export remains OCR-independent.

Do not delete or relocate that helper until the single-line path has an explicit replacement dependency.

### Training export assignment
GUI bootstrap still assigns the training export action onto `PictureCaptureApp` from `training_export_ui.export_training_package_selected_range`. That path owns batch staging/finalization, cancellation cleanup, manifest/ZIP publication, and an auxiliary UI-worker cleanup path. Treat it as a separate ownership decision from the single-line runtime.

### Other installers
Other GUI/bootstrap runtime installers remain. Their existence does not mean they should all be removed in one Phase 5 sweep. Each should be evaluated by actual runtime ownership, import-order constraints, UI mutation, worker behavior, and compatibility surface.

## Next architecture decision point
Phase 5A is complete and recoverable. The next change is **not uniquely mechanical** because the remaining highlighted seams have materially different responsibilities.

Reasonable next directions:
1. **Phase 5B — postproduction single-line runtime decomposition (recommended next family).** The safest approach is likely to split this further rather than removing the whole installer at once: first make the action method ownership explicit, then separately address `__init__` wrapping / dynamic button insertion and the independent worker/poll state if inspection confirms those seams are separable.
2. **Training export method-assignment cleanup.** This is a different batch/export ownership problem and should not be bundled with the single-line runtime.
3. Reassess another bootstrap installer only if live dependency inspection shows a narrower, lower-risk seam than the two above.

Because these choices differ materially, **human confirmation is required before the next production-code write**. Entering Phase 5 authorized Phase 5A but does not override the stop rule at a new architecture choice.

Before the next production write, revalidate:
- live `main` and open PRs;
- `postproduction_single_line_runtime.py` and all call/UI bindings if selecting Phase 5B;
- `training_export_ui.py` and bootstrap assignment if selecting training export;
- tests asserting GUI bootstrap/runtime ownership;
- dependency direction, constructor/UI mutation, worker/poll ownership, and shutdown behavior.

Do not rerun the full suite merely on wake-up with no code change.

## Auto continuation
Phase 5A is complete and recoverable. Automatic production-code continuation is paused at the Phase 5B / training-export architecture decision point.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone/ownership transition not already explicitly approved.
