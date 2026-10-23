"""Physical owner of lookup review callbacks.

ReviewWindow owns original public Tk signatures and passes current collaborators.
This module never imports app.py or changes the stored project formats.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from ..lexicon.network_lookup import LexicalLookupResult


@dataclass(frozen=True)
class ReviewLookupDeps:
    """Live collaborators resolved afresh by the GUI shell."""
    tk: object
    messagebox: object
    webbrowser: object
    filedialog: object
    CC_CEDICT_DOWNLOAD_PAGE_URL: object
    cc_cedict_status: object
    contains_cjk: object
    install_cc_cedict_from_file: object
    cc_cedict_simplified_candidates: object
    simplify_text: object
    lookup_word_free: object
    threading: object
    queue: object
    web_search_url: object

def _refresh_cc_cedict_button_idle(self, deps: ReviewLookupDeps) -> None:
    cc_cedict_status = deps.cc_cedict_status
    try:
        state = cc_cedict_status()
    except Exception:
        state = None
    if state is not None and state.installed:
        self.cc_cedict_lookup_var.set("CC-CEDICT(?)")
        self.cc_simplified_compare_var.set("CC简(?)")
    else:
        self.cc_cedict_lookup_var.set("CC-CEDICT(未装)")
        self.cc_simplified_compare_var.set("CC简(未装)")


def _set_lookup_source_states(self, deps: ReviewLookupDeps, *, pending: bool = False, empty: bool = False) -> None:
    """Reset the compact source badges shown in the review toolbar."""
    cc_cedict_status = deps.cc_cedict_status
    contains_cjk = deps.contains_cjk
    cjk = contains_cjk(self._network_lookup_word)
    try:
        cedict_installed = cc_cedict_status().installed
    except Exception:
        cedict_installed = False
    if empty:
        self.cc_cedict_lookup_var.set("CC-CEDICT(未装)" if not cedict_installed else "CC-CEDICT(?)")
        self.moedict_lookup_var.set("萌(?)")
        self.wiktionary_lookup_var.set("Wiki(?)")
        return
    if pending:
        if cjk:
            self.cc_cedict_lookup_var.set("CC-CEDICT(…)" if cedict_installed else "CC-CEDICT(未装)")
            self.moedict_lookup_var.set("萌(…)")
        else:
            self.cc_cedict_lookup_var.set("CC-CEDICT(—)")
            self.moedict_lookup_var.set("萌(—)")
        self.wiktionary_lookup_var.set("Wiki(…)")


def manage_cc_cedict(self, deps: ReviewLookupDeps) -> None:
    """Install/update a user-downloaded CC-CEDICT archive.

    MDBG's website disallows scripted access, so Picture Capture never
    scrapes or silently downloads it. The user downloads the official
    archive in a browser, then selects that local file here.
    """
    messagebox = deps.messagebox
    webbrowser = deps.webbrowser
    filedialog = deps.filedialog
    CC_CEDICT_DOWNLOAD_PAGE_URL = deps.CC_CEDICT_DOWNLOAD_PAGE_URL
    cc_cedict_status = deps.cc_cedict_status
    install_cc_cedict_from_file = deps.install_cc_cedict_from_file
    try:
        state = cc_cedict_status()
    except Exception:
        state = None
    installed_text = ""
    if state is not None and state.installed:
        installed_text = f"\n\n当前已安装：{state.entry_count:,} 条\n{state.path}"
    choose_local = messagebox.askyesno(
        "CC-CEDICT 安装 / 更新",
        "是否已经从 CC-CEDICT 官方下载页取得数据文件？\n\n"
        "【是】选择本地 ZIP / GZ / TXT / U8 文件并安装\n"
        "【否】打开官方下载页" + installed_text,
        parent=self,
    )
    if not choose_local:
        try:
            webbrowser.open(CC_CEDICT_DOWNLOAD_PAGE_URL)
        except Exception as exc:
            messagebox.showerror("无法打开下载页", str(exc), parent=self)
        return
    source = filedialog.askopenfilename(
        parent=self,
        title="选择已下载的 CC-CEDICT 数据文件",
        filetypes=[
            ("CC-CEDICT 数据", "*.zip *.gz *.txt *.u8"),
            ("ZIP", "*.zip"),
            ("GZip", "*.gz"),
            ("文本", "*.txt *.u8"),
            ("所有文件", "*.*"),
        ],
    )
    if not source:
        return
    try:
        installed = install_cc_cedict_from_file(source)
    except Exception as exc:
        messagebox.showerror("CC-CEDICT 安装失败", str(exc), parent=self)
        return
    self._network_lookup_cache.clear()
    self.cc_cedict_lookup_var.set("CC-CEDICT(?)")
    self.cc_simplified_compare_var.set("CC简(?)")
    messagebox.showinfo(
        "CC-CEDICT 已安装",
        f"已安装 {installed.entry_count:,} 条。\n\n位置：\n{installed.path}\n\n"
        "该词典为所有 Picture Capture 项目共用，无需每个项目重复安装。",
        parent=self,
    )
    if self._active_review_word():
        self._refresh_cc_simplified_comparison(self.active_index)
        self._schedule_network_lookup(force=True)


def _cc_simplified_comparison_details(self, deps: ReviewLookupDeps, index: int | None = None) -> dict[str, object]:
    """Compare OpenCC output with CC-CEDICT's Simplified field.

    CC-CEDICT is evidence, not an authoritative converter: a missing entry
    is reported as missing rather than treated as an OpenCC error.
    """
    contains_cjk = deps.contains_cjk
    cc_cedict_simplified_candidates = deps.cc_cedict_simplified_candidates
    simplify_text = deps.simplify_text
    i = self.active_index if index is None else int(index)
    if not (0 <= i < len(self.vars)):
        return {"state": "empty", "original": "", "opencc": "", "current": "", "candidates": tuple()}
    original = self.vars[i].get().strip()
    if not original or not contains_cjk(original):
        return {"state": "na", "original": original, "opencc": "", "current": "", "candidates": tuple()}
    mapping = cc_cedict_simplified_candidates(original)
    opencc_value = simplify_text(original)
    current_value = self._simplified_query_for_index(i) if i < len(self.simplified_vars) else (opencc_value or "")
    candidates = tuple(mapping.candidates)
    if mapping.found is None:
        state = "uninstalled" if "未安装" in (mapping.detail or "") else "unavailable"
    elif not candidates:
        state = "missing"
    elif opencc_value is None:
        state = "opencc_unavailable"
    elif opencc_value in candidates:
        state = "match"
    else:
        state = "mismatch"
    return {
        "state": state, "original": original, "opencc": opencc_value or "",
        "current": current_value or "", "candidates": candidates,
        "matched_as": mapping.matched_as, "detail": mapping.detail,
    }


def _refresh_cc_simplified_comparison(self, deps: ReviewLookupDeps, index: int | None = None) -> None:
    try:
        info = self._cc_simplified_comparison_details(index)
    except Exception:
        self.cc_simplified_compare_var.set("CC简(?)")
        return
    state = str(info.get("state", ""))
    candidates = tuple(info.get("candidates", ()))
    if state == "match":
        text = "CC简(√)"
    elif state == "mismatch":
        if len(candidates) == 1:
            candidate = str(candidates[0])
            text = f"CC简:{candidate}"
            if len(text) > 14:
                text = "CC简(1候选)"
        else:
            text = f"CC简({len(candidates)}候选)"
    elif state == "missing":
        text = "CC简(×)"
    elif state == "uninstalled":
        text = "CC简(未装)"
    elif state == "na":
        text = "CC简(—)"
    else:
        text = "CC简(?)"
    self.cc_simplified_compare_var.set(text)


def show_cc_simplified_comparison(self, deps: ReviewLookupDeps) -> None:
    messagebox = deps.messagebox
    try:
        info = self._cc_simplified_comparison_details(self.active_index)
    except Exception as exc:
        messagebox.showerror("CC-CEDICT 简体比较", str(exc), parent=self)
        return
    state = str(info.get("state", ""))
    if state == "uninstalled":
        self.manage_cc_cedict()
        return
    original = str(info.get("original", ""))
    opencc_value = str(info.get("opencc", "")) or "（不可用）"
    current_value = str(info.get("current", "")) or "（空）"
    candidates = tuple(str(v) for v in info.get("candidates", ()))
    candidate_text = "、".join(candidates) if candidates else "（未找到繁→简映射）"
    if state == "match":
        verdict = "OpenCC 与 CC-CEDICT 的简体词形一致。"
    elif state == "mismatch":
        verdict = "OpenCC 与 CC-CEDICT 的简体词形不一致，建议人工复核。"
    elif state == "missing":
        verdict = "CC-CEDICT 未提供该词的繁→简映射；这不代表 OpenCC 转换错误。"
    elif state == "na":
        verdict = "当前词条不适用中文繁简比较。"
    else:
        verdict = "暂时无法完成 CC-CEDICT 与 OpenCC 比较。"
    current_note = ""
    if candidates and current_value not in {"（空）", "（不可用）"}:
        current_note = (
            "\n当前简体与 CC-CEDICT：" +
            ("一致" if current_value in candidates else "不一致")
        )
    messagebox.showinfo(
        "CC-CEDICT 简体比较",
        f"原词条：{original}\nOpenCC：{opencc_value}\n当前简体：{current_value}\n"
        f"CC-CEDICT 简体：{candidate_text}\n\n{verdict}{current_note}",
        parent=self,
    )


def open_lookup_source(self, deps: ReviewLookupDeps, name: str) -> None:
    messagebox = deps.messagebox
    webbrowser = deps.webbrowser
    url = self._network_source_urls.get(name, "")
    if not url:
        if self._active_review_word():
            self._schedule_network_lookup(force=True)
        return
    try:
        webbrowser.open(url)
    except Exception as exc:
        messagebox.showerror("无法打开词典页面", str(exc), parent=self)


def _toggle_network_lookup(self, deps: ReviewLookupDeps) -> None:
    tk = deps.tk
    enabled = bool(self.network_lookup_enabled_var.get())
    self.parent.settings.review_network_lookup_enabled = enabled
    self.parent.save_settings()
    if enabled:
        self._schedule_network_lookup(force=True)
    else:
        self._network_lookup_serial += 1
        if self._network_lookup_job is not None:
            try:
                self.after_cancel(self._network_lookup_job)
            except tk.TclError:
                pass
            self._network_lookup_job = None
        self.network_lookup_status_var.set("网络词汇核验：自动检查已关闭")
        try:
            self.network_status_label.configure(fg="#666666")
        except tk.TclError:
            pass
        self._set_lookup_source_states(empty=True)


def _active_review_word(self, deps: ReviewLookupDeps) -> str:
    if 0 <= self.active_index < len(self.vars):
        return self.vars[self.active_index].get().strip()
    return ""


def _schedule_network_lookup(self, deps: ReviewLookupDeps, word: str | None = None, *, force: bool = False) -> None:
    tk = deps.tk
    if not force and not bool(self.network_lookup_enabled_var.get()):
        return
    value = (self._active_review_word() if word is None else str(word)).strip()
    self._network_lookup_word = value
    self._network_lookup_serial += 1
    serial = self._network_lookup_serial
    if self._network_lookup_job is not None:
        try:
            self.after_cancel(self._network_lookup_job)
        except tk.TclError:
            pass
        self._network_lookup_job = None
    if not value:
        self.network_lookup_status_var.set("网络词汇核验：当前词条为空")
        try:
            self.network_status_label.configure(fg="#666666")
        except tk.TclError:
            pass
        self._network_source_urls.clear()
        self._set_lookup_source_states(empty=True)
        return
    cached = self._network_lookup_cache.get(value)
    if cached is not None:
        self._apply_network_lookup_result(serial, value, cached)
        return
    self.network_lookup_status_var.set(f"网络词汇核验：正在查询“{value}”…")
    self._network_source_urls.clear()
    self._set_lookup_source_states(pending=True)
    try:
        self.network_status_label.configure(fg="#555555")
    except tk.TclError:
        pass
    delay = 0 if force else 550
    self._network_lookup_job = self.after(delay, lambda: self._start_network_lookup(serial, value))


def _start_network_lookup(self, deps: ReviewLookupDeps, serial: int, word: str) -> None:
    lookup_word_free = deps.lookup_word_free
    threading = deps.threading
    self._network_lookup_job = None
    if serial != self._network_lookup_serial or not word:
        return
    self._network_pending_serials.add(serial)
    if self._network_poll_job is None:
        self._network_poll_job = self.after(100, self._poll_network_lookup_results)

    def worker() -> None:
        try:
            result: LexicalLookupResult | None = lookup_word_free(word)
        except Exception:
            result = None
        self._network_result_queue.put((serial, word, result))

    threading.Thread(target=worker, name="picture-capture-network-lookup", daemon=True).start()


def _poll_network_lookup_results(self, deps: ReviewLookupDeps) -> None:
    queue = deps.queue
    self._network_poll_job = None
    while True:
        try:
            serial, word, result = self._network_result_queue.get_nowait()
        except queue.Empty:
            break
        self._network_pending_serials.discard(serial)
        if result is not None:
            self._network_lookup_cache[word] = result
        if serial == self._network_lookup_serial and word == self._network_lookup_word:
            self._apply_network_lookup_result(serial, word, result)
    if self._network_pending_serials:
        self._network_poll_job = self.after(100, self._poll_network_lookup_results)


def _apply_network_lookup_result(
    self, deps: ReviewLookupDeps, serial: int, word: str, result: LexicalLookupResult | None,
) -> None:
    tk = deps.tk
    contains_cjk = deps.contains_cjk
    if serial != self._network_lookup_serial or word != self._network_lookup_word:
        return
    if result is None:
        self.network_lookup_status_var.set(
            "⚠ 网络词汇核验暂时失败；可点“网络搜索”手工确认。"
        )
        try:
            self.network_status_label.configure(fg="#9a6700")
        except tk.TclError:
            pass
        self._set_lookup_source_states(empty=True)
        return

    self._network_source_urls = {item.name: item.url for item in result.sources if item.url}
    by_name = {item.name: item for item in result.sources}

    def marker(item_name: str) -> str:
        item = by_name.get(item_name)
        if item is None:
            return "—"
        if item.found is True:
            return "√"
        if item.found is False:
            return "×"
        if item_name == "CC-CEDICT" and "未安装" in (item.detail or ""):
            return "未装"
        return "?"

    if contains_cjk(word):
        self.cc_cedict_lookup_var.set(f"CC-CEDICT({marker('CC-CEDICT')})")
        self.moedict_lookup_var.set(f"萌({marker('萌典')})")
    else:
        self.cc_cedict_lookup_var.set("CC-CEDICT(—)")
        self.moedict_lookup_var.set("萌(—)")
    self.wiktionary_lookup_var.set(f"Wiki({marker('维基词典')})")

    found_names = [item.name for item in result.sources if item.found is True]
    if result.found is True:
        self.network_lookup_status_var.set(
            "✓ 有词典收录：" + "、".join(found_names)
        )
        status_color = "#1b7f3a"
    elif result.found is False:
        self.network_lookup_status_var.set(
            "○ 各可用词典均未检出精确词条（不代表该词不存在）"
        )
        status_color = "#8a5a00"
    else:
        self.network_lookup_status_var.set(
            "⚠ 部分词典未安装或网络来源暂不可用；可继续网络搜索。"
        )
        status_color = "#9a6700"
    try:
        self.network_status_label.configure(fg=status_color)
    except tk.TclError:
        pass


def open_network_web_search(self, deps: ReviewLookupDeps) -> None:
    messagebox = deps.messagebox
    webbrowser = deps.webbrowser
    web_search_url = deps.web_search_url
    # Keep the manual browser search aligned with the most recent lookup.
    # This matters when a row-level “网查” button queried the editable
    # simplified companion rather than the original headword.
    word = (self._network_lookup_word or self._active_review_word()).strip()
    if not word:
        self.network_lookup_status_var.set("网络词汇核验：当前词条为空")
        return
    try:
        webbrowser.open(web_search_url(word))
    except Exception as exc:
        messagebox.showerror("无法打开网页搜索", str(exc), parent=self)

