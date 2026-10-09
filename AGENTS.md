# Picture_Capture engineering contract

This file applies to every bug fix, feature, refactor, and AI-assisted change.

## Before editing
1. Read `docs/refactor/REFACTOR_STATUS.md`, `docs/architecture/CHANGE_POLICY.md`, and the existing callers/tests.
2. Identify a **single source of truth** for the affected state and its owning module. Trace UI → controller/service → domain logic → persistence before changing behavior.
3. Preserve PDIC/schema, stored settings, page sections, and public compatibility paths unless an explicit migration is part of the task.
4. Prefer a small, reviewable PR. Do not mix unrelated feature work into a bug fix.

## Architecture rules
- `app.py` is a composition and compatibility boundary, **not** a destination for new feature logic or full widget builders. Keep additions thinner than removals; extract logic to an explicitly named module.
- UI controllers coordinate actions; services/domain functions own decisions; models own data; serialization stays behind persistence adapters. Dependency flow goes inward, never from a new service/helper back to `app.py`.
- Use explicit imports and call-time wiring. Never resurrect runtime monkeypatch installers, mutable module-global hooks, bulk namespace copying, or class-method injection.
- Respect every ratchet in `scripts/architecture_guard.py`. **Do not change baselines, size limits, or allowlists simply to make CI pass.** A baseline change requires a separately justified architecture proposal.
- Reuse existing settings, event handlers, and rendering primitives. When adding a setting, test default, validation, save/load, and visual update.
- Never map headwords to marker coordinates by list index after reordering; preserve Entry/coordinate identity across section sorting, editing, and export.

## Validation and delivery
- Add a regression reproducing each bug, including reopening or round-tripping state where relevant.
- New features need unit tests for behavior plus GUI smoke/integration coverage for changed wiring; negative cases and cross-platform behavior matter.
- Run `python scripts/architecture_guard.py`, `python scripts/change_architecture_guard.py --base <base-ref>`, the focused tests, and the full CI.
- A green CI is necessary but not proof of every GUI behavior. State what was and was not tested.
- Use `.github/PULL_REQUEST_TEMPLATE.md` as the review checklist. Never silently weaken a test to accommodate an accidental behavioral regression.
