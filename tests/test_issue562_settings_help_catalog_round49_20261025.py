"""Issue #562 Round 49: move complete Settings help metadata without changing UI."""
from __future__ import annotations

import ast
from pathlib import Path

from picture_capture.ui.settings import schema
from picture_capture.ui.settings import help_catalog
from picture_capture.ui.settings import refinement_settings_help


ROOT = Path(__file__).resolve().parents[1]
METADATA = ("SETTING_LABELS", "SETTING_HELP", "SETTING_HELP_IMAGES", "CHECK_HELP")


def test_help_catalog_is_canonical_owner_and_schema_is_compatibility_export():
    schema_path = ROOT / "src/picture_capture/ui/settings/schema.py"
    owner_path = ROOT / "src/picture_capture/ui/settings/help_catalog.py"
    schema_text = schema_path.read_text(encoding="utf-8")
    owner_text = owner_path.read_text(encoding="utf-8")
    owner_tree = ast.parse(owner_text)
    assignments = {
        name.id: node.value
        for node in owner_tree.body if isinstance(node, ast.Assign)
        for name in node.targets if isinstance(name, ast.Name)
    }
    for name in METADATA:
        assert f"{name} = _help_catalog.{name}" in schema_text
        assert isinstance(assignments[name], ast.Dict)
        assert getattr(schema, name) is getattr(help_catalog, name)
    assert "tkinter" not in owner_text
    assert "picture_capture.app" not in owner_text


def test_refinement_spread_and_existing_help_contracts_remain_identical():
    for key, value in refinement_settings_help.REFINEMENT_SETTING_HELP.items():
        assert help_catalog.SETTING_HELP[key] == value
    for key, value in refinement_settings_help.REFINEMENT_CHECK_HELP.items():
        assert help_catalog.CHECK_HELP[key] == value
    assert "共享 OCR 通道" in schema.SETTING_HELP["paddle_lens_mode"]
    assert "兼容字段" in schema.SETTING_HELP["ocr_engine"]
    assert "Layout Core" in schema.CHECK_HELP["ordinary_auto_layout"]
    assert "运行模式仍为 off" in schema.CHECK_HELP["paddle_enable_lens"]
    assert "ref_box_action_position" in schema.SETTING_HELP
    assert "ref_box_delete_always_visible" in schema.CHECK_HELP
    assert "character_height" in schema.SETTING_LABELS
    assert isinstance(schema.SETTING_HELP_IMAGES, dict)


def test_source_audit_follows_physical_help_owner_and_preserves_runtime_keys():
    import importlib.util
    path = ROOT / "scripts/audit_settings_runtime.py"
    spec = importlib.util.spec_from_file_location("round49_settings_audit", path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    assert audit.SCHEMA.name == "schema.py"
    assert audit.HELP_CATALOG.name == "help_catalog.py"
    keys = audit.schema_help_keys()
    for name in ("SETTING_HELP", "CHECK_HELP"):
        assert keys[name]
        assert keys[name] <= set(getattr(schema, name))
    for key in ("paddle_lens_mode", "ocr_engine", "ref_box_fill_color"):
        assert key in keys["SETTING_HELP"]
    for key in ("paddle_enable_lens", "ordinary_auto_layout", "ref_box_show"):
        assert key in keys["CHECK_HELP"]


def test_help_metadata_keeps_mutable_aliases_for_existing_gui_extensions():
    # No frozen/copying metadata layer: class-level overrides still work and
    # a patched shared mapping remains visible from both existing import paths.
    key = "_round49_transient_help"
    try:
        schema.SETTING_HELP[key] = "temporary"
        assert help_catalog.SETTING_HELP[key] == "temporary"
    finally:
        schema.SETTING_HELP.pop(key, None)
    assert key not in help_catalog.SETTING_HELP
