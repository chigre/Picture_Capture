from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROFILE_FILENAME = "dictionary_profile.json"
PROFILE_FORMAT_V2 = "picture-capture-dictionary-profile-v2"
PROFILE_LIBRARY_FORMAT_V2 = "picture-capture-profile-library-v2"
PROFILE_FORMAT_V3 = "picture-capture-dictionary-profile-v3"
PROFILE_LIBRARY_FORMAT_V3 = "picture-capture-profile-library-v3"
DEFAULT_PROFILE_ID = "custom"


@dataclass(frozen=True, slots=True)
class ProfileExample:
    dictionary: str


@dataclass(frozen=True, slots=True)
class DictionaryProfilePreset:
    key: str
    display_name: str
    family: str
    description: str
    examples: tuple[ProfileExample, ...]
    supported_languages: tuple[str, ...]
    default_language: str
    default_paddle_language: str
    paddle_language_by_language: dict[str, str]
    parser_modes: tuple[str, ...]
    settings: dict[str, Any]
    layout: dict[str, Any]
    ocr: dict[str, Any]
    headword: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DictionaryProfile:
    """Resolved dictionary grammar + layout metadata for one OCR run.

    ``DictionaryProfile`` remains the lightweight object consumed by the OCR
    parser.  v2 adds a stable layout preset key and parser modes while keeping
    the v1 grammar fields intact for project compatibility.
    """

    name: str
    pos_labels: tuple[str, ...]
    usage_labels: tuple[str, ...]
    domain_labels: tuple[str, ...]
    relation_labels: tuple[str, ...]
    internal_leading_symbols: tuple[str, ...]
    entry_leading_symbols: tuple[str, ...]
    symbol_meanings: dict[str, str]
    key: str = DEFAULT_PROFILE_ID
    family: str = "latin_structured_symbols"
    parser_modes: tuple[str, ...] = ("latin",)
    description: str = ""
    examples: tuple[ProfileExample, ...] = ()
    headword_features: tuple[str, ...] = ()
    prefix_regex: str = ""
    prefix_required: bool = False

    @property
    def metadata_labels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.usage_labels + self.domain_labels))

    def pos_regex(self) -> str:
        # Longer labels must win over their prefixes (s.amb. before s.).
        alternatives = sorted(self.pos_labels, key=len, reverse=True)
        if not alternatives:
            # Never match when the active profile deliberately has no POS system.
            return r"(?!)"
        return r"(?:" + "|".join(_label_to_regex(value) for value in alternatives) + r")"

    def uses_parser(self, name: str) -> bool:
        return name in self.parser_modes


def _label_to_regex(value: str) -> str:
    pieces: list[str] = []
    for char in value.strip():
        if char.isspace():
            pieces.append(r"\s*")
        elif char == ".":
            pieces.append(r"\.?" )
        elif char == "/":
            pieces.append(r"\s*/\s*")
        else:
            pieces.append(re.escape(char))
    return "".join(pieces)


def _base_language(language: str | None) -> str:
    text = str(language or "").strip()
    if not text:
        return ""
    return next((part.strip() for part in text.split("+") if part.strip()), "")


def _values(block: dict[str, Any], name: str) -> tuple[str, ...]:
    return tuple(str(x).strip() for x in block.get(name, []) if str(x).strip())


def _grammar_profile_from_blocks(
    *,
    name: str,
    key: str,
    family: str,
    parser_modes: Iterable[str],
    description: str,
    examples: tuple[ProfileExample, ...],
    abbreviations: dict[str, Any],
    symbols: dict[str, Any],
    headword: dict[str, Any] | None = None,
) -> DictionaryProfile:
    headword = headword or {}
    return DictionaryProfile(
        name=name,
        pos_labels=_values(abbreviations, "part_of_speech"),
        usage_labels=_values(abbreviations, "usage_and_region"),
        domain_labels=_values(abbreviations, "subject_domains"),
        relation_labels=_values(abbreviations, "article_relations"),
        internal_leading_symbols=tuple(str(x) for x in symbols.get("internal_not_new_entry", [])),
        entry_leading_symbols=tuple(str(x) for x in symbols.get("entry_markers", [])),
        symbol_meanings={str(k): str(v) for k, v in (symbols.get("meanings", {}) or {}).items()},
        key=key,
        family=family,
        parser_modes=tuple(str(x) for x in parser_modes if str(x)),
        description=description,
        examples=examples,
        headword_features=tuple(str(x) for x in headword.get("features", []) if str(x)),
        prefix_regex=str(headword.get("prefix_regex") or ""),
        prefix_required=bool(headword.get("prefix_required", False)),
    )


