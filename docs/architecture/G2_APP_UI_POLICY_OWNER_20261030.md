# G2 app.py UI policy owner extraction — 2026-10-30

## Scope and ownership

In the single Draft PR #663, moved two **pure UI policies** out of `src/picture_capture/app.py` without creating new owner modules or root alias files:

- `transformed_geometry_pending` now executes in `ui/main_app_lifecycle.py`, alongside `_guard_transformed_geometry`, which continues to guard writes when a coordinate adapter is unsupported.
- `review_window_dimensions` now executes in `ui/review_layout_events.py`, with the original 60% screen-width / 70% screen-height clamp and minimum-size behavior.

The historical `app.transformed_geometry_pending(settings)` and `app._review_window_dimensions(screen_w, screen_h)` callable names and signatures remain, forwarding to the current owner **at call time**. Tk window construction still uses the original injected app callback, so live app-global patching remains available. No window is constructed by importing the pure policies.

## Scope boundaries

Only three existing Python modules and one synthetic characterization test are involved. No changes to Tk main-thread execution, persistence schema or bytes (PDIC/PPP/SECTION/Profile), image source-pixel coordinate conversions, OCR, cropping, background workers, file atomicity, human annotation/evidence, or experimental feature defaults. The direct root Python file inventory stays 5; no new compatibility alias modules.

Tests: `tests/test_g2_app_ui_policy_owners_20261030.py` covers small/large/invalid screen dimensions, supported/unsupported transforms and the two separate live patch seams (`app` and physical owner). Test code calls the existing geometry guard as an unbound method on a fake status-bearing object; it is **not** a real Tk GUI user run.

## Gate

Verified exact SOURCE HEAD `089c7334f97fed34869c17b252ef749c55086d62`: [CI #40962965881](https://github.com/chigre/Picture_Capture/actions/runs/40962965881) Windows/macOS/Ubuntu × Python 3.10/3.13 all 6/6 + Risk-tier SUCCESS, [OCR Smoke #40962965552](https://github.com/chigre/Picture_Capture/actions/runs/40962965552) 3/3 SUCCESS, and PR CodeQL Python + Actions 2/2 SUCCESS. Test-first `5bed7d6`: three expected fails; intermediate `732cb51`: preexisting exclusive-ReviewWindow-initializer AST guard caught our new top-level helper, fixed without changing the guard in `089c7334`. The later documentation-only checkpoint does not replace the source-head checks. Real Windows E3 and #483 W1–W11 human acceptance remain **NOT PERFORMED**, explicitly deferred by user; no real licensed dictionary scan, real IME/FocusOut, 20-step Undo/Redo, reopened project or source XY/crop parity is claimed.

Keep PR #663 Draft/Open/Unmerged, main unchanged and #503/#562/#483 open.
