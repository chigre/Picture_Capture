from __future__ import annotations

"""Synchronize binary physical-indent lane roles onto every LayoutLine.

Physical-indent clustering decides which lane is ``entry``.  The row overlay,
however, reads ``LayoutLine.role``.  Keep those two representations strictly in
sync: rows in the entry lane are entry; every other detected row is body.
"""

from typing import Any, Callable


def _sync_column_line_roles(column: Any) -> None:
    modes = list(getattr(column, "indent_modes", []) or [])
    entry_modes = set(id(mode) for mode in (getattr(column, "entry_modes", []) or []))

    assigned: set[int] = set()
    for mode in modes:
        role = "entry" if id(mode) in entry_modes else "body"
        mode.role = role
        for line in list(getattr(mode, "lines", []) or []):
            try:
                line.role = role
                assigned.add(id(line))
            except Exception:
                pass

    # Lines that were detected but did not enter any physical-indent mode are
    # still ordinary page rows; under the requested binary policy they are body.
    for line in list(getattr(column, "lines", []) or []):
        if id(line) in assigned:
            continue
        try:
            line.role = "body"
        except Exception:
            pass


def install_binary_line_role_sync() -> None:
    """Wrap Page Design role assignment and propagate lane roles to rows."""
    from . import dictionary_page_design as page_design

    if getattr(page_design, "_binary_line_role_sync_installed", False):
        return

    original: Callable[..., Any] = page_design._assign_indent_semantics

    def synchronized(column: Any, indent_type: str, reference: float) -> Any:
        result = original(column, indent_type, reference)
        _sync_column_line_roles(column)
        return result

    page_design._assign_indent_semantics = synchronized
    page_design._binary_line_role_sync_installed = True
