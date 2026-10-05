from __future__ import annotations

"""Low-level PDIC backup restore primitives.

This module owns deterministic page-token resolution, merged-PDIC parsing and
one-page atomic publication.  It deliberately contains no Tk/UI orchestration;
controllers decide scope, confirmation, batch lifetime and refresh behavior.
"""

import os
from pathlib import Path
import re

from .formats import write_pdic
from .models import Entry as WordEntry


def build_page_lookup(
    page_stems: list[str],
) -> tuple[dict[str, str], dict[int, str], dict[int, str]]:
    """Build O(1) exact/numeric/suffix lookup tables for project page stems."""
    exact: dict[str, str] = {}
    numeric_candidates: dict[int, list[str]] = {}
    suffix_candidates: dict[int, list[str]] = {}
    for stem in page_stems:
        exact[stem.casefold()] = stem
        if stem.isdigit():
            numeric_candidates.setdefault(int(stem), []).append(stem)
        match = re.search(r"(\d+)$", stem)
        if match:
            suffix_candidates.setdefault(int(match.group(1)), []).append(stem)
    numeric = {
        number: values[0]
        for number, values in numeric_candidates.items()
        if len(values) == 1
    }
    suffix = {
        number: values[0]
        for number, values in suffix_candidates.items()
        if len(values) == 1
    }
    return exact, numeric, suffix


def resolve_page_token(
    token: str,
    page_stems: list[str],
    lookup: tuple[dict[str, str], dict[int, str], dict[int, str]] | None = None,
) -> str | None:
    """Resolve one legacy page token without guessing ambiguous numeric suffixes."""
    cleaned = Path(str(token).strip()).stem.strip()
    if not cleaned:
        return None
    exact, numeric, suffix = lookup or build_page_lookup(page_stems)
    hit = exact.get(cleaned.casefold())
    if hit:
        return hit
    if cleaned.isdigit():
        number = int(cleaned)
        hit = numeric.get(number)
        if hit:
            return hit
        return suffix.get(number)
    return None


def parse_merged_pdic_text(
    text: str,
    page_stems: list[str],
) -> tuple[dict[str, list[WordEntry]], dict[str, int]]:
    """Parse a whole-dictionary PDIC backup into independent per-page entries."""
    mapping: dict[str, list[WordEntry]] = {stem: [] for stem in page_stems}
    lookup = build_page_lookup(page_stems)
    matched = 0
    unmatched = 0
    nonblank = 0
    for line_no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        nonblank += 1
        fields = raw.split("#")
        if len(fields) < 8:
            raise ValueError(
                f"整体 PDIC 第 {line_no} 行字段不足 8 个，不是有效 PDIC 记录"
            )
        try:
            x = int(float(fields[1]))
            y = int(float(fields[2]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"整体 PDIC 第 {line_no} 行坐标无效") from exc
        page = resolve_page_token(fields[5], page_stems, lookup)
        if page is None:
            unmatched += 1
            continue
        mapping[page].append(
            WordEntry(
                word=str(fields[0]),
                x=x,
                y=y,
                current_page=page,
                previous_page=str(fields[6] or "@"),
                next_page=str(fields[7] or "@"),
            )
        )
        matched += 1
    if nonblank == 0:
        raise ValueError("整体 PDIC 文件为空，没有可用于恢复的记录。")
    if matched == 0:
        raise ValueError(
            "整体 PDIC 中没有任何记录能对应当前项目页面，请核对是否选择了正确文件。"
        )
    return mapping, {
        "records": nonblank,
        "matched": matched,
        "unmatched": unmatched,
    }


def write_pdic_atomic(
    target: Path,
    entries: list[WordEntry],
    image_width: int,
    pages: tuple[str, str, str],
) -> None:
    """Atomically replace one page PDIC so stop/crash never leaves a half file."""
    temp = target.with_name(f".{target.name}.restore.tmp")
    try:
        write_pdic(temp, entries, image_width, pages)
        os.replace(temp, target)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
