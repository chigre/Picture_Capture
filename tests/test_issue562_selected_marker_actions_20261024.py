"""Native selected-marker GUI owners, Y spawn boundary and OCR-only guard."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import threading
from picture_capture import app as shell
from picture_capture.ui import selected_marker_actions as owner
from picture_capture.refinement import parallel


ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"


def test_native_method_delegates_and_original_bindings(monkeypatch):
    tree=ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="PictureCaptureApp")
    methods={n.name:n for n in klass.body if isinstance(n,ast.FunctionDef)}
    source=ast.parse((ROOT/"ui/selected_marker_actions.py").read_text(encoding="utf-8"))
    owned={n.name for n in source.body if isinstance(n,ast.FunctionDef)}
    for name in ("refine_lines_selected_scope","ocr_ordinary_lines_text_selected_scope"):
        assert name in owned and name in methods
        calls=[c for c in ast.walk(methods[name]) if isinstance(c,ast.Call)]
        assert any(isinstance(c.func,ast.Attribute) and c.func.attr==name and
                   isinstance(c.func.value,ast.Name) and c.func.value.id=="_selected_marker_actions"
                   for c in calls)
    sentinel=object()
    monkeypatch.setattr(shell,"read_pdic",sentinel)
    assert shell._selected_marker_actions_deps().read_pdic is sentinel


def test_removed_legacy_refinement_import_replaced_by_canonical_worker():
    text=(ROOT/"ui/selected_marker_actions.py").read_text(encoding="utf-8")
    assert "from ..refinement.parallel import (" in text
    assert "from .marker_refinement_parallel import" not in text
    assert not (ROOT/"marker_refinement_parallel.py").exists()
    assert callable(parallel.configured_refine_workers)
    assert callable(parallel.commit_refined_page_result)


def test_refine_started_from_existing_page_keeps_parent_commit_guard(monkeypatch):
    calls=[]
    class Status:
        def set(self,msg):calls.append(("status",msg))
    class App:
        project=SimpleNamespace(images=[Path("0001.png")])
        settings=SimpleNamespace(paddle_refine_separator_y=False)
        current_index=0
        _batch_active=False
        _batch_state_lock=threading.Lock()
        _batch_page_states={0:"processing"}
        status_var=Status()
        def guard(self):return True
        def apply_quick_settings(self,**kw):return True
        def selected_page_indices(self):return [0]
        def _flush_deferred_page_save(self):calls.append(("flush",))
        def _sync_entry_editor_texts(self):calls.append(("sync",))
        def save_pdic(self,**kw):calls.append(("save",kw))
        def _start_parallel_batch_task(self,title,items,worker,job_builder,consumer,done,**kw):
            assert worker is parallel.refine_page_job
            assert kw["isolate_worker"] and kw["respect_cpu_workers"]
            assert kw["foreground_page_edit"] and kw["allow_pdic_edits"]
            assert job_builder(0,0,1)[2] == 0
            assert consumer(0,{"marker":"x"})["saved"] == 1
            calls.append(("batch",title))
    monkeypatch.setattr(parallel,"configured_refine_workers",lambda *a,**kw:1)
    monkeypatch.setattr(parallel,"commit_refined_page_result",lambda index,payload,check:{"saved":int(check(index))})
    owner.refine_lines_selected_scope(
        App(),
        SimpleNamespace(replace=lambda obj:SimpleNamespace(**vars(obj)),
                        messagebox=SimpleNamespace(askyesno=lambda *a,**kw:True)),
    )
    assert [x[0] for x in calls[:3]]==["flush","sync","save"]
    assert calls[-1]==("batch","精修画线")


def test_ocr_guard_is_evaluated_before_current_editor_mutations():
    reached=[]
    fake=SimpleNamespace(guard=lambda:reached.append("edit"))
    owner.ocr_ordinary_lines_text_selected_scope(
        fake,SimpleNamespace(guard_ocr_action_selection=lambda _:False)
    )
    assert reached==[]
