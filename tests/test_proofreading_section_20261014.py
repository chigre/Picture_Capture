"""SECTION attribution follows original image XY and persisted transform/digest."""
from __future__ import annotations

from PIL import Image

from picture_capture.page_sections import PageSection, write_page_sections
from picture_capture.proofreading_events import (
    append_event, make_event, sha256_file,
)
from picture_capture.proofreading_quality_export import summarize_local_events
from picture_capture.proofreading_section import (
    section_fields_for_event, section_snapshot_for_source_point,
)


def test_section_identity_and_gap_never_nearest_neighbor(tmp_path):
    image = tmp_path / "page.png"
    Image.new("RGB", (100, 160), "white").save(image)
    write_page_sections(
        image, [PageSection(0, 65), PageSection(85, 150)],
        layout_transform="identity",
    )
    first = section_snapshot_for_source_point(image, 10, 30)
    second = section_snapshot_for_source_point(image, 10, 100)
    assert first is not None and second is not None
    assert first[0] == "section:1"
    assert second[0] == "section:2"
    assert first[1] == second[1]
    assert section_snapshot_for_source_point(image, 10, 75) is None
    assert section_snapshot_for_source_point(image, -1, 20) is None
    assert section_fields_for_event(
        image, before_xy=(10, 30), after_xy=(10, 100),
    ) == {"section_id": None, "section_snapshot_sha256": None}


def test_rotated_scan_uses_source_x_as_canonical_v(tmp_path):
    image = tmp_path / "rotated.png"
    Image.new("RGB", (200, 80), "white").save(image)
    write_page_sections(
        image, [PageSection(95, 125), PageSection(150, 195)],
        layout_transform="rotate_ccw90",
    )
    # rotate_ccw90: canonical v == source_width - 1 - source_x.
    assert section_snapshot_for_source_point(image, 90, 12)[0] == "section:1"
    assert section_snapshot_for_source_point(image, 20, 12)[0] == "section:2"
    assert section_snapshot_for_source_point(image, 55, 12) is None


def test_section_export_requires_frozen_sidecar_and_image_fingerprint(tmp_path):
    image = tmp_path / "page.png"
    Image.new("RGB", (100, 160), "white").save(image)
    write_page_sections(
        image, [PageSection(0, 65), PageSection(85, 150)],
        layout_transform="identity",
    )
    pdic = tmp_path / "page.pdic"
    pdic.write_bytes(b"saved pdic")
    journal = tmp_path / "journal.json"
    section = section_fields_for_event(image, after_xy=(10, 110))
    assert section["section_id"] == "section:2"
    event = make_event(
        page_id="project/page", action="add", before=None,
        after={"word": "do not export", "x": 10, "y": 110},
        entry_id="stable-1", image_sha256=sha256_file(image),
        pdic_sha256=sha256_file(pdic), **section,
    )
    append_event(journal, event, pdic_file=pdic)
    result = summarize_local_events(
        journal, pdic, image_path=image,
        project_id="proj1", license_statement="audit only",
    )
    assert result["section_unattributed_events"] == 0
    assert result["section_snapshot_stale_events"] == 0
    assert sum(result["section_counts_hashed"].values()) == 1
    write_page_sections(
        image, [PageSection(0, 60), PageSection(95, 150)],
        layout_transform="identity",
    )
    changed = summarize_local_events(
        journal, pdic, image_path=image,
        project_id="proj1", license_statement="audit only",
    )
    assert changed["section_unattributed_events"] == 1
    assert changed["section_snapshot_stale_events"] == 1
    assert "do not export" not in str(changed)


def test_unconfigured_or_invalid_section_file_is_not_fabricated(tmp_path):
    image = tmp_path / "page.png"
    Image.new("RGB", (100, 160), "white").save(image)
    assert section_snapshot_for_source_point(image, 10, 20) is None
    assert section_fields_for_event(image, after_xy=(10, 20)) == {
        "section_id": None, "section_snapshot_sha256": None,
    }
