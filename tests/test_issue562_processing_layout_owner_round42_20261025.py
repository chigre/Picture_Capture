"""Issue #562 Round 42: physically owned page understanding and ordinary Layout roles."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture import processing
from picture_capture.layout import current_page, core_understanding, illustration_mask
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary import layout_roles


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_round42_physical_owners_and_stable_facade_signatures():
    root = ast.parse((ROOT / "processing.py").read_text(encoding="utf-8"))
    layout = ast.parse((ROOT / "layout/current_page.py").read_text(encoding="utf-8"))
    ordinary = ast.parse((ROOT / "ordinary/layout_roles.py").read_text(encoding="utf-8"))
    funcs = {n.name: n for n in root.body if isinstance(n, ast.FunctionDef)}
    assert len(funcs["_understand_page_current"].body) <= 2
    assert len(funcs["_ordinary_entries_from_layout_roles"].body) <= 2
    assert len(funcs["_ordinary_vb_fallback"].body) <= 2
    assert any(isinstance(n, ast.FunctionDef) and n.name == "understand_page_current"
               and len(n.body) >= 10 for n in layout.body)
    for name in ("materialize_layout_role_entries", "ordinary_vb_fallback"):
        assert any(isinstance(n, ast.FunctionDef) and n.name == name
                   and len(n.body) > 5 for n in ordinary.body)
    assert processing._understand_page_current.__module__ == "picture_capture.processing"
    assert processing._ordinary_entries_from_layout_roles.__module__ == "picture_capture.processing"
    assert processing._ordinary_vb_fallback.__module__ == "picture_capture.processing"
    assert list(inspect.signature(processing._ordinary_entries_from_layout_roles).parameters) == [
        "understanding", "image", "page_index", "diagnostics"
    ]
    assert "layout_only" in inspect.signature(processing._understand_page_current).parameters
    assert "profile_page_index" in inspect.signature(processing._ordinary_vb_fallback).parameters


class _Masked:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


def test_round42_mask_trace_source_path_and_analysis_image_lifetime(monkeypatch):
    source = object()
    masked = _Masked()
    calls = {}
    stats = illustration_mask.IllustrationMaskStats(detected=2, masked=1)
    marker = SimpleNamespace(layout=SimpleNamespace(reason="ok"))
    monkeypatch.setattr(
        illustration_mask, "mask_large_illustrations_for_layout",
        lambda image, settings, **kwargs:
            (calls.setdefault("mask", (image, kwargs)) and (masked, stats)),
    )
    monkeypatch.setattr(
        illustration_mask, "append_mask_reason",
        lambda result, current: calls.setdefault("reason", (result, current)),
    )
    monkeypatch.setattr(
        core_understanding, "understand_layout_core",
        lambda image, settings, **kwargs:
            (calls.setdefault("understanding", (image, kwargs)) and marker),
    )
    notes = []
    trace = SimpleNamespace(add_note=lambda *args, **kwargs: notes.append((args, kwargs)))
    previews = []
    result = processing._understand_page_current(
        source, AppSettings(layout_mask_illustrations=True),
        page_index=4, page_sections=[], layout_only=True,
        layout_trace=trace, replay_preview=lambda name, image: previews.append((name, image)),
        source_image_path=Path("saved-page.png"),
    )
    assert result is marker
    assert calls["mask"][0] is source
    assert calls["mask"][1]["source_image_path"] == Path("saved-page.png")
    assert calls["mask"][1]["profile_page_index"] == 4
    assert calls["mask"][1]["candidate_debug"] == []
    assert calls["understanding"][0] is masked
    assert calls["understanding"][1]["trace"] is trace
    assert calls["reason"] == (marker, stats)
    assert previews == [("illustration_mask", masked)]
    assert notes[0][0][0] == "illustration_mask"
    assert notes[0][1]["details"]["masked"] == 1
    assert masked.closed == 1


def test_round42_layout_roles_uses_live_refinement_hook(monkeypatch):
    line = SimpleNamespace(y0=20, y1=32, role="entry")
    column = SimpleNamespace(left=10, lines=[line])
    transform = SimpleNamespace(
        canonical_to_source_point=lambda x, y, size: (x + 1, y + 2)
    )
    layout = SimpleNamespace(
        columns=[column], body_top=100, ordinary_line_height=20.0,
        transform=transform, source_size=(500, 800)
    )
    understanding = SimpleNamespace(layout=layout)
    seen = {}
    def refine(image, page, *, page_index, diagnostics):
        seen.update(image=image, page=page, page_index=page_index, diagnostics=diagnostics)
        return {id(line): 145}
    monkeypatch.setattr(processing, "refined_layout_entry_y_by_line", refine)
    original_entry = processing.Entry
    constructed = []
    def entry_type(**kwargs):
        constructed.append(kwargs)
        return original_entry(**kwargs)
    monkeypatch.setattr(processing, "Entry", entry_type)
    image = Image.new("RGB", (500, 800), "white")
    diagnostics = []
    result = processing._ordinary_entries_from_layout_roles(
        understanding, image, page_index=9, diagnostics=diagnostics
    )
    assert len(result) == 1
    assert (result[0].x, result[0].y) == (11, 147)
    assert seen == {"image": image, "page": understanding,
                    "page_index": 9, "diagnostics": diagnostics}
    assert constructed[0]["ocr_source"] == "page_understanding:ordinary_layout_role"
    assert result[0].issue_type == "PAGE_UNDERSTANDING_ORDINARY_LAYOUT_ROLE"
    image.close()


def test_round42_vb_fallback_retains_live_detector_filter_and_sort(monkeypatch):
    source = Image.new("RGB", (60, 90), "white")
    analysis = source.copy()
    effective = AppSettings(detection_method="combined")
    geometry = object()
    original = Entry(word="", x=7, y=14)
    calls = []
    def detector(image, settings, *, page_sections):
        calls.append(("detect", image, settings.detection_method, page_sections))
        return [original], geometry
    def allowed(entries, image, settings, geom, page_index, sections):
        calls.append(("allowed", image, page_index, sections))
        return entries
    def sorter(entries, geom, sections):
        calls.append(("sort", geom, sections))
        return entries
    monkeypatch.setattr(processing, "_original_detect_entries_left_edge", detector)
    monkeypatch.setattr(processing, "_allowed_entries", allowed)
    monkeypatch.setattr(processing._core, "sort_entries_reading_order", sorter)
    rows, returned = processing._ordinary_vb_fallback(
        analysis, source, AppSettings(), effective,
        profile_page_index=8, page_sections=[]
    )
    assert rows == [original] and returned is geometry
    assert calls[0][0:3] == ("detect", analysis, "left_edge")
    assert calls[1][0:3] == ("allowed", source, 8)
    assert calls[2][0] == "sort"
    assert effective.detection_method == "combined"
    analysis.close()
    source.close()
