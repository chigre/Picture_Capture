"""Standalone illustrated-dictionary index export; never rewrites live PDIC.

One JSON group stays authoritative. Exporters may index only its primary term
(one row with aliases attached), or emit one lookup row per language/alias.
All lookup rows reference the same stable group ID and source-page rectangle.
"""
from __future__ import annotations

import csv
from io import StringIO
import json
from pathlib import Path
from typing import Iterable

from .formats import write_text_atomic
from .illustrated_entries import IllustratedEntry, read_entries
from .project_storage import exports_root

COLUMNS = ("lookup", "page", "group_id", "x", "y", "w", "h",
           "primary", "languages_json", "aliases_json", "status")


def lookup_terms(entry: IllustratedEntry) -> list[str]:
    words = [entry.primary, *entry.lines, *entry.aliases]
    seen: set[str] = set()
    result = []
    for raw in words:
        value = str(raw or "").strip()
        normalized = value.casefold()
        if value and normalized not in seen:
            result.append(value)
            seen.add(normalized)
    return result


def export_illustrated_index(project_root: Path, pages: Iterable[Path], *,
                             split_aliases: bool = False) -> tuple[Path, int]:
    rows = []
    for page in pages:
        for entry in read_entries(project_root, page):
            if not entry.primary.strip() and not entry.lines:
                continue
            terms = lookup_terms(entry)
            if not terms:
                continue
            for lookup in (terms if split_aliases else terms[:1]):
                rows.append((lookup, page.stem, entry.id,
                             entry.x, entry.y, entry.w, entry.h,
                             entry.primary, json.dumps(entry.lines, ensure_ascii=False),
                             json.dumps(terms[1:], ensure_ascii=False), entry.status))
    stream = StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    target = (exports_root(project_root) / "illustrated_dictionary" /
              ("multilingual_lookup.tsv" if split_aliases else "group_lookup.tsv"))
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(target, stream.getvalue())
    return target, len(rows)
