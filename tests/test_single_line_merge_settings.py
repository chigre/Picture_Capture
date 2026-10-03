from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from PIL import Image

from picture_capture.single_line_merge_settings import (
    MERGE_KEY,
    MERGE_LABEL,
    WHITE_TRIM_THRESHOLD,
    _trim_white_border,
    load_merge_by_page,
    merge_page_line_images,
    save_merge_by_page,
)


def test_single_line_merge_setting_uses_crop_settings_store_and_preserves_other_keys(tmp_path):
    root = tmp_path / "project"
    crop_path = root / "QT" / "_CropSettings.json"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_text(
        json.dumps({"version": 5, "entry_left_padding": 7}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_merge_by_page(root) is False
    save_merge_by_page(root, True)

    payload = json.loads(crop_path.read_text(encoding="utf-8"))
    assert payload["version"] == 5
    assert payload["entry_left_padding"] == 7
    assert payload[MERGE_KEY] is True
    assert load_merge_by_page(root) is True


def test_trim_white_border_is_content_tight_and_treats_near_white_as_background():
    image = Image.new("RGB", (12, 9), (253, 253, 253))
    block = Image.new("RGB", (4, 3), (80, 80, 80))
    image.paste(block, (3, 2))
    block.close()

    trimmed = _trim_white_border(image)
    image.close()

    assert WHITE_TRIM_THRESHOLD == 250
    assert trimmed is not None
    try:
        assert trimmed.size == (4, 3)
        assert trimmed.getpixel((0, 0)) == (80, 80, 80)
        assert trimmed.getpixel((3, 2)) == (80, 80, 80)
    finally:
        trimmed.close()


def test_trim_white_border_returns_none_for_blank_slice():
    image = Image.new("RGB", (14, 7), (252, 252, 252))
    trimmed = _trim_white_border(image)
    image.close()
    assert trimmed is None


def test_merge_page_line_images_stacks_in_record_order_and_removes_small_files(tmp_path):
    output = tmp_path / "QT" / "PSW"
    output.mkdir(parents=True)
    page = tmp_path / "page001.jpg"

    first = output / "page001_SW_000.png"
    second = output / "page001_SW_001.png"
    Image.new("RGB", (10, 3), (255, 0, 0)).save(first)
    Image.new("RGB", (6, 4), (0, 0, 255)).save(second)
    manifest = output / "page001.PSWords"
    manifest.write_text(first.name + "\n" + second.name + "\n", encoding="utf-8")

    records = [
        SimpleNamespace(filename=first.name),
        SimpleNamespace(filename=second.name),
    ]
    merged_path = merge_page_line_images(page, records, output)

    assert merged_path == output / "page001_SW_PAGE.png"
    assert merged_path.is_file()
    assert not first.exists()
    assert not second.exists()
    assert manifest.read_text(encoding="utf-8") == "page001_SW_PAGE.png\n"

    with Image.open(merged_path) as merged:
        assert merged.size == (10, 7)
        assert merged.getpixel((1, 1)) == (255, 0, 0)
        assert merged.getpixel((1, 5)) == (0, 0, 255)
        # The narrower lower line is left aligned on a white page canvas.
        assert merged.getpixel((8, 5)) == (255, 255, 255)


def test_merge_trims_each_slice_and_discards_blank_slice_before_stacking(tmp_path):
    output = tmp_path / "QT" / "PSW"
    output.mkdir(parents=True)
    page = tmp_path / "page002.jpg"

    first = output / "page002_SW_000.png"
    blank = output / "page002_SW_001.png"
    third = output / "page002_SW_002.png"

    first_image = Image.new("RGB", (12, 8), "white")
    first_image.paste(Image.new("RGB", (4, 3), "black"), (3, 2))
    first_image.save(first)
    first_image.close()

    Image.new("RGB", (20, 6), (253, 253, 253)).save(blank)

    third_image = Image.new("RGB", (14, 9), (254, 254, 254))
    third_image.paste(Image.new("RGB", (6, 2), (100, 100, 100)), (5, 4))
    third_image.save(third)
    third_image.close()

    manifest = output / "page002.PSWords"
    manifest.write_text(
        first.name + "\n" + blank.name + "\n" + third.name + "\n",
        encoding="utf-8",
    )
    records = [
        SimpleNamespace(filename=first.name),
        SimpleNamespace(filename=blank.name),
        SimpleNamespace(filename=third.name),
    ]

    merged_path = merge_page_line_images(page, records, output)

    assert merged_path == output / "page002_SW_PAGE.png"
    assert not first.exists()
    assert not blank.exists()
    assert not third.exists()
    assert manifest.read_text(encoding="utf-8") == "page002_SW_PAGE.png\n"
    with Image.open(merged_path) as merged:
        # 4x3 first content + 6x2 third content; blank middle slice vanished.
        assert merged.size == (6, 5)
        assert merged.getpixel((0, 0)) == (0, 0, 0)
        assert merged.getpixel((0, 3)) == (100, 100, 100)


def test_merge_all_blank_page_creates_no_useless_page_image(tmp_path):
    output = tmp_path / "QT" / "PSW"
    output.mkdir(parents=True)
    page = tmp_path / "page003.jpg"
    first = output / "page003_SW_000.png"
    second = output / "page003_SW_001.png"
    stale_merged = output / "page003_SW_PAGE.png"
    Image.new("RGB", (10, 4), "white").save(first)
    Image.new("RGB", (12, 5), (254, 254, 254)).save(second)
    Image.new("RGB", (2, 2), "black").save(stale_merged)
    manifest = output / "page003.PSWords"
    manifest.write_text(first.name + "\n" + second.name + "\n", encoding="utf-8")

    result = merge_page_line_images(
        page,
        [SimpleNamespace(filename=first.name), SimpleNamespace(filename=second.name)],
        output,
    )

    assert result is None
    assert not first.exists()
    assert not second.exists()
    assert not stale_merged.exists()
    assert manifest.read_text(encoding="utf-8") == ""


def test_single_line_merge_is_output_only_and_page_worker_reads_crop_option():
    root = Path(__file__).resolve().parents[1]
    merge_source = (
        root / "src" / "picture_capture" / "single_line_merge_settings.py"
    ).read_text(encoding="utf-8")
    worker_source = (
        root / "src" / "picture_capture" / "single_line_parallel.py"
    ).read_text(encoding="utf-8")
    launcher_source = (
        root / "src" / "picture_capture" / "launcher.py"
    ).read_text(encoding="utf-8")

    assert MERGE_LABEL == "单行切图按页合并"
    assert 'CROP_SETTINGS_FILENAME = "_CropSettings.json"' in merge_source
    assert 'command=lambda: _persist_dialog_value(dialog)' in merge_source
    assert '"_save_integrated_crop_settings"' in merge_source
    assert "_trim_white_border(opened)" in merge_source
    assert "split_single_lines(" in worker_source
    assert "merge_page_line_images(image_path, records, output_dir)" in worker_source
    assert worker_source.index("split_single_lines(") < worker_source.index(
        "merge_page_line_images(image_path, records, output_dir)"
    )
    assert "load_merge_by_page(project_root)" in worker_source
    assert "character_height" not in merge_source
    assert "row_padding" not in merge_source
    assert "install_single_line_merge_settings_ui(app_module)" in launcher_source
