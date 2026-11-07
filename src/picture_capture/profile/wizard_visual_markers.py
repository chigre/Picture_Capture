"""Profile Wizard visual marker samples and dialog operations."""
from __future__ import annotations


def refresh_symbol_template_summary(self, *, deps) -> None:
    split_configured_symbols = deps["split_configured_symbols"]
    if not hasattr(self, "effective_entry_markers_var"):
        return
    entry = split_configured_symbols(self.entry_marker_symbols_var.get())
    bracket = split_configured_symbols(self.bracket_open_symbols_var.get())
    self.effective_entry_markers_var.set(
        "有效入口标记：" + (" ".join(entry) if entry else "无")
    )
    self.effective_bracket_markers_var.set(
        "有效括号起始：" + (" ".join(bracket) if bracket else "无")
    )
    samples = list(getattr(self, "visual_marker_samples", []) or [])
    entry_count = sum(
        1 for sample in samples
        if str(sample.get("role") or "") == "entry_marker"
    )
    bracket_count = sum(
        1 for sample in samples
        if str(sample.get("role") or "") == "bracket_open"
    )
    self.visual_marker_sample_count_var.set(
        f"入口标记样本：{entry_count} ｜ 括号起始样本：{bracket_count}"
    )



def capture_visual_marker_sample(self, *, deps) -> None:
    messagebox = deps["messagebox"]
    _visual_marker_capture_defaults = deps["_visual_marker_capture_defaults"]
    VisualMarkerCaptureDialog = deps["VisualMarkerCaptureDialog"]
    if not self.project.images:
        messagebox.showinfo(
            "无法采样", "项目中没有可用页面。", parent=self,
        )
        return
    initial_index = 0
    if self._validation_results:
        try:
            initial_index = int(
                self._validation_results[
                    self.validation_preview_slot % len(self._validation_results)
                ][0]
            )
        except (TypeError, ValueError, IndexError):
            initial_index = 0
    elif self.sample_indices:
        initial_index = int(self.sample_indices[0])
    initial_role, initial_literal = _visual_marker_capture_defaults(
        marker_prefix_enabled=bool(self.marker_prefix_var.get()),
        bracket_enabled=bool(self.cjk_allow_bracketed_var.get()),
        entry_text=self.entry_marker_symbols_var.get(),
        bracket_text=self.bracket_open_symbols_var.get(),
    )
    VisualMarkerCaptureDialog(
        self,
        self.project.images,
        initial_index=initial_index,
        initial_role=initial_role,
        initial_literal=initial_literal,
        on_saved=self._visual_marker_sample_saved,
    )



def visual_marker_sample_saved(self, sample: dict) -> None:
    samples = [
        dict(item) for item in getattr(self, "visual_marker_samples", []) or []
    ]
    sample_id = str(sample.get("id") or "")
    if sample_id:
        samples = [
            item for item in samples
            if str(item.get("id") or "") != sample_id
        ]
    samples.append(dict(sample))
    self._replace_visual_marker_samples(samples)



def replace_visual_marker_samples(self, samples: list[dict], *, deps) -> None:
    serialize_visual_marker_samples = deps["serialize_visual_marker_samples"]
    self.visual_marker_samples = [dict(sample) for sample in samples]
    self.working.profile_symbol_template_version = 1
    self.working.profile_symbol_templates_json = (
        serialize_visual_marker_samples(self.visual_marker_samples)
    )
    self._refresh_symbol_template_summary()
    self._headword_specificity_changed()



def show_visual_marker_samples(self, *, deps) -> None:
    messagebox = deps["messagebox"]
    VisualMarkerSamplesDialog = deps["VisualMarkerSamplesDialog"]
    if not getattr(self, "visual_marker_samples", None):
        messagebox.showinfo(
            "本词典视觉标记样本",
            "尚未保存视觉标记样本。请先点击【从页面采样…】。",
            parent=self,
        )
        return
    VisualMarkerSamplesDialog(
        self,
        [dict(sample) for sample in self.visual_marker_samples],
        on_changed=self._replace_visual_marker_samples,
    )



def clear_visual_marker_samples(self, *, deps) -> None:
    messagebox = deps["messagebox"]
    if not getattr(self, "visual_marker_samples", None):
        return
    if not messagebox.askyesno(
        "清空视觉标记样本",
        "确定清空当前项目保存的全部视觉标记样本吗？\n"
        "原始扫描页不会被修改。",
        parent=self,
    ):
        return
    self._replace_visual_marker_samples([])

