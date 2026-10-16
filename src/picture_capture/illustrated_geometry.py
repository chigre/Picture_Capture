"""Pure source-pixel object geometry for illustrated dictionary annotation.

No Tk, column inference or PDIC effects. Undo/redo is managed by the editor
with immutable before/after page snapshots, including stable object IDs.
"""
from __future__ import annotations
from dataclasses import replace
from math import hypot
from typing import Iterable
from uuid import uuid4
from .illustrated_entries import IllustratedEntry

def bounding(items: Iterable[IllustratedEntry]) -> tuple[int,int,int,int]:
    rows=list(items)
    if not rows: raise ValueError("请选择至少一个文本框")
    return (min(i.x for i in rows),min(i.y for i in rows),
            max(i.x+i.w for i in rows),max(i.y+i.h for i in rows))

def clamp_rect(x:int,y:int,w:int,h:int,page:tuple[int,int])->tuple[int,int,int,int]:
    w=max(1,min(int(w),page[0]));h=max(1,min(int(h),page[1]))
    return (max(0,min(int(x),page[0]-w)),max(0,min(int(y),page[1]-h)),w,h)

def snap_position(x:int,y:int,rect:tuple[int,int,int,int], *,
                  grid:tuple[int,int]=(40,40),origin:tuple[int,int]=(0,0),
                  vertical_guides:Iterable[int]=(),horizontal_guides:Iterable[int]=(),
                  other_boxes:Iterable[IllustratedEntry]=(),tolerance:float=8,
                  scale:float=1, snap_grid:bool=True,snap_guides:bool=True,
                  snap_objects:bool=True)->tuple[int,int]:
    """Snap left/center/right and top/center/bottom edges, in screen-px distance.

    Guide/object wins tied votes over a grid. A single translation is chosen
    independently per axis; geometry is always stored as integer source pixels.
    """
    _,_,w,h=rect
    margin=max(0,float(tolerance))/max(.08,float(scale))
    def axis(value:int,size:int,step:int,base:int,guides,targets)->int:
        anchors=[(0,0),(size/2,1),(size,2)]
        choices=[]
        for offset,idx in anchors:
            current=value+offset
            if snap_guides:
                for target in guides:
                    diff=float(target)-current
                    if abs(diff)<=margin:choices.append((abs(diff),0,idx,diff))
            if snap_objects:
                for target in targets:
                    diff=float(target)-current
                    if abs(diff)<=margin:choices.append((abs(diff),1,idx,diff))
            if snap_grid and step>0:
                nearest=base+round((current-base)/step)*step
                diff=nearest-current
                if abs(diff)<=margin:choices.append((abs(diff),2,idx,diff))
        return int(round(value+min(choices)[-1])) if choices else value
    xs=[v for b in other_boxes for v in (b.x,b.x+b.w/2,b.x+b.w)]
    ys=[v for b in other_boxes for v in (b.y,b.y+b.h/2,b.y+b.h)]
    return axis(x,w,grid[0],origin[0],vertical_guides,xs),axis(y,h,grid[1],origin[1],horizontal_guides,ys)

def transform_selection(entries:list[IllustratedEntry],ids:set[str],operation:str,
                        page:tuple[int,int],*,reference:str="selection",key_id:str|None=None,
                        gap:int|None=None)->list[IllustratedEntry]:
    """Align, distribute by clear gaps, or equal-size; locked boxes are inert.

    Distribution preserves order, first/last external edges and nonnegative
    clearance where possible. Never modifies text, status or stable IDs.
    """
    targets=[e for e in entries if e.id in ids and not e.locked]
    if not targets:return list(entries)
    if reference=="page":bounds=(0,0,page[0],page[1])
    elif reference=="key":
        key=next((e for e in targets if e.id==key_id),None)
        if key is None: raise ValueError("请指定一个已选中的关键对象")
        bounds=(key.x,key.y,key.x+key.w,key.y+key.h)
    else:bounds=bounding(targets)
    lx,ty,rx,by=bounds
    changed={}
    for e in targets:
        x,y,w,h=e.x,e.y,e.w,e.h
        if operation=="left":x=lx
        elif operation=="right":x=rx-w
        elif operation=="center_x":x=round((lx+rx-w)/2)
        elif operation=="top":y=ty
        elif operation=="bottom":y=by-h
        elif operation=="center_y":y=round((ty+by-h)/2)
        elif operation=="equal_width":w=next((a.w for a in targets if a.id==key_id),targets[0].w)
        elif operation=="equal_height":h=next((a.h for a in targets if a.id==key_id),targets[0].h)
        elif operation in ("distribute_x","distribute_y"):continue
        else:raise ValueError("不支持的布局操作")
        changed[e.id]=replace(e,**dict(zip(("x","y","w","h"),clamp_rect(x,y,w,h,page))))
    if operation in ("distribute_x","distribute_y"):
        if len(targets)<3: return list(entries)
        horizontal=operation=="distribute_x"
        ordered=sorted(targets,key=lambda e:(e.x if horizontal else e.y,e.id))
        starts=[e.x if horizontal else e.y for e in ordered]
        sizes=[e.w if horizontal else e.h for e in ordered]
        left=starts[0];right=max(starts[i]+sizes[i] for i in range(len(ordered)))
        clearance=(right-left-sum(sizes))/(len(ordered)-1)
        if gap is not None:clearance=max(0,gap)
        if clearance<0:raise ValueError("对象重叠，无法执行非负等间距分布")
        pos=float(left)
        for e,size in zip(ordered,sizes):
            changed[e.id]=replace(e,**({"x":round(pos)} if horizontal else {"y":round(pos)}))
            pos+=size+clearance
    return [changed.get(e.id,e) for e in entries]

