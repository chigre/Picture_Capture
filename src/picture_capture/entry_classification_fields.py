from __future__ import annotations

"""Expose canonical structural classification as Entry runtime fields."""

from typing import Any

from .models import Entry


_INSTALLED = False


def install_entry_classification_fields() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from .entry_classification import (
        get_entry_classification,
        infer_entry_classification,
        register_entry_classification,
        set_entry_scale_manual,
    )

    def current_classification(entry: Entry):
        """Return metadata consistent with this concrete Entry's own evidence.

        The historical registry is keyed by ``id(entry)``. CPython may recycle an
        object id after a temporary Entry is collected, so a long-running app or
        a large test suite can otherwise attach stale automatic metadata to a new
        Entry. Refresh only when the structural *source* carried by the concrete
        Entry proves that the registry belongs to another object. Scale/height
        may be intentionally assigned later through the public Entry properties,
        so differences in those fields alone must never overwrite an explicit
        assignment.
        """
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

    def source_get(entry: Entry) -> str:
        return current_classification(entry).entry_source

    def source_set(entry: Entry, value: Any) -> None:
        source = str(value or "unknown")
        register_entry_classification(
            entry,
            entry_source=source,
            auto_entry_source=source,
        )

    def scale_get(entry: Entry) -> str:
        return current_classification(entry).entry_scale

    def scale_set(entry: Entry, value: Any) -> None:
        scale = str(value or "regular")
        register_entry_classification(
            entry,
            entry_scale=scale,
            auto_entry_scale=scale,
        )

    def height_get(entry: Entry) -> float:
        return float(current_classification(entry).detected_head_height)

    def height_set(entry: Entry, value: Any) -> None:
        try:
            height = max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            height = 0.0
        register_entry_classification(entry, detected_head_height=height)

    def manual_get(entry: Entry) -> bool:
        return bool(current_classification(entry).manual_override)

    def manual_set(entry: Entry, value: Any) -> None:
        current = current_classification(entry)
        if bool(value):
            set_entry_scale_manual(entry, current.entry_scale)
        else:
            set_entry_scale_manual(entry, None)

    # Entry uses slots, so canonical metadata is deliberately backed by the
    # shared registry rather than expanding the legacy PDIC dataclass layout.
    Entry.entry_source = property(source_get, source_set)  # type: ignore[attr-defined]
    Entry.entry_scale = property(scale_get, scale_set)  # type: ignore[attr-defined]
    Entry.detected_head_height = property(height_get, height_set)  # type: ignore[attr-defined]
    Entry.entry_scale_manual = property(manual_get, manual_set)  # type: ignore[attr-defined]
    _INSTALLED = True


__all__ = ["install_entry_classification_fields"]
