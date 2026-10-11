"""Regression coverage for review taskbar fit and unified crop zoom."""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from picture_capture.models import AppSettings, Entry
from picture_capture.review_crop_extension import resize_fixed_review_preview
from picture_capture.ui import workspace_tools


def test_compact_review_reuses_taskbar_and_titlebar_safe_main_window_height():
    import picture_capture.app as app_module

    source = Path(app_module.__file__).read_text(encoding="utf-8")
    review_init = source.split('class ReviewWindow(', 1)[1].split(
        '    def _review_image_area_width(', 1
    )[0]
    assert 'getattr(parent, "workspace_mode", "") in {"极简", "紧凑"}' in review_init
    assert 'work_x, work_y, work_w, safe_client_height = _preset_work_geometry(parent)' in review_init
    assert 'height = max(1, safe_client_height)' in review_init
    # Never revert to the raw OS work height: Tk geometry sizes the *client*.
    assert "height = max(1, work_bottom - y)" not in review_init


def test_work_geometry_subtracts_chrome_and_respects_work_area(monkeypatch):
    monkeypatch.setattr(workspace_tools, "screen_work_area",
                        lambda _win: (0, 0, 1920, 1040))
    monkeypatch.setattr(workspace_tools, "_window_decoration_height",
                        lambda _win: 40)
    assert workspace_tools._preset_work_geometry(object()) == (0, 0, 1920, 1000)
    # The original full 1040 client height would overlap the taskbar by 40px.


def test_normal_compact_and_extreme_page_tooltips_are_identical():
    import picture_capture.app as app_module
    from picture_capture.ui import simple_page_controls
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    compact = Path(simple_page_controls.__file__).read_text(encoding="utf-8")
    extreme = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    for tip in ("切换到上页（Shift + 鼠标右键）", "切换到下页（鼠标右键）"):
        assert tip in source
        assert tip in compact
        assert tip in extreme
    assert 'app._attach_tooltip(\n            button,' in extreme


@pytest.mark.parametrize(
    "prior,current,expected",
    [
        (1.0, 1.5, (150, 75)),
        (1.5, 1.0, (67, 33)),
        (1.0, 0.5, (50, 25)),
        (1.0, 2.0, (200, 100)),
        (None, 1.5, (100, 50)),
    ],
)
def test_pinned_preview_follows_same_zoom_factor_as_normal_and_large_crop(
    prior, current, expected,
):
    assert resize_fixed_review_preview((100, 50), prior, current) == expected
    # A 150px preview at 150% returns to its 100px baseline at 100%.
    assert resize_fixed_review_preview((150, 75), 1.5, 1.0) == (100, 50)


def test_pinned_preview_zoom_changes_without_resizing_on_active_word_change(monkeypatch):
    import picture_capture.app as module

    source = Image.new("RGB", (200, 300), "white")
    entry = Entry("一", 10, 35)
    multi = Entry("多字", 10, 60)
    parent = SimpleNamespace(
        image=source,
        settings=AppSettings(review_extended_crop_height_multiplier=2.5),
        canvas=SimpleNamespace(winfo_width=lambda: 300),
        current_index=0,
        appearance_mode="light",
    )
    geometry = SimpleNamespace()
    monkeypatch.setattr(module, "_review_crop_context",
                        lambda *_args: (parent.settings, geometry))
    monkeypatch.setattr(module, "_review_line_box",
                        lambda entry, *_args, **_kwargs:
                        (10, 35, 110, 55) if entry is multi else (10, 35, 110, 55))
    monkeypatch.setattr(module.ImageTk, "PhotoImage", lambda img: img)

    class Display:
        def __init__(self):
            self.configurations = []
        def configure(self, **kwargs):
            self.configurations.append(kwargs)

    label, host = Display(), Display()
    texts = [SimpleNamespace(get=lambda: "一"), SimpleNamespace(get=lambda: "多字")]
    review = SimpleNamespace(
        parent=parent, vars=texts, _bound_row_entries=lambda: [entry, multi],
        review_zoom=1.0,
        _review_display_crops=[Image.new("RGB", (100, 20)), Image.new("RGB", (100, 36))],
        active_crop_label=label, active_crop_host=host,
        _active_crop_fixed_size=None, _active_crop_fixed_zoom=None,
        active_crop_photo=None,
    )
    module.ReviewWindow._update_active_crop_preview(review, 0)
    assert review._active_crop_fixed_size == (100, 50)
    assert host.configurations[-1]["height"] == 64
    review.review_zoom = 1.5
    review._review_display_crops = [
        Image.new("RGB", (150, 30)), Image.new("RGB", (150, 54)),
    ]
    module.ReviewWindow._update_active_crop_preview(review, 0)
    assert review._active_crop_fixed_size == (150, 75)
    assert host.configurations[-1]["height"] == 89
    module.ReviewWindow._update_active_crop_preview(review, 1)
    assert review._active_crop_fixed_size == (150, 75)
    review.review_zoom = 1.0
    review._review_display_crops = [
        Image.new("RGB", (100, 20)), Image.new("RGB", (100, 36)),
    ]
    module.ReviewWindow._update_active_crop_preview(review, 0)
    assert review._active_crop_fixed_size == (100, 50)
    assert len(label.configurations) == 4


def test_zoom_command_paths_still_render_both_inline_and_fixed_crops():
    import picture_capture.app as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    for method in ("change_review_zoom", "apply_review_zoom_text", "reset_review_zoom"):
        method_body = source.split(f"    def {method}(", 1)[1].split("\n    def ", 1)[0]
        assert "self._request_render_rows(focus_index=active)" in method_body
    pinned = source.split("    def _update_active_crop_preview(", 1)[1].split(
        "    def _schedule_review_crop_height_update(", 1
    )[0]
    assert "resize_fixed_review_preview(" in pinned
    assert "current_zoom = max(0.01, float(self.review_zoom))" in pinned
    assert "self._active_crop_fixed_zoom = current_zoom" in pinned
    assert "round(multiplier * crop.height)" in pinned
