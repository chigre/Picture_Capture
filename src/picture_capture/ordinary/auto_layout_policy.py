from __future__ import annotations

"""Page-specific ordinary automatic-layout policy; no persistent settings writes.

The legacy processing core owns the public entrypoint and passes current
dataclass-copy and setting-switch bindings. Layout detection stays lazy.
"""

from collections.abc import Callable
from PIL import Image
from ..models import AppSettings


def ordinary_page_layout_settings(
    image: Image.Image, settings: AppSettings, *,
    replace_fn: Callable[[AppSettings], AppSettings],
    field_switches: tuple[tuple[str, str], ...],
) -> tuple[AppSettings, dict[str, int]]:
    """Return page-specific ordinary settings after optional layout detection.

    The project settings are never mutated.  When the master switch is enabled,
    one layout estimate is made for this page and only explicitly selected
    fields replace their project-level values.  bottom_y is deliberately absent:
    the effective page bottom comes from the page height, Profile footer rule,
    or Page SECTION bounds instead of a manually editable main-panel value.
    """
    current = replace_fn(settings)
    if not bool(getattr(current, "ordinary_auto_layout", False)):
        return current, {}

    from ..layout.detection import detect_layout_parameters

    detector_settings = replace_fn(current)
    if bool(getattr(current, "ordinary_auto_columns", True)):
        # "Auto columns" detects page column count even when
        # the project Profile normally fixes it.
        detector_settings.layout_columns_policy = "detect"
    estimate = detect_layout_parameters(image, detector_settings)

    from ..layout.parameter_evidence import row_padding_is_measured

    applied: dict[str, int] = {}
    for field_name, switch_name in field_switches:
        if not bool(getattr(current, switch_name, True)):
            continue
        if field_name == "row_padding" and not row_padding_is_measured(estimate):
            continue
        value = int(getattr(estimate, field_name))
        setattr(current, field_name, value)
        applied[field_name] = value

    # The old manual-columns/manual-Y mode is retired.  Keep the persisted
    # compatibility fields readable, but never let them alter the new flow.
    current.manual_columns = False
    return current, applied
