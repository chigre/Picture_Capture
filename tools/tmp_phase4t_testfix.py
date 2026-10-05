from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "src/picture_capture/ui/controllers/export.py"
CORE = ROOT / "tests/test_core.py"
EXPORT_TEST = ROOT / "tests/test_ui_export_controller.py"

export_text = EXPORT.read_text(encoding="utf-8")
assert export_text.count("        app = app.app\n") == 1
export_text = export_text.replace("        app = app.app\n", "        app = self.app\n", 1)
EXPORT.write_text(export_text, encoding="utf-8")

export_test = EXPORT_TEST.read_text(encoding="utf-8")
old_import_assert = '    assert "from ...formats import pdic_path, read_picdic_index_records" in controller\n'
new_import_assert = '    assert "from ...formats import pdic_path, read_pdic, read_picdic_index_records" in controller\n'
assert export_test.count(old_import_assert) == 1
export_test = export_test.replace(old_import_assert, new_import_assert, 1)
EXPORT_TEST.write_text(export_test, encoding="utf-8")

core = CORE.read_text(encoding="utf-8")
old_sort_test = '''def test_v2114_repair_pdic_button_calls_column_y_sort_only():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("def repair_pdic_order_selected_scope")
    end = app_text.index("def backup_pdic", start)
    body = app_text[start:end]
    assert "sort_entries_column_y(" in body
    assert "read_page_sections(page)" in body
    assert "栏号 → Y" in body
    assert "Y → X" not in body
'''
new_sort_test = '''def test_v2114_repair_pdic_button_calls_column_y_sort_only():
    root = Path(__file__).parents[1] / "src" / "picture_capture"
    app_text = (root / "app.py").read_text(encoding="utf-8")
    controller_text = (root / "ui" / "controllers" / "export.py").read_text(encoding="utf-8")
    app_start = app_text.index("    def repair_pdic_order_selected_scope")
    app_end = app_text.index("    def export_picdic_index", app_start)
    wrapper = app_text[app_start:app_end]
    start = controller_text.index("    def repair_pdic_order_selected_scope")
    end = controller_text.index("    def export_picdic_index", start)
    body = controller_text[start:end]
    assert "self._export_controller_for_call().repair_pdic_order_selected_scope()" in wrapper
    assert "sort_entries_column_y(" in body
    assert "read_page_sections(page)" in body
    assert "栏号 → Y" in body
    assert "Y → X" not in body
'''
assert core.count(old_sort_test) == 1
core = core.replace(old_sort_test, new_sort_test, 1)

old_geometry_test = '''def test_v2115_pdic_repair_and_restore_use_header_only_geometry():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    repair_start = app_text.index("    def repair_pdic_order_selected_scope")
    repair_end = app_text.index("    def backup_pdic", repair_start)
    repair = app_text[repair_start:repair_end]
    assert "derive_nominal_geometry(width, height, settings)" in repair
    assert "normalize_page_rgb(opened)" not in repair
    controller_text = (
        Path(__file__).parents[1]
        / "src" / "picture_capture" / "ui" / "controllers" / "export.py"
    ).read_text(encoding="utf-8")
    restore_start = controller_text.index("    def restore_from_pdic_backup")
    restore = controller_text[restore_start:]
    assert "settings_snapshot = replace(app.settings)" in restore
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in restore
    assert "derive_nominal_geometry(width, height, app.settings)" not in restore
    assert "normalize_page_rgb(opened)" not in restore
'''
new_geometry_test = '''def test_v2115_pdic_repair_and_restore_use_header_only_geometry():
    controller_text = (
        Path(__file__).parents[1]
        / "src" / "picture_capture" / "ui" / "controllers" / "export.py"
    ).read_text(encoding="utf-8")
    repair_start = controller_text.index("    def repair_pdic_order_selected_scope")
    repair_end = controller_text.index("    def export_picdic_index", repair_start)
    repair = controller_text[repair_start:repair_end]
    assert "settings = app.settings" in repair
    assert "derive_nominal_geometry(width, height, settings)" in repair
    assert "normalize_page_rgb(opened)" not in repair
    restore_start = controller_text.index("    def restore_from_pdic_backup")
    restore = controller_text[restore_start:]
    assert "settings_snapshot = replace(app.settings)" in restore
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in restore
    assert "derive_nominal_geometry(width, height, app.settings)" not in restore
    assert "normalize_page_rgb(opened)" not in restore
'''
assert core.count(old_geometry_test) == 1
core = core.replace(old_geometry_test, new_geometry_test, 1)
CORE.write_text(core, encoding="utf-8")
