"""PPP [X] display is tied to shape visibility, not labels."""
from pathlib import Path

from picture_capture.illustration_delete_geometry import interior_polygon_center


def test_rectangular_illustration_x_at_center():
    assert interior_polygon_center([(10, 20), (110, 20), (110, 80), (10, 80)]) == (60, 50)


def test_concave_illustration_x_remains_inside():
    from picture_capture.illustration_delete_geometry import _inside
    polygon = [(0, 0), (80, 0), (80, 20), (20, 20), (20, 80), (0, 80)]
    x, y = interior_polygon_center(polygon)
    assert _inside(x, y, [(float(a), float(b)) for a, b in polygon])


def test_delete_control_tied_to_shape_not_editable_label():
    source = (Path(__file__).resolve().parents[1] / "src" /
              "picture_capture" / "app.py").read_text(encoding="utf-8")
    overlay = (Path(__file__).resolve().parents[1] / "src" /
               "picture_capture" / "illustration_delete_overlay.py").read_text(encoding="utf-8")
    assert "if show_shapes else None" in source
    assert "delete_button.pack" not in overlay
    assert 'font=fixed_overlay_control_font(app.canvas, app.settings.ocr_language)' in overlay
    assert 'width=3' in overlay
    assert 'padx=1' in overlay and 'pady=0' in overlay
    shared = (Path(__file__).resolve().parents[1] / "src" /
              "picture_capture" / "ui" / "overlay_delete_button.py").read_text(encoding="utf-8")
    assert "OVERLAY_CONTROL_FONT_SIZE = 9" in shared
    assert 'bg="#bdbdbd"' in overlay
    assert 'anchor="center"' in overlay
    assert 'f"ppp-delete-{region_index}"' in overlay
    assert 'self.canvas.coords(record["delete_window"], center_x, center_y)' in source
    assert 'delete_button.pack(side="left"' not in source
