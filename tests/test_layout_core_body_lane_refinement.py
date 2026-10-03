from types import SimpleNamespace

from picture_capture.layout_core_understanding import _resolve_directional_body_lanes


def _line():
    return SimpleNamespace(role="unknown")


def _mode(center: float, tolerance: float, support: int):
    lines = [_line() for _ in range(support)]
    return SimpleNamespace(
        center=float(center),
        tolerance=float(tolerance),
        support=int(support),
        role="unknown",
        lines=lines,
    )


def test_singleton_19px_lane_is_body_next_to_24_33px_body_family() -> None:
    # Reproduces the diagnostic page: outer entry lane at 0, one singleton at
    # 19, and the dominant body family centred near 31.  The 19px lane is much
    # closer to the body interval than to the true entry family and must not
    # create a false entry separator.
    entry = _mode(0.0, 1.0, 25)
    near_body = _mode(19.0, 1.0, 1)
    body = _mode(31.0, 8.0, 32)  # normalized body interval ~= 23..39
    column = SimpleNamespace(
        indent_modes=[entry, near_body, body],
        lines=entry.lines + near_body.lines + body.lines,
        body_mode=body,
        entry_modes=[entry, near_body],
    )
    layout = SimpleNamespace(
        indent_type="body",
        ordinary_line_height=35.0,
        columns=[column],
        display_heads=[],
    )

    _resolve_directional_body_lanes(layout)

    assert entry.role == "entry"
    assert near_body.role == "body"
    assert body.role == "body"
    assert column.body_mode is body
    assert column.entry_modes == [entry]
    assert all(line.role == "entry" for line in entry.lines)
    assert all(line.role == "body" for line in near_body.lines + body.lines)
