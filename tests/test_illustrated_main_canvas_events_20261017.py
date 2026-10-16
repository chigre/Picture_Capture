"""Headless main canvas event-level regression for spatial dictionary annotation."""
from types import SimpleNamespace
from pathlib import Path
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.illustrated_entries import read_entries
from picture_capture.illustrated_guides import read_guides
from picture_capture.ui.illustrated_main_canvas import IllustratedCanvasEditor


class Canvas:
    def __init__(self):
        self.tags=("widget","Canvas","all")
        self.events={}
        self.drawn=[]
    def bindtags(self,updated=None):
        if updated is not None:self.tags=tuple(updated)
        return self.tags
    def bind_class(self,tag,sequence,handler):
        self.events[(tag,sequence)]=handler
    def canvasx(self,x):return x
    def canvasy(self,y):return y
    def focus_set(self):pass
    def configure(self,**kwargs):pass
    def delete(self,*args):pass
    def create_rectangle(self,*args,**kwargs):
        self.drawn.append(("rect",args))
    def create_line(self,*args,**kwargs):
        self.drawn.append(("line",args))
    def create_text(self,*args,**kwargs):
        self.drawn.append(("text",args))


def setup(tmp_path):
    image=Image.new("RGB",(400,300),"white")
    page=tmp_path/"page001.png"
    image.save(page)
    canvas=Canvas()
    settings=AppSettings(dictionary_layout_kind="illustrated")
    messages=[]
    app=SimpleNamespace(project=SimpleNamespace(root=tmp_path,images=[page]),
                        current_page=page,current_index=0,
                        canvas=canvas,image=image,view_scale=1.,
                        settings=settings,status_var=SimpleNamespace(set=messages.append),
                        _preprocess_mode_active=lambda:False,
                        redraw=lambda:None)
    controller=IllustratedCanvasEditor(app)
    app._illustrated_main_editor=controller
    assert controller.render()
    return app,controller,messages


def event(x,y,state=0):
    return SimpleNamespace(x=x,y=y,state=state)


def test_main_canvas_creates_persists_selects_resizes_and_undoes(tmp_path):
    app,editor,_=setup(tmp_path)
    assert editor.tag==app.canvas.tags[0]
    assert (editor.tag,"<Button-1>") in app.canvas.events
    assert (editor.tag,"<Control-z>") in app.canvas.events
    assert editor.press(event(30,45))=="break"
    assert editor.release(event(92,90))=="break"
    assert len(read_entries(tmp_path,app.current_page))==1
    first=read_entries(tmp_path,app.current_page)[0]
    assert first.w>=60 and first.h>=40
    assert editor.selected=={first.id}
    assert editor.undo()=="break"
    assert read_entries(tmp_path,app.current_page)==[]
    assert editor.redo()=="break"
    assert read_entries(tmp_path,app.current_page)[0].id==first.id
    # selected bottom-right corner is a resize handle
    assert editor.press(event(first.x+first.w,first.y+first.h))=="break"
    assert editor.release(event(first.x+first.w+24,first.y+first.h+12))=="break"
    resized=read_entries(tmp_path,app.current_page)[0]
    assert resized.w>=first.w+10
    app.image.close()


def test_guides_are_page_local_shift_created_and_movable(tmp_path):
    app,editor,_=setup(tmp_path)
    # Dragging from the TOP ruler creates a horizontal guide at release Y.
    editor.press(event(160,5,1))
    editor.release(event(168,135,1))
    assert read_guides(tmp_path,app.current_page)["horizontal"]==[135]
    editor.press(event(168,135,4))
    editor.release(event(180,150,4))
    assert read_guides(tmp_path,app.current_page)["horizontal"]==[150]
    editor.undo()
    assert read_guides(tmp_path,app.current_page)["horizontal"]==[135]
    # LEFT ruler is the source of vertical guides.
    editor.press(event(5,170,1))
    editor.release(event(190,170,1))
    assert read_guides(tmp_path,app.current_page)["vertical"]==[190]
    app.image.close()


def test_mixed_page_switch_deactivates_class_bindtag(tmp_path):
    app,editor,_=setup(tmp_path)
    assert editor.tag in app.canvas.bindtags()
    app.settings.dictionary_layout_kind="traditional"
    assert editor.render() is False
    assert editor.tag not in app.canvas.bindtags()
    app.settings.dictionary_layout_kind="mixed"
    app.settings.illustrated_page_overrides={app.current_page.name:"illustrated"}
    assert editor.render() is True
    assert editor.tag==app.canvas.bindtags()[0]
    app.image.close()
