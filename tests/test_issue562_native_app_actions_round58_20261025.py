"""Round 58: move the remaining main-shell save, clear, sorting and error actions.

These characterization tests call the original PictureCaptureApp methods without
creating a Tk root; no GUI display or external OCR executable is needed.
"""
from __future__ import annotations

import ast
import inspect
import pickle
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import app as shell
from picture_capture.ui import main_app_lifecycle as lifecycle
from picture_capture.ui import main_pdic_persistence as persistence


ROOT = Path(__file__).resolve().parents[1]


class _Status:
    def __init__(self, events):
        self.events = events

    def set(self, value):
        self.events.append(("status", value))


def _fake_main(*, guard=True):
    events = []
    fake = SimpleNamespace(
        guard=lambda: events.append(("guard",)) or guard,
        entries=[object(), object()],
        redraw=lambda: events.append(("redraw",)),
        save_pdic=lambda: events.append(("pdic",)),
        _save_normalized_ppp=lambda: events.append(("ppp",)),
        status_var=_Status(events),
    )
    return fake, events


def test_shell_callables_remain_original_class_methods_and_owner_has_no_gui_import():
    shell_file = ROOT / "src/picture_capture/app.py"
    source = shell_file.read_text(encoding="utf-8")
    for name in ("clear_entries", "save_all", "save_settings",
                 "_order_key", "_order_display_key", "show_error"):
        func = shell.PictureCaptureApp.__dict__[name]
        assert inspect.isfunction(func)
        assert Path(func.__code__.co_filename).resolve() == shell_file.resolve()
        assert pickle.loads(pickle.dumps(func)) is func
        assert f"    def {name}(" in source
    for name, owner in (
        ("save_all", persistence), ("save_settings", persistence),
        ("order_key", persistence), ("order_display_key", persistence),
        ("clear_entries", lifecycle), ("show_error", lifecycle),
    ):
        assert inspect.isfunction(getattr(owner, name))
        owner_file = Path(owner.__file__)
        code = owner_file.read_text(encoding="utf-8")
        assert "from ..app import" not in code
        assert "from picture_capture.app import" not in code
    assert "self.entries.clear(); self.redraw()" not in source
    assert "self.settings.to_json(settings_path(self.project.root))" not in source


def test_clear_entries_denied_guard_does_not_prompt_or_mutate(monkeypatch):
    fake, events = _fake_main(guard=False)
    original = fake.entries
    monkeypatch.setattr(
        shell.messagebox, "askyesno",
        lambda *_args, **_kwargs: pytest.fail("guard must precede dialog"),
    )
    shell.PictureCaptureApp.clear_entries(fake)
    assert fake.entries is original and len(original) == 2
    assert events == [("guard",)]


def test_clear_entries_rejected_dialog_keeps_original_marker_identities(monkeypatch):
    fake, events = _fake_main()
    original = fake.entries
    monkeypatch.setattr(
        shell.messagebox, "askyesno",
        lambda title, text, *, parent: events.append(("dialog", title, text, parent)) or False,
    )
    shell.PictureCaptureApp.clear_entries(fake)
    assert fake.entries is original and len(original) == 2
    assert events[0] == ("guard",)
    assert events[1] == ("dialog", "清除画线", "清除当前页全部词条标记？", fake)


def test_clear_entries_confirmed_does_not_replace_list_and_redraws_once(monkeypatch):
    fake, events = _fake_main()
    original = fake.entries
    monkeypatch.setattr(
        shell.messagebox, "askyesno",
        lambda _a, _b, *, parent: events.append(("confirmed", parent)) or True,
    )
    shell.PictureCaptureApp.clear_entries(fake)
    assert fake.entries is original and not original
    assert events == [("guard",), ("confirmed", fake), ("redraw",)]


def test_save_all_is_guarded_and_never_swallows_or_reorders_failure():
    denied, events = _fake_main(guard=False)
    shell.PictureCaptureApp.save_all(denied)
    assert events == [("guard",)]

    allowed, events = _fake_main()
    shell.PictureCaptureApp.save_all(allowed)
    assert events == [("guard",), ("pdic",), ("ppp",)]

    failing, events = _fake_main()
    def failed_save():
        events.append(("pdic",))
        raise OSError("pdic write failure")
    failing.save_pdic = failed_save
    with pytest.raises(OSError, match="pdic write failure"):
        shell.PictureCaptureApp.save_all(failing)
    assert events == [("guard",), ("pdic",)]


def test_save_settings_project_only_and_live_path_binding(monkeypatch, tmp_path):
    fake, events = _fake_main()
    written = []
    fake.project = None
    fake.settings = SimpleNamespace(to_json=lambda path: written.append(path))
    monkeypatch.setattr(
        shell, "settings_path",
        lambda root: tmp_path / (str(root) + ".json"),
    )
    shell.PictureCaptureApp.save_settings(fake)
    assert written == [] and events == []

    fake.project = SimpleNamespace(root="dictionary")
    shell.PictureCaptureApp.save_settings(fake)
    assert written == [tmp_path / "dictionary.json"]
    assert events == [("status", "参数已保存")]


def test_sort_adapters_preserve_live_legacy_binding_and_default_policy(monkeypatch):
    collected = []
    def key(*args):
        collected.append(("sort", args))
        return (42,)
    def label(*args):
        collected.append(("label", args))
        return "shown"
    monkeypatch.setattr(shell, "collation_key", key)
    monkeypatch.setattr(shell, "display_key", label)
    monkeypatch.setattr(shell, "LATIN_ORDER", "#legacy-order")
    fake = SimpleNamespace(settings=SimpleNamespace())
    assert shell.PictureCaptureApp._order_key(fake, "Abc") == (42,)
    assert shell.PictureCaptureApp._order_display_key(fake, "Abc") == "shown"
    assert collected == [
        ("sort", ("Abc", "auto", "eng", "#legacy-order", True)),
        ("label", ("Abc", "auto", "eng", "#legacy-order", True)),
    ]
    fake.settings.headword_sort_mode = "custom"
    fake.settings.ocr_language = "chi_sim"
    fake.settings.headword_custom_order = "ZYX"
    fake.settings.headword_custom_fold_accents = False
    shell.PictureCaptureApp._order_key(fake, "z")
    assert collected[-1] == ("sort", ("z", "custom", "chi_sim", "ZYX", False))
    assert list(inspect.signature(shell.PictureCaptureApp._order_key).parameters) == ["self", "word"]


def test_show_error_preserves_status_modal_traceback_order(monkeypatch):
    fake, events = _fake_main()
    failure = RuntimeError("broken")
    monkeypatch.setattr(
        shell.messagebox, "showerror",
        lambda title, detail, *, parent: events.append(("error", title, detail, parent)),
    )
    monkeypatch.setattr(
        shell, "traceback",
        SimpleNamespace(print_exc=lambda: events.append(("traceback",))),
    )
    shell.PictureCaptureApp.show_error(fake, "检查失败", failure)
    assert events == [
        ("status", "检查失败：broken"),
        ("error", "检查失败", "broken\n\n详细信息已输出到终端。", fake),
        ("traceback",),
    ]
    assert list(inspect.signature(shell.PictureCaptureApp.show_error).parameters) == [
        "self", "title", "exc",
    ]
