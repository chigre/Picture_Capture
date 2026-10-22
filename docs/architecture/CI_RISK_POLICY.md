# Picture Capture risk-tier CI policy

This policy replaces the unconditional six-platform PR matrix. No tests,
architecture guards or safety contracts are relaxed. Effective only after
a dedicated policy PR passes the *old/current* review and acceptance gates.

## Automatic classification

| Tier | Verified diff | Required checks |
| --- | --- | --- |
| docs | Only ordinary Markdown/RST/text docs or README/changelog | Ubuntu architecture guard; stable risk-tier CI gate |
| fast | Test/doc changes and production implementations whose full AST is unchanged **after removing only import statements**; physical renames allowed; architecture guard only gains lines | Existing Python 3.13 suite, GUI smoke and wheel on Ubuntu; existing full Python 3.10 suite on Ubuntu **and Windows**; CodeQL, review and risk-tier CI gate |
| full | Everything else: actual algorithm/behavior changes, project settings/schema, dependencies/workflow, critical image/geometry, persistence, GPU, spawn, bootstrap or unknown changes | Original six complete jobs: Python 3.10/3.13 × Ubuntu/Windows/macOS; CodeQL, review and risk-tier CI gate |

The `scripts/ci_risk_tier.py` classifier uses the real Git base/head, not
PR text, labels or a self-reported risk flag. Any unexpected Git diff,
unknown path, unrecognized status or AST parser error **fails closed to full**.
The changes to critical paths are full even if import-only. A change to
function bodies or dataclass semantics is not eligible for fast CI.

## Full-matrix independent coverage

- GitHub scheduled run on the default branch every day at **12:19
  Asia/Singapore** (GitHub cron may start later).
- Tagged `v*` release pushes and manual workflow dispatch trigger full CI.
- All high-risk PRs trigger full CI **before merge**.
- Existing release/macOS app and dedicated CPU OCR dependency workflows remain.
- CI cannot replace human real-page Tk review, native CUDA model ownership,
  physical Y accuracy, or PDIC/PPP/SECTION/Profile format and parent-writer checks.

## Acceptance and branch protection

The new stable `Risk-tier CI gate` succeeds only if the *selected tier's*
required jobs succeeded. Skipped/macOS-unselected checks are **not** reported
as executed. CodeQL and reviews are independent additional obligations.
After merge, verify main's tier-appropriate CI and CodeQL.

Branch protection was not readable via the connected GitHub integration (403).
If an existing ruleset requires the old individual macOS jobs, it must be
updated by an authorized repository admin to require the stable gate instead.
Until then, branch protection is authoritative; never bypass it or force-merge.

See `docs/architecture/CHANGE_POLICY.md` and Issue #562 for continuing
architecture constraints and human acceptance scope.
