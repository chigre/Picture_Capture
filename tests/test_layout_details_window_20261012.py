"""Full detailed Layout text is copyable off-image; candidate labels match IDs."""
from __future__ import annotations

from types import SimpleNamespace

import picture_capture.layout_details_window as panel
import picture_capture.layout_visualization_summary as summary
import picture_capture.layout_visualization_ui_v3 as ui


def test_detailed_layout_text_preserves_untruncated_source_report(monkeypatch):
    snapshot = object()
    monkeypatch.setattr(
        "picture_capture.layout_visualization_ui._snapshot_for_app",
        lambda app: snapshot,
    )
    monkeypatch.setattr(
        summary, "_format_summary",
        lambda app, value: "Layout AUTO\nmethod=real\nraw=123 used=456"
        if value is snapshot else "wrong snapshot",
    )
    assert panel.layout_detail_text(object()) == (
        "Layout AUTO\nmethod=real\nraw=123 used=456"
    )


def test_detailed_scan_never_draws_verbose_diagnostic_text(monkeypatch):
    calls = []
    monkeypatch.setattr(
        summary, "draw_layout_visualization",
        lambda app, *, minimal_text=False:
        calls.append(("geometry", minimal_text)),
    )
    monkeypatch.setattr(
        summary, "_snapshot_for_app",
        lambda app: SimpleNamespace(used_values={}),
    )
    monkeypatch.setattr(
        summary, "_draw_indent_blocks",
        lambda app, snap: calls.append(("indents", True)),
    )
    monkeypatch.setattr(
        summary, "_draw_role_strips",
        lambda app, snap: calls.append(("roles", True)),
    )
    monkeypatch.setattr(
        summary, "_format_summary",
        lambda app, snap: (_ for _ in ()).throw(
            AssertionError("must not compute long text during canvas draw")
        ),
    )
    summary.draw_layout_visualization_detailed(
        SimpleNamespace(canvas=object()),
    )
    assert calls == [
        ("geometry", True), ("indents", True), ("roles", True),
    ]


def test_explicit_detailed_density_opens_separate_window(monkeypatch):
    calls = []
    class _Var:
        def get(self):
            return "详细"
    app = SimpleNamespace(
        redraw=lambda: calls.append("redraw"),
        _layout_display_density_var=_Var(),
    )
    monkeypatch.setattr(
        panel, "show_layout_details_window",
        lambda _app: calls.append("open copyable window"),
    )
    ui.on_layout_density_change(app)
    assert calls == ["redraw", "open copyable window"]


def test_copy_all_uses_actual_visible_report_text():
    class FakeText:
        def __init__(self):
            self.copied = None
        def get(self, a, b):
            assert (a, b) == ("1.0", "end-1c")
            return "Layout AUTO\n详细参数=原始文字"
        def clipboard_clear(self):
            self.copied = ""
        def clipboard_append(self, text):
            self.copied = text
    widget = FakeText()
    panel._copy_detail_text(widget)
    assert widget.copied == "Layout AUTO\n详细参数=原始文字"


def test_real_copyable_toplevel_and_clipboard_if_tk_available(monkeypatch):
    import tkinter as tk
    from tkinter import ttk
    import pytest

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no graphical Tk display")
    root.withdraw()
    try:
        monkeypatch.setattr(
            panel, "layout_detail_text",
            lambda _app: "Layout AUTO\nline 2: methods + complete explanation",
        )
        app = SimpleNamespace(root=root, current_index=8)
        panel.show_layout_details_window(app)
        root.update_idletasks()
        window = app._layout_details_window
        report = app._layout_details_text
        assert window.winfo_exists()
        assert "第9页" in window.title()
        assert "Layout AUTO" in report.get("1.0", "end-1c")
        assert report.cget("state") == "disabled"
        assert isinstance(report, tk.Text)

        # Select and copy all without requiring a keyboard mapping.
        panel._select_all(SimpleNamespace(widget=report))
        assert report.tag_ranges("sel")
        panel._copy_detail_text(report)
        assert "complete explanation" in report.clipboard_get()

        children = []
        def descend(widget):
            for child in widget.winfo_children():
                children.append(child)
                descend(child)
        descend(window)
        labels = [
            widget.cget("text")
            for widget in children if isinstance(widget, ttk.Button)
        ]
        assert "复制全部" in labels and "刷新" in labels

        monkeypatch.setattr(
            panel, "layout_detail_text",
            lambda _app: "第10页\nnew settings",
        )
        app.current_index = 9
        panel.refresh_layout_details_if_open(app)
        assert "第10页" in window.title()
        assert report.get("1.0", "end-1c").startswith("第10页")
        window.destroy()
    finally:
        root.destroy()


def test_compact_settings_has_explicit_copyable_details_action():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ui/compact_display_menu.py"
    ).read_text(encoding="utf-8")
    assert 'text="Layout详细诊断（复制）"' in source
    assert "on_layout_density_change(app)" in source
