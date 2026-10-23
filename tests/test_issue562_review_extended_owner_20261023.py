"""Regression contract for the 55 migrated ReviewWindow controls, wordslist and style methods."""
from __future__ import annotations
import ast
import inspect
import unicodedata
from pathlib import Path
from types import SimpleNamespace
import pytest

from picture_capture import app as gui
from picture_capture.ui import (
    review_workspace_workflow as chrome,
    review_reference_workflow as reference,
    review_appearance_workflow as appearance,
)

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"
CHROME = ["_change_review_mode","_set_filter_navigation","_clear_review_workspace","copy_char","_review_membership_colors","_configure_word_list_appearance","_clear_word_list_rows","_render_word_list_rows","_set_word_list_highlight","_word_list_local_index_from_event","_toggle_review_panel","_sync_autosave_label","_toggle_shared_autosave","open_sort_rules","run_order_check","_update_title"]
REFERENCE = ["_effective_wordslist_locator_mode","_change_wordslist_locator_mode","_wordslist_lookup_key","refresh_wordslist_display","_show_wordslist_window","shift_wordslist_window","choose_wordslist_file","_exact_reference_position","_previous_page_reference_target","_current_wordslist_global_target","_sorted_reference_position","_infer_sorted_reference_target","_infer_reference_target","locate_reference_word"]
APPEARANCE = ["_schedule_review_font_apply","_apply_review_font_settings","_schedule_review_simplified_font_apply","_apply_review_simplified_font_settings","_schedule_review_padding_apply","_apply_review_padding_setting","_schedule_review_vertical_padding_apply","_apply_review_vertical_padding_setting","_review_height_pixels_from_percent_var","_review_height_pixels_from_pixel_var","_sync_review_height_vars","_schedule_review_line_height_apply","_apply_review_line_height_setting","_schedule_review_row_padding_apply","_apply_review_row_padding_setting","_schedule_review_regular_crop_height_apply","_apply_review_regular_crop_height_setting","_schedule_review_single_cjk_height_apply","_apply_review_single_cjk_height_setting","_schedule_review_extended_crop_multiplier_apply","_apply_review_extended_crop_multiplier_setting","_apply_review_main_ocr_display_options","change_review_zoom","apply_review_zoom_text","reset_review_zoom"]
STATIC = {"_wordslist_lookup_key", "_review_height_pixels_from_pixel_var"}


