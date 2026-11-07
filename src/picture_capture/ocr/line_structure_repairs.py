from __future__ import annotations

"""OCR logical line repair: same-row fragments and two forms of wrapped grammar.

These operations are purely in-memory; all original core patch hooks
(parse, line merge, vertical overlap, grammar POS, model class, NumPy, regex)
are supplied at call time. Original OCRLine pickle identity is retained.
"""

from collections.abc import Callable
from typing import Any
import re
import numpy as np
from ..models import AppSettings
from .headword_models import HeadwordParse, OCRLine


def repair_split_headword_lines(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
    *,
    parse_fn: Callable[..., Any],
    overlap_fn: Callable[..., float],
    merge_fn: Callable[..., OCRLine],
    np_module: Any = np,
) -> list[OCRLine]:
    """Actively absorb right-side OCR fragments for a left-edge lemma.

    OCR engines sometimes assign the bold lemma and ``, da adj.`` / ``v.`` to
    separate line boxes because their baselines/heights differ.  Normal line
    clustering can therefore miss a valid POS cue.  We only perform this rescue
    for a line beginning at the column left edge, only absorb fragments to its
    right, and only keep the merge if it creates a structural dictionary cue.
    """
    if not lines:
        return []
    heights = [max(1, line.box[3] - line.box[1]) for line in lines]
    median_h = max(1.0, float(np_module.median(heights)))
    used: set[int] = set()
    output: list[OCRLine] = []

    def structural(parsed: HeadwordParse | None) -> bool:
        return bool(parsed and (parsed.has_pos or parsed.has_inflection or parsed.has_descriptor))

    for i, line in enumerate(lines):
        if i in used:
            continue
        parsed = parse_fn(line.text, settings, patterns)
        if line.box[0] > left_limit or structural(parsed):
            output.append(line)
            continue
        # A plausible split fragment should sit to the right on essentially the
        # same physical row. Nearby lines starting again at the left margin are
        # almost certainly separate dictionary/body rows and are never absorbed.
        current = line
        selected: list[int] = []
        candidates: list[tuple[int, OCRLine]] = []
        for j, other in enumerate(lines):
            if j == i or j in used:
                continue
            if other.box[0] <= left_limit:
                continue
            if other.box[0] < current.box[0]:
                continue
            h = max(current.box[3] - current.box[1], other.box[3] - other.box[1], 1)
            cy1 = (current.box[1] + current.box[3]) / 2.0
            cy2 = (other.box[1] + other.box[3]) / 2.0
            same_row = overlap_fn(current.box, other.box) >= 0.18 or abs(cy1 - cy2) <= 0.55 * h
            gap = other.box[0] - current.box[2]
            if same_row and -0.5 * median_h <= gap <= 7.0 * median_h:
                candidates.append((j, other))
        for j, other in sorted(candidates, key=lambda pair: pair[1].box[0])[:4]:
            trial = merge_fn([current, other])
            trial_parsed = parse_fn(trial.text, settings, patterns)
            # We may need more than one fragment (lemma | gender | POS), so keep
            # extending while fragments are adjacent; commit only after structure
            # appears.
            current = trial
            selected.append(j)
            if structural(trial_parsed):
                used.update(selected)
                parsed = trial_parsed
                current.logical_repairs = tuple(dict.fromkeys(current.logical_repairs + ("RIGHT_FRAGMENT_ABSORBED",)))
                break
        if structural(parsed):
            output.append(current)
        else:
            output.append(line)
    return sorted(output, key=lambda item: (item.box[1], item.box[0]))




def repair_wrapped_headword_structure(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
    *,
    parse_fn: Callable[..., Any],
    find_pos_fn: Callable[..., Any],
    strip_fn: Callable[[str], str],
    line_cls: type[OCRLine] = OCRLine,
    np_module: Any = np,
) -> list[OCRLine]:
    """Attach a POS label that wrapped onto the next printed line.

    Long forms such as ``agroalimentación (pl. ...)`` can consume the whole
    first line and leave ``s.f.`` at the beginning of the next one.  The marker
    belongs at the first line's Y, so this function augments only the logical
    text used for parsing while keeping the original first-line geometry.
    """
    if not lines:
        return []
    _headword_pattern, _special_pattern, pos_pattern = patterns
    heights = [max(1, line.box[3] - line.box[1]) for line in lines]
    median_h = max(1.0, float(np_module.median(heights)))
    output: list[OCRLine] = []
    for i, line in enumerate(lines):
        parsed = parse_fn(line.text, settings, patterns)
        if (
            i + 1 >= len(lines) or line.box[0] > left_limit or not parsed
            or parsed.has_pos or parsed.looks_like_continuation
        ):
            output.append(line)
            continue
        nxt = lines[i + 1]
        vertical_gap = nxt.box[1] - line.box[3]
        # Printed lines may have slightly overlapping OCR boxes; allow only the
        # immediately adjacent row and a modest indentation.
        if vertical_gap > 0.80 * median_h or nxt.box[0] > left_limit + 1.25 * median_h:
            output.append(line)
            continue
        pos_match, noise = find_pos_fn(nxt.text, pos_pattern, min(48, settings.paddle_pos_search_chars))
        if pos_match is None:
            output.append(line)
            continue
        # A genuine wrapped POS must occur at the beginning, apart from a tiny
        # square-marker OCR artifact accepted by _find_pos_cue.
        prefix = nxt.text[:pos_match.start()]
        if strip_fn(prefix).strip() and not noise:
            output.append(line)
            continue
        pos_text = pos_match.group(0).strip()
        synthetic = f"{line.text.rstrip()} {pos_text}"
        output.append(line_cls(
            text=synthetic, confidence=min(line.confidence, nxt.confidence),
            box=line.box, records=line.records,
            logical_repairs=tuple(dict.fromkeys(line.logical_repairs + ("MULTILINE_POS",))),
        ))
    return output





