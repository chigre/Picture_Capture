"""Opt-in per-page timings; per-PID files avoid cross-process locks.

Stage durations are elapsed wall times and MAY overlap in GPU/CPU pipelines.
Never sum overlapped stages to estimate total elapsed batch time.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
import os
from pathlib import Path
import time
from ..runtime_environment import user_data_root

_ENV = "PICTURE_CAPTURE_DRAW_PROFILE"
_CURRENT_PAGE: ContextVar[str | None] = ContextVar("draw_profile_page", default=None)


def bind_page(path: str | Path):
    return _CURRENT_PAGE.set(str(path))


def unbind_page(token) -> None:
    _CURRENT_PAGE.reset(token)



def enabled() -> bool:
    return os.environ.get(_ENV, "").strip().lower() in {"1", "true", "yes"}


def _directory() -> Path:
    return user_data_root() / "draw_profiles"


def record_page(image_path: str | Path, page_index: int, stages: dict[str, float],
                *, mode: str = "ordinary", stage_group: str = "page") -> None:
    if not enabled():
        return
    try:
        folder = _directory()
        folder.mkdir(parents=True, exist_ok=True)
        row = {
            "time": time.time(), "pid": os.getpid(),
            "page_index": int(page_index), "page": (
                _CURRENT_PAGE.get() if str(image_path) == "<substage>" else str(image_path)
            ),
            "mode": mode, "stage_group": stage_group,
            "stages_ms": {str(k): round(max(0.0, float(v)) * 1000, 3)
                          for k, v in stages.items()},
        }
        with (folder / f"{os.getpid()}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        pass


def recent_profiles(since: float, *, pages: set[str] | None = None) -> list[dict]:
    rows: list[dict] = []
    try:
        files = list(_directory().glob("*.jsonl"))
    except OSError:
        return rows
    for path in files:
        try:
            if path.stat().st_mtime < since:
                continue
            for line in path.read_text(encoding="utf-8").splitlines()[-2000:]:
                try:
                    record = json.loads(line)
                    if float(record.get("time", 0)) < since:
                        continue
                    if pages is not None and str(record.get("page")) not in pages:
                        continue
                    rows.append(record)
                except (ValueError, TypeError):
                    continue
        except OSError:
            continue
    return sorted(rows, key=lambda row: (row["time"], row.get("page_index", 0)))


def summarize(records: list[dict]) -> dict[str, float]:
    sums: dict[str, float] = {}
    for record in records:
        for key, milliseconds in record.get("stages_ms", {}).items():
            sums[key] = sums.get(key, 0.0) + float(milliseconds)
    return sums


def export_batch_report(records: list[dict], *, label: str,
                        elapsed_seconds: float, completed: int,
                        settings=None) -> Path | None:
    """Write human-readable Markdown and per-page CSV beside JSONL logs."""
    import csv
    from datetime import datetime
    import re
    try:
        root = _directory() / "reports"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(label))[:40]
        prefix = root / f"{stamp}_{safe_label}"
        keys = sorted({k for item in records
                       for k in item.get("stages_ms", {})})
        csv_path = prefix.with_suffix(".csv")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["page", "page_index", "pid", "stage_group", *keys])
            for item in sorted(records, key=lambda x: (x.get("page_index", 0),
                                                       x.get("stage_group", ""))):
                metrics = item.get("stages_ms", {})
                writer.writerow([item.get("page"), item.get("page_index"),
                                 item.get("pid"), item.get("stage_group"),
                                 *(metrics.get(k, "") for k in keys)])
        totals = summarize(records)
        configuration = {}
        if settings is not None:
            from ..layout_scale_experiment import FLAG
            from ..adaptive_denoise import resolve_denoise_strength
            properties = (
                "draw_performance_profile", "reuse_prepared_analysis",
                "analysis_denoise_enabled", "analysis_denoise_strength",
                "layout_denoise_enabled", "layout_scale_enabled",
                "layout_scale_columns", "layout_scale_column_width",
                "layout_scale_gutter", "layout_scale_start_y",
                "layout_scale_manual_x", "layout_scale_character_height",
                "layout_scale_row_padding", "layout_mask_illustrations",
                "layout_mask_illustrations_use_existing",
            )
            configuration = {
                name: getattr(settings, name, None) for name in properties
            }
            configuration["resolved_shared_denoise"] = resolve_denoise_strength(settings)
            configuration["scale_environment_override"] = os.environ.get(FLAG)
            configuration["prepared_reuse_environment"] = os.environ.get(
                "PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS"
            )
            configuration["profiling_environment"] = os.environ.get(_ENV)
        snapshot_path = prefix.with_suffix(".settings.json")
        snapshot_path.write_text(
            json.dumps(configuration, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report = [
            f"# Picture Capture — {label} 性能诊断",
            "",
            f"- 已完成页数：{completed}",
            f"- 批次实际耗时：{elapsed_seconds:.3f} 秒",
            f"- 吞吐量：{completed / max(0.001, elapsed_seconds):.3f} 页/秒",
            f"- 计时事件数：{len(records)}",
            "",
            "## 运行配置快照",
            "",
            "以下设置记录本批次启动时的项目设置及运行时环境；"
            "若使用环境变量覆盖缩图选择，以环境变量为准。",
            "",
            "```json",
            json.dumps(configuration, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 本批次实际缩图比例",
            "",
        ] + [
            f"- {group.removeprefix('layout_scale_')}: {sum(1 for item in records if item.get('stage_group') == group)} 页"
            for group in sorted({
                str(item.get("stage_group", "")) for item in records
                if str(item.get("stage_group", "")).startswith("layout_scale_")
            })
        ] + [
            "",
            "## 各阶段累计耗时",
            "",
            "| 阶段 | 累计耗时（秒） |",
            "|---|---:|",
        ]
        for key, ms in sorted(totals.items(), key=lambda x: -x[1]):
            report.append(f"| {key} | {ms / 1000:.3f} |")
        report.extend([
            "",
            "## 数据解释",
            "",
            "各 worker 和 GPU/CPU 阶段存在重叠，累计耗时不能相加作为批次总耗时。",
            "detect_entries 内部计时与上层 detect_entries 计时属于嵌套关系，也不能相加。",
            "模型推理耗时未细分 CUDA kernel，不能据此宣称 GPU 实测利用率。",
            f"详细逐页数据：`{csv_path.name}`",
            f"独立运行配置快照：`{snapshot_path.name}`",
            "",
        ])
        md_path = prefix.with_suffix(".md")
        md_path.write_text("\n".join(report), encoding="utf-8")
        return md_path
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(f"性能报告导出失败：{_directory() / 'reports'}：{exc}") from exc
