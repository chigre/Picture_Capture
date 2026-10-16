"""Page-local, rectangle-based illustrated dictionary annotations.

One spatial text group is one stable entry; its multilingual lines can be
indexed as aliases without splitting the source group. Never writes PDIC,
PPP, REF or SECTION files.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json
import uuid

from .formats import write_text_atomic
from .project_storage import is_managed_project, storage_root

FORMAT = "picture-capture-illustrated-entries-v1"
STATUSES = frozenset({"draft", "reviewed"})


@dataclass(frozen=True, slots=True)
class IllustratedEntry:
    id: str
    x: int
    y: int
    w: int
    h: int
    lines: tuple[str, ...] = ()
    primary: str = ""
    aliases: tuple[str, ...] = ()
    status: str = "draft"
    source: str = "manual"
    group_id: str = ""
    locked: bool = False
    hidden: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def entry_root(project_root: Path) -> Path:
    root = Path(project_root)
    base = storage_root(root) if is_managed_project(root) else root
    return base / "data" / "illustrated_entries"


def entry_path(project_root: Path, image_path: Path) -> Path:
    return entry_root(project_root) / f"{Path(image_path).stem}.json"


def file_ticket(project_root: Path, image_path: Path) -> str | None:
    try:
        return sha256(entry_path(project_root, image_path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def make_entry(x: int, y: int, w: int, h: int, *,
               lines: tuple[str, ...] = (), source: str = "manual") -> IllustratedEntry:
    return IllustratedEntry(uuid.uuid4().hex, x, y, w, h,
                            lines=lines, primary=next((v for v in lines if v.strip()), ""),
                            source=source)


def _clean_lines(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("多语言内容必须是文本列表")
    if not all(isinstance(v, str) for v in values):
        raise ValueError("多语言内容不得包含非文本")
    return tuple(v.strip() for v in values if v.strip())


def validate(entries: list[IllustratedEntry], *,
             image_size: tuple[int, int] | None = None) -> None:
    ids: set[str] = set()
    for item in entries:
        if not isinstance(item, IllustratedEntry):
            raise ValueError("图解词条数据类型无效")
        if not isinstance(item.id, str) or not item.id or item.id in ids:
            raise ValueError("图解词条 ID 重复或为空")
        ids.add(item.id)
        if any(type(v) is not int for v in (item.x, item.y, item.w, item.h)):
            raise ValueError("图解词条坐标必须是整数")
        if min(item.x, item.y) < 0 or min(item.w, item.h) < 1:
            raise ValueError("图解词条矩形范围无效")
        if image_size and (item.x + item.w > image_size[0]
                           or item.y + item.h > image_size[1]):
            raise ValueError("图解词条矩形超出原图")
        if not isinstance(item.group_id, str) or len(item.group_id)>128:
            raise ValueError("图解对象组 ID 无效")
        if type(item.locked) is not bool or type(item.hidden) is not bool:
            raise ValueError("图解对象锁定/隐藏状态无效")
        if item.status not in STATUSES or item.source not in {"manual", "ocr"}:
            raise ValueError("图解词条来源或校对状态无效")
        if not isinstance(item.primary, str) or not isinstance(item.lines, tuple):
            raise ValueError("图解词条文字格式无效")
        if not isinstance(item.aliases, tuple):
            raise ValueError("图解词条别名格式无效")
        if any(not isinstance(x, str) or "\0" in x for x in (*item.lines, *item.aliases, item.primary)):
            raise ValueError("图解词条包含非法文本")


def read_entries(project_root: Path, image_path: Path) -> list[IllustratedEntry]:
    path = entry_path(project_root, image_path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict) or payload.get("format") != FORMAT:
            raise ValueError("版本不受支持")
        if payload.get("page") != Path(image_path).name:
            raise ValueError("基准页面不匹配")
        rows = payload.get("entries")
        if not isinstance(rows, list):
            raise ValueError("entries 必须是列表")
        result = [
            IllustratedEntry(
                id=str(row["id"]),
                x=row["x"], y=row["y"], w=row["w"], h=row["h"],
                lines=_clean_lines(row.get("lines", [])),
                primary=row.get("primary", ""),
                aliases=_clean_lines(row.get("aliases", [])),
                status=row.get("status", "draft"),
                source=row.get("source", "manual"),
                group_id=row.get("group_id", ""),
                locked=row.get("locked", False),
                hidden=row.get("hidden", False),
            )
            for row in rows
        ]
        validate(result)
        return result
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} 图解词条文件损坏，不会覆盖：{exc}") from exc


def write_entries(project_root: Path, image_path: Path, entries: list[IllustratedEntry],
                  *, expected_ticket: str | None,
                  image_size: tuple[int, int] | None = None) -> str:
    validate(entries, image_size=image_size)
    path = entry_path(project_root, image_path)
    if file_ticket(project_root, image_path) != expected_ticket:
        raise RuntimeError("图解词条文件已在外部变化，请重新打开后再保存")
    if path.exists():
        read_entries(project_root, image_path)
    payload = {
        "format": FORMAT, "page": Path(image_path).name,
        "entries": [asdict(row) for row in entries],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if file_ticket(project_root, image_path) != expected_ticket:
        raise RuntimeError("图解词条文件在保存前发生变化")
    write_text_atomic(path, text)
    if read_entries(project_root, image_path) != entries:
        raise RuntimeError("写入后校验失败，请重新载入图解词条")
    return file_ticket(project_root, image_path) or sha256(text.encode()).hexdigest()
