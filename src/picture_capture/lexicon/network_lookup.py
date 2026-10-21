from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .reference_index import contains_cjk
from .cc_cedict import DOWNLOAD_PAGE_URL as CC_CEDICT_DOWNLOAD_PAGE_URL, lookup as lookup_cc_cedict


USER_AGENT = "PictureCapture/2.13.2 dictionary-proofreading"
MAX_JSON_RESPONSE_BYTES = 1024 * 1024
# Shared bounded workers avoid creating/shutting down a pool for each query.
_LOOKUP_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="lexical-lookup")


@dataclass(frozen=True)
class LookupSourceResult:
    name: str
    found: bool | None
    url: str
    detail: str = ""


@dataclass(frozen=True)
class LexicalLookupResult:
    word: str
    sources: tuple[LookupSourceResult, ...]

    @property
    def found(self) -> bool | None:
        if any(item.found is True for item in self.sources):
            return True
        known = [item.found for item in self.sources if item.found is not None]
        if known and all(item is False for item in known):
            return False
        return None


def _read_json(url: str, timeout: float) -> object:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=max(1.0, float(timeout))) as response:
        payload = response.read(MAX_JSON_RESPONSE_BYTES + 1)
        if len(payload) > MAX_JSON_RESPONSE_BYTES:
            raise ValueError("Network dictionary response exceeds 1 MiB limit")
        return json.loads(payload.decode("utf-8"))




def _lookup_cc_cedict(word: str, timeout: float) -> LookupSourceResult:
    del timeout
    result = lookup_cc_cedict(word)
    return LookupSourceResult("CC-CEDICT", result.found, CC_CEDICT_DOWNLOAD_PAGE_URL, result.detail)

def _lookup_moedict(word: str, timeout: float) -> LookupSourceResult:
    encoded = quote(word, safe="")
    page_url = f"https://www.moedict.tw/{encoded}"
    api_url = f"https://www.moedict.tw/a/{encoded}.json"
    try:
        payload = _read_json(api_url, timeout)
        title = str(payload.get("title", "")) if isinstance(payload, dict) else ""
        found = bool(title and title.strip() == word.strip())
        # Some entries use a Unicode-normalized title; a nonempty object is also
        # useful exact-endpoint evidence even when title formatting differs.
        if isinstance(payload, dict) and payload and not title:
            found = True
        return LookupSourceResult("萌典", found, page_url, "华语开放辞典")
    except HTTPError as exc:
        if exc.code == 404:
            return LookupSourceResult("萌典", False, page_url, "未收录")
        return LookupSourceResult("萌典", None, page_url, f"HTTP {exc.code}")
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return LookupSourceResult("萌典", None, page_url, str(exc))


def _lookup_wiktionary(word: str, timeout: float) -> LookupSourceResult:
    host = "zh.wiktionary.org" if contains_cjk(word) else "en.wiktionary.org"
    page_url = f"https://{host}/wiki/{quote(word.replace(' ', '_'), safe='')}"
    params = urlencode({
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
        "titles": word,
    })
    api_url = f"https://{host}/w/api.php?{params}"
    try:
        payload = _read_json(api_url, timeout)
        pages = payload.get("query", {}).get("pages", []) if isinstance(payload, dict) else []
        page = pages[0] if pages else {}
        found = bool(page) and "missing" not in page and "invalid" not in page
        return LookupSourceResult("维基词典", found, page_url, "精确词条页")
    except HTTPError as exc:
        return LookupSourceResult("维基词典", None, page_url, f"HTTP {exc.code}")
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return LookupSourceResult("维基词典", None, page_url, str(exc))


def lookup_word_free(word: str, timeout: float = 4.0) -> LexicalLookupResult:
    """Check free public lexical sources without an API token.

    This is intentionally an evidence check, not an assertion that an unknown
    word is invalid. Chinese text checks local CC-CEDICT first, then Moedict
    and Chinese Wiktionary; other scripts use Wiktionary only.
    """
    value = str(word or "").strip()
    if not value:
        return LexicalLookupResult("", tuple())
    jobs: list[Callable[[], LookupSourceResult]] = []
    if contains_cjk(value):
        jobs.append(lambda: _lookup_cc_cedict(value, timeout))
        jobs.append(lambda: _lookup_moedict(value, timeout))
    jobs.append(lambda: _lookup_wiktionary(value, timeout))
    futures = [_LOOKUP_EXECUTOR.submit(job) for job in jobs]
    sources = tuple(future.result() for future in futures)
    return LexicalLookupResult(value, sources)


def web_search_url(word: str) -> str:
    """Return a free manual exact-phrase search URL for the system browser."""
    query = f'"{str(word or "").strip()}"'
    return "https://duckduckgo.com/?" + urlencode({"q": query})
