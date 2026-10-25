"""Profile Wizard catalog and canonical CJK visual-symbol role policy.

The UI facade passes its current symbol parser and role set at call time so
legacy monkeypatch seams remain observable without owning the policy body.
"""
from __future__ import annotations

OCR_LANGUAGE_LABEL_TO_VALUE = {
    "英语 (eng)": "eng",
    "中文简体 (chi_sim)": "chi_sim",
    "中文繁体 (chi_tra)": "chi_tra",
    "日语 (jpn)": "jpn",
    "法语 (fra)": "fra",
    "德语 (deu)": "deu",
    "西班牙语 (spa)": "spa",
    "意大利语 (ita)": "ita",
    "葡萄牙语 (por)": "por",
    "阿拉伯语 (ara)": "ara",
    "荷兰语 (nld)": "nld",
    "波兰语 (pol)": "pol",
    "土耳其语 (tur)": "tur",
    "越南语 (vie)": "vie",
    "捷克语 (ces)": "ces",
    "丹麦语 (dan)": "dan",
    "挪威语 (nor)": "nor",
    "瑞典语 (swe)": "swe",
    "芬兰语 (fin)": "fin",
    "罗马尼亚语 (ron)": "ron",
    "匈牙利语 (hun)": "hun",
    "印度尼西亚语 (ind)": "ind",
    "马来语 (msa)": "msa",
    "克罗地亚语 (hrv)": "hrv",
    "斯洛伐克语 (slk)": "slk",
    "斯洛文尼亚语 (slv)": "slv",
    "加泰罗尼亚语 (cat)": "cat",
    "巴斯克语 (eus)": "eus",
    "加利西亚语 (glg)": "glg",
    "拉丁语 (lat)": "lat",
}

OCR_TO_INDEX_LANGUAGE = {
    "eng": "en", "chi_sim": "zh", "chi_tra": "zh", "jpn": "ja",
    "fra": "fr", "deu": "de", "spa": "es", "ita": "it", "por": "pt",
    "ara": "ar", "nld": "nl", "pol": "pl", "tur": "tr", "vie": "vi",
    "ces": "cs", "dan": "da", "nor": "no", "swe": "sv", "fin": "fi",
    "ron": "ro", "hun": "hu", "ind": "id", "msa": "ms", "hrv": "hr",
    "slk": "sk", "slv": "sl", "cat": "ca", "eus": "eu", "glg": "gl",
    "lat": "la",
}

HEADWORD_HELP_LINES = {
    "latin_regular": (
        "识别对象：词头位于正文栏起始边，通常为明显粗体拉丁词，并常紧跟词性/语法标记。",
        "主要依据：严格栏左缘 + 词性/词后结构优先；若小号斜体词性被 OCR 漏掉或错认，可由明显粗体词形保守补救，普通定义续行仍排除。",
    ),
    "cjk_visual": (
        "识别对象：默认同时识别“大字单字”和“【括号词头】”。两者是两套独立证据：大字靠字号/版式，括号词靠括号结构。",
        "重要：【是括号起始 bracket_open，不是 ○ / ● / ◆ 那种独立入口标记 entry_marker。只有词典真的用独立符号开头时，才勾选“固定符号开头”。",
        "OCR 已能读出【时直接按括号结构解析；视觉样本只用于 OCR 漏掉/错认括号时补救，并建议保持 marker lane 过滤开启。",
    ),
    "numbered_prefix": (
        "识别对象：词头前有稳定数字编号，例如“1. word”“00［词头］”。",
        "主要依据：编号前缀是强词头提示。",
    ),
    "marker_prefixed": (
        "识别对象：词头前有稳定符号，例如 ○、●、◆。",
        "主要依据：符号前缀是强词头提示。",
    ),
    "custom": (
        "识别对象：无法由以上四类稳定描述的特殊版式。",
        "主要依据：沿用当前项目的高级识别参数与自定义规则。",
    ),
}


HEADWORD_EXAMPLE_FILES = {
    "latin_regular": "headword_example_1.png",
    "cjk_visual": "headword_example_2.png",
    "numbered_prefix": "headword_example_3.png",
    "marker_prefixed": "headword_example_4.png",
}


SEPARATOR_LABEL_TO_VALUE = {
    "自动判断": "auto",
    "有中央分隔线": "present",
    "无中央分隔线": "absent",
}
HEADER_LABEL_TO_VALUE = {
    "自动检测页眉": "auto",
    "没有页眉": "none",
    "有页眉，排除固定区域": "present",
}
FOOTER_LABEL_TO_VALUE = {
    "自动检测页尾": "auto",
    "不排除页尾": "none",
    "有页尾，排除固定区域": "present",
}
SIDE_LABEL_TO_VALUE = {
    "无页边占位内容": "none",
    "左侧固定": "left",
    "右侧固定": "right",
    "A/B 页外侧交替": "outer",
    "A/B 页内侧交替": "inner",
}

VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE = {
    "字符符号集 + 视觉样本": "combined",
    "仅字符符号集": "off",
    "视觉样本优先": "template_first",
}
VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE = {
    "按角色合并（推荐）": "role",
    "按具体符号区分": "literal",
}
BRACKET_ROLE_SYMBOLS = frozenset("【〔［[「『〈《")


def _normalize_cjk_visual_symbol_roles(
    entry_text: str,
    bracket_text: str,
    samples: list[dict] | None = None,
    *,
    split_symbols,
    bracket_role_symbols: frozenset[str],
) -> tuple[str, str, list[dict]]:
    """Keep bracket openers out of the standalone entry-marker role."""
    entry = list(split_symbols(entry_text))
    bracket = list(split_symbols(bracket_text))
    bracket_set = set(bracket)
    moved = [
        symbol for symbol in entry
        if symbol in bracket_role_symbols or symbol in bracket_set
    ]
    entry = [symbol for symbol in entry if symbol not in moved]
    bracket = list(dict.fromkeys([*bracket, *moved]))
    bracket_set = set(bracket)
    normalized_samples: list[dict] = []
    for sample in samples or []:
        item = dict(sample)
        literal = str(item.get("literal") or "")
        if (
            str(item.get("role") or "") == "entry_marker"
            and literal
            and literal in bracket_set
        ):
            item["role"] = "bracket_open"
        normalized_samples.append(item)
    return " ".join(entry), " ".join(bracket), normalized_samples


def _visual_marker_capture_defaults(
    *,
    marker_prefix_enabled: bool,
    bracket_enabled: bool,
    entry_text: str,
    bracket_text: str,
    split_symbols,
) -> tuple[str, str]:
    """Choose the semantically correct initial sample role in the capture UI."""
    entry = split_symbols(entry_text)
    bracket = split_symbols(bracket_text)
    if marker_prefix_enabled and entry:
        return "entry_marker", entry[0]
    if bracket_enabled and bracket:
        return "bracket_open", bracket[0]
    if entry:
        return "entry_marker", entry[0]
    if bracket:
        return "bracket_open", bracket[0]
    return ("bracket_open", "") if bracket_enabled else ("entry_marker", "")




def label_for_value(mapping: dict[str, str], value: str, fallback: str) -> str:
    """Resolve the first label matching a stored Profile value."""
    for label, mapped in mapping.items():
        if mapped == value:
            return label
    return fallback


def ocr_language_code(value: str, *, label_to_value: dict[str, str] | None = None) -> str:
    """Resolve a wizard OCR-language label while preserving raw engine codes."""
    text = str(value or "").strip()
    labels = OCR_LANGUAGE_LABEL_TO_VALUE if label_to_value is None else label_to_value
    return labels.get(text, text or "eng")
