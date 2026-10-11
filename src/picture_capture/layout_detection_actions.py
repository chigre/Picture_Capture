"""Manual project layout detection and cross-page consistency reports.

Extracted from app.py without changing callbacks, worker scheduling, data
aggregation, report formats, or the regular per-page ordinary drawing policy.
"""
from __future__ import annotations

import csv
import re
import statistics
from dataclasses import replace
from datetime import datetime
from tkinter import messagebox

from PIL import Image

from .coordinate_space import SOURCE_COORDINATE_SPACE
from .layout_detection import detect_layout_consistency, detect_layout_parameters
from .layout_transform import LayoutTransform
from .project_storage import exports_root


def detect_layout_current(self) -> None:
    if not self.guard() or not self.apply_quick_settings(show_status=False): return
    try:
        indices = self.selected_page_indices()
    except Exception as exc:
        self.show_error("页面范围无效", exc); return
    names = [self.project.images[i].name for i in indices]
    if not messagebox.askyesno(
        "选择检测页面范围",
        f"将按页面列表上方当前选择的范围检测 {len(indices)} 页。\n"
        f"范围：{names[0]}" + (f" ～ {names[-1]}" if len(names) > 1 else "") +
        "\n\n多页数值参数将取稳健中位数；分栏数按多数页面的栏数确定。"
        "检测结果会填充分栏/起始Y/首栏X/栏宽/栏间空/行高/行间空；"
        "页底不再作为手工参数写入。是否继续？",
        parent=self,
    ):
        return
    settings = replace(self.settings)
    pages = list(self.project.images)

    def worker(index: int, _position: int, _total: int):
        with Image.open(pages[index]) as opened:
            return detect_layout_parameters(opened, settings)

    def done(_completed, _total, stopped, results, error) -> None:
        if error or not results:
            return
        from .layout_detection import aggregate_layout_estimates
        values, consistency = aggregate_layout_estimates(
            results,
            columns_policy=self.settings.layout_columns_policy,
            fixed_columns=self.settings.columns,
        )
        from .layout_parameter_evidence import verified_multi_page_row_padding
        measured_padding, padding_pages = verified_multi_page_row_padding(list(results))
        if measured_padding is None:
            values.pop("row_padding", None)
        else:
            values["row_padding"] = measured_padding
        old_character_height = max(1, int(self.settings.character_height))
        body_indent_was_auto = int(self.settings.body_indent) == old_character_height
        horizontal_tolerance_was_auto = (
            int(self.settings.horizontal_tolerance)
            == max(1, round(old_character_height / 2.0))
        )
        for name, value in values.items():
            if name == "bottom_y":
                continue
            setattr(self.settings, name, value)
        if "character_height" in values:
            new_character_height = max(1, int(self.settings.character_height))
            if body_indent_was_auto:
                self.settings.body_indent = new_character_height
            if horizontal_tolerance_was_auto:
                self.settings.horizontal_tolerance = max(
                    1, round(new_character_height / 2.0)
                )
        self.sync_quick_settings(); self.save_settings(); self.redraw()
        suffix = "（任务提前停止，按已完成页面计算）" if stopped else ""
        summary = "稳健中位数" if len(results) >= 2 else "单页检测值"
        padding_note = (
            f"；行间空有可靠文本框{padding_pages}/{len(results)}页"
            if measured_padding is not None
            else f"；行间空仅{padding_pages}/{len(results)}页有实测，保留原设置"
        )
        self.status_var.set(
            f"版面参数检测完成：{consistency}；数值参数使用{summary}{padding_note}{suffix}"
        )

    self._start_batch_task("检测版面参数", indices, worker, done, item_label=lambda i: pages[i].name)

