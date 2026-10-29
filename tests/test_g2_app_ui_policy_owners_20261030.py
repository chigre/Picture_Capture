"""G2 app shell: physical policy owners retain live legacy forwarding (synthetic E2).

No Tk root, licensed scan, PDIC/PPP/SECTION file, or user acceptance is involved.
"""
from types import SimpleNamespace

from picture_capture import app
from picture_capture.ui import main_app_lifecycle, review_window_initialization


def test_review_window_dimensions_physical_owner_and_boundary_parity():
    owner = getattr(review_window_initialization, "review_window_dimensions", None)
    assert callable(owner), "review window dimension logic must live in the UI owner"
    for screen_w, screen_h, expected in (
        (1920, 1080, (1152, 756)),
        (800, 600, (560, 420)),
        (320, 240, (320, 240)),
        (0, -10, (1, 1)),
    ):
        assert owner(screen_w, screen_h) == expected
        assert app._review_window_dimensions(screen_w, screen_h) == expected


def test_transformed_geometry_pending_physical_owner_and_fail_closed_parity():
    owner = getattr(main_app_lifecycle, "transformed_geometry_pending", None)
    assert callable(owner), "geometry safety policy must live in the main UI owner"
    for transform, expected in (
        ("identity", False),
        ("mirror_x", False),
        ("rotate_ccw90", False),
        ("rotate_cw90", False),
        ("perspective", True),
        ("rotate_180", True),
        ("", False),
        (None, False),
    ):
        settings = SimpleNamespace(layout_transform=transform)
        assert owner(settings) is expected
        assert app.transformed_geometry_pending(settings) is expected
    assert owner(SimpleNamespace()) is False


def test_app_legacy_wrappers_resolve_live_owner_and_guard_patchpoints(monkeypatch):
    monkeypatch.setattr(review_window_initialization, "review_window_dimensions",
                        lambda _w, _h: (321, 432))
    assert app._review_window_dimensions(1920, 1080) == (321, 432)

    monkeypatch.setattr(main_app_lifecycle, "transformed_geometry_pending",
                        lambda _settings: True)
    settings = SimpleNamespace(layout_transform="identity")
    assert app.transformed_geometry_pending(settings) is True

    class Status:
        text = None

        def set(self, text):
            self.text = text

    status = Status()
    host = SimpleNamespace(settings=settings, status_var=status)
    assert app.PictureCaptureApp._guard_transformed_geometry(host, "导出切图") is False
    assert "导出切图" in status.text
    assert "原图坐标" in status.text

    monkeypatch.setattr(app, "transformed_geometry_pending", lambda _settings: False)
    assert app.PictureCaptureApp._guard_transformed_geometry(host, "导出切图") is True
