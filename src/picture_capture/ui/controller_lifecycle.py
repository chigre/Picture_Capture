"""Single UI-owned lazy controller cache; no imports from the large Tk shell."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

ControllerT = TypeVar("ControllerT")


def get_or_create_controller(
    app: Any, cache_key: str, controller_type: Callable[..., ControllerT], /,
    **constructor_kwargs: Any,
) -> ControllerT:
    """Use app.__dict__ exactly as before; only initialize when absent or None."""
    cache = app.__dict__
    controller = cache.get(cache_key)
    if controller is None:
        controller = controller_type(app, **constructor_kwargs)
        cache[cache_key] = controller
    return controller
