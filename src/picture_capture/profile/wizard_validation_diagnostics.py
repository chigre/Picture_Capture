"""Owner for raw OCR and selected headword coverage diagnostic summaries."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings


def validation_coverage_summary(
    cache_path: Path | None, entries, geometry, settings: AppSettings, *, deps,
) -> str:
    json = deps["json"]
    """Show raw OCR coverage, final-headword coverage and rejection clues."""
    prefix = (
        "测试方式：PaddleOCR（强制重新识别）"
        f"｜列跟踪：{'开' if bool(getattr(settings, 'follow_column_deformation', False)) else '关'}"
    )
    if cache_path is None or not cache_path.exists() or not geometry.column_starts:
        return prefix + "\n诊断缓存未生成；请重新运行【测试当前 Profile】。"
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        columns = list(payload.get("columns") or [])
    except (OSError, ValueError, TypeError) as exc:
        return prefix + f"\n诊断缓存读取失败：{exc}"

    selected_by_column: dict[int, list[float]] = {
        index: [] for index in range(len(geometry.column_starts))
    }
    span = max(1, int(geometry.bottom) - int(geometry.top))
    for entry in entries:
        try:
            u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
            col = min(
                range(len(geometry.column_starts)),
                key=lambda idx: abs(geometry.x_at(idx, v) - u),
            )
            selected_by_column[col].append(
                max(0.0, min(1.0, (float(v) - float(geometry.top)) / span))
            )
        except Exception:
            continue

    parts: list[str] = [prefix]
    for index in range(len(geometry.column_starts)):
        raw_pct = 0
        lower_total = 0
        lower_accepted = 0
        template_matches = 0
        template_scores: list[float] = []
        strong_edge_rescues = 0
        reject_counts: dict[str, int] = {}
        if index < len(columns):
            column = columns[index] or {}
            band_size = list(column.get("band_size") or [])
            band_height = max(1, int(band_size[1])) if len(band_size) >= 2 else span
            raw_bottom = 0
            for record in column.get("ocr_records", []) or []:
                box = record.get("box") if isinstance(record, dict) else None
                if isinstance(box, (list, tuple)) and len(box) == 4:
                    try:
                        raw_bottom = max(raw_bottom, int(box[3]))
                    except (TypeError, ValueError):
                        pass
            raw_pct = max(0, min(100, round(raw_bottom * 100 / band_height)))

            for row in column.get("candidates", []) or []:
                if not isinstance(row, dict) or "meta" in row:
                    continue
                box = row.get("box")
                if not isinstance(box, (list, tuple)) or len(box) != 4:
                    continue
                try:
                    center_y = (float(box[1]) + float(box[3])) / 2.0
                except (TypeError, ValueError):
                    continue
                features = row.get("features") if isinstance(row, dict) else None
                if isinstance(features, dict):
                    try:
                        template_score = float(
                            features.get("visual_marker_template_score") or 0.0
                        )
                    except (TypeError, ValueError):
                        template_score = 0.0
                    if template_score > 0:
                        template_matches += 1
                        template_scores.append(template_score)
                    if bool(
                        features.get("ordinary_strong_edge_visual_rescue")
                    ):
                        strong_edge_rescues += 1
                if center_y < band_height * 0.50:
                    continue
                lower_total += 1
                if bool(row.get("accepted")):
                    lower_accepted += 1
                else:
                    reason = str(row.get("reject_reason") or "candidate_rejected")
                    reject_counts[reason] = reject_counts.get(reason, 0) + 1

        selected_rows = selected_by_column.get(index) or []
        selected_pct = (
            max(0, min(100, round(max(selected_rows) * 100)))
            if selected_rows else 0
        )

        nominal_x = int(geometry.column_starts[index])
        path = (
            geometry.column_paths[index]
            if index < len(getattr(geometry, "column_paths", []))
            else None
        )
        drift = 0
        if path is not None:
            try:
                drift = max(
                    [abs(int(x) - nominal_x) for _y, x in path.points] or [0]
                )
            except Exception:
                drift = 0

        if reject_counts:
            top_reasons = sorted(
                reject_counts.items(), key=lambda item: (-item[1], item[0])
            )[:2]
            reason_text = "、".join(
                f"{reason}×{count}" for reason, count in top_reasons
            )
        else:
            reason_text = "无"

        warning = ""
        if raw_pct >= 85 and selected_pct <= 65:
            warning = " ⚠原始OCR完整但词头在中途停止"
        template_text = ""
        if bool(getattr(settings, "profile_symbol_template_debug_enabled", False)):
            best_template = max(template_scores) if template_scores else 0.0
            template_text = (
                f"｜模板命中{template_matches}（最高{best_template:.2f}）"
            )
        rescue_text = (
            f"｜强粗体左缘补救{strong_edge_rescues}"
            if strong_edge_rescues else ""
        )
        parts.append(
            f"{index + 1}栏：原始OCR至{raw_pct}%｜词头至{selected_pct}%｜"
            f"下半页候选{lower_total}（通过{lower_accepted}；拒绝主因：{reason_text}）｜"
            f"左缘最大漂移{drift}px{rescue_text}{template_text}{warning}"
        )
    return "\n".join(parts)


