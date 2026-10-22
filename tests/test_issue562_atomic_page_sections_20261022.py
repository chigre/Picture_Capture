"""Issue #562: SECTION writes must be complete, isolated, and migration-safe."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from PIL import Image
import pytest

import picture_capture.page_sections as section_io
from picture_capture.geometry.coordinate_space import SOURCE_COORDINATE_SPACE
from picture_capture.page_sections import (
    PAGE_SECTIONS_FORMAT, PageSection, read_page_sections, write_page_sections,
)
from picture_capture.project_storage import page_sections_path_for_image


def _page(tmp_path: Path, name: str = "scan.png") -> Path:
    image = tmp_path / name
    Image.new("RGB", (150, 210), "white").save(image)
    return image


def _new_temp_files(path: Path) -> list[Path]:
    return list(path.parent.glob(f".{path.name}.*.tmp"))


@pytest.mark.parametrize(
    "transform, sections",
    [
        ("identity", [PageSection(8, 65), PageSection(80, 180)]),
        ("mirror_x", [PageSection(8, 65), PageSection(80, 180)]),
        ("rotate_ccw90", [PageSection(8, 50), PageSection(65, 125)]),
        ("rotate_cw90", [PageSection(8, 50), PageSection(65, 125)]),
    ],
)
def test_section_atomic_roundtrip_preserves_original_xy_and_v2_schema(
    tmp_path: Path, transform: str, sections: list[PageSection],
):
    image = _page(tmp_path)
    path = write_page_sections(image, sections, layout_transform=transform)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert path == page_sections_path_for_image(image)
    assert raw["format"] == PAGE_SECTIONS_FORMAT
    assert raw["version"] == 2
    assert raw["coordinate_space"] == SOURCE_COORDINATE_SPACE
    assert raw["source_width"] == 150
    assert raw["source_height"] == 210
    assert raw["layout_transform_internal"] == transform
    assert len(raw["sections"]) == len(sections)
    assert all(
        len(row["top_source_segment_xyxy"]) == 2
        and len(row["bottom_source_segment_xyxy"]) == 2
        for row in raw["sections"]
    )
    assert read_page_sections(image) == sections
    assert _new_temp_files(path) == []


@pytest.mark.parametrize("fault", ["fsync", "replace"])
def test_failed_section_commit_preserves_original_file_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
):
    image = _page(tmp_path)
    original = [PageSection(0, 70), PageSection(90, 190)]
    sidecar = write_page_sections(image, original)
    snapshot = sidecar.read_bytes()
    attempts: list[str] = []

    def fail(*_args, **_kwargs):
        attempts.append(fault)
        raise OSError(f"injected {fault} failure")

    monkeypatch.setattr(section_io.os, fault, fail)
    with pytest.raises(OSError, match=f"injected {fault} failure"):
        write_page_sections(image, [PageSection(10, 60)])

    assert attempts == [fault]
    assert sidecar.read_bytes() == snapshot
    assert read_page_sections(image) == original
    assert _new_temp_files(sidecar) == []


def test_failed_first_section_save_does_not_create_partial_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    image = _page(tmp_path)
    target = page_sections_path_for_image(image)

    def no_replace(*_args, **_kwargs):
        raise OSError("replace injection")

    monkeypatch.setattr(section_io.os, "replace", no_replace)
    with pytest.raises(OSError, match="replace injection"):
        write_page_sections(image, [PageSection(0, 80)])

    assert not target.exists()
    assert _new_temp_files(target) == []


def test_concurrent_same_page_section_writers_produce_one_complete_record(
    tmp_path: Path,
):
    image = _page(tmp_path)
    payloads = [
        [PageSection(3 + index, 72 + index), PageSection(90 + index, 180 + index)]
        for index in range(8)
    ]

    def publish(sections: list[PageSection]) -> Path:
        return write_page_sections(image, sections)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(publish, payloads))
    target = page_sections_path_for_image(image)
    assert all(saved == target for saved in results)
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["format"] == PAGE_SECTIONS_FORMAT
    assert raw["version"] == 2
    assert read_page_sections(image) in payloads
    assert _new_temp_files(target) == []


def test_old_fixed_tmp_cannot_override_new_sidecar(tmp_path: Path):
    image = _page(tmp_path)
    target = page_sections_path_for_image(image)
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy_staging = target.with_suffix(target.suffix + ".tmp")
    legacy_staging.write_text("{partial legacy tmp", encoding="utf-8")

    sections = [PageSection(12, 90)]
    write_page_sections(image, sections)
    assert read_page_sections(image) == sections
    # This file belongs to the *retired* fixed-tmp writer, not our transaction.
    assert legacy_staging.read_text(encoding="utf-8") == "{partial legacy tmp"
    assert _new_temp_files(target) == []


def test_section_zero_still_unlinks_nonmigrated_canonical_sidecar(
    tmp_path: Path,
):
    image = _page(tmp_path)
    target = write_page_sections(image, [PageSection(0, 180)])
    assert target.exists()
    assert write_page_sections(image, []) == target
    assert not target.exists()
    assert read_page_sections(image) == []
    assert _new_temp_files(target) == []
