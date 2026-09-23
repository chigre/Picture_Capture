from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re


IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}


def natural_text_key(value: object) -> tuple:
    """Return the application's single natural, case-insensitive sort key."""
    parts = re.split(r"(\d+)", str(value or "").casefold())
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts if part)


@dataclass(slots=True)
class Entry:
    """A dictionary headword marker in original-image pixel coordinates."""

    word: str
    x: int
    y: int
    current_page: str = ""
    previous_page: str = "@"
    next_page: str = "@"
    # Runtime OCR metadata. PDIC stays backward-compatible and does not persist
    # these fields; the GUI restores them from QT/PaddleOCR/<page>.json when
    # available.
    confidence: float | None = None
    ocr_source: str = ""
    alphabetical_warning: str = ""
    # v2.0 OCR fusion/review metadata (runtime only; PDIC remains unchanged).
    candidate_id: str = ""
    final_engine: str = ""
    issue_type: str = ""
    parser_score: float | None = None
    manually_selected: bool = False


@dataclass(slots=True)
class PolygonRegion:
    label: str
    points: list[tuple[int, int]] = field(default_factory=list)


@dataclass(slots=True)
class AppSettings:
    # Project-level dictionary metadata. It is stored with the project but does
    # not participate in OCR, line detection, cropping, or PDIC serialization.
    dictionary_full_name: str = ""
    dictionary_abbreviation: str = ""
    dictionary_isbn: str = ""
    dictionary_index_language: str = ""
    dictionary_content_language: str = ""
    dictionary_body_page_range: str = ""
    # Geometric values use the old program's displayed-image pixel convention.
    # ``parameter_display_width`` records that displayed image width so batch
    # processing can convert the values back to source-image pixels.
    parameter_display_width: int = 0
    columns: int = 2
    # Profile v3 layout semantics. Geometry is measured in canonical space;
    # source images and PDIC entry coordinates are never rewritten.
    layout_writing_mode: str = "horizontal-tb"
    layout_text_direction: str = "ltr"
    layout_transform: str = "identity"
    layout_columns_policy: str = "detect"
    layout_column_separator_mode: str = "auto"
    analysis_threshold_mode: str = "auto"
    gutter: int = 50
    column_width: int = 700
    start_y: int = 55
    bottom_y: int = 0
    manual_x: int = 28
    manual_y: int = 400
    body_indent: int = 28
    character_height: int = 26
    row_padding: int = 1
    # Percentage of the detected column width used by rightward entry boxes.
    right_ratio: float = 100.0
    right_ratio_percent_version: int = 1
    horizontal_tolerance: int = 5
    marker_height: int = 2
    guide_width: int = 4
    # Main overlay colours. The classic Picture Capture visual language uses
    # red guide/headword markers by default; PPP colours are independently configurable.
    guide_color: str = "#ff0000"
    headword_marker_color: str = "#ff0000"
    illustration_outline_color: str = "#1565c0"
    illustration_outline_width: int = 1
    illustration_fill_color: str = "#ffe66d"
    illustration_label_border_color: str = "#d81b60"
    illustration_label_border_width: int = 1
    illustration_label_fill_color: str = "#ffffff"
    illustration_label_font_family: str = "Microsoft YaHei"
    illustration_label_font_size: int = 32
    illustration_label_font_bold: bool = False
    illustration_label_font_italic: bool = False
    show_column_guides: bool = True
    show_headword_markers: bool = True
    # Page-list optional columns can be hidden from the heading context menu.
    # The page-name column is intentionally permanent.
    page_list_show_lined: bool = True
    page_list_show_fill_status: bool = True
    page_list_show_illustrations: bool = True
    page_bookmarks: list[str] = field(default_factory=list)
    darkness_threshold: int = 300
    dark_area_percent: int = 90
    batch_interval: float = 3.0
    # Page-level multiprocessing is used only for entry/illustration cropping.
    # 0 = automatic conservative worker count; 1 = serial crop processing.
    crop_parallel_workers: int = 0
    # Automatic PPP illustration detection intentionally adds a little context
    # around dark connected components. The right side gets a larger default
    # because classic dictionary illustrations often extend into the gutter.
    illustration_detect_padding: int = 8
    illustration_detect_right_padding: int = 16
    white_threshold_high: int = 999
    row_step_multiplier: float = 1.2
    whitespace_adjustment: int = 2
    upward_ratio: float = 1.5
    white_threshold_low: int = 700
    analysis_left: int = 0
    analysis_right: int = 0
    ocr_language: str = "eng"
    tesseract_language: str = ""
    ocr_replace: bool = True
    lowercase_ocr: bool = False
    manual_columns: bool = False
    crop_to_bottom_y: bool = False
    hide_overlays: bool = False
    polygon_mode: bool = False
    show_illustration_labels: bool = False
    ocr_executable: str = "tesseract"
    image_suffix: str = ".png"
    # Overlay editor presentation at 100% page scale. The page zoom multiplies
    # the base font, so text boxes zoom together with the scanned page.
    main_entry_font_family: str = "DengXian"
    main_entry_font_size: int = 32
    main_entry_font_bold: bool = False
    main_entry_font_italic: bool = False
    main_entry_width_chars: int = 18
    main_entry_x_ratio: float = 0.66
    main_entry_follow_zoom: bool = True
    main_entry_default_color: str = "#ffffff"
    # Review zoom and typography are independent from the main page viewer and
    # are persisted per project. 64% is a practical default for large scans.
    review_zoom_percent: int = 64
    review_entry_font_family: str = "Cambria"
    review_entry_font_size: int = 18
    # v2 means review_entry_font_size is the actual fixed editor font size.
    # Before v2.11.13 it represented a 100%-zoom base size and was multiplied
    # by review_zoom_percent while rendering.  The marker lets old projects be
    # migrated once without repeatedly shrinking the saved value.
    review_font_semantics_version: int = 2
    review_entry_font_bold: bool = False
    review_entry_font_italic: bool = False
    # Independent typography for the editable Simplified companion in the
    # proofreading window. Older projects inherit the ordinary headword style
    # once when loaded, then persist these values independently.
    review_simplified_font_family: str = "Cambria"
    review_simplified_font_size: int = 18
    review_simplified_font_bold: bool = False
    review_simplified_font_italic: bool = False
    # Extra visual padding before review-entry text. This changes only the
    # proofreading editor presentation and never modifies the saved headword.
    review_entry_left_padding: int = 0
    # Extra vertical safety space inside each proofreading Entry. This is
    # presentation-only and helps tall accented/special glyphs avoid clipping.
    # The value is applied symmetrically to the top and bottom.
    review_entry_vertical_padding: int = 3
    # Review crop height for a one-character CJK headword, in the same
    # parameter-pixel convention as ``character_height``. 0 means automatic:
    # CJK index/profile defaults to 2.5× the shared single-line height.
    review_single_cjk_line_height: int = 0
    # Review crop height for ordinary (non-single-CJK) entries. 0 keeps the
    # automatic value: character_height + row_padding.
    review_regular_crop_height: int = 0
    # While the proofreading window is open, keep the main canvas visually
    # quiet by default. These switches let users restore either OCR aid.
    review_main_show_ocr_choices: bool = False
    review_main_show_ocr_background: bool = False
    # OCR source used for the review-editor mismatch outline. Supported values:
    # fusion / paddle / tesseract / lens. Missing engine output is neutral.
    review_ocr_compare_source: str = "fusion"
    # Show an editable Traditional-to-Simplified companion field beside each
    # proofreading editor. OpenCC provides the initial value; manual corrections
    # are saved per page. Unchanged automatic conversions display a check mark.
    review_show_simplified: bool = False
    # Review-window numeric shortcuts. Order is 1..9,0. Each entry is the
    # replacement string inserted when “数字转变音字母” is enabled.
    review_digit_map: list[str] = field(default_factory=lambda: list("áéíóúãçñõü"))
    # Auxiliary headword reference list used by the review window and main-view membership styling.
    # Relative paths are resolved from the project root; absolute paths are also supported.
    wordslist_path: str = "wordslist.txt"
    # How the review panel positions a page-less auxiliary index. ``auto`` uses
    # sorted-index lookup for CJK projects and the historical sequential-anchor
    # behaviour for Latin projects. ``sorted`` is intended for an index copied
    # from another dictionary, where missing/extra entries make row offsets
    # unreliable; ``sequential`` preserves the old same-source list behaviour.
    wordslist_locator_mode: str = "auto"
    # Free online lexical verification in the review panel. No AI/API token is
    # required: exact-title checks use public dictionary APIs in a background
    # thread, with an explicit browser search button as a manual fallback.
    review_network_lookup_enabled: bool = True
    ocr_engine: str = "tesseract"
    # Headword markers are detected with the restored left-edge rule or PaddleOCR.
    detection_method: str = "paddleocr"
    # v2.10 dictionary detection profile. Stable IDs describe layout families,
    # while project-specific numeric edits are persisted as overrides.
    dictionary_profile_id: str = "latin_structured_symbols"
    # Project-specific display name for the built-in stable "custom" headword
    # profile. The profile key remains "custom"; only the human-facing label is
    # renamed so saved parser/layout semantics stay compatible.
    dictionary_custom_profile_name: str = ""
    # Dictionary collation used by the headword-order checker. ``auto`` follows
    # the selected OCR language; custom mode accepts arbitrary alphabet units
    # (including multi-character letters such as ch / ll).
    headword_sort_mode: str = "auto"
    headword_custom_order: str = "a b c d e f g h i j k l m n o p q r s t u v w x y z"
    headword_custom_fold_accents: bool = True
    follow_column_deformation: bool = False
    # v2.12.12 resets the two layout-behavior checkboxes to safer opt-in defaults.
    layout_behavior_defaults_version: int = 1
    column_track_radius: int = 80
    column_track_block_height: int = 120
    column_track_max_step: int = 28
    # PaddleOCR is optional and is loaded only when the dedicated headword
    # detection mode is selected.
    paddle_language: str = ""
    paddle_device: str = "cpu"
    paddle_ocr_version: str = "PP-OCRv6"
    paddle_use_textline_orientation: bool = False
    # Wider than v1.4 so long syllabified lemmas usually include the nearby
    # plural/POS label, which is a much stronger entry cue than boldness alone.
    paddle_band_width: int = 600
    # Main-window simplification: percentage of the historical candidate band.
    # 100 means the original configured ``paddle_band_width``; values are capped at 100.
    paddle_band_width_ratio: int = 100
    # OCR-only guard/preprocessing; source pixels and canvas rendering are never replaced.
    paddle_max_input_side: int = 2800
    paddle_preprocessing: str = "original"
    paddle_band_left_margin: int = 12
    paddle_left_tolerance: int = 34
    paddle_rec_score_threshold: float = 0.20
    paddle_line_merge_y_ratio: float = 0.70
    paddle_height_ratio: float = 1.08
    paddle_boldness_ratio: float = 1.12
    paddle_gap_ratio: float = 0.7
    paddle_min_candidate_score: float = 1.0
    paddle_require_visual_cue: bool = True
    # For ordinary dictionary pages, a nearby POS label (or an explicit entry
    # symbol) is the safest way to reject indented definition lines.
    paddle_require_pos_or_symbol: bool = True
    paddle_remove_syllable_separators: bool = True
    paddle_auto_header_rule: bool = True
    paddle_header_search_height: int = 100
    paddle_header_rule_ink_ratio: float = 0.55
    paddle_header_rule_margin: int = 6
    paddle_pos_search_chars: int = 140
    # Refine the horizontal marker after OCR coarse localization.  The search
    # is limited to a small fraction of the recognized headword-line height
    # and chooses the centre of the local low-ink valley, so descenders from
    # the preceding line (g/j/p/q/y) are not cut by the marker.
    paddle_refine_separator_y: bool = True
    paddle_separator_search_ratio: float = 0.30
    paddle_separator_band_radius: int = 2
    # Downward-biased Y-refinement safety clearance. The value follows the
    # program's historical display-pixel convention and is converted to source
    # pixels at runtime. 0 allows the separator to touch the detected ink edge.
    paddle_separator_safety_px: int = 2
    # Width of the left-side local X ROI used by image-boundary/Y-refinement
    # analysis, expressed as a percentage of the current straightened column.
    # Keeping this local prevents long definition text at the right side of a
    # column from pulling the separator toward the preceding line.
    paddle_separator_roi_width_ratio: int = 60
    paddle_separator_column_margin: int = 8
    # Optional second OCR pass for diagnostics / conservative rescue.  It uses
    # the same straightened candidate band and the existing Tesseract language/path.
    paddle_use_paddleocr: bool = True
    paddle_compare_tesseract: bool = True
    paddle_tesseract_rescue: bool = False
    paddle_tesseract_psm: int = 6
    paddle_tesseract_auto_psm: bool = True
    # v2.0 dual-OCR fusion.  When enabled and Tesseract comparison is available,
    # candidates are sequence-aligned (lemma order) with Y as a geometric guard,
    # then arbitrated instead of treating Tesseract as only a rescue pass.
    paddle_dual_ocr_arbitration: bool = True
    paddle_alignment_y_tolerance_ratio: float = 0.85
    paddle_alignment_min_similarity: float = 0.55
    paddle_conflict_review_margin: float = 0.75
    # Google Lens is an optional network-backed third opinion. ``conflict``
    # invokes it only for columns where Paddle/Tesseract disagree or one engine
    # failed; ``diagnostic`` and ``full`` run it for every column, while only
    # ``full`` may influence otherwise non-conflicting decisions.
    paddle_enable_lens: bool = False
    paddle_lens_mode: str = "conflict"
    paddle_lens_language: str = "es"
    paddle_lens_timeout: int = 60
    paddle_lens_default_confidence: float = 0.82
    # Overlay one checkbox for every left-edge OCR row.  A rejected/missed row can
    # therefore be manually promoted into the final PDIC result without changing
    # parser rules. Selections are persisted in a per-page sidecar.
    paddle_show_candidate_checkboxes: bool = True
    # Page-level dual-OCR agreement thresholds used by list/status colouring.
    paddle_agreement_good: float = 0.95
    paddle_agreement_warn: float = 0.85
    # Unicode-letter regex supporting dictionary syllable separators while
    # preserving real hyphens/apostrophes in the normalized lemma.
    paddle_headword_regex: str = (
        r"^\s*[•◆◇►▶*†‡§¶]?\s*"
        # True interpuncts may have OCR whitespace around them. ASCII ./:/+ are
        # accepted as syllable separators only when directly adjacent to the
        # next letters, so ``mail. Pron.`` is not swallowed as one fake lemma.
        # Mixed runs such as '.-' / '+-' remain supported.
        r"(-?[^\W\d_]+(?:\s*[·•∙‧]\s*[^\W\d_]+|"
        r"[.:+]{1,3}[^\W\d_]+|[·•∙‧.:+]*-+[·•∙‧.:+]*[^\W\d_]+|"
        r"['’][^\W\d_]+)*-?)"
    )
    paddle_pos_regex: str = (
        # Dictionary POS labels observed across pp.55-70. Longer forms must
        # precede bare ``s.`` / ``pron.`` so the boundary check can distinguish
        # ``s.amb.`` and ``pron.indef.`` from truncated matches.
        r"(?:n\.?|s\.?\s*(?:m|f|com|n|amb)\.(?:\s*pl\.)?|s\.\s*pl\.|s\.|"
        r"adj\.?\s*(?:inv\.?)?|adv\.?|v\.(?:t\.|i\.|tr\.|intr\.|\s*prnl\.?)?|y\.(?:\s*prnl\.?)?|"
        r"prep\.?|conj\.?|pron\.?(?:\s*(?:indef|dem|pers|rel|interr|exclam|poses)\.?)?|"
        r"det\.?|interj\.?|art\.?|num\.?|loc\.?|"
        r"superlat\.?(?:\s*irreg\.?)?)"
    )
    paddle_special_symbol_regex: str = r"^\s*[•◆◇►▶*†‡§¶]"

    @property
    def row_height(self) -> int:
        return max(1, self.character_height + self.row_padding)

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path) -> "AppSettings":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if int(raw.get("right_ratio_percent_version", 0) or 0) < 1:
            old_divisor = max(0.01, float(raw.get("right_ratio", 1.0) or 1.0))
            raw["right_ratio"] = 100.0 / old_divisor
            raw["right_ratio_percent_version"] = 1
        # Transparently upgrade the untouched v1.4 default regex. Without this
        # migration, an existing project would keep matching only the first
        # syllable of display forms such as ``a·ga·rrón``. User-customized
        # regexes are left exactly as they are.
        legacy_headword_regex = r"^\s*[•◆◇■□►▶*†‡§¶]?\s*([^\W\d_]+(?:[-'’][^\W\d_]+)*)"
        if raw.get("paddle_headword_regex") == legacy_headword_regex:
            raw["paddle_headword_regex"] = cls().paddle_headword_regex
            # Also upgrade untouched v1.4 defaults that would otherwise crop
            # long ``lemma (plural) POS`` lines before the grammatical cue.
            if raw.get("paddle_band_width") == 180:
                raw["paddle_band_width"] = cls().paddle_band_width
            if raw.get("paddle_min_candidate_score") == 4.0:
                # Historical v1.4 migration keeps the v1.5 compatibility target.
                # Fresh v2.3 projects use the new UI/default value 1.0 instead.
                raw["paddle_min_candidate_score"] = 5.0
        # v1.5.x shipped conservative OCR defaults while the real dictionary
        # pages showed that longer headword/POS lines and syllabified bold text
        # benefit from a wider band, lower candidate confidence and looser same-line merge.
        # Upgrade only untouched defaults; explicit user tuning is preserved.
        old_v15_regex = (
            r"^\s*[•◆◇■□►▶*†‡§¶]?\s*"
            r"([^\W\d_]+(?:\s*[·•∙‧]\s*[^\W\d_]+|[.:][^\W\d_]+|[-'’][^\W\d_]+)*)"
        )
        if raw.get("paddle_headword_regex") == old_v15_regex:
            raw["paddle_headword_regex"] = cls().paddle_headword_regex
        old_v156_regex = (
            r"^\s*[•◆◇■□►▶*†‡§¶]?\s*"
            r"(-?[^\W\d_]+(?:\s*[·•∙‧]\s*[^\W\d_]+|[.:][^\W\d_]+|[-'’][^\W\d_]+)*)"
        )
        if raw.get("paddle_headword_regex") == old_v156_regex:
            raw["paddle_headword_regex"] = cls().paddle_headword_regex
        old_v158_headword_regex = (
            r"^\s*[•◆◇■□►▶*†‡§¶]?\s*"
            r"(-?[^\W\d_]+(?:\s*[·•∙‧.:+]{1,3}\s*[^\W\d_]+|"
            r"[·•∙‧.:+]*-+[·•∙‧.:+]*[^\W\d_]+|['’][^\W\d_]+)*-?)"
        )
        if raw.get("paddle_headword_regex") == old_v158_headword_regex:
            raw["paddle_headword_regex"] = cls().paddle_headword_regex
        if raw.get("paddle_band_width") == 420:
            raw["paddle_band_width"] = cls().paddle_band_width
        if raw.get("paddle_rec_score_threshold") == 0.45:
            raw["paddle_rec_score_threshold"] = cls().paddle_rec_score_threshold
        if raw.get("paddle_line_merge_y_ratio") == 0.55:
            raw["paddle_line_merge_y_ratio"] = cls().paddle_line_merge_y_ratio
        if raw.get("paddle_pos_search_chars") == 96:
            raw["paddle_pos_search_chars"] = cls().paddle_pos_search_chars
        # v1.5.5 did not recognize the dictionary's bare ``s.`` POS label, so
        # entries such as ``agregado, da s.`` and ``agricultor, to·ra s.``
        # could be rejected. Upgrade only the untouched shipped default.
        old_v155_pos_regex = (
            r"(?:s\.?\s*(?:m|f|com|n)\.?|adj\.?\s*(?:inv\.?)?|adv\.?|"
            r"[vy]\.(?:\s*prnl\.?)?|prep\.?|conj\.?|pron\.?|interj\.?|"
            r"art\.?|num\.?|loc\.?|superlat\.?(?:\s*irreg\.?)?)"
        )
        if raw.get("paddle_pos_regex") == old_v155_pos_regex:
            raw["paddle_pos_regex"] = cls().paddle_pos_regex
        # v1.5.8 still lacked ``s.amb.`` and extended pronoun labels such as
        # ``pron.indef.``. Upgrade only the untouched shipped default.
        old_v158_pos_regex = (
            r"(?:s\.?\s*(?:m|f|com|n)\.?|s\.|adj\.?\s*(?:inv\.?)?|adv\.?|"
            r"[vy]\.(?:\s*prnl\.?)?|prep\.?|conj\.?|pron\.?|interj\.?|"
            r"art\.?|num\.?|loc\.?|superlat\.?(?:\s*irreg\.?)?)"
        )
        if raw.get("paddle_pos_regex") == old_v158_pos_regex:
            raw["paddle_pos_regex"] = cls().paddle_pos_regex
        old_symbol_regex = r"^\s*[•◆◇■□►▶*†‡§¶]"
        if raw.get("paddle_special_symbol_regex") == old_symbol_regex:
            raw["paddle_special_symbol_regex"] = cls().paddle_special_symbol_regex
        if raw.get("detection_method") in {"projection", "hybrid"}:
            raw["detection_method"] = "left_edge"
        # v2.5 Spanish-only sort modes migrate to the generalized collation
        # profiles introduced in v2.6.
        if raw.get("headword_sort_mode") == "es_modern":
            raw["headword_sort_mode"] = "spa_modern"
        elif raw.get("headword_sort_mode") == "es_traditional":
            raw["headword_sort_mode"] = "spa_traditional"

        # v2.11.13 changed review typography from ``base size × review zoom``
        # to a fixed font size.  Some established projects therefore carry a
        # deliberately large old base size (for example 72 at 26% zoom gave an
        # actual ~19 pt editor).  Interpreting 72 as the new fixed size makes a
        # one-line Entry look enormous.  Migrate only clearly legacy-large
        # values; ordinary 18-24 pt fixed sizes from v2.11.13 are left intact.
        if int(raw.get("review_font_semantics_version", 1) or 1) < 2:
            try:
                old_size = max(6, int(raw.get("review_entry_font_size", cls().review_entry_font_size)))
                old_zoom = min(250, max(20, int(raw.get("review_zoom_percent", cls().review_zoom_percent))))
                if old_size > 36 and old_zoom < 100:
                    raw["review_entry_font_size"] = max(6, min(48, round(old_size * old_zoom / 100.0)))
            except (TypeError, ValueError):
                pass
            raw["review_font_semantics_version"] = 2

        # v2.12.9 split review typography into independent original-headword
        # and Simplified styles. Existing projects inherit their established
        # headword style on first load so the upgrade does not change display.
        if "review_simplified_font_family" not in raw:
            raw["review_simplified_font_family"] = str(
                raw.get("review_entry_font_family", cls().review_entry_font_family) or cls().review_entry_font_family
            )
        if "review_simplified_font_size" not in raw:
            raw["review_simplified_font_size"] = raw.get("review_entry_font_size", cls().review_entry_font_size)
        if "review_simplified_font_bold" not in raw:
            raw["review_simplified_font_bold"] = bool(raw.get("review_entry_font_bold", cls().review_entry_font_bold))
        if "review_simplified_font_italic" not in raw:
            raw["review_simplified_font_italic"] = bool(raw.get("review_entry_font_italic", cls().review_entry_font_italic))

        # v2.12.12: both layout-behavior options become opt-in.  Older projects
        # inherited ``follow_column_deformation=True`` by default and may also
        # have ``manual_columns`` persisted as checked.  Reset them once on the
        # first load after this upgrade; subsequent user choices are preserved.
        if int(raw.get("layout_behavior_defaults_version", 0) or 0) < 1:
            raw["manual_columns"] = False
            raw["follow_column_deformation"] = False
            raw["layout_behavior_defaults_version"] = 1

        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in raw.items() if key in known})

    @classmethod
    def from_legacy(cls, path: Path) -> "AppSettings":
        """Read the positional _Mysettings.ini format emitted by Form1.vb."""
        parts = path.read_text(encoding="utf-8-sig").split("@")
        settings = cls()
        converters = {
            2: ("columns", int),
            3: ("gutter", int),
            4: ("column_width", int),
            5: ("start_y", int),
            6: ("manual_y", int),
            7: ("manual_x", int),
            8: ("body_indent", int),
            9: ("character_height", int),
            10: ("row_padding", int),
            11: ("right_ratio", float),
            12: ("horizontal_tolerance", int),
            13: ("marker_height", int),
            14: ("guide_width", int),
            15: ("darkness_threshold", int),
            16: ("dark_area_percent", int),
            17: ("batch_interval", float),
        }
        for index, (name, cast) in converters.items():
            if len(parts) > index and parts[index].strip():
                try:
                    setattr(settings, name, cast(parts[index]))
                except ValueError:
                    pass
        if len(parts) > 18 and parts[18].strip().isdigit():
            # Old ComboBox used the language string, not a stable numeric enum.
            legacy_languages = ["eng", "spa", "ita", "fra", "por", "deu", "chi_sim", "chi_tra"]
            idx = int(parts[18])
            if 0 <= idx < len(legacy_languages):
                settings.ocr_language = legacy_languages[idx]
        settings.right_ratio = 100.0 / max(0.01, float(settings.right_ratio))
        return settings