def detect_layout_consistency_selected(self) -> None:
    if not self.guard() or not self.apply_quick_settings(show_status=False): return
    try:
        indices = self.selected_page_indices()
    except Exception as exc:
        self.show_error("页面范围无效", exc); return
    if len(indices) < 2:
        messagebox.showwarning(
            "检测版面一致性",
            "版面一致性检测至少需要选择 2 页；当前页面范围不足 2 页，未执行检测。",
            parent=self,
        )
        return
    if not messagebox.askyesno(
        "检测版面一致性",
        f"将快速扫描当前所选 {len(indices)} 页，输出原图 X/Y 中的页眉边界与正文左缘。\n\n"
        "此任务使用灰度投影而非 PaddleVL/OCR，以便高效处理数千页。是否继续？",
        parent=self,
    ):
        return
    project = self.project
    pages = list(project.images); settings = replace(self.settings)
    range_name = pages[indices[0]].stem if len(indices) == 1 else f"{pages[indices[0]].stem}-{pages[indices[-1]].stem}"
    range_name = re.sub(r'[^0-9A-Za-z_.-]+', "_", range_name)

    def worker(index: int, _position: int, _total: int):
        with Image.open(pages[index]) as opened:
            image_size = opened.size
            estimate = detect_layout_consistency(opened, settings)
        transform_kind = str(getattr(settings, "layout_transform", "identity") or "identity")
        transform = LayoutTransform(transform_kind)
        canonical_width, canonical_height = transform.canonical_size(image_size)
        header_segment = None
        if estimate.header_rule_y is not None:
            header_segment = transform.canonical_marker_to_source(
                (0, int(estimate.header_rule_y)),
                (max(0, canonical_width - 1), int(estimate.header_rule_y)),
                image_size,
            )
        left_segment = None
        if estimate.body_left_x is not None:
            left_segment = transform.canonical_marker_to_source(
                (int(estimate.body_left_x), 0),
                (int(estimate.body_left_x), max(0, canonical_height - 1)),
                image_size,
            )
        header_y = (
            int(header_segment[0][1])
            if header_segment and int(header_segment[0][1]) == int(header_segment[1][1])
            else None
        )
        left_x = (
            int(left_segment[0][0])
            if left_segment and int(left_segment[0][0]) == int(left_segment[1][0])
            else None
        )
        return (
            pages[index].name, header_segment, left_segment,
            header_y, left_x, estimate.is_blank, transform_kind,
        )

    def done(_completed, _total, stopped, results, error) -> None:
        if error or not results:
            return
        rows = list(results)
        stopped_early = bool(stopped)
        export_dir = exports_root(project.root)
        self.status_var.set("版面扫描完成；正在后台生成 CSV 与统计报告…")

        def finalize_report():
            base = f"layout_consistency_{range_name}_{datetime.now():%Y%m%d_%H%M%S_%f}"
            target = export_dir / f"{base}.csv"
            report = export_dir / f"{base}_report.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            temp_csv = target.with_name(f".{target.name}.tmp")
            temp_report = report.with_name(f".{report.name}.tmp")

            def segment_text(segment) -> str:
                if not segment:
                    return ""
                (x0, y0), (x1, y1) = segment
                return f"{x0},{y0}->{x1},{y1}"

            try:
                with temp_csv.open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow((
                        "page",
                        "header_rule_source_segment_xyxy",
                        "body_left_source_segment_xyxy",
                        "header_rule_source_y",
                        "body_left_source_x",
                        "coordinate_space",
                        "layout_transform_internal",
                        "status",
                    ))
                    writer.writerows((
                        row[0], segment_text(row[1]), segment_text(row[2]),
                        row[3], row[4], SOURCE_COORDINATE_SPACE, row[6],
                        "blank_skipped" if row[5] else "analyzed",
                    ) for row in rows)

                analyzed = [row for row in rows if not row[5]]
                blanks = [row[0] for row in rows if row[5]]
                header_values = [row[3] for row in analyzed if row[3] is not None]
                left_values = [row[4] for row in analyzed if row[4] is not None]

                def summary(values) -> str:
                    return (
                        "无可比较的同轴值" if not values
                        else f"均值 {statistics.fmean(values):.1f}，范围 {min(values)}–{max(values)}，标准差 {statistics.pstdev(values):.1f}"
                    )

                def outliers(column: int) -> list[str]:
                    pairs = [(row[0], row[column]) for row in analyzed if row[column] is not None]
                    if len(pairs) < 3:
                        return []
                    values = [value for _name, value in pairs]
                    mean = statistics.fmean(values)
                    deviation = statistics.pstdev(values)
                    tolerance = max(3.0, deviation * 2.5)
                    return [name for name, value in pairs if abs(value - mean) > tolerance]

                abnormal = sorted(set(outliers(3) + outliers(4)))
                header_summary = summary(header_values)
                left_summary = summary(left_values)
                report_text = (
                    f"页面范围：{range_name}\n总页数：{len(rows)}\n有效分析：{len(analyzed)}\n"
                    f"空白页跳过：{len(blanks)}（{', '.join(blanks) or '无'}）\n"
                    f"页眉横线 Y（原图px）：{header_summary}\n"
                    f"正文左缘 X（原图px）：{left_summary}\n"
                    f"异常页面：{', '.join(abnormal) or '无'}\n"
                )
                temp_report.write_text(report_text, encoding="utf-8-sig")
                temp_csv.replace(target)
                try:
                    temp_report.replace(report)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
                return {
                    "target": target, "report": report,
                    "analyzed": len(analyzed), "blanks": len(blanks),
                    "header_summary": header_summary, "left_summary": left_summary,
                    "abnormal": abnormal, "total": len(rows),
                }
            except Exception:
                temp_csv.unlink(missing_ok=True)
                temp_report.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                report.unlink(missing_ok=True)
                raise

        def finalized(payload) -> None:
            if self.project is not project:
                return
            abnormal_text = ", ".join(payload["abnormal"]) or "无"
            messagebox.showinfo(
                "版面一致性统计",
                f"完成 {payload['total']} 页，有效 {payload['analyzed']} 页，跳过空白页 {payload['blanks']} 页"
                f"{'（提前停止）' if stopped_early else ''}\n"
                f"页眉横线 Y（原图px）：{payload['header_summary']}\n"
                f"正文左缘 X（原图px）：{payload['left_summary']}\n"
                f"异常页面：{abnormal_text}\n\n"
                "CSV 只保存原图 X/Y 边界线段与可直接比较的 source X/Y 数值。\n"
                f"结果：{payload['target']}\n报告：{payload['report']}",
                parent=self,
            )
            self.status_var.set(f"版面一致性检测完成：{payload['target'].name}")

        def finalize_failed(exc, detail) -> None:
            if detail:
                print(detail)
            if self.project is project:
                self.show_error("生成版面一致性报告失败", exc)

        self._start_ui_worker(
            "layout-consistency-finalize",
            finalize_report, finalized, finalize_failed,
            wait_on_close=True,
        )

    self._start_batch_task("检测版面一致性", indices, worker, done, item_label=lambda i: pages[i].name)

