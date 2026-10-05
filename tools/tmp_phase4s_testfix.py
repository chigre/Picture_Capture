from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEXT = ROOT / "tests/test_next_stage_regressions.py"
CORE = ROOT / "tests/test_core.py"

next_text = NEXT.read_text(encoding="utf-8")
core = CORE.read_text(encoding="utf-8")

old = '''    restore_start = app.index("    def restore_from_pdic_backup(")
    restore_end = app.index("\\n    def restore_from_merged_pdic", restore_start)
    restore = app[restore_start:restore_end]
    assert "settings_snapshot = replace(self.settings)" in restore
    worker = restore[restore.index("        def worker("):restore.index("        def done(", restore.index("        def worker("))]
    assert "self.settings" not in worker
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in worker
'''
new = '''    export_controller = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "export.py"
    ).read_text(encoding="utf-8")
    restore_start = export_controller.index("    def restore_from_pdic_backup(")
    restore = export_controller[restore_start:]
    assert "settings_snapshot = replace(app.settings)" in restore
    worker = restore[
        restore.index("        def worker("):
        restore.index("        def done(", restore.index("        def worker("))
    ]
    assert "app.settings" not in worker
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in worker
'''
assert old in next_text
next_text = next_text.replace(old, new, 1)

old = '''    restore_start = app_text.index("    def restore_from_pdic_backup")
    restore_end = app_text.index("    def restore_from_merged_pdic", restore_start)
    restore = app_text[restore_start:restore_end]
    assert "settings_snapshot = replace(self.settings)" in restore
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in restore
    assert "derive_nominal_geometry(width, height, self.settings)" not in restore
    assert "normalize_page_rgb(opened)" not in restore
'''
new = '''    controller_text = (
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
assert old in core
core = core.replace(old, new, 1)

old = '''    start = controller_text.index("    def backup_pdic(self) -> None:")
    body = controller_text[start:]
    return app_text, wrapper, body
'''
new = '''    start = controller_text.index("    def backup_pdic(self) -> None:")
    end = controller_text.index("    def restore_from_pdic_backup(self) -> None:", start)
    body = controller_text[start:end]
    return app_text, wrapper, body
'''
assert old in core
core = core.replace(old, new, 1)

old = '''    start = controller_text.index("    def export_picdic_index(self) -> None:")
    body = controller_text[start:]
'''
new = '''    start = controller_text.index("    def export_picdic_index(self) -> None:")
    end = controller_text.index("    def backup_pdic(self) -> None:", start)
    body = controller_text[start:end]
'''
assert old in core
core = core.replace(old, new, 1)

NEXT.write_text(next_text.rstrip() + "\n", encoding="utf-8")
CORE.write_text(core.rstrip() + "\n", encoding="utf-8")
