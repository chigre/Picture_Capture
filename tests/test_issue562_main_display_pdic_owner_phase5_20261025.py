"""Issue #562: physical main display caches and safe PDIC/autosave ownership."""
from __future__ import annotations
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from picture_capture import app
from picture_capture.models import AppSettings
from picture_capture.ui import main_display_cache, main_pdic_persistence, main_canvas_render_workflow


def test_legacy_methods_are_delegates_and_owners_have_real_algorithms():
    cases = {
        main_display_cache: ("_get_cached_display_photo","_current_effective_profile_settings",
            "_display_geometry_key","_get_cached_display_geometry"),
        main_canvas_render_workflow: ("_current_page_crop_plan",),
        main_pdic_persistence: ("_ordered_entries_reading_order","_sort_entries_reading_order",
            "pages_tuple","save_pdic","_sync_entry_editor_texts","toggle_autosave","autosave_tick"),
    }
    for owner, names in cases.items():
        for name in names:
            old = getattr(app.PictureCaptureApp,name)
            actual = getattr(owner,name)
            assert old.__module__ == "picture_capture.app"
            assert "return _" in inspect.getsource(old)
            assert len(inspect.getsource(actual).splitlines()) > 4
    source=inspect.getsource(main_pdic_persistence.save_pdic)
    assert "_recovery_path" in source and "protect_app_pdic_commit" in source
    assert "write_pdic(" in source


def test_display_photo_cache_reuses_same_photo_and_invalidates_on_mode(monkeypatch):
    seen=[]
    monkeypatch.setattr(app.ImageTk,"PhotoImage",lambda img: seen.append(img.copy()) or object())
    monkeypatch.setattr(app,"themed_display_image",lambda img,mode: img)
    stub=SimpleNamespace(image=Image.new("RGB",(16,12),"white"),
        binary_preview_var=SimpleNamespace(get=lambda:False),appearance_mode="light",
        photo=None,_display_photo_cache_key=None)
    try:
        first=app.PictureCaptureApp._get_cached_display_photo(stub,(8,6))
        assert app.PictureCaptureApp._get_cached_display_photo(stub,(8,6)) is first
        assert len(seen)==1
        stub.appearance_mode="dark"
        assert app.PictureCaptureApp._get_cached_display_photo(stub,(8,6)) is not first
        assert len(seen)==2
    finally:
        stub.image.close()
        for img in seen: img.close()


def test_display_geometry_cache_invalidates_on_live_profile_settings(monkeypatch):
    seen=[]
    monkeypatch.setattr(app,"effective_page_settings",
        lambda settings,size,page: seen.append(("profile",page)) or settings)
    monkeypatch.setattr(app,"page_template_analysis_image",
        lambda image,settings,page: seen.append(("analysis",page)) or image)
    monkeypatch.setattr(app,"derive_geometry",
        lambda image,settings: seen.append(("geometry",image.size)) or object())
    s=AppSettings()
    fake=SimpleNamespace(image=Image.new("RGB",(100,80),"white"),
        settings=s,current_index=2,_display_geometry_cache=None,_display_geometry_cache_key=None)
    fake._display_geometry_key=lambda: app.PictureCaptureApp._display_geometry_key(fake)
    fake._current_effective_profile_settings=lambda: app.PictureCaptureApp._current_effective_profile_settings(fake)
    try:
        one=app.PictureCaptureApp._get_cached_display_geometry(fake)
        assert app.PictureCaptureApp._get_cached_display_geometry(fake) is one
        assert len([x for x in seen if x[0]=="geometry"])==1
        s.manual_x+=1
        assert app.PictureCaptureApp._get_cached_display_geometry(fake) is not one
        assert len([x for x in seen if x[0]=="geometry"])==2
        assert seen[0]==("profile",2)
    finally:
        fake.image.close()


def test_crop_plan_uses_live_planner_and_special_page_overrides(monkeypatch):
    observed=[]
    monkeypatch.setattr(app,"build_page_crop_plan",lambda *a,**kw: observed.append((a,kw)) or "plan")
    page=Path("page-01.png")
    fake=SimpleNamespace(image=object(),current_page=page,settings=SimpleNamespace(start_y=12),
        entries=[object()],polygons=[object()],page_sections=[object()],current_index=3,
        _auxiliary_edits=SimpleNamespace(lines=[object()]),
        _load_crop_settings=lambda:{"special_pages":{"page-01":{"top_y":44,"bottom_y":123}},
            "general_top_y":9,"general_bottom_y":11,"polygon_margin":4,
            "entry_left_padding_x":2,"entry_right_padding_x":5},
        _illustration_controller_for_call=lambda:SimpleNamespace(previous_entry_ref=lambda:"prior"))
    assert app.PictureCaptureApp._current_page_crop_plan(fake)=="plan"
    args,kw=observed[0]
    assert args[0] is fake.image and args[1]==fake.entries
    assert kw["top_y"]==44 and kw["bottom_y"]==123
    assert kw["page_stem"]=="page-01" and kw["previous_entry_ref"]=="prior"
    assert kw["profile_page_index"]==3


def test_autosave_error_keeps_edits_and_always_reschedules():
    seen=[]
    fake=SimpleNamespace(autosave_job=42,autosave_var=SimpleNamespace(get=lambda:True),
        _batch_active=False,project=object(),current_page=Path("test.png"),
        _last_pdic_write_changed=False,review_window=None,
        save_pdic=lambda silent=False: (_ for _ in ()).throw(OSError("disk full")),
        status_var=SimpleNamespace(set=lambda value:seen.append(value)),
        toggle_autosave=lambda:seen.append("rescheduled"))
    app.PictureCaptureApp.autosave_tick(fake)
    assert fake.autosave_job is None
    assert "自动保存失败" in seen[0] and "disk full" in seen[0]
    assert seen[-1]=="rescheduled"


def test_pdic_recovery_marker_quarantines_before_writer(monkeypatch,tmp_path):
    from picture_capture.proofreading.transactions import _recovery_path
    page=tmp_path/"synthetic.png"
    _recovery_path(page).write_text("unfinished",encoding="utf-8")
    monkeypatch.setattr(app,"write_pdic",lambda *a,**kw: pytest.fail("unsafe write"))
    fake=SimpleNamespace(project=object(),current_page=page,image=SimpleNamespace(width=100))
    with pytest.raises(RuntimeError,match="Unresolved R3 transaction"):
        app.PictureCaptureApp.save_pdic(fake)
