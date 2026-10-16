"""Main-canvas illustrated dictionary overlay and object editor.

A frontmost *bindtag* captures pointer/keyboard gestures only while the active
page is illustrated; traditional REF/PPP/PDIC bindings remain untouched.
Geometry is always in original-image pixels. Draft OCR proposals are transient.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
from tkinter import Menu, messagebox, simpledialog
import tkinter as tk

from ..illustrated_entries import make_entry, read_entries, write_entries, file_ticket
from ..illustrated_guides import read_guides, write_guides, guide_ticket
from ..illustrated_profile import effective_page_kind
from ..illustrated_geometry import (
    clamp_rect,snap_position,transform_selection,group_objects,ungroup_objects,
    merge_text_groups,split_text_group,duplicate,
)
from .illustrated_entry_dialog import edit_illustrated_group


class IllustratedCanvasEditor:
    def __init__(self,app):
        self.app=app
        self.page=None
        self.root=None
        self.entries=[]
        self.proposals=[]
        self.guides={"vertical":[],"horizontal":[]}
        self.ticket=None
        self.guide_version=None
        self.selected:set[str]=set()
        self.key_id:str|None=None
        self.clipboard=[]  # in-app page-object clipboard, not the OS clipboard
        self.last_pointer=(0,0)
        self.drag=None
        self.mode="box"
        self.undo_stack=[]
        self.redo_stack=[]
        self.busy=False
        self.tag=f"PCIllustratedCanvas{id(self)}"
        self.bound=False

    def _ready(self):
        a=self.app
        return (a.project is not None and a.image is not None
                and a.current_page is not None and not a._preprocess_mode_active()
                and effective_page_kind(a.settings,a.current_page)=="illustrated")

    def install(self):
        if self.bound:return
        c=self.app.canvas
        for seq,func in (
            ("<Button-1>",self.press),("<Shift-Button-1>",self.press),
            ("<B1-Motion>",self.motion),("<ButtonRelease-1>",self.release),
            ("<Double-Button-1>",self.double_click),("<Button-3>",self.context),
            ("<Control-Button-1>",self.press),
            ("<Control-z>",lambda e:self.undo()),("<Control-y>",lambda e:self.redo()),
            ("<Delete>",lambda e:self.delete()),("<Control-a>",lambda e:self.select_all()),
            ("<Control-g>",lambda e:self.group()),("<Control-G>",lambda e:self.ungroup()),
            ("<Control-Shift-g>",lambda e:self.ungroup()),
            ("<F2>",lambda e:self.edit_selected()),
            ("<Control-d>",lambda e:self.duplicate()),
            ("<Control-c>",lambda e:self.copy_selected()),
            ("<Control-v>",lambda e:self.paste_selected()),
            ("<Left>",lambda e:self.nudge(-1,0,e)),("<Right>",lambda e:self.nudge(1,0,e)),
            ("<Up>",lambda e:self.nudge(0,-1,e)),("<Down>",lambda e:self.nudge(0,1,e)),
            ("<Escape>",lambda e:self.escape()),
            ("<Key-b>",lambda e:self.switch_mode("box")),
            ("<Key-v>",lambda e:self.switch_mode("select")),
        ):
            c.bind_class(self.tag,seq,func)
        self.bound=True
        self._activate_tags()

    def _activate_tags(self):
        tags=self.app.canvas.bindtags()
        if self.tag not in tags:self.app.canvas.bindtags((self.tag,)+tags)

    def deactivate(self):
        if self.bound:
            tags=self.app.canvas.bindtags()
            if self.tag in tags:self.app.canvas.bindtags(tuple(t for t in tags if t!=self.tag))

    def _sync(self):
        if not self._ready():
            self.deactivate()
            return False
        a=self.app
        if a.current_page!=self.page or a.project.root!=self.root:
            try:
                entries=read_entries(a.project.root,a.current_page)
                guides=read_guides(a.project.root,a.current_page)
            except (OSError,ValueError) as exc:
                a.status_var.set(f"图解标注文件读取失败：{exc}")
                self.deactivate()
                return False
            self.page=a.current_page
            self.root=a.project.root
            self.entries=entries
            self.guides=guides
            self.ticket=file_ticket(self.root,self.page)
            self.guide_version=guide_ticket(self.root,self.page)
            self.proposals=[]
            self.selected.clear()
            self.undo_stack=[]
            self.redo_stack=[]
            self.drag=None
        self.install()
        self._activate_tags()
        return True

    def _source(self,event):
        c=self.app.canvas
        zoom=max(.08,float(self.app.view_scale))
        w,h=self.app.image.size
        return (max(0,min(w,round(c.canvasx(event.x)/zoom))),
                max(0,min(h,round(c.canvasy(event.y)/zoom))))

    def _size(self):return self.app.image.size

    def _hit(self,x,y):
        for row in reversed(self.entries):
            if not row.hidden and row.x<=x<=row.x+row.w and row.y<=y<=row.y+row.h:
                return row
        return None

    def _ids_for(self,row):
        if row.group_id:
            return {v.id for v in self.entries if v.group_id==row.group_id and not v.hidden}
        return {row.id}

    def _editable(self):
        locked_groups={e.group_id for e in self.entries if e.group_id and e.locked}
        return [e for e in self.entries if e.id in self.selected and not e.locked
                and e.group_id not in locked_groups]

    def _commit(self,proposal,*,which="entries",remember=True):
        if not self._sync() or self.busy:return False
        a=self.app
        previous=list(self.entries) if which=="entries" else {k:list(v) for k,v in self.guides.items()}
        if previous==proposal:return True
        try:
            if which=="entries":
                new_ticket=write_entries(self.root,self.page,proposal,expected_ticket=self.ticket,image_size=self._size())
            else:
                new_ticket=write_guides(self.root,self.page,proposal,expected_ticket=self.guide_version,size=self._size())
        except (ValueError,RuntimeError,OSError) as exc:
            messagebox.showerror("图解编辑保存失败",str(exc),parent=a)
            return False
        if which=="entries":
            self.entries=list(proposal);self.ticket=new_ticket
        else:
            self.guides={k:list(v) for k,v in proposal.items()};self.guide_version=new_ticket
        if remember:
            self.undo_stack.append((which,previous,proposal))
            limit=int(a.settings.illustrated_history_depth)
            del self.undo_stack[:-limit]
            self.redo_stack.clear()
        a.redraw()
        return True

    def _apply_history(self,forward:bool):
        src=self.redo_stack if forward else self.undo_stack
        dst=self.undo_stack if forward else self.redo_stack
        if not src:return "break"
        kind,old,new=src[-1]
        if self._commit(new if forward else old,which=kind,remember=False):
            dst.append(src.pop())
        return "break"

    def undo(self):return self._apply_history(False)
    def redo(self):return self._apply_history(True)
    def switch_mode(self,mode):
        self.mode=mode
        self.app.status_var.set("图解 "+("选择工具" if mode=="select" else "框选新词条工具"))
        return "break"
    def escape(self):
        self.drag=None
        self.selected.clear()
        self.app.redraw()
        return "break"
    def select_all(self):
        self.selected={v.id for v in self.entries if not v.hidden}
        self.app.redraw()
        return "break"

    def press(self,event):
        if not self._sync():return None
        self.app.canvas.focus_set()
        x,y=self._source(event)
        self.last_pointer=(x,y)
        shift=bool(getattr(event,"state",0)&0x1)
        control=bool(getattr(event,"state",0)&0x4)
        # Drag from a 16-screen-pixel on-image ruler to add a guide.
        margin=16/max(.08,self.app.view_scale)
        if shift and self.app.settings.illustrated_guides_visible and not self.app.settings.illustrated_guides_locked:
            # Adobe-like ruler semantics: drag from TOP to create a
            # horizontal guide (at release Y), from LEFT for a vertical one.
            if y<margin and x>=margin:
                self.drag=("guide","horizontal",x,y);return "break"
            if x<margin and y>=margin:
                self.drag=("guide","vertical",x,y);return "break"
        # Ctrl+drag an existing guide to reposition it. Shift+drag from the
        # rulers above creates guides and remains distinct from text selection.
        tol=self.app.settings.illustrated_snap_tolerance/max(.08,self.app.view_scale)
        if control and self.app.settings.illustrated_guides_visible and not self.app.settings.illustrated_guides_locked:
            for axis,pos in (
                [("vertical",v) for v in self.guides["vertical"]] +
                [("horizontal",v) for v in self.guides["horizontal"]]
            ):
                if abs((x if axis=="vertical" else y)-pos)<=tol:
                    self.drag=("guide-edit",axis,pos,0)
                    return "break"
        hit=self._hit(x,y)
        if hit:
            ids=self._ids_for(hit)
            self.key_id=hit.id
            corner=(abs(x-(hit.x+hit.w))*self.app.view_scale<=10
                    and abs(y-(hit.y+hit.h))*self.app.view_scale<=10)
            # An already-selected single box can be resized at its handle.
            # Otherwise Shift/Ctrl clicks consistently toggle selection.
            if corner and hit.id in self.selected and not hit.locked and len(self.selected)==1:
                self.drag=("resize",hit.id,x,y)
            elif shift or control:
                if hit.id in self.selected:self.selected.difference_update(ids)
                else:self.selected.update(ids)
                self.drag=None
            else:
                if hit.id not in self.selected:self.selected=ids
                self.drag=("copy" if bool(getattr(event,"state",0)&0x0008) else "move",
                           x,y,list(self.entries))
        elif shift:
            self.drag=("marquee",x,y,None)
        else:
            if not control:self.selected.clear()
            self.drag=("create" if self.mode=="box" else "marquee",x,y,None)
        self.app.redraw()
        return "break"

    def motion(self,event):
        if not self._ready() or not self.drag:return "break"
        x,y=self._source(event)
        c=self.app.canvas
        c.delete("ill-preview")
        kind,px,py,_=self.drag
        z=self.app.view_scale
        if kind in ("move","copy"):
            for e in self._editable():
                nx,ny,_,_=clamp_rect(e.x+x-px,e.y+y-py,e.w,e.h,self._size())
                c.create_rectangle(nx*z,ny*z,(nx+e.w)*z,(ny+e.h)*z,
                                   outline="#ef4444",dash=(4,3),width=2,tags="ill-preview")
        elif kind=="resize":
            target=next((a for a in self.entries if a.id==px),None)
            if target is not None:
                c.create_rectangle(target.x*z,target.y*z,x*z,y*z,
                                   outline="#ef4444",dash=(4,3),width=2,tags="ill-preview")
        elif kind in {"create","marquee"}:
            c.create_rectangle(min(px,x)*z,min(py,y)*z,max(px,x)*z,max(py,y)*z,
                               outline="#ef4444",dash=(4,3),width=2,tags="ill-preview")
        elif kind in ("guide","guide-edit"):
            axis="vertical" if px=="vertical" else "horizontal"
            pos=x if axis=="vertical" else y
            if axis=="vertical":coords=(pos*z,0,pos*z,self.app.image.height*z)
            else:coords=(0,pos*z,self.app.image.width*z,pos*z)
            c.create_line(*coords,fill="#e11d88",width=2,tags="ill-preview")
        return "break"

    def release(self,event):
        if not self._ready():return "break"
        c=self.app.canvas;c.delete("ill-preview")
        if self.drag is None:return "break"
        action,x0,y0,original=self.drag
        self.drag=None
        x,y=self._source(event)
        z=self.app.view_scale
        if action in ("move","copy"):
            delta_x,delta_y=x-x0,y-y0
            if getattr(event,"state",0)&0x1:
                if abs(delta_x)>=abs(delta_y):delta_y=0
                else:delta_x=0
            chosen=self._editable()
            if chosen and (delta_x or delta_y):
                first=chosen[0]
                other=[v for v in self.entries if v.id not in self.selected and not v.hidden]
                settings=self.app.settings
                nx,ny=snap_position(first.x+delta_x,first.y+delta_y,
                    (first.x,first.y,first.w,first.h),
                    grid=(max(1,settings.illustrated_grid_x//settings.illustrated_grid_subdivisions),
                          max(1,settings.illustrated_grid_y//settings.illustrated_grid_subdivisions)),
                    origin=(settings.illustrated_grid_origin_x,settings.illustrated_grid_origin_y),
                    vertical_guides=self.guides["vertical"],horizontal_guides=self.guides["horizontal"],
                    other_boxes=other,tolerance=settings.illustrated_snap_tolerance,
                    scale=z,snap_grid=settings.illustrated_snap_grid,
                    snap_guides=settings.illustrated_snap_guides,
                    snap_objects=settings.illustrated_snap_objects)
                dx,dy=nx-first.x,ny-first.y
                # Keep a multi-object translation coherent by clamping global
                # offset to all selected bounds (not each object's own delta).
                dx=max(-min(e.x for e in chosen),min(dx,self.app.image.width-max(e.x+e.w for e in chosen)))
                dy=max(-min(e.y for e in chosen),min(dy,self.app.image.height-max(e.y+e.h for e in chosen)))
                if action=="copy":
                    copies=[replace(e,id=uuid4().hex,x=e.x+dx,y=e.y+dy,
                                    group_id="",locked=False,status="draft")
                            for e in chosen]
                    if self._commit(self.entries+copies):
                        self.selected={e.id for e in copies}
                else:
                    self._commit([replace(v,x=v.x+dx,y=v.y+dy) if v in chosen else v for v in self.entries])
        elif action=="resize":
            target=next((a for a in self.entries if a.id==x0),None)
            if target is not None and not target.locked:
                settings=self.app.settings
                sx,sy=snap_position(
                    x,y,(x,y,1,1),
                    grid=(max(1,settings.illustrated_grid_x//settings.illustrated_grid_subdivisions),
                          max(1,settings.illustrated_grid_y//settings.illustrated_grid_subdivisions)),
                    origin=(settings.illustrated_grid_origin_x,settings.illustrated_grid_origin_y),
                    vertical_guides=self.guides["vertical"],horizontal_guides=self.guides["horizontal"],
                    other_boxes=[v for v in self.entries if v.id!=target.id and not v.hidden],
                    tolerance=settings.illustrated_snap_tolerance,scale=z,
                    snap_grid=settings.illustrated_snap_grid,snap_guides=settings.illustrated_snap_guides,
                    snap_objects=settings.illustrated_snap_objects,
                )
                width=max(1,min(self.app.image.width-target.x,sx-target.x))
                height=max(1,min(self.app.image.height-target.y,sy-target.y))
                self._commit([replace(e,w=width,h=height) if e.id==target.id else e
                              for e in self.entries])
        elif action=="create":
            left,top=min(x,x0),min(y,y0)
            w,h=abs(x-x0),abs(y-y0)
            if w>=4 and h>=4:
                s=self.app.settings
                nx,ny=snap_position(left,top,(left,top,w,h),
                    grid=(max(1,s.illustrated_grid_x//s.illustrated_grid_subdivisions),
                          max(1,s.illustrated_grid_y//s.illustrated_grid_subdivisions)),
                    origin=(s.illustrated_grid_origin_x,s.illustrated_grid_origin_y),
                    vertical_guides=self.guides["vertical"],horizontal_guides=self.guides["horizontal"],
                    other_boxes=self.entries,tolerance=s.illustrated_snap_tolerance,scale=z,
                    snap_grid=s.illustrated_snap_grid,snap_guides=s.illustrated_snap_guides,
                    snap_objects=s.illustrated_snap_objects)
                nx,ny,w,h=clamp_rect(nx,ny,w,h,self._size())
                new=make_entry(nx,ny,w,h)
                if self._commit(self.entries+[new]):self.selected={new.id}
        elif action=="marquee":
            x0,x1=sorted((x0,x));y0,y1=sorted((y0,y))
            hits={v.id for v in self.entries if not v.hidden and
                  v.x>=x0 and v.y>=y0 and v.x+v.w<=x1 and v.y+v.h<=y1}
            self.selected=hits|{v.id for v in self.entries if v.group_id and
                                 any(z.id in hits and z.group_id==v.group_id for z in self.entries)}
        elif action in ("guide","guide-edit"):
            axis=x0;pos=x if axis=="vertical" else y
            proposed={k:list(v) for k,v in self.guides.items()}
            if action=="guide-edit" and y0 in proposed[axis]:
                proposed[axis].remove(y0)
            if pos not in proposed[axis]:
                proposed[axis].append(pos);proposed[axis].sort()
            self._commit(proposed,which="guides")
        self.app.redraw()
        return "break"

    def double_click(self,event):
        if not self._sync():return None
        x,y=self._source(event)
        target=self._hit(x,y)
        if target:
            self.selected={target.id}
            edit_illustrated_group(self.app,target,
                lambda updated:self._commit([updated if e.id==target.id else e for e in self.entries]))
        return "break"

    def _operate(self,method,**kwargs):
        if not self._sync():return "break"
        try:
            proposal=transform_selection(self.entries,self.selected,method,self._size(),**kwargs)
            self._commit(proposal)
        except ValueError as exc:self.app.status_var.set(str(exc))
        return "break"
    def align(self,method):return self._operate(method)
    def align_to_key(self,method):
        return self._operate(method,reference="key",key_id=self.key_id)
    def align_to_page(self,method):
        return self._operate(method,reference="page")
    def distribute_with_gap(self,horizontal=True):
        gap=simpledialog.askinteger("指定等间距","输入对象间的空白距离（原图像素）",
                                    parent=self.app,minvalue=0,maxvalue=10000)
        if gap is not None:
            return self._operate("distribute_x" if horizontal else "distribute_y",gap=gap)
        return "break"
    def edit_selected(self):
        if len(self.selected)!=1:return "break"
        target=next((e for e in self.entries if e.id in self.selected),None)
        if target is not None:
            edit_illustrated_group(self.app,target,
                 lambda updated:self._commit([
                     updated if e.id==target.id else e for e in self.entries
                 ]))
        return "break"

    def group(self):
        self._commit(group_objects(self.entries,self.selected))
        return "break"
    def ungroup(self):
        self._commit(ungroup_objects(self.entries,self.selected))
        return "break"
    def lock(self,value):
        self._commit([replace(e,locked=value) if e.id in self.selected else e for e in self.entries])
        return "break"
    def hide(self,value):
        self._commit([replace(e,hidden=value) if e.id in self.selected else e for e in self.entries])
        if value:self.selected.clear()
        return "break"
    def show_all(self):
        self._commit([replace(e,hidden=False) for e in self.entries])
        return "break"
    def delete(self):
        if self.selected:
            self._commit([e for e in self.entries if e.id not in self.selected or e.locked])
            self.selected.clear()
            self.app.redraw()
        return "break"
    def duplicate(self):
        proposed,ids=duplicate(self.entries,self.selected,self._size())
        if self._commit(proposed):
            self.selected=ids
            self.app.redraw()
        return "break"

    def copy_selected(self):
        if not self._sync():return "break"
        self.clipboard=[e for e in self.entries if e.id in self.selected and not e.hidden]
        self.app.status_var.set(f"已复制 {len(self.clipboard)} 个文字框；Ctrl+V 粘贴")
        return "break"

    def paste_selected(self):
        if not self._sync() or not self.clipboard:return "break"
        original=self.clipboard
        width,height=self._size()
        left=min(e.x for e in original);top=min(e.y for e in original)
        right=max(e.x+e.w for e in original);bottom=max(e.y+e.h for e in original)
        # One common offset preserves alignment and distances within the set.
        dx=max(-left,min(12,width-right))
        dy=max(-top,min(12,height-bottom))
        group_mapping={}
        additions=[]
        for e in original:
            gid=""
            if e.group_id:
                gid=group_mapping.setdefault(e.group_id,uuid4().hex)
            additions.append(replace(e,id=uuid4().hex,x=e.x+dx,y=e.y+dy,
                                     group_id=gid,locked=False,hidden=False,
                                     status="draft"))
        if self._commit([*self.entries,*additions]):
            self.selected={e.id for e in additions}
            self.app.redraw()
        return "break"
    def nudge(self,dx,dy,event):
        if not self._ready():return None
        scale=int(self.app.settings.illustrated_nudge_step)
        if getattr(event,"state",0)&0x1:scale*=10
        targets=self._editable()
        if not targets:return "break"
        # Treat a selected layout group as one geometric translation; do not
        # individually clamp its members and accidentally deform their spacing.
        mx=dx*scale;my=dy*scale
        mx=max(-min(e.x for e in targets),
               min(mx,self._size()[0]-max(e.x+e.w for e in targets)))
        my=max(-min(e.y for e in targets),
               min(my,self._size()[1]-max(e.y+e.h for e in targets)))
        ids={e.id for e in targets}
        self._commit([replace(e,x=e.x+mx,y=e.y+my) if e.id in ids
                      else e for e in self.entries])
        return "break"
    def semantic_merge(self):
        try:self._commit(merge_text_groups(self.entries,self.selected))
        except ValueError as exc:self.app.status_var.set(str(exc))
        return "break"
    def semantic_split(self):
        if len(self.selected)!=1:return "break"
        target=next((e for e in self.entries if e.id in self.selected),None)
        if target is None or len(target.lines)<2:return "break"
        at=simpledialog.askinteger("拆分多语言词条","从第几行开始创建第二个词条？",
                                   parent=self.app,minvalue=2,maxvalue=len(target.lines))
        if at is not None:
            try:self._commit(split_text_group(self.entries,target.id,at-1))
            except ValueError as exc:self.app.status_var.set(str(exc))
        return "break"
    def numeric_position(self):
        if len(self.selected)!=1:return "break"
        target=next((e for e in self.entries if e.id in self.selected),None)
        if target is None or target.locked:return "break"
        value=simpledialog.askstring("精确坐标","输入 X,Y,宽,高（原图像素）",
                                     initialvalue=f"{target.x},{target.y},{target.w},{target.h}",
                                     parent=self.app)
        if not value:return "break"
        try:
            parts=[int(v.strip()) for v in value.replace("，",",").split(",")]
            if len(parts)!=4 or parts[2]<1 or parts[3]<1:raise ValueError()
            if clamp_rect(*parts,self._size())!=tuple(parts):raise ValueError()
            self._commit([replace(e,x=parts[0],y=parts[1],w=parts[2],h=parts[3])
                          if e.id==target.id else e for e in self.entries])
        except ValueError:self.app.status_var.set("请输入图像范围内有效的 X,Y,宽,高")
        return "break"
    def toggle_grid(self):
        s=self.app.settings
        s.illustrated_grid_visible=not s.illustrated_grid_visible
        self.app.save_settings()
        self.app.redraw()
        return "break"
    def clear_guides(self):
        if self.app.settings.illustrated_guides_locked:return "break"
        if messagebox.askyesno("清除辅助线","清除本页所有图解辅助线？",parent=self.app):
            self._commit({"vertical":[],"horizontal":[]},which="guides")
        return "break"
    def remove_nearest_guide(self):
        if self.app.settings.illustrated_guides_locked:return "break"
        x,y=self.last_pointer
        values=[(abs(x-pos),"vertical",pos) for pos in self.guides["vertical"]]
        values += [(abs(y-pos),"horizontal",pos) for pos in self.guides["horizontal"]]
        if not values:return "break"
        delta,axis,pos=min(values)
        if delta*self.app.view_scale>self.app.settings.illustrated_snap_tolerance:
            self.app.status_var.set("指针附近没有辅助线")
            return "break"
        proposed={k:list(v) for k,v in self.guides.items()}
        proposed[axis].remove(pos)
        self._commit(proposed,which="guides")
        return "break"

    def add_guide(self,axis):
        if self.app.settings.illustrated_guides_locked:return "break"
        point=self.last_pointer[0 if axis=="vertical" else 1]
        proposed={k:list(v) for k,v in self.guides.items()}
        if point not in proposed[axis]:
            proposed[axis].append(point);proposed[axis].sort()
            self._commit(proposed,which="guides")
        return "break"
    def context(self,event):
        if not self._sync():return None
        self.last_pointer=self._source(event)
        c=Menu(self.app.canvas,tearoff=False)
        for name,action in (
            ("选择工具 V",lambda:self.switch_mode("select")),
            ("新建文字框 B",lambda:self.switch_mode("box")),
            ("左对齐",lambda:self.align("left")),
            ("水平居中",lambda:self.align("center_x")),
            ("右对齐",lambda:self.align("right")),
            ("顶端对齐",lambda:self.align("top")),
            ("垂直居中",lambda:self.align("center_y")),
            ("底端对齐",lambda:self.align("bottom")),
            ("水平等间距",lambda:self.align("distribute_x")),
            ("垂直等间距",lambda:self.align("distribute_y")),
            ("等宽",lambda:self.align("equal_width")),
            ("等高",lambda:self.align("equal_height")),
            ("以关键对象左对齐",lambda:self.align_to_key("left")),
            ("对齐到页面水平中心",lambda:self.align_to_page("center_x")),
            ("对齐到页面垂直中心",lambda:self.align_to_page("center_y")),
            ("设置水平间距…",lambda:self.distribute_with_gap(True)),
            ("设置垂直间距…",lambda:self.distribute_with_gap(False)),
            ("编辑文字 F2",self.edit_selected),
            ("组合 Ctrl+G",self.group),("取消组合 Ctrl+Shift+G",self.ungroup),
            ("复制 Ctrl+D",self.duplicate),
            ("复制到剪贴板 Ctrl+C",self.copy_selected),
            ("粘贴 Ctrl+V",self.paste_selected),
            ("锁定选中",lambda:self.lock(True)),
            ("解锁选中",lambda:self.lock(False)),("隐藏选中",lambda:self.hide(True)),
            ("全部显示",self.show_all),("精确坐标…",self.numeric_position),
            ("合并为一个多语言词条",self.semantic_merge),
            ("按语言行拆分词条…",self.semantic_split),
            ("显示/隐藏网格",self.toggle_grid),
            ("添加横向辅助线",lambda:self.add_guide("horizontal")),
            ("添加垂直辅助线",lambda:self.add_guide("vertical")),
            ("删除最近辅助线",self.remove_nearest_guide),
            ("清除本页辅助线",self.clear_guides),
            ("接受全部 OCR 候选",self.accept_proposals),
            ("撤销 Ctrl+Z",self.undo),("重做 Ctrl+Y",self.redo),
        ):
            c.add_command(label=name,command=action)
        try:c.tk_popup(event.x_root,event.y_root)
        finally:c.grab_release()
        return "break"

    def detect(self):
        if self.busy or not self._sync():return
        from dataclasses import replace as clone
        from ..illustrated_ocr import propose_page_entries,proposal_overlaps
        page=self.page;root=self.root
        settings=clone(self.app.settings)
        self.busy=True
        def finished(_completed,_total,stopped,results,error):
            self.busy=False
            if not self._ready() or self.app.project.root!=root or self.app.current_page!=page:return
            if error or stopped or not results:
                self.app.status_var.set(f"图解 OCR 未完成：{error or '已停止'}")
                return
            self.proposals=[e for e in results[-1] if not any(
                proposal_overlaps(e,old) for old in self.entries)]
            self.app.redraw()
            self.app.status_var.set(f"图解 OCR 提议 {len(self.proposals)} 个文字组；请检查后从右键菜单接受")
        try:
            self.app._start_batch_task("图解词典全页 OCR",[self.app.current_index],
                lambda *_args:propose_page_entries(page,settings),finished,
                item_label=lambda i:self.app.project.images[i].name)
        except Exception as exc:
            self.busy=False
            messagebox.showerror("图解 OCR",str(exc),parent=self.app)
    def accept_proposals(self):
        if not self.proposals:return
        if not messagebox.askyesno("接受候选",f"确认保存 {len(self.proposals)} 个 OCR 文字组？",parent=self.app):return
        if self._commit(self.entries+self.proposals):self.proposals=[]
        self.app.redraw()

    def render(self)->bool:
        if not self._sync():return False
        a=self.app;c=a.canvas;s=a.settings
        z=float(a.view_scale);w,h=a.image.size
        c.configure(scrollregion=(0,0,round(w*z),round(h*z)))
        def line(*pts,color="#8faaca",dash=(),width=1):
            c.create_line(*pts,fill=color,dash=dash,width=width,tags=("illustrated-overlay",))
        # Avoid thousands of grid lines at high zoom or tiny spacing.
        if s.illustrated_grid_visible:
            # Tk Canvas has no line alpha: blend the requested color against
            # white for a stable, non-destructive visual approximation.
            def blend(hexcolor,amount):
                v=[int(hexcolor[i:i+2],16) for i in (1,3,5)]
                a=amount/100
                return "#"+"".join(f"{round(255*(1-a)+n*a):02x}" for n in v)
            dx=max(1,s.illustrated_grid_x//s.illustrated_grid_subdivisions)
            dy=max(1,s.illustrated_grid_y//s.illustrated_grid_subdivisions)
            color=blend(s.illustrated_grid_color,s.illustrated_grid_opacity)
            if w//dx<450:
                for i,x in enumerate(range(s.illustrated_grid_origin_x%dx,w+1,dx)):
                    line(x*z,0,x*z,h*z,color=color,width=2 if (x-s.illustrated_grid_origin_x)%s.illustrated_grid_x==0 else 1)
            if h//dy<450:
                for y in range(s.illustrated_grid_origin_y%dy,h+1,dy):
                    line(0,y*z,w*z,y*z,color=color,width=2 if (y-s.illustrated_grid_origin_y)%s.illustrated_grid_y==0 else 1)
        if s.illustrated_guides_visible:
            for x in self.guides["vertical"]:
                line(x*z,0,x*z,h*z,color=s.illustrated_guide_color,dash=(6,3))
            for y in self.guides["horizontal"]:
                line(0,y*z,w*z,y*z,color=s.illustrated_guide_color,dash=(6,3))
        # Light rulers are confined to a 16 screen-pixel strip. They are
        # decoration on the canvas, not persisted to the image/PDF/export.
        c.create_rectangle(0,0,w*z,16,fill="#ecf0f4",outline="",tags="illustrated-overlay")
        c.create_rectangle(0,0,16,h*z,fill="#ecf0f4",outline="",tags="illustrated-overlay")
        for x in range(0,w+1,max(20,round(100/z))):
            c.create_line(x*z,9,x*z,16,fill="#64748b",tags="illustrated-overlay")
            c.create_text(x*z+2,1,anchor="nw",text=str(x),fill="#475569",
                          font=("TkDefaultFont",7),tags="illustrated-overlay")
        for y in range(0,h+1,max(20,round(100/z))):
            c.create_line(9,y*z,16,y*z,fill="#64748b",tags="illustrated-overlay")
            c.create_text(1,y*z+2,anchor="nw",text=str(y),fill="#475569",
                          font=("TkDefaultFont",7),tags="illustrated-overlay")
        for row in self.entries:
            if row.hidden:continue
            active=row.id in self.selected
            color="#2563eb" if active else ("#64748b" if row.locked else "#07966a")
            coords=(row.x*z,row.y*z,(row.x+row.w)*z,(row.y+row.h)*z)
            c.create_rectangle(*coords,outline=color,width=3 if active else 2,
                               tags=("illustrated-overlay",))
            if active:
                for x,y in ((coords[0],coords[1]),(coords[2],coords[1]),
                            (coords[0],coords[3]),(coords[2],coords[3])):
                    c.create_rectangle(x-3,y-3,x+3,y+3,fill="white",outline=color,
                                       tags=("illustrated-overlay",))
            if row.primary:
                c.create_text(coords[0]+3,coords[1]+3,anchor="nw",text=row.primary[:30],
                              fill="#166534",font=("TkDefaultFont",9),
                              tags=("illustrated-overlay",))
        for row in self.proposals:
            c.create_rectangle(row.x*z,row.y*z,(row.x+row.w)*z,(row.y+row.h)*z,
                               outline="#0e8bc0",dash=(4,4),width=2,
                               tags=("illustrated-overlay",))
        if self.drag is not None:
            # Redraw may occur between press and release; transient overlay is
            # recovered on the next B1-Motion.
            pass
        return True


def render_illustrated_main_overlay(app)->bool:
    """Called once after the main photo is painted, before ordinary overlays."""
    editor=getattr(app,"_illustrated_main_editor",None)
    if editor is None:
        editor=IllustratedCanvasEditor(app)
        app._illustrated_main_editor=editor
    return editor.render()


def illustrated_main_action(app,action="open"):
    if not app.project or app.current_page is None:return
    if app._preprocess_mode_active():
        app.status_var.set("请先退出预处理模式，再编辑图解词条")
        return
    app.redraw()
    editor=getattr(app,"_illustrated_main_editor",None)
    if editor is None or not editor._ready():return
    if action=="detect":editor.detect()
    elif action=="accept":editor.accept_proposals()
    elif action=="export":
        from ..illustrated_export import export_illustrated_index
        try:
            path,count=export_illustrated_index(app.project.root,app.project.images,
                split_aliases=app.settings.illustrated_export_split_aliases)
            app.status_var.set(f"导出 {count} 条图解索引：{path}")
        except (ValueError,OSError) as exc:messagebox.showerror("图解导出",str(exc),parent=app)
    elif action in {"align","guides"}:editor.context(SimpleEvent(app.canvas))
    elif action=="select":editor.switch_mode("select")
    elif action=="box":editor.switch_mode("box")
    elif action=="group":editor.group()
    elif action=="ungroup":editor.ungroup()
    elif action=="undo":editor.undo()
    elif action=="redo":editor.redo()
    elif action=="grid":editor.toggle_grid()
    else:
        app.canvas.focus_set()
        app.status_var.set("主画布图解编辑：B 新建框／V 选择／Shift 多选或拖出标尺辅助线／右键对象操作")


class SimpleEvent:
    def __init__(self,canvas):
        self.x=self.y=0
        self.x_root=canvas.winfo_rootx()+80
        self.y_root=canvas.winfo_rooty()+80
