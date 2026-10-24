"""Issue #562 Round 44: shared geometry and review-observation physical owners."""
from __future__ import annotations
import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from picture_capture import processing
from picture_capture.models import AppSettings, Entry
from picture_capture.layout import shared_geometry
from picture_capture.ordinary import observation_policy

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_round44_real_owner_and_stable_legacy_api():
    facade = ast.parse((ROOT / "processing.py").read_text(encoding="utf-8"))
    functions = {n.name: n for n in facade.body if isinstance(n, ast.FunctionDef)}
    for name in ("_geometry_from_page_understanding", "_ordinary_settings_for_shared_geometry",
                 "_allowed_entries", "_review_candidates_from_cache",
                 "_hard_negative_rows_from_candidates"):
        assert len(functions[name].body) <= 2
        assert getattr(processing, name).__module__ == "picture_capture.processing"
    for owner, names in (
        ("layout/shared_geometry.py", ("geometry_from_page_understanding", "ordinary_settings_for_shared_geometry")),
        ("ordinary/observation_policy.py", ("allowed_entries", "review_candidates_from_cache",
                                            "hard_negative_rows_from_candidates")),
    ):
        parsed = ast.parse((ROOT / owner).read_text(encoding="utf-8"))
        funcs = {n.name: n for n in parsed.body if isinstance(n, ast.FunctionDef)}
        assert all(len(funcs[n].body) >= 3 for n in names)
    assert list(inspect.signature(processing._allowed_entries).parameters) == [
        "entries", "image", "settings", "geometry", "profile_page_index", "page_sections",
    ]


def test_round44_geometry_live_factories_and_compatibility_helper(monkeypatch):
    calls = []
    def path_factory(points):
        calls.append(("path", points))
        return points
    def geometry_factory(**kwargs):
        calls.append(("geometry", kwargs))
        return SimpleNamespace(**kwargs)
    monkeypatch.setattr(processing._core, "ColumnPath", path_factory)
    monkeypatch.setattr(processing._core, "Geometry", geometry_factory)
    layout = SimpleNamespace(
        columns=[SimpleNamespace(left=20, right=90), SimpleNamespace(left=140, right=240)],
        body_top=55, body_bottom=600, transform=object(), source_size=(300, 700),
    )
    got = processing._geometry_from_page_understanding(SimpleNamespace(layout=layout))
    assert got.column_starts == [20, 140] and got.column_widths == [70, 100]
    assert got.column_paths == [[(55, 20), (600, 20)], [(55, 140), (600, 140)]]
    assert got.transform is layout.transform and got.source_size == (300, 700)
    assert [row[0] for row in calls] == ["path", "path", "geometry"]
    assert processing._geometry_from_page_design(layout).column_starts == [20, 140]


def test_round44_freeze_nonuniform_columns_without_mutating_settings(monkeypatch):
    from dataclasses import replace
    source = AppSettings(columns=3, manual_x=5, column_width=70, gutter=4)
    source.ordinary_auto_layout = True
    source.follow_column_deformation = True
    copies = []
    monkeypatch.setattr(processing, "replace",
                        lambda s: (copies.append(s) or replace(s)))
    geo = SimpleNamespace(column_starts=[30, 160, 315],
                          column_widths=[110, 110, 110], top=70)
    frozen = processing._ordinary_settings_for_shared_geometry(source, geo, method="combined")
    assert copies == [source] and frozen is not source
    assert source.ordinary_auto_layout is True
    assert not frozen.ordinary_auto_layout and not frozen.follow_column_deformation
    assert frozen.detection_method == "combined" and frozen.start_y == 70
    assert frozen.column_width == 110 and frozen.gutter == 20
    assert frozen.column_start_offsets == [0, 0, 25]


def test_round44_source_size_template_and_section_filters(monkeypatch):
    image = Image.new("RGB", (40, 60), "white")
    a, b = Entry(word="a", x=3, y=5), Entry(word="b", x=3, y=35)
    calls = []
    monkeypatch.setattr(processing._core, "normalize_page_rgb",
                        lambda _: (_ for _ in ()).throw(AssertionError("unnecessary copy")))
    monkeypatch.setattr(processing._core, "effective_page_settings",
                        lambda settings, size, idx: (calls.append(("size", size, idx)) or settings))
    monkeypatch.setattr(processing._core, "entry_allowed_by_page_template",
                        lambda x, y, size, settings, idx: (calls.append(("template", y)) or True))
    monkeypatch.setattr(processing._core, "v_is_inside_sections",
                        lambda v, sections, top, bottom: v < 20)
    geo = SimpleNamespace(top=0, bottom=60, source_to_canonical=lambda x, y: (x, y))
    try:
        assert processing._allowed_entries([a, b], image, AppSettings(), geo, 7, [object()]) == [a]
        assert calls[0] == ("size", (40, 60), 7)
    finally:
        image.close()


def test_round44_cache_readonly_and_hard_negative_live_callbacks(tmp_path, monkeypatch):
    cache = tmp_path / "ocr.json"
    cache.write_text(json.dumps({"review_candidates": [{"id": 1}, 2, {"id": 2}]}),
                     encoding="utf-8")
    before = cache.read_bytes()
    assert processing._review_candidates_from_cache(cache) == [{"id": 1}, {"id": 2}]
    assert cache.read_bytes() == before
    assert processing._review_candidates_from_cache(tmp_path / "missing") == []
    cache.write_text("{invalid", encoding="utf-8")
    assert processing._review_candidates_from_cache(cache) == []
    monkeypatch.setattr(processing.json, "loads", lambda _: {"review_candidates": [{"patched": 1}]})
    assert processing._review_candidates_from_cache(cache) == [{"patched": 1}]
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    geo = object()
    monkeypatch.setattr(processing._core, "_latent_review_rows",
                        lambda values, geometry: [(rows[0], 0, 8), (rows[1], 1, 31), (rows[2], 1, 42)])
    def consensus(row):
        if row is rows[2]:
            raise ValueError("bad row")
        return row is rows[1]
    monkeypatch.setattr(processing._core, "_review_candidate_hard_negative_consensus", consensus)
    assert processing._hard_negative_rows_from_candidates(rows, geo) == [(1, 31)]
    monkeypatch.setattr(processing._core, "_latent_review_rows",
                        lambda *args: (_ for _ in ()).throw(ValueError("bad geometry")))
    assert processing._hard_negative_rows_from_candidates(rows, geo) == []