def repair_multiline_headword_state_machine(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
    max_follow_lines: int = 2,
    *,
    parse_fn: Callable[..., Any],
    find_pos_fn: Callable[..., Any],
    line_cls: type[OCRLine] = OCRLine,
    np_module: Any = np,
    re_module: Any = re,
) -> list[OCRLine]:
    """General v2.0 multi-line grammar recovery.

    The earlier repair handled only `lemma ...` + immediate `POS`.  This state
    machine can inspect up to two following printed lines and stops as soon as a
    structured parse is recovered. Geometry remains anchored to the first line,
    so the separator is never moved to the continuation row.
    """
    if not lines:
        return []
    _headword_pattern, _special_pattern, pos_pattern = patterns
    median_h = max(1.0, float(np_module.median([max(1, l.box[3] - l.box[1]) for l in lines])))
    out: list[OCRLine] = []
    for i, line in enumerate(lines):
        parsed = parse_fn(line.text, settings, patterns)
        if (
            line.box[0] > left_limit or not parsed or parsed.has_pos or parsed.has_descriptor
            or parsed.looks_like_continuation
        ):
            out.append(line)
            continue
        # Only trigger for a plausible incomplete dictionary head: morphology
        # note, grammatical comma, cropped opening parenthesis, or a long bold
        # display form that consumed most of the OCR band.
        unmatched_slash = line.text.count("/") % 2 == 1
        open_pronunciation = bool(
            ("[" in line.text and "]" not in line.text) or unmatched_slash
        )
        incomplete_shape = bool(
            parsed.has_inflection
            or re_module.search(r",\s*[^,;:]{0,24}$", line.text, flags=re_module.UNICODE)
            or ("(" in line.text and ")" not in line.text)
            or open_pronunciation
            or len(parsed.normalized.strip("-")) >= 11
        )
        if not incomplete_shape:
            out.append(line)
            continue

        synthetic = line.text.rstrip()
        joined_records = list(line.records)
        joined_conf = line.confidence
        recovered: OCRLine | None = None
        prev = line
        for step in range(1, max_follow_lines + 1):
            j = i + step
            if j >= len(lines):
                break
            nxt = lines[j]
            gap = nxt.box[1] - prev.box[3]
            if gap > 0.95 * median_h or nxt.box[0] > left_limit + 1.75 * median_h:
                break
            pronunciation_still_open = bool(
                ("[" in synthetic and "]" not in synthetic)
                or synthetic.count("/") % 2 == 1
            )
            # Do not absorb a clearly new headword row.
            nxt_parsed = parse_fn(nxt.text, settings, patterns)
            if (
                not pronunciation_still_open and nxt.box[0] <= left_limit
                and nxt_parsed and (nxt_parsed.has_pos or nxt_parsed.has_descriptor)
            ):
                break
            # The continuation should begin with POS/grammar material or be a
            # short continuation of an open morphology note.
            pm, noise = find_pos_fn(nxt.text, pos_pattern, min(64, settings.paddle_pos_search_chars))
            starts_grammar = bool(pm is not None and (pm.start() <= 3 or noise))
            if not starts_grammar and not (
                ("(" in synthetic and ")" not in synthetic) or pronunciation_still_open
            ):
                break
            synthetic = synthetic + " " + nxt.text.strip()
            joined_records.extend(nxt.records)
            joined_conf = min(joined_conf, nxt.confidence)
            trial = parse_fn(synthetic, settings, patterns)
            if trial and trial.normalized.casefold() == parsed.normalized.casefold() and (
                trial.has_pos or trial.has_descriptor or trial.has_inflection
            ):
                recovered = line_cls(
                    text=synthetic,
                    confidence=joined_conf,
                    box=line.box,
                    records=joined_records,
                    logical_repairs=tuple(dict.fromkeys(
                        line.logical_repairs + (f"MULTILINE_STATE_JOIN:{step}",)
                    )),
                )
                if trial.has_pos or trial.has_descriptor:
                    break
            prev = nxt
        out.append(recovered or line)
    return out
