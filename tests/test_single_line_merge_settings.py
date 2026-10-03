from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from PIL import Image

from picture_capture.single_line_merge_settings import (
    MERGE_KEY,
    MERGE_LABEL,
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


def test_single_line_merge_is_output_only_and_main_runtime_reads_crop_option():
    root = Path(__file__).resolve().parents[1]
    merge_source = (
        root / "src" / "picture_capture" / "single_line_merge_settings.py"
    ).read_text(encoding="utf-8")
    runtime_source = (
        root / "src" / "picture_capture" / "postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")
    launcher_source = (
        root / "src" / "picture_capture" / "launcher.py"
    ).read_text(encoding="utf-8")

    assert MERGE_LABEL == "单行切图按页合并"
    assert 'CROP_SETTINGS_FILENAME = "_CropSettings.json"' in merge_source
    assert 'command=lambda: _persist_dialog_value(dialog)' in merge_source
    assert '"_save_integrated_crop_settings"' in merge_source
    assert "split_single_lines(" in runtime_source
    assert "merge_page_line_images(image_path, records, output_dir)" in runtime_source
    assert runtime_source.index("split_single_lines(") < runtime_source.index(
        "merge_page_line_images(image_path, records, output_dir)"
    )
    assert "load_merge_by_page(project_root)" in runtime_source
    assert "Image.crop(" not in merge_source
    assert "character_height" not in merge_source
    assert "row_padding" not in merge_source
    assert "install_single_line_merge_settings_ui(app_module)" in launcher_source
