"""Native owner and behavior regression tests for main canvas entry actions."""
from __future__ import annotations
import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from picture_capture import app as shell
from picture_capture.models import Entry
from picture_capture.ui import main_entry_actions as owned

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"
NAMES = ["_remove_entry_overlay","_entry_sequence_text","_refresh_entry_index_labels","_update_entry_overlays_local","_confidence_bg","_style_entry_editor","_entry_overlay_style","_candidate_for_entry","_short_ocr_menu_word","_fill_main_entry_from_ocr","_create_main_ocr_menu","update_entry","focus_next","focus_previous","_delete_aligned_simplified_entry","delete_entry"]

def test_physical_ownership_abi_live_dependencies_and_static_descriptors(monkeypatch):
    root=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))
    klass=next(n for n in root.body if isinstance(n,ast.ClassDef) and n.name=="PictureCaptureApp")
    wrappers={n.name:n for n in klass.body if isinstance(n,ast.FunctionDef)}
    leaf=ast.parse((ROOT/"ui/main_entry_actions.py").read_text(encoding="utf-8"))
    functions={n.name for n in leaf.body if isinstance(n,ast.FunctionDef)}
    assert set(NAMES)<=functions
    for name in NAMES:
        assert name in wrappers
        calls=[n for n in ast.walk(wrappers[name]) if isinstance(n,ast.Call)]
        assert any(isinstance(n.func,ast.Attribute) and n.func.attr==name
                   and isinstance(n.func.value,ast.Name) and n.func.value.id=="_main_entry_actions"
                   for n in calls)
        assert any(isinstance(n.func,ast.Name) and n.func.id=="_main_entry_actions_deps"
                   for n in calls)
        assert list(inspect.signature(getattr(shell.PictureCaptureApp,name)).parameters)
    for name in ("_entry_sequence_text","_short_ocr_menu_word"):
        assert isinstance(shell.PictureCaptureApp.__dict__[name],staticmethod)
    marker=object()
    monkeypatch.setattr(shell,"resolve_wordslist_path",marker)
    monkeypatch.setattr(shell,"_candidate_choice_rows",marker)
    deps=shell._main_entry_actions_deps()
    assert deps.resolve_wordslist_path is marker
    assert deps._candidate_choice_rows is marker
    assert not any(isinstance(n,ast.ImportFrom) and n.module in {"app","picture_capture.app"}
                   for n in ast.walk(leaf))

def test_entry_number_and_confidence_fixed_semantics():
    cls=shell.PictureCaptureApp
    assert cls._entry_sequence_text(0,100)=="000"
    assert cls._entry_sequence_text(99,100)=="099"
    assert cls._short_ocr_menu_word("a"*15,12)=="a"*11+"…"
    assert cls._confidence_bg(None)=="#eeeeee"
    assert cls._confidence_bg(.95)=="#c8e6c9"
    assert cls._confidence_bg(.64)=="#ffcdd2"

def test_main_ocr_menu_duplicate_alternatives_skip_tk_creation():
    fake=SimpleNamespace(canvas=object())
    deps=SimpleNamespace(_candidate_choice_rows=lambda _:[],
                         _has_distinct_ocr_alternatives=lambda _:False,
                         tk=SimpleNamespace(Menubutton=lambda *a,**kw:None))
    assert owned._create_main_ocr_menu(fake,deps,Entry("甲",1,1),None,{"word":"甲"}) is None

def test_guarded_edit_restores_original_text_and_disables_processing_editor():
    entry=Entry("original",3,4)
    calls=[]
    class Widget:
        text="changed"
        def get(self):return self.text
        def configure(self,**kw):calls.append(kw)
        def delete(self,*args):self.text=""
        def insert(self,*args):self.text=args[-1]
    widget=Widget()
    fake=SimpleNamespace(_claim_page_for_manual_edit=lambda:False,
                         _foreground_batch_state=lambda index:"processing",current_index=0)
    deps=SimpleNamespace(tk=SimpleNamespace(TclError=RuntimeError))
    owned.update_entry(fake,deps,entry,widget)
    assert entry.word=="original" and widget.text=="original"
    assert {"state":"disabled"} in calls

def test_local_remove_skips_geometry_and_redraw():
    entry=Entry("test",1,2)
    called=[]
    fake=SimpleNamespace(image=object(),cursor_canvas_xy=None,
                         _remove_entry_overlay=lambda x:called.append("remove"),
                         _refresh_entry_index_labels=lambda:called.append("numbers"),
                         _set_idle_cursor_status=lambda:called.append("status"),
                         _get_cached_display_geometry=lambda:(_ for _ in ()).throw(AssertionError("geometry")))
    owned._update_entry_overlays_local(fake,SimpleNamespace(parameter_scale=None),removed=[entry])
    assert called==["remove","numbers","status"]
