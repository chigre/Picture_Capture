# Resumable Architecture Refactor Protocol

Purpose: allow a fresh execution context to recover the Picture Capture architecture refactor from GitHub and advance at most one safe unit without relying on chat memory.

## Authority
GitHub is the only authoritative progress source. If chat history, prior plans, and GitHub disagree, use GitHub.

## Mandatory recovery order
Before any write:

1. inspect repository metadata and default branch;
2. inspect refactor-related branches;
3. inspect recent merged PRs;
4. inspect all open PRs;
5. inspect recent commits;
6. inspect active/recent CI and tests;
7. inspect current affected code structure;
8. read `docs/refactor/REFACTOR_STATUS.md`;
9. verify the checkpoint against code;
10. only then use prior chat/roadmap context as secondary guidance.

## Concurrency guard
Do not modify code when any clear parallel-work signal exists, including:

- an open architecture/refactor PR;
- CI still running for current refactor work or a just-merged refactor commit;
- recent commits suggesting another Work/Codex instance is active;
- checkpoint says `Work in progress: true`;
- uncertainty about whether another instance is modifying the same area.

In these cases, perform read-only inspection and end the run.

## One-run scope
Each scheduled run may advance at most one safe unit. A safe unit must have a narrow boundary, independent commit/PR, focused tests, easy rollback/recovery, and no simultaneous architecture-layer changes.

Do not perform broad rewrites, opportunistic cleanup, multi-concern PRs, or unplanned architecture redesign.

## Behavior contract
This milestone is architecture refactoring, not feature work. Preserve:

> same input -> same user-observable behavior

Do not change project formats, compatibility behavior, public API, or known legacy behavior as a side effect. Record bugs separately instead of fixing them inside architecture PRs.

## PR discipline
Prefer one architecture concern per PR. Include characterization/regression coverage, affected-module validation, compatibility verification, and normal PR CI. Use targeted tests while iterating; run the full suite only when the safe unit has changed code and is ready for its merge gate.

## Automatic stop conditions
Stop and update the checkpoint with a blocker instead of expanding scope when any of the following occurs:

1. characterization/regression failure;
2. unexplained CI failure;
3. required user-visible behavior change;
4. file-format or compatibility change;
5. public API decision;
6. two or more materially different architecture choices;
7. large compatibility-code deletion;
8. change spanning multiple core modules;
9. GitHub/checkpoint contradiction;
10. merge conflict;
11. uncertain concurrent execution;
12. transition to a new milestone rather than mechanical continuation of the current one.

## End-of-run checkpoint
Before ending a run, leave the repository in an explainable state and update `REFACTOR_STATUS.md` with:

- verified repository state;
- work completed this run;
- test/CI result;
- commit/PR state;
- next safe unit;
- blocker, if any;
- `Work in progress` and auto-continuation status.

Assume the next model has no memory beyond GitHub.

## Resource discipline
Use incremental inspection: recent PRs/commits, affected modules, checkpoint, and necessary tests. Do not repeatedly deep-audit the full repository or reread all historical PRs unless entering a milestone boundary or investigating an architecture anomaly.
