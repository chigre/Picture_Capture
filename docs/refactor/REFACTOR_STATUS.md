# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4P is complete.

## Architecture checkpoint
- Last completed architecture PR: #213 — `build_picdic()` action orchestration routed through the existing `ExportController`
- Last completed architecture merge commit: `4feaf9801e029b374455e89e2437907d8f34623d`
- Recovery protocol bootstrap PRs: #194 and #195 — merged (administrative, not architecture phases)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Crop, Detection, Export, Illustration, Page, Project, Review, Session.

The following historical `PictureCaptureApp` entry points remain compatibility wrappers: `export_text()`, `import_text()`, `split_lines_current()`, `split_whole_current()`, `batch_split_whole()`, `split_entries_selected_scope()`, `detect_illustrations_selected_scope()`, `split_illustrations_selected_scope()`, `_start_illustration_crop()`, and `build_picdic()`.

`ExportController` now owns current-page `.OCRed` import/export orchestration and the PicDic package-build action boundary. `.OCRed` serialization/crop algorithms and the PicDic package builder remain outside controllers; project path policy remains in `project_storage`.

## Last verified tests
- Phase 4P pre-PR focused controller/regression suite: 204 passed
- Phase 4P pre-PR full suite: 1198 passed, 2 existing Pillow deprecation warnings
- Phase 4P PR #213 fixed head: `f626fccb5e4fdd8f7911e6be2d5ee7ed713aad59`
- PR #213 CI at the fixed head: Ubuntu / Windows / macOS all passed, including GUI smoke, compatibility runner, compile, F821, and wheel build
- `main` merge-push CI after #213: Ubuntu / Windows / macOS all passed
- CodeQL after #213: Python and Actions analyses passed
- `app.py` architecture size baseline after #213: 862,472 bytes

Phase 4P validation history worth preserving for recovery:
- the first focused validation run reported 1 failure and 203 passes because `tests/test_next_stage_regressions.py::test_round1_blocking_ui_paths_use_background_workers` still required `_start_batch_task(...)` to be physically inside `PictureCaptureApp.build_picdic()`
- that source-shape regression test was updated to follow the compatibility wrapper into `ExportController.build_picdic()` and verify the same background-batch/cooperative-cancellation contract there; production code was not changed to resolve this test-only failure
- a later isolated-validation commit initially omitted staging that test-only source-boundary update; the staging omission was corrected and the focused/full/static validation was rerun successfully
- temporary isolated-validation workflows/scripts were removed before PR creation; the final net diff contained only 4 expected production/test files

## Completed Phase 4P seam
`PictureCaptureApp.build_picdic()` now remains as a compatibility wrapper and delegates to `ExportController.build_picdic()`.

The controller preserves:
- `guard()` short-circuit behavior
- exact batch-active status `已有批量任务正在运行，请结束后再制作 PicDic。`
- foreground `save_pdic(silent=True)` before starting the build
- exact preparation error boundary/title `PicDic 制作准备失败`
- project root and OCR-language capture before the worker runs
- `build_picdic_package(root, language, should_stop=app._batch_stop_event.is_set)` cooperative-stop contract
- `PicDicBuildCancelled` conversion to a `None` worker result
- completion no-op on error, stopped task, or empty results
- exact success status/dialog contents and parent ownership
- the existing app-owned `_start_batch_task(...)` boundary, title `PicDic 制作`, one-root work item, item label `生成 DSL 与图片包`, and `refresh_page_quality=False`
- the existing UI `PicDic制作` binding

Only the action-owned `PicDicBuildCancelled` / `build_picdic_package` imports moved out of `app.py`; the PicDic processing implementation, output format, paths, and package publication behavior were not changed. `export_picdic_index()` was explicitly not moved in Phase 4P.

## Runtime-owned exclusions
`run_normal_draw_action` remains intentionally outside `DetectionController` because `ordinary_action_runtime` replaces it at runtime. Runtime-patch removal belongs to a later milestone/phase.

`postproduction_single_line_runtime` separately installs `split_single_lines_selected_scope` and its UI button at runtime. Do not fold this path into controller decomposition; it belongs with later runtime-patch cleanup.

## Current issue / architecture choice required
There is no failing implementation blocker. Automatic production-code continuation is paused because post-Phase-4P live review again exposes several materially different next controller seams rather than one mandatory mechanical move.

The strongest next candidate is `export_picdic_index()` -> existing `ExportController`, because it is clearly an export action. However, unlike the small current-page `.OCRed` actions and the bounded Phase 4P package-build entry, this method owns a project-wide streaming/atomic-publication workflow with materially more state:
- validates an open project/current page/image and the batch-active guard
- flushes deferred edits, syncs entry-editor text, and foreground-saves PDIC before export
- filters the project to pages with existing PDIC files
- creates a timestamped export target plus a hidden temporary file
- lazily opens and reuses a stream across batch worker calls
- converts each saved PDIC with `read_picdic_index_records(...)` and writes rows incrementally
- tracks page/record counts in shared action state
- closes the stream and deletes the temporary file on errors/stops
- atomically publishes with `os.replace(temp, target)` only after successful completion
- owns exact stopped/completed status strings and completion/error dialogs
- delegates scheduling to the existing app-owned `_start_batch_task(...)` with `refresh_page_quality=False`

Other remaining app seams are semantically different again, including project-wide PDIC backup/streaming, headword-order review, and training-package export. Moving any of these would establish the next ownership direction rather than merely finish Phase 4P.

## Revalidation facts for the next decision
After Phase 4P merge-push verification:
- live `main` is `4feaf9801e029b374455e89e2437907d8f34623d`
- no open competing PR exists at revalidation time
- `ExportController` owns `.OCRed` import/export and PicDic package-build orchestration, while the app keeps compatibility wrappers and the generic batch runner boundary
- `export_picdic_index()` remains directly in `PictureCaptureApp` and retains its streaming temporary-file / atomic-publication semantics
- `build_picdic_package(...)` remains in `picdic.py`; Phase 4P did not move or alter the algorithm
- no Phase 5 runtime-patch cleanup has begun

## Recommended next action
If continuing Phase 4 controller decomposition, the preferred Phase 4Q candidate is a **single narrow migration of only `PictureCaptureApp.export_picdic_index()` action orchestration into the existing `ExportController`**, retaining the historical app wrapper, app-owned `_start_batch_task(...)`, `read_picdic_index_records(...)`, `exports_root(...)`, temporary-file/atomic-rename behavior, exact UI/status/error contracts, and all file-format/path semantics.

Because this candidate has a larger streaming-resource lifecycle than Phase 4P and other materially different app seams remain available, obtain human confirmation before Phase 4Q production writes. Before modifying code, revalidate live `main`, open PRs, the exact method/callers/import ownership, runtime ownership, and the complete stream/temp cleanup contract. Keep Phase 4Q to this one action only and repeat focused/full/three-platform/merge-push/CodeQL validation.

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Paused pending human confirmation of the recommended Phase 4Q seam above. After confirmation, automatic continuation may resume one safe unit at a time under `RESUMABLE_EXECUTION_PROTOCOL.md`.

## Must stop for human confirmation
Stop without modifying production code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
