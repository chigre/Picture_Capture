"""Round 28: large app UI implementations and original public method delegates."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import app as gui
from picture_capture.ui import (
    main_appearance_policy, quick_settings_apply, detection_batch_execution,
)


def test_exact_ui_algorithm_owners_and_retained_app_method_signatures():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 5
    mapping = {
        "main_appearance_policy.py": {
            "configure_global_appearance", "configure_main_workspace_styles",
            "_app_icon_toplevel_mapped", "_maximize_main_window",
            "_apply_current_appearance", "_appearance_toplevel_mapped",
            "_appearance_mode_selected", "_cancel_system_appearance_poll",
            "_schedule_system_appearance_poll", "_poll_system_appearance",
            "set_appearance_mode",
        },
        "quick_settings_apply.py": {
            "apply_quick_settings", "_quick_percent_parameter_changed",
            "_quick_pixel_parameter_changed", "_quick_parameter_changed",
            "_quick_geometry_value",
            "_style_color_button", "choose_overlay_color",
            "_apply_overlay_visibility_toggle", "_run_quick_autosave",
            "_refresh_quick_coordinate_labels",
        },
        "detection_batch_execution.py": {"detect_pages"},
    }
    for file, names in mapping.items():
        path = root / "ui" / file
        assert path.is_file()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} == names
        assert not any(isinstance(n, (ast.ClassDef, ast.Assign, ast.AnnAssign)) for n in tree.body)
    klass = gui.PictureCaptureApp
    for name in (
        "_configure_global_appearance", "_configure_main_workspace_styles",
        "apply_quick_settings", "_detect_pages",
    ):
        assert getattr(klass, name).__module__ == "picture_capture.app"
    assert list(inspect.signature(klass._configure_global_appearance).parameters) == ["self"]
    assert list(inspect.signature(klass._configure_main_workspace_styles).parameters) == ["self"]
    assert list(inspect.signature(klass.apply_quick_settings).parameters) == [
        "self", "show_status", "persist", "silent_errors",
    ]
    assert list(inspect.signature(klass._detect_pages).parameters) == [
        "self", "indices", "method", "force_refresh",
    ]


def test_original_tk_method_adapters_pass_current_module_patches(monkeypatch):
    observed = []
    for owner, target in (
        (main_appearance_policy, "configure_global_appearance"),
        (main_appearance_policy, "configure_main_workspace_styles"),
        (quick_settings_apply, "apply_quick_settings"),
        (detection_batch_execution, "detect_pages"),
    ):
        def make_spy(name):
            def spy(self, *args, deps, **kwargs):
                observed.append((name, self, args, kwargs, deps))
                return name
            return spy
        monkeypatch.setattr(owner, target, make_spy(target))
    dummy = object()
    assert gui.PictureCaptureApp._configure_global_appearance(dummy) == "configure_global_appearance"
    assert gui.PictureCaptureApp._configure_main_workspace_styles(dummy) == "configure_main_workspace_styles"
    assert gui.PictureCaptureApp.apply_quick_settings(dummy, show_status=False, persist=True) == "apply_quick_settings"
    assert gui.PictureCaptureApp._detect_pages(dummy, [1, 3], method="combined", force_refresh=True) == "detect_pages"

    assert [item[0] for item in observed] == [
        "configure_global_appearance", "configure_main_workspace_styles",
        "apply_quick_settings", "detect_pages",
    ]
    assert all(item[1] is dummy for item in observed)
    appearance = observed[0][-1]
    workspace = observed[1][-1]
    quick = observed[2][-1]
    detection = observed[3][-1]
    assert appearance["tk"] is gui.tk and appearance["ttk"] is gui.ttk
    assert workspace["appearance_palette"] is gui.appearance_palette
    assert quick["_layout_percent_to_pixels"] is gui._layout_percent_to_pixels
    assert quick["LAYOUT_PERCENT_AXES"] is gui.LAYOUT_PERCENT_AXES
    assert detection["detect_entries_job"] is gui.detect_entries_job
    assert detection["write_pdic"] is gui.write_pdic
    assert detection["statistics"] is gui.statistics
    assert observed[3][3] == {"method": "combined", "force_refresh": True}


def test_real_moved_detection_batch_empty_request_is_safe_without_gui(monkeypatch):
    result = []
    fake = SimpleNamespace(
        project=None,
        status_var=SimpleNamespace(set=result.append),
    )
    assert gui.PictureCaptureApp._detect_pages(
        fake, [2], method="left_edge", force_refresh=False,
    ) is None
    assert result == ["没有需要处理的页面"]


def test_batch_guards_source_order_and_relative_subpackage_imports():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app_source = (root / "app.py").read_text(encoding="utf-8")
    owner = (root / "ui" / "detection_batch_execution.py").read_text(encoding="utf-8")
    assert "_detection_batch_execution.detect_pages(" in app_source
    assert 'indices = list(dict.fromkeys(indices))' in owner
    assert 'if method == "left_edge" and ordinary_workers <= 1 else None' in owner
    assert "self.save_pdic(silent=True)" in owner
    assert owner.index("preserve_prior_pdic(project.root") < owner.index("write_pdic(saved_pdic")
    assert owner.index("write_pdic(saved_pdic") < owner.index("record_final_decisions(")
    assert "and not force_refresh" in owner
    assert "only_blank=True" in owner
    assert "from ..ocr.page_resume import validated_resume" in owner
    assert "from ..ordinary.gpu_pipeline import (" in owner
    assert "from ..persistence.project_storage import page_sections_read_path_for_image" in owner
