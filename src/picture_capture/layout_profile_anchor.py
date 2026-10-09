from __future__ import annotations

"""Anchor per-page automatic layout to the multi-page Project Profile.

Project Profile already aggregates representative pages into stable physical
layout values.  A single page is therefore an observation around that template,
not a new template.  This module keeps scan-position fields page-adaptive while
shrinking stable typography/column fields back toward the Project/Profile
baseline.
"""

from dataclasses import replace
from typing import Any, Callable


# Stable page-template fields.  ``columns`` and ``row_padding`` are discrete and
# should remain the Profile values.  The other fields may move slightly to
# accommodate page scaling/curvature, but a single sparse page must not redefine
# the dictionary template.
_STABLE_BLEND: dict[str, float] = {
    "column_width": 0.20,
    "gutter": 0.20,
    "character_height": 0.25,
}

_STABLE_LIMITS: dict[str, tuple[float, int]] = {
    # (maximum relative movement from Profile, minimum pixel allowance)
    "column_width": (0.015, 6),
    "gutter": (0.08, 3),
    "character_height": (0.06, 2),
}


def _profile_value(settings: Any, field: str) -> int | None:
    try:
        value = int(getattr(settings, field))
    except (AttributeError, TypeError, ValueError):
        return None
    if field in {"column_width", "character_height"} and value <= 0:
        return None
    if field == "gutter" and value < 0:
        return None
    return value


def _anchored_scalar(field: str, profile_value: int, observed_value: int) -> int:
    """Shrink one page observation toward its Profile baseline and clamp drift."""
    alpha = float(_STABLE_BLEND[field])
    blended = float(profile_value) + alpha * (float(observed_value) - float(profile_value))
    relative, minimum_px = _STABLE_LIMITS[field]
    allowance = max(int(minimum_px), int(round(abs(profile_value) * float(relative))))
    low = int(profile_value) - allowance
    high = int(profile_value) + allowance
    return int(round(min(max(blended, low), high)))


def anchor_resolved_layout_to_profile(
    profile_settings: Any,
    resolved_settings: Any,
    applied: dict[str, int],
) -> tuple[Any, dict[str, int]]:
    """Return one page's resolved settings anchored to Project/Profile values.

    ``profile_settings`` is the project-level object before automatic per-page
    replacement.  ``resolved_settings`` contains the raw page estimate selected
    by the user's auto-field switches.  Position/registration fields are left
    untouched; stable physical-template fields are anchored here.
    """
    current = replace(resolved_settings)
    anchored = dict(applied)

    # Number of columns is a dictionary-template property.  Profile analysis is
    # multi-page and therefore more trustworthy than a sparse single page.
    if "columns" in anchored:
        baseline = _profile_value(profile_settings, "columns")
        if baseline is not None and baseline > 0:
            current.columns = int(baseline)
            anchored["columns"] = int(baseline)

    # Row padding is a discrete rendering/layout convention rather than useful
    # per-page evidence; preserve the stable Profile value when auto is enabled.
    if "row_padding" in anchored:
        baseline = _profile_value(profile_settings, "row_padding")
        if baseline is not None:
            current.row_padding = int(baseline)
            anchored["row_padding"] = int(baseline)

    for field in _STABLE_BLEND:
        if field not in anchored:
            continue
        baseline = _profile_value(profile_settings, field)
        if baseline is None:
            continue
        observed = int(anchored[field])
        value = _anchored_scalar(field, baseline, observed)
        setattr(current, field, value)
        anchored[field] = value

    return current, anchored


def install_profile_layout_anchor() -> None:
    """Install Profile anchoring once at the page-layout policy boundary."""
    from . import dictionary_page_layout_policy as policy

    if getattr(policy, "_profile_layout_anchor_installed", False):
        return

    original: Callable[..., Any] = policy.resolve_page_layout_policy

    def wrapped(
        image: Any,
        settings: Any,
        *,
        page_index: int = 0,
        ops: Any = None,
    ):
        resolved, estimate, applied = original(
            image, settings, page_index=page_index,
            **({"ops": ops} if ops is not None else {}),
        )
        resolved, applied = anchor_resolved_layout_to_profile(
            settings,
            resolved,
            applied,
        )
        return resolved, estimate, applied

    policy.resolve_page_layout_policy = wrapped
    policy._profile_layout_anchor_installed = True
