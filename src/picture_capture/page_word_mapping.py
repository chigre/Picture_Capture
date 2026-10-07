from __future__ import annotations

"""Page-aware headword text parsing and comparison helpers."""

import difflib
import re

from .models import Entry as WordEntry
from .pdic_restore import (
    build_page_lookup as _build_words_page_lookup,
    resolve_page_token as _resolve_words_page_token,
)


def _parse_words_of_pages_text(
    text: str, page_stems: list[str], *, present_pages: set[str] | None = None,
) -> dict[str, list[str]]:
    """Parse page-aware legacy headword text without cross-page spillover.

    Supported forms are full PDIC records (page stem in field 6), tab-delimited
    ``page<TAB>word`` rows, and explicit page sections such as ``[0012]`` or
    ``页码: 0012``. A plain undivided word list is deliberately rejected: once
    page boundaries are unknown, distributing by cursor would recreate the exact
    spillover bug this importer is intended to prevent.
    """
    mapping: dict[str, list[str]] = {stem: [] for stem in page_stems}
    lookup = _build_words_page_lookup(page_stems)
    raw_lines = text.splitlines()
    nonblank = [line for line in raw_lines if line.strip()]
    if not nonblank:
        return mapping

    rich_hits = 0
    for raw in nonblank:
        fields = raw.split("#")
        if len(fields) >= 8:
            page = _resolve_words_page_token(fields[5], page_stems, lookup)
            if page is not None:
                mapping[page].append(fields[0].strip())
                if present_pages is not None:
                    present_pages.add(page)
                rich_hits += 1
    if rich_hits:
        return mapping

    tab_hits = 0
    tab_mapping: dict[str, list[str]] = {stem: [] for stem in page_stems}
    for raw in nonblank:
        fields = raw.split("\t", 1)
        if len(fields) != 2:
            continue
        page = _resolve_words_page_token(fields[0], page_stems, lookup)
        if page is not None:
            tab_mapping[page].append(fields[1].strip())
            if present_pages is not None:
                present_pages.add(page)
            tab_hits += 1
    if tab_hits:
        return tab_mapping

    section_mapping: dict[str, list[str]] = {stem: [] for stem in page_stems}
    current: str | None = None
    saw_section = False
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            continue
        match = re.match(r"^\[([^\]]+)\]$", stripped)
        if not match:
            match = re.match(r"^(?:page|页码|頁碼|页|頁)\s*[:：]?\s*(\S+)\s*$", stripped, re.I)
        if match:
            page = _resolve_words_page_token(match.group(1), page_stems, lookup)
            if page is None:
                raise ValueError(f"TXT 中找不到对应项目页面：{match.group(1)}")
            current = page
            if present_pages is not None:
                present_pages.add(page)
            saw_section = True
            continue
        if current is not None:
            section_mapping[current].append(stripped.split("#", 1)[0].strip())
    if saw_section:
        return section_mapping

    raise ValueError(
        "该 TXT 没有可识别的页码边界。请使用完整 PDIC/_WordsOfPages 记录、"
        "page\t词条，或 [页码] 分组格式；为避免错页，本功能不会把无分页的词表顺序灌入下一页。"
    )


def _fill_page_entries(entries: list[WordEntry], words: list[str]) -> tuple[int, int, int]:
    """Fill only the words belonging to one page and never borrow from neighbours."""
    ordered = list(entries)
    count = min(len(ordered), len(words))
    for entry, word in zip(ordered[:count], words[:count]):
        entry.word = str(word).strip()
    return count, len(ordered), len(words)


def _page_word_mapping_text(page_order: list[str], mapping: dict[str, list[str]]) -> str:
    """Render page-aware headwords as ``page<TAB>word`` text in page order."""
    rows: list[str] = []
    for page in page_order:
        for raw_word in mapping.get(page, []):
            word = str(raw_word or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")
            rows.append(f"{page}\t{word}")
    return "\n".join(rows) + ("\n" if rows else "")


def _compare_page_word_sequences(page: str, old_words: list[str], new_words: list[str]) -> list[dict[str, object]]:
    """Return line-oriented additions, deletions and replacements for one page.

    The comparison is exact after the surrounding page-aware parsers have
    stripped line endings/outer whitespace.  ``SequenceMatcher`` first anchors
    unchanged headwords, so a newly inserted row normally appears as an insert
    rather than turning every following row into a false modification.
    """
    changes: list[dict[str, object]] = []
    matcher = difflib.SequenceMatcher(a=list(old_words), b=list(new_words), autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for old_index in range(i1, i2):
                changes.append({
                    "kind": "删除", "page": page,
                    "old_index": old_index + 1, "old": old_words[old_index],
                    "new_index": None, "new": "",
                })
            continue
        if tag == "insert":
            for new_index in range(j1, j2):
                changes.append({
                    "kind": "新增", "page": page,
                    "old_index": None, "old": "",
                    "new_index": new_index + 1, "new": new_words[new_index],
                })
            continue

        paired = min(i2 - i1, j2 - j1)
        for offset in range(paired):
            old_index = i1 + offset
            new_index = j1 + offset
            changes.append({
                "kind": "修改", "page": page,
                "old_index": old_index + 1, "old": old_words[old_index],
                "new_index": new_index + 1, "new": new_words[new_index],
            })
        for old_index in range(i1 + paired, i2):
            changes.append({
                "kind": "删除", "page": page,
                "old_index": old_index + 1, "old": old_words[old_index],
                "new_index": None, "new": "",
            })
        for new_index in range(j1 + paired, j2):
            changes.append({
                "kind": "新增", "page": page,
                "old_index": None, "old": "",
                "new_index": new_index + 1, "new": new_words[new_index],
            })
    return changes


def _compare_page_word_mappings(
    page_order: list[str], old_mapping: dict[str, list[str]], new_mapping: dict[str, list[str]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Compare old/new page-aware word mappings and return changes + totals."""
    changes: list[dict[str, object]] = []
    counts = {"新增": 0, "删除": 0, "修改": 0, "old_rows": 0, "new_rows": 0}
    for page in page_order:
        old_words = list(old_mapping.get(page, []))
        new_words = list(new_mapping.get(page, []))
        counts["old_rows"] += len(old_words)
        counts["new_rows"] += len(new_words)
        page_changes = _compare_page_word_sequences(page, old_words, new_words)
        changes.extend(page_changes)
        for item in page_changes:
            kind = str(item.get("kind") or "")
            if kind in {"新增", "删除", "修改"}:
                counts[kind] += 1
    return changes, counts