@pytest.mark.parametrize(("file", "module", "names", "factory", "dispatch"), [
    ("review_workspace_workflow", chrome, CHROME, "_review_workspace_deps", "_review_workspace"),
    ("review_reference_workflow", reference, REFERENCE, "_review_reference_deps", "_review_reference"),
    ("review_appearance_workflow", appearance, APPEARANCE, "_review_appearance_deps", "_review_appearance"),
])
def test_review_owners_and_unmodified_tk_delegates(file, module, names, factory, dispatch):
    source = (ROOT / "ui" / (file + ".py")).read_text("utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    app_ast = ast.parse((ROOT / "app.py").read_text("utf-8"))
    cls = next(n for n in app_ast.body if isinstance(n, ast.ClassDef) and n.name == "ReviewWindow")
    adapters = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    for name in names:
        assert name in functions
        assert functions[name].end_lineno - functions[name].lineno > 2, name
        adapter = adapters[name]
        calls = [node for node in ast.walk(adapter) if isinstance(node, ast.Call)]
        assert any(isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                   and call.func.value.id == dispatch and call.func.attr == name
                   for call in calls), name
        assert any(isinstance(call.func, ast.Name) and call.func.id == factory
                   for call in calls), name
        assert not any(isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                       and node.value.id == "deps" and node.attr == "app" for node in ast.walk(functions[name]))
        if name in STATIC:
            assert isinstance(inspect.getattr_static(gui.ReviewWindow, name), staticmethod)
    assert not any(isinstance(n, ast.ImportFrom) and n.module in {"app", "processing"}
                   for n in ast.walk(tree))


def test_original_tk_signatures_default_and_static_abi():
    cls = gui.ReviewWindow
    assert list(inspect.signature(cls._set_filter_navigation).parameters) == ["self", "active"]
    assert list(inspect.signature(cls._clear_review_workspace).parameters) == ["self", "message"]
    assert inspect.signature(cls._clear_review_workspace).parameters["message"].default == ""
    assert list(inspect.signature(cls._wordslist_lookup_key).parameters) == ["word"]
    assert list(inspect.signature(cls._review_height_pixels_from_pixel_var).parameters) == ["variable", "minimum", "maximum"]
    assert list(inspect.signature(cls.locate_reference_word).parameters) == ["self", "word", "active_index"]
    assert list(inspect.signature(cls._apply_review_extended_crop_multiplier_setting).parameters) == ["self", "revert_invalid"]


def test_dispatch_captures_current_patchpoints(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(gui, "reference_sort_key", sentinel)
    monkeypatch.setattr(gui, "parse_review_crop_multiplier", sentinel)
    monkeypatch.setattr(gui, "appearance_palette", sentinel)
    assert gui._review_reference_deps().reference_sort_key is sentinel
    assert gui._review_appearance_deps().parse_review_crop_multiplier is sentinel
    assert gui._review_workspace_deps().appearance_palette is sentinel
    assert len(chrome.ReviewWorkspaceDeps.__dataclass_fields__) == 19
    assert len(reference.ReviewReferenceDeps.__dataclass_fields__) == 11
    assert len(appearance.ReviewAppearanceDeps.__dataclass_fields__) == 11


def test_reference_folded_key_and_duplicate_near_position():
    assert reference._wordslist_lookup_key(
        SimpleNamespace(unicodedata=unicodedata), " École! "
    ) == "ecole"
    view = SimpleNamespace(word_exact_indices={"a": [1, 7, 12]})
    assert reference._exact_reference_position(view, SimpleNamespace(), "A", near=9) == 7
    assert reference._exact_reference_position(view, SimpleNamespace(), "B") is None


def test_reference_window_virtualizes_190k_indices():
    captions, seen, selected = [], [], []
    project = SimpleNamespace(root=Path("/tmp/work"), words=["w"] * 190000)
    view = SimpleNamespace(
        parent=SimpleNamespace(project=project, settings=SimpleNamespace(wordslist_path="")),
        word_window_radius=20, word_window_indices=[], word_window_start=0,
        word_highlight_index=None, word_window_var=SimpleNamespace(set=captions.append),
        _render_word_list_rows=lambda words: seen.append(len(words)),
        _set_word_list_highlight=selected.append,
    )
    reference._show_wordslist_window(
        view, SimpleNamespace(resolve_wordslist_path=lambda root, path: Path("/tmp/work/wordslist.txt")), 900,
    )
    assert view.word_window_start == 880
    assert len(view.word_window_indices) == 41
    assert view.word_window_indices[20] == 900 and view.word_highlight_index == 20
    assert seen == [190000] and selected == [20]
    assert "881-921 / 190000" in captions[-1]


def test_focused_navigation_button_labels_remain_original():
    changes = []
    def button(which):
        return SimpleNamespace(configure=lambda **kw: changes.append((which, kw["text"])))
    view = SimpleNamespace(prev_page_button=button("prev"), next_page_button=button("next"))
    chrome._set_filter_navigation(view, SimpleNamespace(tk=SimpleNamespace(TclError=Exception)), True)
    assert changes == [("prev", "上\n一\n批"), ("next", "下\n一\n批")]


def test_appearance_debounce_retains_original_120_ms():
    canceled, pending = [], []
    view = SimpleNamespace(
        _review_font_apply_job="old",
        after_cancel=canceled.append,
        after=lambda delay, callback: pending.append((delay, callback)) or "job",
        _apply_review_font_settings=lambda: None,
    )
    appearance._schedule_review_font_apply(view, SimpleNamespace(tk=SimpleNamespace(TclError=Exception), font=None))
    assert canceled == ["old"]
    assert pending[0][0] == 120 and view._review_font_apply_job == "job"


def test_review_zoom_clamped_with_exact_existing_callback_order():
    calls = []
    view = SimpleNamespace(
        review_zoom=2.0, review_zoom_auto=True, active_index=4,
        review_zoom_var=SimpleNamespace(set=lambda x: calls.append(("display", x))),
        parent=SimpleNamespace(
            settings=SimpleNamespace(review_zoom_percent=0),
            save_settings=lambda: calls.append(("save",)),
        ),
        _commit_edits=lambda: calls.append(("commit",)),
        _stored_review_zoom_percent=lambda: 250.0,
        _request_render_rows=lambda **kwargs: calls.append(("render", kwargs)),
    )
    appearance.change_review_zoom(view, SimpleNamespace(_format_layout_percent=lambda x: str(round(x))), 3.0)
    assert view.review_zoom == 2.5 and view.review_zoom_auto is False
    assert view.parent.settings.review_zoom_percent == 250.0
    assert [v[0] for v in calls] == ["commit", "save", "display", "render"]
    assert calls[-1][1] == {"focus_index": 4}
