from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_binary_finalize import finalize_binary_physical_roles


def _line() -> SimpleNamespace:
    return SimpleNamespace(role="unknown")


def _mode(center: float, support: int, role: str = "unknown") -> SimpleNamespace:
    lines = [_line() for _ in range(support)]
    return SimpleNamespace(center=center, support=support, role=role, lines=lines)


def test_finalizer_rebuilds_entry_and_body_after_legacy_sparse_modes() -> None:
    # Simulate a finished column after legacy propagation: several modes are
    # still unknown and an old sparse mode has been tagged entry.
    entry = _mode(0.0, 16, "unknown")
    body = _mode(26.0, 50, "body")
    stray = _mode(43.0, 1, "entry")
    deep = _mode(97.0, 1, "unknown")
    extra_line = _line()
    column = SimpleNamespace(
        indent_modes=[entry, body, stray, deep],
        lines=entry.lines + body.lines + stray.lines + deep.lines + [extra_line],
        entry_modes=[stray],
        body_mode=body,
    )
    layout = SimpleNamespace(indent_type="body", columns=[column])

    result = finalize_binary_physical_roles(layout)

    assert result is layout
    assert column.entry_modes == [entry]
    assert entry.role == "entry"
    assert all(line.role == "entry" for line in entry.lines)
    assert all(mode.role == "body" for mode in (body, stray, deep))
    assert all(line.role == "body" for mode in (body, stray, deep) for line in mode.lines)
    assert extra_line.role == "body"
    assert column.body_mode is body


def test_finalizer_keeps_single_lane_column_as_body() -> None:
    only = _mode(3.0, 12, "unknown")
    column = SimpleNamespace(
        indent_modes=[only],
        lines=list(only.lines),
        entry_modes=[],
        body_mode=None,
    )
    layout = SimpleNamespace(indent_type="body", columns=[column])

    finalize_binary_physical_roles(layout)

    assert only.role == "body"
    assert all(line.role == "body" for line in only.lines)
    assert column.entry_modes == []
    assert column.body_mode is only