def _profile_from_legacy_dict(raw: dict[str, Any]) -> DictionaryProfile:
    abbreviations = raw.get("abbreviations", {}) or {}
    symbols = raw.get("symbols", {}) or {}
    return _grammar_profile_from_blocks(
        name=str(raw.get("name") or "Custom dictionary profile"),
        key="legacy_custom",
        family="legacy_custom",
        parser_modes=("latin", "cjk_bracketed", "cjk_single_visual"),
        description=str(raw.get("source_note") or "Legacy v1 project profile"),
        examples=(),
        abbreviations=abbreviations,
        symbols=symbols,
        headword={},
    )


def bundled_profile_path() -> Path:
    """Compatibility path for the original v1 bundled grammar profile."""
    return Path(__file__).resolve().parent / "data" / "default_dictionary_profile.json"


def profile_library_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "dictionary_profiles_v3.json"


def _load_profile_library_raw() -> dict[str, Any]:
    path = profile_library_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"内置 Profile 库无法读取：{path}（{exc}）") from exc
    if not isinstance(raw, dict) or raw.get("format") != PROFILE_LIBRARY_FORMAT_V3:
        raise ValueError(f"内置 Profile 库格式无效：{path}")
    return raw


def available_dictionary_profiles() -> tuple[DictionaryProfilePreset, ...]:
    raw = _load_profile_library_raw()
    result: list[DictionaryProfilePreset] = []
    languages = raw.get("languages") or {}
    supported = tuple(str(key) for key in languages)
    paddle_by_language = {
        str(key): str(value.get("paddle_language") or "")
        for key, value in languages.items() if isinstance(value, dict)
    }
    for key, item in (raw.get("headword_profiles") or {}).items():
        if not isinstance(item, dict) or item.get("user_visible") is False:
            continue
        examples = tuple(
            ProfileExample(dictionary=str(name))
            for name in item.get("validated_examples", []) if str(name)
        )
        headword = dict(item)
        layout: dict[str, Any] = {}
        ocr: dict[str, Any] = {}
        settings = dict(headword.get("settings") or {})
        if "require_visual_cue" in headword:
            settings["paddle_require_visual_cue"] = bool(headword["require_visual_cue"])
        result.append(
            DictionaryProfilePreset(
                key=str(key),
                display_name=str(headword.get("display_name") or key),
                family=str(item.get("family") or key),
                description=str(item.get("description") or ""),
                examples=examples,
                supported_languages=supported,
                default_language="eng",
                default_paddle_language="en",
                paddle_language_by_language=paddle_by_language,
                parser_modes=tuple(str(x) for x in headword.get("parser_modes", ["latin"]) if str(x)),
                settings=settings,
                layout=layout,
                ocr=ocr,
                headword=headword,
                raw=item,
            )
        )
    return tuple(result)


def dictionary_profile_preset(key: str | None) -> DictionaryProfilePreset:
    wanted = str(key or DEFAULT_PROFILE_ID)
    profiles = available_dictionary_profiles()
    for profile in profiles:
        if profile.key == wanted:
            return profile
    raw = _load_profile_library_raw()
    alias = (raw.get("compatibility_aliases") or {}).get(wanted)
    if isinstance(alias, dict):
        base_key = str(alias.get("headword_profile") or DEFAULT_PROFILE_ID)
        base = next((profile for profile in profiles if profile.key == base_key), profiles[0])
        return _preset_for_configuration(wanted, base, alias, raw)
    for profile in profiles:
        if profile.key == DEFAULT_PROFILE_ID:
            return profile
    if not profiles:
        raise ValueError("内置 Profile 库为空")
    return profiles[0]


def _canonical_transform(writing_mode: str, text_direction: str) -> str:
    if writing_mode == "vertical-rl":
        return "rotate_ccw90"
    if writing_mode == "vertical-lr":
        return "rotate_cw90"
    return "mirror_x" if text_direction == "rtl" else "identity"


