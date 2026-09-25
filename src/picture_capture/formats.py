from __future__ import annotations

from pathlib import Path
import os
import tempfile

from .models import Entry, PolygonRegion
from .text_encoding import read_text_detected
from .project_storage import pdic_path_for_image


def pdic_path(image_path: Path) -> Path:
    """Return the active PDIC path for legacy or managed-v2 projects."""
    return pdic_path_for_image(image_path)


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Publish one text file atomically so concurrent readers never see a partial write."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def read_pdic(path: Path) -> list[Entry]:
    entries: list[Entry] = []
    if not path.exists():
        return entries
    for number, raw in enumerate(read_text_detected(path)[0].splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.split("#")
        if len(fields) < 3:
            raise ValueError(f"{path.name} 第 {number} 行不是有效的 PDIC 记录")
        try:
            x, y = int(float(fields[1])), int(float(fields[2]))
        except ValueError as exc:
            raise ValueError(f"{path.name} 第 {number} 行坐标无效") from exc
        entries.append(
            Entry(
                word=fields[0],
                x=x,
                y=y,
                current_page=fields[5] if len(fields) > 5 else path.stem,
                previous_page=fields[6] if len(fields) > 6 else "@",
                next_page=fields[7] if len(fields) > 7 else "@",
            )
        )
    return entries


def write_pdic(path: Path, entries: list[Entry], image_width: int, pages: tuple[str, str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current, previous, following = pages
    records: list[str] = []
    for entry in entries:
        x_percent = round(entry.x / image_width * 100, 2) if image_width else 0
        y_percent = round(entry.y / image_width * 100, 2) if image_width else 0
        word = entry.word.replace("\r", " ").replace("\n", " ").replace("#", "＃").strip()
        records.append(
            f"{word}#{entry.x}#{entry.y}#{x_percent:g}#{y_percent:g}#"
            f"{current}#{previous}#{following}"
        )
    _atomic_write_text(
        path, "\n".join(records) + ("\n" if records else ""), encoding="utf-8",
    )


def read_picdic_index_records(path: Path, fallback_page: str = "") -> list[str]:
    """Convert saved PDIC rows to PicDic index rows without changing coordinates.

    Output rows have exactly four tab-separated fields::

        WORD\txx.xx\tyy.yy\tpage

    X/Y percentages are read from PDIC fields 4/5 (zero-based 3/4) rather
    than recalculated.  Keeping the stored values is important because PDIC
    is the coordinate source of truth for downstream PicDic conversion.
    """
    records: list[str] = []
    if not path.exists():
        return records
    for number, raw in enumerate(read_text_detected(path)[0].splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.split("#")
        if len(fields) < 5:
            raise ValueError(f"{path.name} 第 {number} 行缺少 X/Y 比例，无法导出 PicDic 索引")
        word = fields[0].replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
        if not word:
            continue
        try:
            x_percent = float(fields[3].strip().rstrip("%"))
            y_percent = float(fields[4].strip().rstrip("%"))
        except ValueError as exc:
            raise ValueError(f"{path.name} 第 {number} 行 X/Y 比例无效") from exc
        page = (fields[5].strip() if len(fields) > 5 else "") or str(fallback_page or path.stem)
        page = page.replace("\t", " ").replace("\r", " ").replace("\n", " ")
        records.append(f"{word}\t{x_percent:.2f}\t{y_percent:.2f}\t{page}")
    return records


def read_ppp(path: Path) -> list[PolygonRegion]:
    regions: list[PolygonRegion] = []
    if not path.exists():
        return regions
    for raw in read_text_detected(path)[0].splitlines():
        if not raw.strip():
            continue
        fields = raw.split("\t")
        if len(fields) < 3:
            continue
        points: list[tuple[int, int]] = []
        for token in fields[2].split("|"):
            if not token or "," not in token:
                continue
            x, y = token.split(",", 1)
            points.append((int(float(x)), int(float(y))))
        regions.append(PolygonRegion(label=fields[1], points=points))
    return regions


def write_ppp(path: Path, regions: list[PolygonRegion], page_stem: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, region in enumerate(regions, 1):
        label = region.label or f"{page_stem}|P_{index:02d}|1|{page_stem}|"
        coords = "".join(f"|{x},{y}" for x, y in region.points)
        lines.append(f"{index}\t{label}\t{coords}")
    _atomic_write_text(
        path, "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8",
    )
