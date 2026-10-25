"""Issue #562: legacy VB recovery is physically owned by ordinary/, not root."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PIL import Image

from picture_capture import processing
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary import visual_fallback


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_legacy_vb_recovery_physical_owner_and_public_signature():
    root = ast.parse((ROOT / "processing/__init__.py").read_text(encoding="utf-8"))
    owner = ast.parse((ROOT / "ordinary/visual_fallback.py").read_text(encoding="utf-8"))
    funcs = {n.name: n for n in root.body if isinstance(n, ast.FunctionDef)}
    implementations = {n.name: n for n in owner.body if isinstance(n, ast.FunctionDef)}
    assert len(funcs["_detect_entries_left_edge"].body) == 2
    assert len(implementations["detect_entries_left_edge_with_recovery"].body) >= 6
    assert processing._detect_entries_left_edge.__module__ == "picture_capture.processing"
    assert list(inspect.signature(processing._detect_entries_left_edge).parameters) == [
        "image", "settings", "page_sections",
    ]
    assert callable(visual_fallback.detect_entries_left_edge_with_recovery)


def test_legacy_vb_cjk_recovery_respects_live_hooks_and_combined_guard(monkeypatch):
    image = Image.new("RGB", (64, 96), "white")
    geometry = object()
    first = Entry(word="initial", x=3, y=10)
    final = Entry(word="recovered", x=3, y=15)
    calls = []

    def detector(image_arg, settings, *, page_sections):
        calls.append(("detector", image_arg, page_sections))
        return [first], geometry

    def topology(image_arg, entries, geom, settings, *, page_sections):
        calls.append(("topology", entries, page_sections))
        return [final]

    def oversized(image_arg, entries, geom, settings, *, page_sections):
        calls.append(("oversized", entries, page_sections))
        return entries

    def sort(entries, geom, sections):
        calls.append(("sort", entries, sections))
        return list(reversed(entries))

    monkeypatch.setattr(processing, "_original_detect_entries_left_edge", detector)
    monkeypatch.setattr(processing, "uses_cjk_role_model", lambda _: True)
    monkeypatch.setattr(processing, "indent_type_label", lambda _: "headword")
    monkeypatch.setattr(processing, "_uses_cjk_indent_topology", lambda _: True)
    monkeypatch.setattr(processing, "finalize_indented_topology", topology)
    monkeypatch.setattr(processing, "recover_cjk_oversized_heads", oversized)
    monkeypatch.setattr(processing._core, "sort_entries_reading_order", sort)
    sections = [object()]
    try:
        rows, geo = processing._detect_entries_left_edge(
            image, AppSettings(detection_method="left_edge"), sections,
        )
        assert rows == [final] and geo is geometry
        assert [item[0] for item in calls] == ["detector", "topology", "oversized", "sort"]
        assert calls[0][1] is image and calls[0][2] is sections
        assert calls[2][1] == [final] and calls[-1][2] is sections

        calls.clear()
        rows, geo = processing._detect_entries_left_edge(
            image, AppSettings(detection_method="combined"), sections,
        )
        assert rows == [first] and geo is geometry
        assert [item[0] for item in calls] == ["detector", "sort"]

        calls.clear()
        monkeypatch.setattr(processing, "indent_type_label", lambda _: "无明显缩进")
        rows, geo = processing._detect_entries_left_edge(
            image, AppSettings(detection_method="left_edge"), sections,
        )
        assert rows == [first] and geo is geometry
        assert [item[0] for item in calls] == ["detector", "sort"]
    finally:
        image.close()


def test_legacy_vb_non_cjk_visual_recovery_order_and_live_patch(monkeypatch):
    image = Image.new("RGB", (48, 64), "white")
    geometry = object()
    first = Entry(word="first", x=1, y=8)
    second = Entry(word="second", x=1, y=12)
    calls = []

    monkeypatch.setattr(processing, "_original_detect_entries_left_edge",
                        lambda img, settings, *, page_sections: ([first], geometry))
    monkeypatch.setattr(processing, "uses_cjk_role_model", lambda _: False)
    monkeypatch.setattr(processing, "indent_type_label", lambda _: "无明显缩进")
    def visual(img, entries, geom, settings, *, page_sections):
        calls.append(("visual", img, entries, page_sections))
        return entries + [second]
    def stabilize(img, entries, geom, settings, *, page_sections):
        calls.append(("stabilize", img, entries, page_sections))
        return list(reversed(entries))
    monkeypatch.setattr(processing, "recover_ordinary_visual_entries", visual)
    monkeypatch.setattr(processing, "stabilize_ordinary_visual_entries", stabilize)
    monkeypatch.setattr(processing._core, "sort_entries_reading_order",
                        lambda entries, geom, sections: (calls.append(("sort", entries, sections)) or entries))
    try:
        result, geo = processing._detect_entries_left_edge(
            image, AppSettings(detection_method="combined"), [],
        )
        assert result == [second, first] and geo is geometry
        assert [item[0] for item in calls] == ["visual", "stabilize", "sort"]
        assert calls[0][1] is image
        assert calls[1][2] == [first, second]
    finally:
        image.close()