def _preset_for_configuration(
    key: str, base: DictionaryProfilePreset, config: dict[str, Any], library: dict[str, Any]
) -> DictionaryProfilePreset:
    layout = dict(config.get("layout") or {})
    writing = str(layout.get("writing_mode") or "horizontal-tb")
    direction = str(layout.get("text_direction") or "ltr")
    layout["canonical_transform"] = _canonical_transform(writing, direction)
    language_key = str(config.get("language") or "eng")
    language = dict((library.get("languages") or {}).get(language_key) or {})
    tesseract = str(language.get("tesseract_language") or language_key)
    psm = 6
    orientation = False
    if writing.startswith("vertical"):
        tesseract = str(language.get("vertical_tesseract_language") or tesseract)
        psm = int(language.get("vertical_tesseract_psm") or 5)
        orientation = bool(language.get("use_textline_orientation", False))
    ocr = {
        "semantic_language": str(language.get("semantic_language") or language_key),
        "paddle_language": str(language.get("paddle_language") or ""),
        "tesseract_language": tesseract,
        "tesseract_psm": psm,
        "use_textline_orientation": orientation,
    }
    headword = dict(base.headword)
    headword["features"] = list(config.get("headword_features") or [])
    overrides = config.get("headword_overrides") or {}
    internal = list(overrides.get("internal_labels") or []) if isinstance(overrides, dict) else []
    grammar_override = overrides.get("grammar") if isinstance(overrides, dict) else None
    if isinstance(grammar_override, dict):
        headword["grammar"] = dict(grammar_override)
    if internal:
        grammar = dict(headword.get("grammar") or {})
        grammar["internal_not_new_entry"] = internal + list(grammar.get("internal_not_new_entry") or [])
        headword["grammar"] = grammar
    settings = dict(base.settings)
    settings.update({
        "layout_writing_mode": writing,
        "layout_text_direction": direction,
        "layout_transform": layout["canonical_transform"],
        "columns": max(1, int(layout.get("columns") or 1)),
        "layout_columns_policy": str(layout.get("columns_policy") or "detect"),
        "layout_column_separator_mode": str(layout.get("column_separator") or "auto"),
        "analysis_threshold_mode": str(layout.get("analysis_threshold_mode") or "auto"),
        "ocr_language": ocr["semantic_language"],
        "paddle_language": ocr["paddle_language"],
        "tesseract_language": tesseract,
        "paddle_tesseract_psm": psm,
        "paddle_use_textline_orientation": orientation,
    })
    supported = tuple(str(x) for x in config.get("supported_languages", []) if str(x)) or (ocr["semantic_language"],)
    parser_modes = tuple(str(x) for x in config.get("parser_modes", []) if str(x)) or base.parser_modes
    headword["parser_modes"] = list(parser_modes)
    return DictionaryProfilePreset(
        key=key, display_name=base.display_name, family=base.family,
        description=base.description, examples=base.examples,
        supported_languages=supported,
        default_language=ocr["semantic_language"], default_paddle_language=ocr["paddle_language"],
        paddle_language_by_language=base.paddle_language_by_language,
        parser_modes=parser_modes, settings=settings, layout=layout, ocr=ocr,
        headword=headword, raw=config,
    )


def dictionary_profile_labels() -> dict[str, str]:
    """Return UI label -> stable preset key mapping in library order."""
    return {profile.display_name: profile.key for profile in available_dictionary_profiles()}


def profile_layout_summary(profile: DictionaryProfilePreset, layout_override: dict[str, Any] | None = None) -> str:
    """Return a compact, user-facing summary of v3 layout semantics."""
    layout = layout_override or profile.layout
    columns = max(1, int(layout.get("columns") or 1))
    writing = str(layout.get("writing_mode") or "horizontal-tb")
    direction = str(layout.get("text_direction") or "ltr").lower()
    transform = str(layout.get("canonical_transform") or "identity")
    separator = str(layout.get("column_separator") or "auto")
    if writing.startswith("vertical"):
        rotation = {"rotate_ccw90": "CCW90", "rotate_cw90": "CW90"}.get(transform, transform)
        return f"竖排 · {rotation} · {columns} canonical columns"
    transform_label = {
        "identity": "原向",
        "mirror_x": "镜像",
        "rotate_ccw90": "CCW90",
        "rotate_cw90": "CW90",
    }.get(transform, transform)
    separator_label = {"present": "中央分隔线", "absent": "无中央分隔线", "auto": "分隔线自动"}.get(
        separator, separator
    )
    return f"{columns}栏 · {direction.upper()} · {transform_label} · {separator_label}"


