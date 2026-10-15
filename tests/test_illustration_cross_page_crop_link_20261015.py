"""Canonical PPP association and cross-page continuation: synthetic regressions.

These tests use only generated image/PDIC data; no dictionary scans.
"""
from __future__ import annotations

from PIL import Image

from picture_capture import processing_core as core
from picture_capture.crop_plan_formatting import canonical_polygon_link
from picture_capture.formats import write_pdic, write_ppp, read_ppp
from picture_capture.illustration_labels import (
    illustration_labels, previous_entry_ref_for_image,
)
from picture_capture.models import AppSettings, Entry, PolygonRegion
from picture_capture.page_sections import PageSection
from picture_capture.processing_core import Geometry


def geo():
    return Geometry(
        column_starts=[0, 110], column_widths=[100, 100],
        top=0, bottom=400, column_paths=[],
    )


def region(label, x0=20, y0=40, x1=85, y1=85):
    return PolygonRegion(label, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_first_figure_of_new_page_uses_exact_predecessor_last_ordinal():
    entries = [Entry("first local", 15, 150), Entry("second local", 115, 130)]
    labels = illustration_labels(
        [region(""), region("", 120, 40, 180, 85)],
        "080006", geo(), [PageSection(0, 400)],
        entries=entries, associate=True,
        previous_entry_ref=("080005", 13),
    )
    assert labels == ["P_01|080005|013", "P_02|080006|xxx"]
    assert illustration_labels(
        [region("")], "080006", geo(), entries=entries, associate=True,
    ) == ["P_01|080006|xxx"]


def test_in_page_word_takes_precedence_and_existing_cross_page_survives_renumber():
    local = [Entry("first", 15, 10), Entry("second", 15, 150)]
    assert illustration_labels(
        [region("")], "080006", geo(), entries=local, associate=True,
        previous_entry_ref=("080005", 25),
    ) == ["P_01|080006|000"]
    previous = region("P_09|080005|013|AUTO_02")
    assert illustration_labels([previous], "080006", geo()) == [
        "P_01|080005|013|AUTO_02"
    ]
    assert previous.label == "P_09|080005|013|AUTO_02"


def test_previous_ordinal_reads_saved_pdic_and_never_guesses_missing(tmp_path):
    previous = tmp_path / "080005.png"
    Image.new("RGB", (220, 400), "white").save(previous)
    assert previous_entry_ref_for_image(previous) is None
    write_pdic(
        previous.with_suffix(".PDIC"),
        [Entry("A", 10, 10), Entry("B", 10, 150), Entry("C", 110, 80)],
        220, ("080005", "080004", "080006"),
    )
    # Reader is case-aware on Linux. Use the canonical PDIC path in case a
    # managed project places it elsewhere.
    from picture_capture.formats import pdic_path
    target = pdic_path(previous)
    if target != previous.with_suffix(".PDIC"):
        previous.with_suffix(".PDIC").replace(target)
    assert previous_entry_ref_for_image(previous) == ("080005", 2)


def test_canonical_decoder_distinguishes_unlinked_legacy_and_auto():
    assert canonical_polygon_link(region("P_01|080005|013|AUTO_02")) == ("080005", 13)
    assert canonical_polygon_link(region("P_01|080005|000")) == ("080005", 0)
    assert canonical_polygon_link(region("P_01|080005|xxx")) == ("080005", None)
    assert canonical_polygon_link(region("080005|Plate A|linked")) is None
    assert canonical_polygon_link(region("P_01|080005|untrusted")) is None


def fake_pieces(_image, _entries, _settings, **_kwargs):
    ordered = [Entry("first", 15, 150), Entry("second", 15, 250)]
    pieces = [
        core.EntryCropPiecePlan(0, None, "_上页末词条_", (10, 0, 100, 140), "(0-1)"),
        core.EntryCropPiecePlan(0, 0, "first", (10, 140, 100, 240), "(1)"),
        core.EntryCropPiecePlan(1, 1, "second", (10, 240, 100, 390), "(1)"),
    ]
    return ordered, pieces


def plan(monkeypatch, polygons, *, previous=None, integrated=True):
    monkeypatch.setattr(core, "_base_entry_crop_pieces", fake_pieces)
    image = Image.new("RGB", (240, 400), "white")
    return core.build_page_crop_plan(
        image, [Entry("ignored", 15, 150)], polygons, AppSettings(),
        page_stem="080006", previous_entry_ref=previous,
        integrate_illustrations=integrated,
    )


def test_same_page_canonical_link_controls_containment_and_partial_union(monkeypatch):
    polygons = [
        region("P_01|080006|000|AUTO_02", 20, 165, 80, 210),
        region("P_02|080006|000", 85, 190, 120, 220),
        region("P_03|080006|xxx", 20, 170, 60, 200),
        region("P_04|wrong_page|000", 20, 170, 60, 200),
        region("P_05|080006|999", 20, 170, 60, 200),
    ]
    result = plan(monkeypatch, polygons)
    assert [d.relation for d in result.illustrations] == [
        "contained", "partial", "unassociated", "unassociated", "unassociated",
    ]
    assert [d.associated_entry_index for d in result.illustrations] == [
        0, 0, None, None, None,
    ]
    assert result.entry_pieces[1].source_mode == "linked_original"
    assert result.entry_pieces[1].merge_polygon_indices == (1,)
    assert [d.standalone for d in result.illustrations] == [
        False, False, True, True, True,
    ]


def test_previous_page_label_merges_into_ww000_not_current_word_000(monkeypatch):
    figure = region("P_01|080005|013", 20, 30, 80, 85)
    result = plan(monkeypatch, [figure], previous=("080005", 13))
    assert result.illustrations[0].associated_entry_index == -1
    assert result.illustrations[0].relation == "contained"
    assert result.illustrations[0].standalone is False
    assert result.entry_pieces[0].entry_ref_index == -1
    assert result.entry_pieces[0].source_mode == "linked_original"
    assert result.entry_pieces[1].source_mode != "linked_original"
    without_prev = plan(monkeypatch, [figure])
    assert without_prev.illustrations[0].relation == "unassociated"


def test_previous_page_partial_union_and_disabled_integration(monkeypatch):
    figure = region("P_01|080005|013", 85, 55, 125, 100)
    merged = plan(monkeypatch, [figure], previous=("080005", 13))
    assert merged.illustrations[0].relation == "partial"
    assert merged.entry_pieces[0].merge_polygon_indices == (0,)
    assert merged.illustrations[0].standalone is False
    independent = plan(monkeypatch, [figure], previous=("080005", 13), integrated=False)
    assert independent.illustrations[0].standalone is True
    assert independent.entry_pieces[0].merge_polygon_indices == ()


def test_previously_saved_cross_page_label_survives_ppp_roundtrip(tmp_path):
    figure = region("P_01|080005|013|AUTO_01")
    file = tmp_path / "080006.ppp"
    assert write_ppp(file, [figure], "080006")
    persisted = read_ppp(file)
    assert persisted[0].label == "P_01|080005|013|AUTO_01"
    renumbered = illustration_labels(persisted, "080006", geo())
    assert renumbered == ["P_01|080005|013|AUTO_01"]


def test_actual_ww000_export_contains_previous_page_partial_polygon(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_base_entry_crop_pieces", fake_pieces)
    page = tmp_path / "080006.png"
    source = Image.new("RGB", (240, 400), "white")
    source.putpixel((115, 80), (0, 0, 0))
    source.save(page)
    polygon = region("P_01|080005|013", 85, 55, 125, 100)
    output = tmp_path / "QT" / "PWW"
    records = core.split_whole_entries(
        page, [Entry("current first", 15, 150)], AppSettings(),
        output, polygons=[polygon], top_y=0,
        previous_entry_ref=("080005", 13),
    )
    leading = next(r for r in records if "WW_000(0-1)" in r.filename)
    assert leading.box[2] >= 125
    with Image.open(output / leading.filename) as extracted:
        assert extracted.getpixel((115 - leading.box[0], 80 - leading.box[1])) == (0, 0, 0)
    # The explicitly previous-page-owned PPP should NOT be re-emitted as a
    # separate figure when it already travels with WW_000.
    pictures = core.split_illustrations(
        page, [polygon], tmp_path / "QT" / "PIC", AppSettings(),
        entries=[Entry("current first", 15, 150)], top_y=0,
        previous_entry_ref=("080005", 13),
    )
    assert pictures.records == []
    assert pictures.events[0].relation == "partial"
