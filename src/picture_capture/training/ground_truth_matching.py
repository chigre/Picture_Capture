from __future__ import annotations

"""Training-only OCR candidate to human-confirmed PDIC line matching.

The temporary canonical reading axis is for comparisons only. Exported
annotations always use the actual original-image X/Y source coordinates.
The original training_export entrypoint re-exports this very same function.
"""

from typing import Any


def _candidate_ground_truth_link(
    candidate: dict[str, Any],
    ground_truth: list[dict[str, Any]],
    geometry,
    line_height: int,
) -> dict[str, Any]:
    """Link one OCR candidate to the nearest saved line.

    Reading-order comparison may use a temporary transformed axis internally,
    but training annotations expose only original-image X/Y coordinates.
    """
    try:
        column = int(candidate.get("column", -1))
        source_x = int(candidate.get("source_x"))
        source_y = int(candidate.get("source_y", candidate.get("refined_source_y")))
        _axis_u, candidate_axis_v = geometry.source_to_canonical(source_x, source_y)
    except Exception:
        return {
            "ground_truth_selected": False,
            "nearest_ground_truth_source": None,
            "ground_truth_source_y_delta": None,
        }

    same_col = [
        row for row in ground_truth
        if int(row.get("column", -2)) == column
    ]
    if not same_col:
        return {
            "ground_truth_selected": False,
            "nearest_ground_truth_source": None,
            "ground_truth_source_y_delta": None,
        }

    def axis_v(row: dict[str, Any]) -> int:
        _u, v = geometry.source_to_canonical(int(row["x"]), int(row["y"]))
        return int(v)

    nearest = min(same_col, key=lambda row: abs(axis_v(row) - int(candidate_axis_v)))
    axis_delta = abs(axis_v(nearest) - int(candidate_axis_v))
    tolerance = max(4, round(max(1, line_height) * 0.60))
    return {
        "ground_truth_selected": bool(axis_delta <= tolerance),
        "nearest_ground_truth_source": [int(nearest["x"]), int(nearest["y"])],
        "nearest_ground_truth_source_x": int(nearest["x"]),
        "nearest_ground_truth_source_y": int(nearest["y"]),
        "ground_truth_source_x_delta": abs(int(nearest["x"]) - source_x),
        "ground_truth_source_y_delta": abs(int(nearest["y"]) - source_y),
    }
