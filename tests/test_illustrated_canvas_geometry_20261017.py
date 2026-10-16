"""Pure Illustrator-like illustrated geometry and native-pixel guide persistence."""
from dataclasses import replace
from pathlib import Path
import pytest
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.illustrated_entries import make_entry,read_entries,write_entries
from picture_capture.illustrated_geometry import (
    snap_position,transform_selection,group_objects,ungroup_objects,
    merge_text_groups,split_text_group,duplicate,
)
from picture_capture.illustrated_guides import (
    guide_path,guide_ticket,read_guides,write_guides,
)
from picture_capture.illustrated_profile import (
    validate_illustrated_preferences,profile_payload,apply_profile_payload,
)


def boxes():
    a=replace(make_entry(15,20,40,24,lines=("hair","cheveux")),primary="hair")
    b=replace(make_entry(115,65,60,28,lines=("nose","nez")),primary="nose")
    c=replace(make_entry(239,125,45,27,lines=("ear","oreille")),primary="ear")
    return [a,b,c]


def test_screenspace_snap_scale_and_priority():
    b=boxes()
    assert snap_position(36,67,(36,67,40,30),grid=(40,40),
                         scale=1,tolerance=6,snap_objects=False) == (40,65)
    assert snap_position(36,67,(36,67,40,30),grid=(40,40),
                         scale=2,tolerance=6,snap_objects=False) == (36,65)
    assert snap_position(36,67,(36,67,40,30),grid=(40,40),
                         vertical_guides=[34],horizontal_guides=[67],
                         scale=1,tolerance=6) == (34,67)
    assert snap_position(37,67,(37,67,40,30),grid=(40,40),
                         scale=1,tolerance=6,snap_grid=False,
                         snap_objects=False,snap_guides=False) == (37,67)


def test_align_equal_size_and_distribute_keep_text_and_ids():
    original=boxes();ids={a.id for a in original};page=(400,300)
    updated=transform_selection(original,ids,"left",page)
    assert {v.x for v in updated} == {15}
    assert [v.lines for v in updated] == [v.lines for v in original]
    assert [v.id for v in updated] == [v.id for v in original]
    updated=transform_selection(original,ids,"equal_width",page,key_id=original[1].id)
    assert [v.w for v in updated] == [60,60,60]
    updated=transform_selection(original,ids,"distribute_x",page)
    gaps=[updated[i+1].x-(updated[i].x+updated[i].w) for i in range(2)]
    assert abs(gaps[0]-gaps[1])<=1
    updated=transform_selection(original,ids,"distribute_y",page)
    gaps=[updated[i+1].y-(updated[i].y+updated[i].h) for i in range(2)]
    assert abs(gaps[0]-gaps[1])<=1
    assert original[1].x == 115


def test_locked_items_and_grouping_are_safe():
    items=boxes()
    items[2]=replace(items[2],locked=True)
    ids={v.id for v in items}
    result=transform_selection(items,ids,"left",(400,300))
    assert result[2]==items[2]
    result=group_objects(items,ids,group_id="layoutgroup")
    assert [v.group_id for v in result] == ["layoutgroup","layoutgroup",""]
    ungrouped=ungroup_objects(result,{result[0].id})
    assert all(v.group_id=="" for v in ungrouped)
    duplicated,added=duplicate(items,{items[0].id},(400,300))
    assert len(duplicated)==4 and len(added)==1
    assert duplicated[-1].id != items[0].id
    assert duplicated[-1].lines==items[0].lines


def test_semantic_merge_is_different_from_layout_group():
    items=boxes()
    grouped=group_objects(items,{items[0].id,items[1].id})
    assert len(grouped)==3 and [e.lines for e in grouped]==[e.lines for e in items]
    merged=merge_text_groups(items,{items[0].id,items[1].id})
    assert len(merged)==2
    assert {s for e in merged for s in e.lines}=={"hair","cheveux","nose","nez","ear","oreille"}
    head=next(e for e in merged if "hair" in e.lines)
    assert head.id==items[0].id
    pieces=split_text_group(merged,head.id,2)
    assert len(pieces)==3
    assert {tuple(e.lines) for e in pieces}=={("hair","cheveux"),("nose","nez"),("ear","oreille")}
    assert len({e.id for e in pieces})==3


def test_guides_atomic_per_page_and_collision_protection(tmp_path):
    page=tmp_path/"0001.png"
    Image.new("RGB",(400,300)).save(page)
    q=tmp_path/"0002.png"
    Image.new("RGB",(400,300)).save(q)
    assert read_guides(tmp_path,page)=={"vertical":[],"horizontal":[]}
    stamp=write_guides(tmp_path,page,{"vertical":[80,180],"horizontal":[45]},
                       expected_ticket=None,size=(400,300))
    assert stamp==guide_ticket(tmp_path,page)
    assert read_guides(tmp_path,page)["vertical"]==[80,180]
    assert read_guides(tmp_path,q)["vertical"]==[]
    with pytest.raises(RuntimeError,match="外部"):
        write_guides(tmp_path,page,{"vertical":[],"horizontal":[]},
                     expected_ticket=None,size=(400,300))
    guide_path(tmp_path,page).write_text("not JSON",encoding="utf-8")
    with pytest.raises(ValueError,match="文件损坏"):
        read_guides(tmp_path,page)


def test_old_page_json_opens_with_new_layout_object_fields(tmp_path):
    page=tmp_path/"p001.png"
    Image.new("RGB",(300,400)).save(page)
    entry=make_entry(25,35,90,30,lines=("eye","œil"))
    stamp=write_entries(tmp_path,page,[entry],expected_ticket=None,image_size=(300,400))
    loaded=read_entries(tmp_path,page)
    assert loaded==[entry]
    enriched=replace(entry,group_id="box_1",locked=True,hidden=True)
    write_entries(tmp_path,page,[enriched],expected_ticket=stamp,image_size=(300,400))
    assert read_entries(tmp_path,page)==[enriched]


def test_grid_profile_limits_and_payload():
    s=AppSettings(dictionary_layout_kind="illustrated",illustrated_grid_visible=True,
                  illustrated_grid_x=48,illustrated_grid_y=32,
                  illustrated_grid_subdivisions=4,illustrated_snap_tolerance=9)
    validate_illustrated_preferences(s)
    stored=profile_payload(s)
    assert stored["illustrated_grid_x"]==48
    fresh=AppSettings()
    apply_profile_payload(fresh,stored)
    assert fresh.illustrated_grid_subdivisions==4
    assert fresh.illustrated_snap_tolerance==9
    s.illustrated_grid_y=0
    with pytest.raises(ValueError):validate_illustrated_preferences(s)


def test_main_canvas_hook_and_bindtag_are_isolated_from_normal_page():
    base=Path(__file__).resolve().parents[1]/"src"/"picture_capture"
    app=(base/"app.py").read_text("utf-8")
    source=(base/"ui"/"illustrated_main_canvas.py").read_text("utf-8")
    assert "render_illustrated_main_overlay(self)" in app
    assert "if render_illustrated_main_overlay(self):" in app
    assert "self.tag not in tags" in source
    assert "self.deactivate()" in source
    assert "effective_page_kind(a.settings,a.current_page)" in source
    assert "write_entries(self.root,self.page" in source
    assert "write_guides(self.root,self.page" in source
    assert "self.undo_stack" in source and "self.redo_stack" in source
