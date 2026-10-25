"""#562: physical main dialog and page-save ownership, without Tk mainloop."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
import pytest
from picture_capture import app
from picture_capture.ui import main_dialog_lifecycle, main_pdic_persistence


def test_main_ui_owners_are_real_and_public_methods_remain_stable():
    owners = {
        main_dialog_lifecycle: ("show_help_dialog", "show_environment_center",
            "open_settings", "open_project_profile", "open_review"),
        main_pdic_persistence: ("_save_current_page_files",
            "_save_current_page_by_mode", "save_current_page",
            "_persist_current_page_sections"),
    }
    for owner, names in owners.items():
        for name in names:
            assert getattr(app.PictureCaptureApp, name).__module__ == "picture_capture.app"
            assert "return _" in inspect.getsource(getattr(app.PictureCaptureApp, name))
            assert len(inspect.getsource(getattr(owner, name)).splitlines()) >= 7
    assert "self._sync_entry_editor_texts()" in inspect.getsource(main_dialog_lifecycle.open_review)
    assert "self._save_normalized_ppp()" in inspect.getsource(main_pdic_persistence._save_current_page_files)


def test_open_settings_uses_live_monkeypatched_dialog_and_reuses_window(monkeypatch):
    made=[]
    class FakeDialog:
        def __init__(self, parent, initial_tab=None):
            self.parent=parent
            self.initial_tab=initial_tab
            made.append(self)
        def bind(self, *args, **kwargs): pass
        def winfo_exists(self): return True
        def select_tab(self, tab): self.initial_tab=tab
        def deiconify(self): pass
        def lift(self): pass
    monkeypatch.setattr(app, "SettingsDialog", FakeDialog)
    stub=SimpleNamespace(__dict__=None) if False else SimpleNamespace()
    stub.apply_quick_settings=lambda **kwargs: True
    app.PictureCaptureApp.open_settings(stub, "ocr")
    assert len(made)==1 and made[0].initial_tab=="ocr"
    app.PictureCaptureApp.open_settings(stub, "project")
    assert len(made)==1 and made[0].initial_tab=="project"
    assert stub._settings_dialog is made[0]


def test_page_navigation_commits_pdic_and_ppp_with_live_path(monkeypatch):
    page=Path("/tmp/sample.png")
    calls=[]
    monkeypatch.setattr(app,"pdic_path",lambda p: calls.append(("path",p)) or Path("/tmp/sample.pdic"))
    stub=SimpleNamespace(project=object(),current_page=page,image=object(),current_index=3,
        save_pdic=lambda **kw: calls.append(("pdic",kw)),
        _ppp_write_path=lambda p: Path("/tmp/sample.ppp"),
        _save_normalized_ppp=lambda: calls.append(("ppp",)),
        _update_page_row=lambda i: calls.append(("row",i)))
    result=app.PictureCaptureApp._save_current_page_files(stub,sync_editors=False)
    assert result==(Path("/tmp/sample.pdic"),Path("/tmp/sample.ppp"))
    assert calls==[("pdic",{"silent":True,"sync_editors":False}),
                   ("ppp",),("row",3),("path",page)]


def test_page_save_rejects_background_nonowned_page():
    status=[]
    stub=SimpleNamespace(project=object(),current_page=Path("/tmp/a.png"),
        image=object(),_batch_active=True,
        _can_save_current_during_batch_navigation=lambda:False,
        status_var=SimpleNamespace(set=status.append))
    assert app.PictureCaptureApp._save_current_page_by_mode(stub) is None
    assert status and "只读" in status[0]


def test_open_review_reuses_live_window_without_overwriting_editor():
    actions=[]
    existing=SimpleNamespace(winfo_exists=lambda:True,
        lift=lambda:actions.append("lift"),focus_force=lambda:actions.append("focus"))
    stub=SimpleNamespace(guard=lambda:True,entries=[object()],review_window=existing,
        _sync_entry_editor_texts=lambda:actions.append("sync"))
    app.PictureCaptureApp.open_review(stub)
    assert actions==["lift","focus"]


def test_section_persistence_writes_only_sections(monkeypatch):
    calls=[]
    class Transform:
        def __init__(self, kind):self.kind=kind
        def canonical_size(self,size):return size
    monkeypatch.setattr(app,"LayoutTransform",Transform)
    monkeypatch.setattr(app,"write_page_sections",lambda *a,**kw:calls.append((a,kw)))
    stub=SimpleNamespace(current_page=Path("/tmp/one.png"),image=SimpleNamespace(size=(400,600)),
        settings=SimpleNamespace(layout_transform="identity"),page_sections=[object()])
    app.PictureCaptureApp._persist_current_page_sections(stub)
    assert len(calls)==1
    assert calls[0][1]["canonical_width"]==400
    assert calls[0][1]["canonical_height"]==600
    assert calls[0][1]["layout_transform"]=="identity"
