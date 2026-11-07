"""Issue #562: real owners for review crop, current OCR and main shutdown."""
from __future__ import annotations
import inspect
from types import SimpleNamespace
from PIL import Image
from picture_capture import app
from picture_capture.ui import review_crop_geometry, main_app_lifecycle, ocr_current_workflow


def test_physical_owners_and_original_public_import_paths():
    for name in ("_review_crop_settings","_review_crop_context","_is_cjk_review_index",
                 "_effective_review_single_cjk_line_height","_effective_review_regular_crop_height",
                 "_review_line_box"):
        original=getattr(app,name)
        assert original.__module__=="picture_capture.app"
        assert "return _review_crop_geometry." in inspect.getsource(original)
        assert len(inspect.getsource(getattr(review_crop_geometry,name)).splitlines())>=4
    for name,owner in (("on_close",main_app_lifecycle),("ocr_current",ocr_current_workflow)):
        original=getattr(app.PictureCaptureApp,name)
        assert original.__module__=="picture_capture.app"
        assert "return _main_" in inspect.getsource(original)
        assert len(inspect.getsource(getattr(owner,name)).splitlines())>35


def test_review_crop_text_height_and_transform_use_live_line_box(monkeypatch):
    calls=[]
    def line_box(entry,geometry,image,settings):
        calls.append(settings.character_height)
        return (3,10,55,20)
    monkeypatch.setattr(app,"line_box",line_box)
    monkeypatch.setattr(app,"replace",lambda obj:SimpleNamespace(**vars(obj)))
    monkeypatch.setattr(app,"_focused_review_is_single_character",lambda text:len(text)==1)
    settings=SimpleNamespace(character_height=10,row_padding=4,review_regular_crop_height=0,
        review_single_cjk_line_height=0,entry_regular_crop_height=0,entry_oversized_crop_height=0,
        ocr_language="chi_sim",dictionary_profile_id="",layout_transform="identity")
    entry=SimpleNamespace(word="中",y=40)
    geometry=SimpleNamespace(top=0,transform=SimpleNamespace(kind="identity"))
    image=SimpleNamespace(height=200)
    assert app._effective_review_single_cjk_line_height(settings)==25
    assert app._review_line_box(entry,geometry,image,settings)==(3,38,55,63)
    assert app._review_line_box(entry,geometry,image,settings,editor_text="中国")== (3,38,55,52)
    geometry.transform.kind="mirror_x"
    assert app._review_line_box(entry,geometry,image,settings)==(3,10,55,20)
    assert calls==[10,10,25] and settings.character_height==10


def test_review_crop_context_uses_current_page_profile(monkeypatch):
    settings=SimpleNamespace(value=1)
    img=SimpleNamespace(size=(40,60))
    effective=SimpleNamespace(value=2)
    seen=[]
    monkeypatch.setattr(app,"effective_page_settings",lambda s,sz,i:(seen.append(("effective",sz,i)) or effective))
    monkeypatch.setattr(app,"page_template_analysis_image",lambda image,s,i:(seen.append(("analysis",i)) or "analysis"))
    monkeypatch.setattr(app,"derive_geometry",lambda image,s:(seen.append(("geometry",image)) or "geom"))
    monkeypatch.setattr(app,"_review_crop_settings",lambda image,s,w:s)
    assert app._review_crop_context(img,settings,100,4)==(effective,"geom")
    assert seen==[("effective",(40,60),4),("analysis",4),("geometry","analysis")]


def test_current_page_ocr_uses_live_writers_and_ui_done(monkeypatch,tmp_path):
    page=tmp_path/"page.png"
    Image.new("RGB",(20,30),"white").save(page)
    project=SimpleNamespace(root=tmp_path)
    entry=SimpleNamespace(word="old",x=3,y=4)
    events=[]
    monkeypatch.setattr(app,"replace",lambda obj:SimpleNamespace(**vars(obj)))
    monkeypatch.setattr(app,"replace_rules_path",lambda r:tmp_path/"rules.txt")
    monkeypatch.setattr(app,"qt_root",lambda r:tmp_path)
    monkeypatch.setattr(app,"load_replace_rules",lambda p:events.append(("rules",p.name)) or [])
    monkeypatch.setattr(app,"ocr_entries",lambda image,entries,s,rules,**kw:
        events.append(("ocr",image.size,kw["profile_page_index"])) or ["new"])
    monkeypatch.setattr(app,"export_ocred",lambda p,texts:events.append(("ocred",p.name,list(texts))))
    monkeypatch.setattr(app,"write_pdic",lambda p,entries,width,pages:
        events.append(("pdic",p.name,width,entries[0].word)))
    monkeypatch.setattr(app,"pdic_path",lambda p:tmp_path/(p.stem+".pdic"))
    def start(label,indices,worker,done,**kwargs):
        assert label=="当前页 OCR" and indices==[2]
        result=worker(indices[0],0,1)
        assert entry.word=="old"
        done(1,1,False,[result],None)
    instance=SimpleNamespace(_batch_active=False,guard=lambda:True,
        _guard_transformed_geometry=lambda label:True,project=project,current_page=page,
        current_index=2,settings=SimpleNamespace(ocr_engine="tesseract"),
        entries=[entry],page_sections=[],pages_tuple=lambda i:(i,),
        _ordered_entries_reading_order=lambda:[entry],_start_batch_task=start,
        redraw=lambda:events.append(("redraw",)),
        status_var=SimpleNamespace(set=lambda s:events.append(("status",s))))
    app.PictureCaptureApp.ocr_current(instance)
    assert entry.word=="new"
    assert ("ocr",(20,30),2) in events
    assert ("pdic","page.pdic",20,"new") in events
    assert ("ocred","page.OCRed",["new"]) in events
    assert ("redraw",) in events


def test_on_close_waits_for_batch_and_durable_file_worker(monkeypatch):
    prompts=[]
    monkeypatch.setattr(app.messagebox,"askyesno",lambda *a,**k:prompts.append("ask") or True)
    stopped=[]
    batch=SimpleNamespace(_batch_active=True,_batch_close_after_stop=False,
        _request_batch_stop=lambda:stopped.append("stop"))
    app.PictureCaptureApp.on_close(batch)
    assert prompts==["ask"] and stopped==["stop"] and batch._batch_close_after_stop
    events=[]
    pending=SimpleNamespace(_batch_active=False,_ui_worker_close_wait={("file",1)},
        _ui_close_requested=False,_ui_worker_generations={"file":1},
        _invalidate_ui_worker=lambda key:events.append(("invalidate",key)),
        status_var=SimpleNamespace(set=lambda s:events.append(("status",s))),
        withdraw=lambda:events.append(("withdraw",)),_ui_worker_poll_job=None,
        after=lambda delay,callback:events.append(("poll",delay)) or "job",
        _poll_ui_worker_queue=lambda:None)
    app.PictureCaptureApp.on_close(pending)
    assert pending._ui_close_requested and pending._ui_worker_poll_job=="job"
    assert ("withdraw",) in events and ("invalidate","file") in events
