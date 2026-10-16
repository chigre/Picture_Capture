"""Per-image illustrated guide lines, independent from PDIC auxiliary crop lines."""
from __future__ import annotations
import json
from hashlib import sha256
from pathlib import Path
from .formats import write_text_atomic
from .illustrated_entries import entry_root

FORMAT = "picture-capture-illustrated-guides-v1"

def guide_path(root:Path,page:Path)->Path:
    return entry_root(root)/"guides"/(Path(page).stem+".json")

def guide_ticket(root:Path,page:Path)->str|None:
    try:return sha256(guide_path(root,page).read_bytes()).hexdigest()
    except FileNotFoundError:return None

def read_guides(root:Path,page:Path)->dict[str,list[int]]:
    path=guide_path(root,page)
    if not path.is_file():return {"vertical":[],"horizontal":[]}
    try:
        raw=json.loads(path.read_text("utf-8-sig"))
        if not isinstance(raw,dict) or raw.get("format")!=FORMAT or raw.get("page")!=Path(page).name:
            raise ValueError("不支持的辅助线记录或页面名不匹配")
        data={key:raw[key] for key in ("vertical","horizontal")}
        for arr in data.values():
            if not isinstance(arr,list) or len(arr)>300 or any(type(n)!=int or n<0 for n in arr):
                raise ValueError("辅助线坐标格式无效")
        return data
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError("图解辅助线文件损坏，不会覆盖："+str(exc)) from exc

def write_guides(root:Path,page:Path,guides:dict[str,list[int]],*,
                 expected_ticket:str|None,size:tuple[int,int])->str:
    for key,limit in (("vertical",size[0]),("horizontal",size[1])):
        arr=guides.get(key)
        if not isinstance(arr,list) or len(arr)>300 or any(type(v)!=int or not 0<=v<=limit for v in arr):
            raise ValueError("图解辅助线超出图像范围")
    old=guide_ticket(root,page)
    if old!=expected_ticket:raise RuntimeError("辅助线文件在外部被修改，请重新载入")
    if old is not None:read_guides(root,page)
    path=guide_path(root,page)
    path.parent.mkdir(parents=True,exist_ok=True)
    if guide_ticket(root,page)!=expected_ticket:raise RuntimeError("辅助线文件保存冲突")
    write_text_atomic(path,json.dumps({"format":FORMAT,"page":Path(page).name,
                                       "vertical":guides["vertical"],"horizontal":guides["horizontal"]},
                                      ensure_ascii=False,indent=2)+"\n")
    return guide_ticket(root,page) or ""