@dataclass
class ProjectState:
    root: Path
    images: list[Path]
    settings: AppSettings
    words: list[str] = field(default_factory=list)

    @classmethod
    def open(cls, root: Path) -> "ProjectState":
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)

        images = sorted(
            (path for path in root.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
            key=lambda p: natural_text_key(p.name),
        )

        # Storage v2: a clean/new scan folder gets exactly one software-owned
        # child directory. Existing legacy projects remain readable until the GUI
        # explicitly migrates them, so opening a project never silently moves data.
        # Do not create anything in an empty/non-project folder selected by mistake.
        from .project_storage import (
            ensure_project_storage, has_legacy_project_data, is_managed_project,
            legacy_ini_path, profile_path as active_profile_path,
            qt_root, settings_path as active_settings_path,
        )
        if images and (is_managed_project(root) or not has_legacy_project_data(root)):
            try:
                from . import __version__
            except Exception:
                __version__ = "unknown"
            ensure_project_storage(root, __version__)
        json_settings = active_settings_path(root)
        legacy_settings = legacy_ini_path(root)
        if json_settings.exists():
            settings = AppSettings.from_json(json_settings)
        elif legacy_settings.exists():
            settings = AppSettings.from_legacy(legacy_settings)
        else:
            settings = AppSettings()
            # A v3 profile sidecar can bootstrap a project that predates
            # settings.json.  Never apply this over an existing modern/legacy
            # settings file: those remain authoritative.
            try:
                from .dictionary_profile import apply_project_profile_components
                apply_project_profile_components(active_profile_path(root), settings)
            except Exception:
                pass
        # settings.json is authoritative for mutable project state.  The profile
        # sidecar is only a compatibility fallback for projects that do not yet
        # have settings.json; it must never overwrite a user's newer selection.
        settings_has_profile = False
        if json_settings.exists():
            try:
                saved_settings = json.loads(json_settings.read_text(encoding="utf-8-sig"))
                settings_has_profile = bool(
                    isinstance(saved_settings, dict)
                    and str(saved_settings.get("dictionary_profile_id") or "").strip()
                )
            except (OSError, ValueError, TypeError):
                settings_has_profile = False
        if not settings_has_profile:
            try:
                from .dictionary_profile import project_profile_preset_id
                settings.dictionary_profile_id = project_profile_preset_id(
                    active_profile_path(root), getattr(settings, "dictionary_profile_id", "latin_structured_symbols")
                )
            except Exception:
                pass
        words_path = resolve_wordslist_path(root, settings.wordslist_path)
        words = read_noncomment_lines(words_path) if words_path.exists() else []
        active_qt = qt_root(root)
        (active_qt / "PaddleOCR").mkdir(parents=True, exist_ok=True)
        (active_qt / "PSW").mkdir(parents=True, exist_ok=True)
        (active_qt / "PWW").mkdir(parents=True, exist_ok=True)
        (active_qt / "PIC").mkdir(parents=True, exist_ok=True)
        (active_qt / "PicDic").mkdir(parents=True, exist_ok=True)
        return cls(root=root, images=images, settings=settings, words=words)


def resolved_tesseract_language(settings: AppSettings) -> str:
    """Use the engine-specific language pack, falling back for old projects."""
    return str(settings.tesseract_language or settings.ocr_language or "eng").strip()


def resolve_wordslist_path(root: Path, configured: str | Path | None) -> Path:
    """Resolve the configured auxiliary wordslist path for one project.

    ``wordslist.txt`` remains the portable default. Relative paths travel with
    the project; an explicitly chosen outside file is stored as an absolute path.
    """
    raw = str(configured or "wordslist.txt").strip() or "wordslist.txt"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def read_noncomment_lines(path: Path) -> list[str]:
    """Read one-word-per-line reference files without duplicating the whole file in memory.

    Large wordslist files can contain hundreds of thousands of entries.  Iterating the
    text stream avoids the temporary giant string + ``splitlines()`` copy created by
    ``Path.read_text`` and keeps project opening responsive and memory-predictable.
    """
    from .text_encoding import read_text_detected
    rows: list[str] = []
    text, _encoding = read_text_detected(path)
    for raw in text.splitlines():
        line = raw.strip()
        if line and not raw.lstrip().startswith("'"):
            rows.append(line)
    return rows
