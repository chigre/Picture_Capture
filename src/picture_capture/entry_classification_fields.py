from __future__ import annotations

"""Registry-backed helpers for Entry structural-classification properties."""

from typing import Any

from .models import Entry


def _current_classification(entry: Entry):
    """Return metadata consistent with this concrete Entry's own evidence.

    The historical registry is keyed by id(entry). CPython may recycle an
    object id after a temporary Entry is collected, so a long-running app or a
    large test suite can otherwise attach stale automatic metadata to a new
    Entry. Refresh only when the structural source carried by the concrete
    Entry proves that the registry belongs to another object. Scale/height may
    be intentionally assigned later through the public Entry properties, so
    differences in those fields alone must never overwrite an explicit
    assignment.
    """
    from .entry_classification import (
        get_entry_classification,
        infer_entry_classification,
        register_entry_classification,
    )

    current = get_entry_classification(entry)
    inferred = infer_entry_classification(entry)
    source_mismatch = bool(
        inferred.entry_source != "unknown"
        and (
            current.entry_source != inferred.entry_source
            or current.auto_entry_source != inferred.auto_entry_source
        )
    )
    if not current.manual_override and source_mismatch:
        current = register_entry_classification(
            entry,
            entry_source=inferred.entry_source,
            entry_scale=inferred.entry_scale,
            detected_head_height=inferred.detected_head_height,
            manual_override=False,
            auto_entry_source=inferred.auto_entry_source,
            auto_entry_scale=inferred.auto_entry_scale,
        )
    return current


def entry_source_get(entry: Entry) -> str:
    return _current_classification(entry).entry_source


def entry_source_set(entry: Entry, value: Any) -> None:
    from .entry_classification import register_entry_classification

    source = str(value or "unknown")
    register_entry_classification(
        entry,
        entry_source=source,
        auto_entry_source=source,
    )


def entry_scale_get(entry: Entry) -> str:
    return _current_classification(entry).entry_scale


def entry_scale_set(entry: Entry, value: Any) -> None:
    from .entry_classification import register_entry_classification

    scale = str(value or "regular")
    register_entry_classification(
        entry,
        entry_scale=scale,
        auto_entry_scale=scale,
    )


def detected_head_height_get(entry: Entry) -> float:
    return float(_current_classification(entry).detected_head_height)


def detected_head_height_set(entry: Entry, value: Any) -> None:
    from .entry_classification import register_entry_classification

    try:
        height = max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        height = 0.0
    register_entry_classification(entry, detected_head_height=height)


def entry_scale_manual_get(entry: Entry) -> bool:
    return bool(_current_classification(entry).manual_override)


def entry_scale_manual_set(entry: Entry, value: Any) -> None:
    from .entry_classification import set_entry_scale_manual

    current = _current_classification(entry)
    if bool(value):
        set_entry_scale_manual(entry, current.entry_scale)
    else:
        set_entry_scale_manual(entry, None)


def install_entry_classification_fields() -> None:
    """Compatibility no-op; Entry owns the four descriptors statically."""
    return None


__all__ = [
    "detected_head_height_get",
    "detected_head_height_set",
    "entry_scale_get",
    "entry_scale_manual_get",
    "entry_scale_manual_set",
    "entry_scale_set",
    "entry_source_get",
    "entry_source_set",
    "install_entry_classification_fields",
]
