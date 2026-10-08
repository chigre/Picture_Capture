from __future__ import annotations

"""Pure data models shared by Paddle headword OCR and evidence fusion."""

from dataclasses import dataclass
import re


@dataclass(slots=True)
class OCRRecord:
    text: str
    confidence: float
    box: tuple[int, int, int, int]
    # Synthetic records created when one pathological OCR detection box spans
    # multiple physically separate display-head glyphs. Ordinary OCR records
    # keep these fields empty, preserving existing constructors/equality.
    recovery: str = ""
    recovery_source_text: str = ""
    parent_box: tuple[int, int, int, int] | None = None


@dataclass(slots=True)
class OCRLine:
    """One visual text line assembled from one or more OCR records."""

    text: str
    confidence: float
    box: tuple[int, int, int, int]
    records: list[OCRRecord]
    # Logical repairs applied after OCR grouping (right-fragment absorption,
    # wrapped POS recovery, multi-line state-machine joins).  Keeping them on
    # the line makes the parser/debug report explain *how* a synthetic line was
    # assembled instead of only showing its final text.
    logical_repairs: tuple[str, ...] = ()


@dataclass(slots=True)
class GrammarTailParse:
    """Structured grammar tail produced after the display lemma.

    The parser advances a cursor through morphology, POS, usage/labels and the
    remaining definition.  Individual stages may still use small regexes, but
    the overall decision is a state machine rather than one monolithic match.
    """

    variants: tuple[str, ...] = ()
    inflections: tuple[str, ...] = ()
    pos_text: str = ""
    usage_text: str = ""
    descriptor_text: str = ""
    definition_text: str = ""
    consumed: int = 0
    stage: str = "lemma"
    trace: tuple[str, ...] = ()


@dataclass(slots=True)
class HeadwordParse:
    raw: str
    normalized: str
    has_pos: bool
    pos_text: str
    has_inflection: bool
    inflection_text: str
    has_descriptor: bool
    descriptor_text: str
    match_end: int
    looks_like_continuation: bool = False
    continuation_reason: str = ""
    corrected_raw: str = ""
    parse_text: str = ""
    ocr_repairs: tuple[str, ...] = ()
    # v2.0 structured grammar parse. These fields are deliberately explicit so
    # diagnostics can show where parsing stopped instead of reducing the whole
    # decision to one regular-expression match.
    variants: tuple[str, ...] = ()
    plural_text: str = ""
    usage_text: str = ""
    definition_text: str = ""
    parser_stage: str = ""
    parser_trace: tuple[str, ...] = ()
    bug_types: tuple[str, ...] = ()


@dataclass(slots=True)
class HeadwordFilterRule:
    kind: str
    value: str
    line_number: int
    source: str
    regex: re.Pattern[str] | None = None

    @property
    def display(self) -> str:
        return f"{self.kind}: {self.value}"


# Preserve historical class module paths for pickle/debug compatibility.
for _cls in (OCRRecord, OCRLine, GrammarTailParse, HeadwordParse, HeadwordFilterRule):
    _cls.__module__ = "picture_capture.paddle_headwords_core"
del _cls
