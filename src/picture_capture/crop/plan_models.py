"""Canonical crop result/plan dataclasses re-exported by the historical core.

processing_core retains the exact class objects and historical pickle module
names. Changing field order or defaults is a persistence-breaking change.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(slots=True)
class CropRecord:
    page: str
    index: int
    word: str
    filename: str
    box: tuple[int, int, int, int]


@dataclass(slots=True)
class EntryCropPiecePlan:
    output_index: int
    entry_ref_index: int | None
    word: str
    box: tuple[int, int, int, int]
    suffix: str
    source_mode: str = "cleaned"
    merge_polygon_indices: tuple[int, ...] = ()


@dataclass(slots=True)
class IllustrationCropPlan:
    polygon_index: int
    name: str
    associated_entry_index: int | None
    associated_word: str
    relation: str
    standalone: bool
    box: tuple[int, int, int, int] | None


@dataclass(slots=True)
class PageCropPlan:
    entry_pieces: list[EntryCropPiecePlan]
    illustrations: list[IllustrationCropPlan]
    integrate_illustrations: bool = True
    # Preview-only regions after auxiliary stop lines; never included in WW export.
    auxiliary_gaps: list[tuple[int, int, int, int]] = field(default_factory=list)


@dataclass(slots=True)
class IllustrationCropEvent:
    page: str
    polygon_index: int
    name: str
    associated_word: str
    relation: str
    action: str
    filename: str = ""


@dataclass(slots=True)
class IllustrationSplitResult:
    records: list[CropRecord]
    events: list[IllustrationCropEvent]

    # Backward-compatible sequence behaviour for callers that historically
    # treated split_illustrations() as a list of CropRecord.
    def __iter__(self):
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index):
        return self.records[index]