def group_objects(entries:list[IllustratedEntry],ids:set[str],*,group_id:str|None=None
                  )->list[IllustratedEntry]:
    chosen=[e for e in entries if e.id in ids and not e.locked]
    if len(chosen)<2:return list(entries)
    gid=group_id or uuid4().hex
    return [replace(e,group_id=gid) if e in chosen else e for e in entries]

def ungroup_objects(entries:list[IllustratedEntry],ids:set[str])->list[IllustratedEntry]:
    groups={e.group_id for e in entries if e.id in ids and e.group_id}
    return [replace(e,group_id="") if e.group_id in groups and not e.locked else e for e in entries]

def merge_text_groups(entries:list[IllustratedEntry],ids:set[str])->list[IllustratedEntry]:
    """Destructive semantic merge is explicit and keeps first selected ID."""
    rows=[e for e in entries if e.id in ids]
    if len(rows)<2 or any(e.locked for e in rows):raise ValueError("至少选择两个未锁定的词条")
    rows.sort(key=lambda e:(e.y,e.x,e.id))
    x0,y0,x1,y1=bounding(rows)
    first=rows[0]
    combined=replace(first,x=x0,y=y0,w=x1-x0,h=y1-y0,
                     lines=tuple(s for row in rows for s in row.lines),
                     aliases=tuple(dict.fromkeys(s for row in rows for s in row.aliases)),
                     group_id="",status="draft")
    removed={e.id for e in rows}
    return [combined if e.id==first.id else e for e in entries if e.id not in removed-{first.id}]

def split_text_group(entries:list[IllustratedEntry],target_id:str,
                     split_at:int)->list[IllustratedEntry]:
    """Split at a language-line boundary. Duplicated geometry is intentional."""
    target=next((e for e in entries if e.id==target_id),None)
    if target is None or target.locked or not (0<split_at<len(target.lines)):
        raise ValueError("请在未锁定文字组的有效行间拆分")
    # Partition the original annotation region proportionally by line count;
    # two new groups must not occupy exactly the same rectangle on the canvas.
    # When the box is too short, refuse rather than create out-of-bounds boxes.
    if target.h<2:
        raise ValueError("文字框高度不足，无法拆分；请先调整框范围")
    upper_h=max(1,min(target.h-1,round(target.h*split_at/len(target.lines))))
    first=replace(target,h=upper_h,lines=target.lines[:split_at],
                  primary=target.lines[0],aliases=(),group_id="",status="draft")
    second=replace(target,id=uuid4().hex,y=target.y+upper_h,h=target.h-upper_h,
                   lines=target.lines[split_at:],primary=target.lines[split_at],
                   aliases=(),group_id="",status="draft")
    return [first,second] + [e for e in entries if e.id != target_id]

def duplicate(entries:list[IllustratedEntry],ids:set[str],page:tuple[int,int],
              offset:int=12)->tuple[list[IllustratedEntry],set[str]]:
    added=[]
    for e in entries:
        if e.id in ids:
            x,y,w,h=clamp_rect(e.x+offset,e.y+offset,e.w,e.h,page)
            added.append(replace(e,id=uuid4().hex,x=x,y=y,group_id="",locked=False,status="draft"))
    return list(entries)+added,{e.id for e in added}
