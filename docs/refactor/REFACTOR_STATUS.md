# Picture Capture Refactor Status

This file is the crash-recovery checkpoint for the modular architecture refactor. GitHub state is authoritative; revalidate this file against the repository before changing code. Do not treat any historical commit recorded here as the current repository HEAD; fetch the live HEAD at recovery time.

## Current milestone
Modular architecture refactor

## Current phase
Phase 4 — controller decomposition. Phase 4G is complete.

## Architecture checkpoint
- Last completed architecture PR: #193 — DetectionController OCR action-entry seam
- Last completed architecture merge commit: `6c2ecba043fcdc8d318dd24dd35e669b33fdeff1`
- Recovery protocol bootstrap PR: #194 — merged (administrative, not an architecture phase)
- Current architecture PR: none
- Work in progress: false

## Current structure
Explicit controllers on `main`: Canvas, Detection, Page, Project, Review, Session.

## Last verified tests
- Phase 4G branch full suite: 1133 passed, 2 warnings
- PR #193 CI: Ubuntu / Windows / macOS all passed
- `main` merge-push CI after #193: Ubuntu / Windows / macOS all passed
- CodeQL after #193: passed
- Recovery protocol PR #194 CI: Ubuntu / Windows / macOS all passed
- `main` merge-push CI and CodeQL after #194: passed

## Current issue
No active architecture blocker. `run_normal_draw_action` remains intentionally outside DetectionController because `ordinary_action_runtime` still replaces it at runtime; runtime-patch removal belongs to a later milestone/phase.

## Next safe unit
Phase 4H candidate: extract only `PictureCaptureApp.export_text()` and `PictureCaptureApp.import_text()` action-entry orchestration into a narrow `ExportController`, preserving app compatibility wrappers and behavior exactly.

Before acting, revalidate that both methods still exist on live `main`, are not replaced by runtime installers, and can move without changing file formats, public API, or user-visible behavior. If any check fails, stop and record a blocker instead of choosing a broader task.

## Required validation for the next safe unit
- characterization/regression tests for export/import behavior and compatibility wrappers
- reverse-dependency/boundary test for the controller
- targeted tests while iterating
- full suite and normal PR CI before merge

Do not rerun the full suite on a wake-up that makes no code change.

## Auto continuation
Allowed: yes, but only one safe unit per scheduled run and only after the recovery protocol in `RESUMABLE_EXECUTION_PROTOCOL.md` passes.

## Must stop for human confirmation
Stop without modifying code if there is an unexplained test/CI failure, behavior/file-format/API change, merge conflict, concurrent work, checkpoint mismatch, multiple materially different architecture choices, large compatibility deletion, cross-core-module change, or a milestone transition (including Phase 5 runtime-patch cleanup).
