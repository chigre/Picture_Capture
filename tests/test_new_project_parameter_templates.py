"""New project defaults and source-volume parameter reuse."""
import json
from pathlib import Path
from types import SimpleNamespace

from picture_capture.models import AppSettings
from picture_capture.project_storage import crop_settings_path, settings_path
from picture_capture.project_parameter_templates import (
    apply_parameters_to_project, capture_parameters, save_default_parameters,
)


def _configured_source(root):
    root.mkdir()
    settings = AppSettings()
    settings.right_ratio = 13
    settings.columns = 3
    settings.ocr_language = "ita"
    settings.image_suffix = ".jpg"
    settings.dictionary_full_name = "Old volume"
    settings.page_bookmarks = ["page003"]
    settings.to_json(settings_path(root))
    crop = crop_settings_path(root, "_CropSettings.json")
    crop.parent.mkdir(parents=True, exist_ok=True)
    crop.write_text(json.dumps({
        "parallel_workers": 3,
        "merge_by_page": True,
        "special_pages": {"page001": {"top_y": 22}},
    }), encoding="utf-8")
    return settings


def test_save_default_and_apply_to_new_volume_without_identity_fields(tmp_path):
    source = tmp_path / "volume_1"
    settings = _configured_source(source)
    template = tmp_path / "default.json"
    save_default_parameters(settings, source, path=template)
    data = json.loads(template.read_text(encoding="utf-8"))
    assert "dictionary_full_name" not in data["settings"]
    assert "special_pages" not in data["crop_settings"]
    target = tmp_path / "volume_2"
    target.mkdir()
    new = AppSettings()
    new.image_suffix = ".tif"
    new.dictionary_full_name = "Volume 2"
    project = SimpleNamespace(root=target, settings=new)
    assert apply_parameters_to_project(project, default_path=template) is True
    assert project.settings.columns == 3
    assert project.settings.right_ratio == 13
    assert project.settings.ocr_language == "ita"
    assert project.settings.image_suffix == ".tif"
    assert project.settings.dictionary_full_name == "Volume 2"
    assert project.settings.page_bookmarks == []
    copied = json.loads(crop_settings_path(target, "_CropSettings.json").read_text(encoding="utf-8"))
    assert copied["parallel_workers"] == 3
    assert "special_pages" not in copied


def test_copy_parameters_from_existing_project_with_no_cross_volume_data(tmp_path):
    source = tmp_path / "original"
    _configured_source(source)
    (source / "page001.PDIC").write_text("hello#1#2", encoding="utf-8")
    target = tmp_path / "next"
    target.mkdir()
    project = SimpleNamespace(root=target, settings=AppSettings())
    assert apply_parameters_to_project(project, source_project=source)
    assert project.settings.columns == 3
    assert not list(target.rglob("*.PDIC"))


def test_new_project_ui_exposes_defaults_and_existing_volume_source():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    gui = (root / "app.py").read_text(encoding="utf-8")
    controller = (root / "ui/controllers/project.py").read_text(encoding="utf-8")
    assert "_project_templates.add_default_button(footer, self)" in gui
    assert "_project_templates.apply_parameters_to_project(project, parameter_template_root)" in gui
    assert 'title="选择要复制参数的已有项目目录"' in controller
    assert '"parameter_template_root": template_root' in controller
