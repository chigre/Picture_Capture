# Architecture change policy

## Purpose
Prevent bug fixes and feature additions from undoing the modularization documented in `docs/refactor/REFACTOR_STATUS.md`. This policy is additive to `scripts/architecture_guard.py`, which already ratchets oversized legacy modules, dynamic namespaces/proxies, and retired runtime installers.

## Ownership and dependency direction

| Layer | Responsibilities | May depend on |
| --- | --- | --- |
| GUI shell (`app.py`, bootstrap) | Compose widgets and call controllers/services; compatibility entrypoints | Controllers, helpers, services |
| `ui/controllers/`, UI helpers/dialogs | Bind events, render widgets, translate inputs/results | Models and application/domain services |
| Processing, layout, OCR, crop services | Deterministic logic; explicit dependencies injected by the caller | Models, pure helpers, external libraries |
| Models and persistence | Type/serialization contracts and migrations | Pure helpers; never the GUI shell |

A helper must never import the large GUI shell to reach functionality. Pass data/functions explicitly. Existing facade compatibility boundaries are documented exceptions, **not patterns to copy**.

## Definition of done for a change
1. **Inventory** the current owner, call path, impacted formats/settings, and consumers.
2. **Design** minimal changes and identify which module owns each new responsibility.
3. **Implement** with explicit imports, without growing legacy debt; keep the public compatibility surface unchanged unless deliberate.
4. **Test** failing-before/passing-after regression for the bug; persistence round-trip and at least one edge case where applicable.
5. **Verify** architecture ratchets and change-specific guard; full cross-platform CI, GUI smoke, and wheel build.
6. **Review** diff and state side effects (focus loss, autosave, reorder/section identity, undo/navigation, zoom, export, restart).
7. **Merge only after green gates**; document residual limitations honestly.

## Machine-enforced checks
- Existing `scripts/architecture_guard.py`: production module size, legacy ratchets, forbidden mutations, compatibility seams.
- New `scripts/change_architecture_guard.py`: checks **newly added** Python modules under `src/picture_capture`. Rejects imports of `picture_capture.app` / relative `.app`, global `setattr` calls, and module-level `install_*` invocations; reports offending paths and lines.
- CI executes both checks; repository policy requires PR review to catch semantic layering errors that static checks cannot detect.

The change guard is designed to have no dependency on GitHub APIs. Against a PR base:
`python scripts/change_architecture_guard.py --base origin/main`
It compares the merge-base of `origin/main` to the working HEAD. Against a push, default is `HEAD^ ` when no base is supplied. A repository without history can run its pure source-validation tests.

## Exceptions
Exceptions are narrowly scoped and must document the ownership reason, compatibility contract, regression tests, planned removal (if technical debt), and alternative considered. An exception is not achieved by raising architectural baselines or disabling the gate.

## Pull request acceptance
The PR template captures responsibility boundaries, state ownership, behavior parity, tests, and architecture gate output. PRs violating an enforced rule cannot be merged until the code is redesigned; any proposed change to an enforcement rule belongs in a separate, explicit architecture review.
