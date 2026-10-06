from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tests/test_next_stage_regressions.py"
text = PATH.read_text(encoding="utf-8")

old_round2 = '''    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile_text = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")

    app_start = app_text.index("class PictureCaptureApp")
    training_start = app_text.index("    def export_training_package(", app_start)
    training_end = app_text.index("\\n    def show_help_dialog", training_start)
    training = app_text[training_start:training_end]
    assert 'items: list[object] = ["__prepare__"]' in training
    assert "context_files[:] = copy_project_context(project.root, staging)" in training
    assert "make_training_zip(" in training
    assert "should_stop=self._batch_stop_event.is_set" in training
    assert "shutil.rmtree(staging, ignore_errors=True)" in training
    done_start = training.index("        def done(")
    done = training[done_start:]
    assert "shutil.rmtree(staging, ignore_errors=True)" not in done
    assert 'self._start_ui_worker(' in done
'''
new_round2 = '''    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile_text = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    export_controller_text = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "export.py"
    ).read_text(encoding="utf-8")

    app_start = app_text.index("class PictureCaptureApp")
    wrapper_start = app_text.index("    def export_training_package(", app_start)
    wrapper_end = app_text.index("\\n    def show_help_dialog", wrapper_start)
    wrapper = app_text[wrapper_start:wrapper_end]
    assert "self._export_controller_for_call().export_training_package()" in wrapper

    training_start = export_controller_text.index("    def export_training_package(")
    training_end = export_controller_text.index("\\n    def build_picdic", training_start)
    training = export_controller_text[training_start:training_end]
    assert 'items: list[object] = ["__prepare__"]' in training
    assert "context_files[:] = copy_project_context(project.root, staging)" in training
    assert "make_training_zip(" in training
    assert "should_stop=app._batch_stop_event.is_set" in training
    assert "shutil.rmtree(staging, ignore_errors=True)" in training
    done_start = training.index("        def done(")
    done = training[done_start:]
    assert "shutil.rmtree(staging, ignore_errors=True)" not in done
    assert 'app._start_ui_worker(' in done
'''
if text.count(old_round2) != 1:
    raise SystemExit(f"round2 assertion block match count: {text.count(old_round2)}")
text = text.replace(old_round2, new_round2, 1)

old_concurrency = '''    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    training = (root / "src" / "picture_capture" / "training_export.py").read_text(encoding="utf-8")
'''
new_concurrency = '''    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    training = (root / "src" / "picture_capture" / "training_export.py").read_text(encoding="utf-8")
    export_controller = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "export.py"
    ).read_text(encoding="utf-8")
'''
if text.count(old_concurrency) != 1:
    raise SystemExit(f"concurrency prelude match count: {text.count(old_concurrency)}")
text = text.replace(old_concurrency, new_concurrency, 1)

old_export = '''    export_start = app.index("    def export_training_package(")
    export_end = app.index("\\n    def show_help_dialog", export_start)
    export = app[export_start:export_end]
    assert 'startswith("training-cleanup-")' in export
    assert '%Y%m%d_%H%M%S_%f' in export
    assert "uuid.uuid4().hex" in training
'''
new_export = '''    wrapper_start = app.index("    def export_training_package(")
    wrapper_end = app.index("\\n    def show_help_dialog", wrapper_start)
    wrapper = app[wrapper_start:wrapper_end]
    assert "self._export_controller_for_call().export_training_package()" in wrapper

    export_start = export_controller.index("    def export_training_package(")
    export_end = export_controller.index("\\n    def build_picdic", export_start)
    export = export_controller[export_start:export_end]
    assert 'startswith("training-cleanup-")' in export
    assert '%Y%m%d_%H%M%S_%f' in export
    assert "app._start_ui_worker(" in export
    assert "wait_on_close=True" in export
    assert "uuid.uuid4().hex" in training
'''
if text.count(old_export) != 1:
    raise SystemExit(f"concurrency export block match count: {text.count(old_export)}")
text = text.replace(old_export, new_export, 1)

PATH.write_text(text, encoding="utf-8")

repair_path = ROOT / "tests/test_ui_pdic_order_repair_controller.py"
repair = repair_path.read_text(encoding="utf-8")
old_repair = '''    assert "    def repair_pdic_order_selected_scope(self) -> None:" in controller
    assert 'settings = app.settings' in controller
    assert 'settings = replace(app.settings)' not in controller
    assert 'write_pdic_atomic(' in controller
'''
new_repair = '''    repair_start = controller.index("    def repair_pdic_order_selected_scope(self) -> None:")
    repair_end = controller.index("\\n    def export_picdic_index(self) -> None:", repair_start)
    repair_method = controller[repair_start:repair_end]
    assert 'settings = app.settings' in repair_method
    assert 'settings = replace(app.settings)' not in repair_method
    assert 'write_pdic_atomic(' in repair_method
'''
if repair.count(old_repair) != 1:
    raise SystemExit(f"repair assertion block match count: {repair.count(old_repair)}")
repair = repair.replace(old_repair, new_repair, 1)
repair_path.write_text(repair, encoding="utf-8")

print("Phase 5F stale ownership assertions migrated")