def managed_profile_setting_names() -> tuple[str, ...]:
    names: set[str] = {"ocr_language", "paddle_language"}
    for profile in available_dictionary_profiles():
        names.update(profile.settings)
    return tuple(sorted(names))


def profile_effective_settings(key: str | None, current_language: str | None = None) -> dict[str, Any]:
    """Resolve preset defaults for a project without hiding the language choice.

    If the current OCR language belongs to the preset's supported language
    family (e.g. ``ita`` for the shared Portuguese/Italian classic layout), it
    is retained.  Otherwise the preset's recommended language is selected.
    """
    profile = dictionary_profile_preset(key)
    settings = dict(profile.settings)
    current_base = _base_language(current_language)
    if current_base and current_base in profile.supported_languages:
        language = str(current_language)
    else:
        language = profile.default_language
    if language:
        settings["ocr_language"] = language
    base = _base_language(language)
    paddle_language = profile.paddle_language_by_language.get(base, profile.default_paddle_language)
    if paddle_language:
        settings["paddle_language"] = paddle_language
    settings.update(language_effective_settings(language, str(settings.get("layout_writing_mode") or "horizontal-tb")))
    return settings


def language_effective_settings(language: str, writing_mode: str = "horizontal-tb") -> dict[str, Any]:
    """Resolve OCR backends from language + orientation, independently of headword type."""
    raw = _load_profile_library_raw()
    key = _base_language(language)
    resource = dict((raw.get("languages") or {}).get(key) or {})
    if not resource:
        return {"ocr_language": language, "tesseract_language": language}
    vertical = writing_mode.startswith("vertical")
    return {
        "ocr_language": language or str(resource.get("semantic_language") or key),
        "paddle_language": str(resource.get("paddle_language") or ""),
        "tesseract_language": str(
            (resource.get("vertical_tesseract_language") if vertical else None)
            or resource.get("tesseract_language") or key
        ),
        "paddle_tesseract_psm": int(resource.get("vertical_tesseract_psm") or 5) if vertical else 6,
        "paddle_use_textline_orientation": bool(resource.get("use_textline_orientation", False)) if vertical else False,
    }


