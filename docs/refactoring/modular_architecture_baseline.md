# Modular Architecture Refactor — Phase 0 Baseline

This document freezes the behavior and architecture baseline immediately after
PR #161 (Evidence Fusion v3) was merged to `main` at commit
`51921204c6b35d1ba10525c8a21fd9be8959ce1e`.

Phase 0 changes **tests and guardrails only**. It does not move production code,
change detector thresholds, alter persistence formats, or change GUI/worker
runtime installation order.

## Invariants during the refactor

For the same project and settings, the refactor must preserve:

- project discovery and managed `_PictureCapture` paths;
- `AppSettings` JSON persistence and migration behavior;
- PDIC records and coordinates;
- PPP illustration polygons;
- Layout physical rows and their persisted cache semantics;
- ordinary / OCR / combined drawing results;
- OCR cache placement and reuse semantics;
- existing-marker OCR behavior;
- crop planning and output behavior;
- GUI and multiprocessing-spawn behavior.

The intended rule is: **same input -> same observable output**. Architecture
work is not an opportunity to tune algorithms.

## Characterization coverage

| Contract | Baseline coverage |
| --- | --- |
| GUI construction / launcher path | `scripts/gui_smoke.py`, cross-platform CI |
| multiprocessing spawn entry path | `tests/test_runtime_entry_path_guards.py`, `tests/test_spawn_layout_runtime.py` |
| `AppSettings` JSON round-trip | `tests/test_refactor_behavior_baseline.py` plus existing settings tests |
| managed project + sidecar paths | `tests/test_refactor_behavior_baseline.py`, project-storage regression tests |
| PDIC byte format and read-back | `tests/test_refactor_behavior_baseline.py` plus existing format/processing tests |
| PPP illustration polygon format | `tests/test_refactor_behavior_baseline.py` |
| Layout rows/cache | `tests/test_layout_rows_fast_path.py` and Layout regression suite |
| OCR cache location | `tests/test_refactor_behavior_baseline.py` plus OCR cache regressions |
| existing-marker OCR | existing `refine_existing_entries` / marker OCR regressions in `tests/test_next_stage_regressions.py` |
| crop behavior | existing processing/crop regression suite and compatibility runner |

As modules are extracted, source-string tests should be replaced with behavioral
imports/tests before the old source location is removed.

## Architecture debt baseline

`scripts/architecture_guard.py` implements a **no-new-debt** policy.

It currently allows, but does not bless, the legacy structures that already
exist at the PR #161 baseline:

- five production modules above 100 KB, each capped at its current byte size;
- the existing `*_runtime.py` modules, with no new runtime installer filename
  permitted;
- dynamic module namespace/proxy behavior only in the three existing
  compatibility facades;
- only the current set of import-time installer calls in
  `picture_capture.__init__`.

All four baselines are intentionally monotonic: deleting a runtime, removing a
proxy, removing an import-time installer, or shrinking an oversized module is
allowed without updating the baseline. Increasing the debt fails CI.

## Planned next step

Phase 1 introduces one explicit bootstrap/composition root. The first migration
must preserve the current installer order while moving ownership out of package
import side effects. GUI and spawn workers will then converge on the same
bootstrap API with explicit profiles before runtime monkey patches are removed.
