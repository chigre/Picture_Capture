from __future__ import annotations

import codecs
from pathlib import Path

from charset_normalizer import from_bytes


_COMMON_CJK = frozenset(
    "的一是在不了有人我他这這中大来來上个個国國到说說们們为為子和你地出道也时時年得就那要"
    "下以生会會自着著去之过過家学學对對可她里裡后後小么麼心多天而能好都然没沒日于於起还還"
    "发發成事只作当當想看文无無开開手十用主行方又如前所本见見经經头頭面公同三已老从從动動"
    "两兩长長知民样樣现現分将將外但身些与與高意进進把法此实實回二理美点點月明其种種声聲全"
    "工己话話儿兒者向情部正名定女问問力机機给給等几幾很业業最间間新什打便位因重被走电電四"
    "第门門相次东東政海口使教西再平真听聽世气氣信北少关關并並内內数數化太目制合非型马馬色"
    "简簡体體词詞条條繁"
)


def _cjk_likelihood(text: str) -> int:
    common = sum(char in _COMMON_CJK for char in text)
    cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
    hangul = sum("\uac00" <= char <= "\ud7af" for char in text)
    return common * 5 + cjk - hangul * 8


def decode_text_bytes(data: bytes) -> tuple[str, str]:
    """Decode imported text using BOMs, Unicode validity, and legacy fallbacks."""
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16"), "utf-16"
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return data.decode("utf-32"), "utf-32"
    if data:
        even_nulls = data[0::2].count(0) / max(1, len(data[0::2]))
        odd_nulls = data[1::2].count(0) / max(1, len(data[1::2]))
        if max(even_nulls, odd_nulls) > 0.35:
            encoding = "utf-16-be" if even_nulls > odd_nulls else "utf-16-le"
            return data.decode(encoding), encoding
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    legacy_candidates: list[tuple[int, str, str]] = []
    for encoding in ("gb18030", "big5"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        legacy_candidates.append((_cjk_likelihood(text), text, encoding))
    if legacy_candidates:
        score, text, encoding = max(legacy_candidates, key=lambda item: item[0])
        if score > 0:
            return text, encoding
    match = from_bytes(data).best()
    if match is not None and match.encoding:
        return str(match), str(match.encoding).lower()
    return data.decode("cp1252"), "cp1252"


def read_text_detected(path: str | Path) -> tuple[str, str]:
    """Read a user-supplied text file and return ``(text, detected_encoding)``."""
    return decode_text_bytes(Path(path).read_bytes())


def detect_text_file_encoding(
    path: str | Path, *, sample_size: int = 512 * 1024,
) -> str:
    """Detect a text file encoding from a bounded prefix suitable for streaming reads.

    Incremental decoders use final=False so a multibyte character split at
    the sample boundary is not mistaken for an invalid encoding.
    """
    path = Path(path)
    with path.open("rb") as handle:
        data = handle.read(max(4096, int(sample_size)))

    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return "utf-32"
    if data:
        even_nulls = data[0::2].count(0) / max(1, len(data[0::2]))
        odd_nulls = data[1::2].count(0) / max(1, len(data[1::2]))
        if max(even_nulls, odd_nulls) > 0.35:
            return "utf-16-be" if even_nulls > odd_nulls else "utf-16-le"

    try:
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        decoder.decode(data, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        pass

    legacy_candidates: list[tuple[int, str]] = []
    for encoding in ("gb18030", "big5"):
        try:
            decoder = codecs.getincrementaldecoder(encoding)("strict")
            text = decoder.decode(data, final=False)
        except UnicodeDecodeError:
            continue
        legacy_candidates.append((_cjk_likelihood(text), encoding))
    if legacy_candidates:
        score, encoding = max(legacy_candidates, key=lambda item: item[0])
        if score > 0:
            return encoding

    match = from_bytes(data).best()
    if match is not None and match.encoding:
        return str(match.encoding).lower()
    return "cp1252"


def iter_text_lines_detected(path: str | Path):
    """Yield decoded lines without materializing the entire file in memory."""
    path = Path(path)
    encoding = detect_text_file_encoding(path)
    with path.open("r", encoding=encoding, newline=None) as handle:
        yield from handle
