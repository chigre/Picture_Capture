from __future__ import annotations

from pathlib import Path

from picture_capture.performance_metrics import timing_summary_ms


def test_timing_summary_ms_reports_deterministic_distribution() -> None:
    assert timing_summary_ms([4.0, 1.0, 3.0, 2.0]) == {
        "samples": 4,
        "total": 10.0,
        "mean": 2.5,
        "median": 2.5,
        "p95": 4.0,
        "min": 1.0,
        "max": 4.0,
    }


def test_timing_summary_ms_handles_empty_and_nonfinite_samples() -> None:
    assert timing_summary_ms([]) == {
        "samples": 0,
        "total": 0.0,
        "mean": None,
        "median": None,
        "p95": None,
        "min": None,
        "max": None,
    }
    assert timing_summary_ms([float("nan"), float("inf"), 7.1254]) == {
        "samples": 1,
        "total": 7.125,
        "mean": 7.125,
        "median": 7.125,
        "p95": 7.125,
        "min": 7.125,
        "max": 7.125,
    }


def test_detection_benchmark_keeps_stage_timing_instrumentation() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "detection_benchmark.py").read_text(encoding="utf-8")

    assert "from time import perf_counter" in text
    assert "project_open_started = perf_counter()" in text
    assert "image_load_started = perf_counter()" in text
    assert "metadata_started = perf_counter()" in text
    assert "detect_started = perf_counter()" in text
    assert "pairwise_started = perf_counter()" in text
    assert '"benchmark_total": round((perf_counter() - benchmark_started)' in text
    assert '"timing_ms": timing_summary_ms(total["timing_ms"])' in text

def test_detection_benchmark_repeat_mode_is_opt_in_and_warm_after_first() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "detection_benchmark.py").read_text(encoding="utf-8")

    assert '"--timing-repeats"' in text
    assert "default=1" in text
    assert "if timing_repeats < 1:" in text
    assert "for _repeat_index in range(1, timing_repeats):" in text
    assert "force_paddle_refresh=False" in text
    assert '"timing_runs_ms": timing_runs_ms' in text
    assert '"repeat_timing_ms": timing_summary_ms(timing_runs_ms[1:])' in text
    assert '"timing_repeats": timing_repeats' in text


def test_detection_benchmark_repeat_mode_keeps_first_run_as_formal_result() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "detection_benchmark.py").read_text(encoding="utf-8")

    first_detect = text.index("entries, geometry = detect_entries(")
    repeat_loop = text.index("for _repeat_index in range(1, timing_repeats):")
    formal_result = text.index("detected[mode] = (entries, geometry)")
    ground_truth = text.index("metrics = match_markers(entries, gt, geometry, tolerance)")

    assert first_detect < formal_result < repeat_loop < ground_truth
    repeat_block = text[repeat_loop:ground_truth]
    assert "detected[mode]" not in repeat_block
    assert "metrics = match_markers" not in repeat_block