def _grammar_block_from_preset(profile: DictionaryProfilePreset, language: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    item = profile.headword
    base_language = _base_language(language)
    grammar = item.get("grammar") or {}
    by_language = item.get("grammar_by_language") or {}
    if base_language and isinstance(by_language, dict) and isinstance(by_language.get(base_language), dict):
        grammar = by_language[base_language]
    grammar = grammar if isinstance(grammar, dict) else {}
    abbreviations = {
        "part_of_speech": list(grammar.get("part_of_speech") or []),
        "usage_and_region": list(grammar.get("usage_and_region") or []),
        "subject_domains": list(grammar.get("subject_domains") or []),
        "article_relations": list(grammar.get("article_relations") or []),
    }
    symbols = {
        "internal_not_new_entry": list(grammar.get("internal_not_new_entry") or []),
        "entry_markers": list(grammar.get("entry_markers") or []),
        "meanings": dict(grammar.get("meanings") or {}),
    }
    return abbreviations, symbols


def _merge_list_override(original: list[Any], override: Any) -> list[Any]:
    if override is None:
        return original
    if isinstance(override, list):
        return override
    return original


def _apply_grammar_overrides(
    abbreviations: dict[str, Any], symbols: dict[str, Any], overrides: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    overrides = overrides or {}
    ab_override = overrides.get("abbreviations") if isinstance(overrides, dict) else None
    sym_override = overrides.get("symbols") if isinstance(overrides, dict) else None
    ab_override = ab_override if isinstance(ab_override, dict) else {}
    sym_override = sym_override if isinstance(sym_override, dict) else {}
    for name in ("part_of_speech", "usage_and_region", "subject_domains", "article_relations"):
        abbreviations[name] = _merge_list_override(list(abbreviations.get(name) or []), ab_override.get(name))
    for name in ("internal_not_new_entry", "entry_markers"):
        symbols[name] = _merge_list_override(list(symbols.get(name) or []), sym_override.get(name))
    if isinstance(sym_override.get("meanings"), dict):
        symbols["meanings"] = {**dict(symbols.get("meanings") or {}), **sym_override["meanings"]}
    return abbreviations, symbols


def load_dictionary_profile(
    path: Path | None = None,
    *,
    preset: str | None = None,
    language: str | None = None,
) -> DictionaryProfile:
    """Load a v3/v2 preset project or a legacy v1 grammar file.

    ``preset`` normally comes from ``AppSettings.dictionary_profile_id`` and is
    authoritative when supplied. A project sidecar is used as a migration
    fallback, or contributes synchronized overrides only when it names the same
    preset. A v1 project file remains supported when no preset is supplied.
    """
    raw: dict[str, Any] | None = None
    if path is not None and path.exists():
        try:
            candidate = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"词典配置无法读取：{path}（{exc}）") from exc
        if not isinstance(candidate, dict):
            raise ValueError(f"词典配置顶层必须是 JSON 对象：{path}")
        raw = candidate
        if candidate.get("format") not in {PROFILE_FORMAT_V2, PROFILE_FORMAT_V3} and not str(preset or "").strip():
            return _profile_from_legacy_dict(candidate)

    requested = str(preset or "").strip()
    compatibility_default = "latin_structured_symbols" if raw is None and not requested else DEFAULT_PROFILE_ID
    selected = requested or str((raw or {}).get("preset") or compatibility_default)
    profile = dictionary_profile_preset(selected)
    raw_matches = False
    if raw is not None and raw.get("format") in {PROFILE_FORMAT_V2, PROFILE_FORMAT_V3}:
        try:
            raw_matches = dictionary_profile_preset(str(raw.get("preset") or selected)).key == profile.key
        except (KeyError, ValueError):
            raw_matches = False
    effective_raw = raw if not requested or raw_matches else None
    selected_language = str(language or (effective_raw or {}).get("language") or profile.default_language)
    abbreviations, symbols = _grammar_block_from_preset(profile, selected_language)
    overrides = ((effective_raw or {}).get("overrides") or {}).get("grammar") if effective_raw else None
    abbreviations, symbols = _apply_grammar_overrides(abbreviations, symbols, overrides)
    return _grammar_profile_from_blocks(
        name=profile.display_name,
        key=profile.key,
        family=profile.family,
        parser_modes=profile.parser_modes,
        description=profile.description,
        examples=profile.examples,
        abbreviations=abbreviations,
        symbols=symbols,
        headword=profile.headword,
    )


def project_profile_preset_id(path: Path | None, fallback: str = DEFAULT_PROFILE_ID) -> str:
    if path is None or not path.exists():
        return fallback
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return fallback
    if not isinstance(raw, dict) or raw.get("format") not in {PROFILE_FORMAT_V2, PROFILE_FORMAT_V3}:
        return fallback
    key = str(raw.get("preset") or fallback)
    library = _load_profile_library_raw()
    alias = (library.get("compatibility_aliases") or {}).get(key)
    if isinstance(alias, dict):
        return str(alias.get("headword_profile") or DEFAULT_PROFILE_ID)
    return dictionary_profile_preset(key).key


def effective_project_profile_id(settings: Any, path: Path | None = None) -> str:
    """Resolve a current profile with mutable settings taking precedence."""
    configured = str(getattr(settings, "dictionary_profile_id", "") or "").strip()
    if configured:
        return dictionary_profile_preset(configured).key
    return project_profile_preset_id(path, DEFAULT_PROFILE_ID)


def apply_project_profile_components(path: Path | None, settings: Any) -> None:
    """Apply explicit v3 component selections; legacy profiles remain read-only."""
    if path is None or not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return
    if not isinstance(raw, dict) or raw.get("format") != PROFILE_FORMAT_V3:
        return
    layout = raw.get("layout") or {}
    ocr = raw.get("ocr") or {}
    mapping = {
        "layout_writing_mode": layout.get("writing_mode"),
        "layout_text_direction": layout.get("text_direction"),
        "columns": layout.get("columns"),
        "layout_columns_policy": layout.get("columns_policy"),
        "layout_column_separator_mode": layout.get("column_separator"),
        "analysis_threshold_mode": layout.get("analysis_threshold_mode"),
        "ocr_language": ocr.get("semantic_language"),
        "paddle_language": ocr.get("paddle_language"),
        "tesseract_language": ocr.get("tesseract_language"),
        "paddle_use_textline_orientation": ocr.get("use_textline_orientation"),
    }
    writing = str(mapping["layout_writing_mode"] or getattr(settings, "layout_writing_mode", "horizontal-tb"))
    direction = str(mapping["layout_text_direction"] or getattr(settings, "layout_text_direction", "ltr"))
    mapping["layout_transform"] = _canonical_transform(writing, direction)
    for name, value in mapping.items():
        if value is not None and hasattr(settings, name):
            setattr(settings, name, value)


def profile_settings_overrides(settings: Any, key: str | None) -> dict[str, Any]:
    current_language = str(getattr(settings, "ocr_language", "") or "")
    defaults = profile_effective_settings(key, current_language=current_language)
    overrides: dict[str, Any] = {}
    for name in managed_profile_setting_names():
        if not hasattr(settings, name) or name not in defaults:
            continue
        actual = getattr(settings, name)
        if actual != defaults[name]:
            overrides[name] = actual
    return overrides


def write_project_profile(
    path: Path, settings: Any, key: str | None = None, *, force: bool = False,
) -> None:
    requested = key or getattr(settings, "dictionary_profile_id", DEFAULT_PROFILE_ID)
    selected_profile = dictionary_profile_preset(requested)
    library = _load_profile_library_raw()
    selected = selected_profile.family if selected_profile.family in (library.get("headword_profiles") or {}) else selected_profile.key
    if path.exists() and not force:
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            existing = None
        # Old v1 and v2 profiles are read-only compatibility inputs. Merely
        # opening/saving a project must not silently migrate or rewrite them;
        # an explicit Profile selection (force=True) creates v3 instead.
        if isinstance(existing, dict) and existing.get("format") != PROFILE_FORMAT_V3:
            return
    payload = {
        "format": PROFILE_FORMAT_V3,
        "schema_version": 3,
        "preset": selected,
        "language": str(getattr(settings, "ocr_language", "") or ""),
        "layout": {
            "writing_mode": str(getattr(settings, "layout_writing_mode", "horizontal-tb")),
            "text_direction": str(getattr(settings, "layout_text_direction", "ltr")),
            "columns": int(getattr(settings, "columns", 1)),
            "columns_policy": str(getattr(settings, "layout_columns_policy", "detect")),
            "column_separator": str(getattr(settings, "layout_column_separator_mode", "auto")),
            "analysis_threshold_mode": str(getattr(settings, "analysis_threshold_mode", "auto")),
        },
        "ocr": {
            "semantic_language": str(getattr(settings, "ocr_language", "")),
            "paddle_language": str(getattr(settings, "paddle_language", "")),
            "tesseract_language": str(getattr(settings, "tesseract_language", "")),
            "use_textline_orientation": bool(getattr(settings, "paddle_use_textline_orientation", False)),
        },
        "headword": selected_profile.headword,
        "overrides": {
            "settings": profile_settings_overrides(settings, selected),
            "grammar": {},
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def starts_with_internal_article_symbol(text: str, profile: DictionaryProfile) -> str:
    stripped = text.lstrip()
    for symbol in sorted(profile.internal_leading_symbols, key=len, reverse=True):
        if stripped.startswith(symbol):
            return symbol
    return ""


def leading_relation_label(text: str, profile: DictionaryProfile) -> str:
    stripped = text.lstrip()
    for label in sorted(profile.relation_labels, key=len, reverse=True):
        pattern = _label_to_regex(label)
        if re.match(pattern + r"(?=\s|\[|→|$)", stripped, flags=re.IGNORECASE | re.UNICODE):
            return label
    return ""
