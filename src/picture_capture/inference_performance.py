"""Machine-local inference policy shared by PaddleOCR and TextDetection.

The OCR pipeline may be used by both ordinary and OCR drawing.  This module
does not import Paddle and can be safely imported before worker initialization.
"""
from __future__ import annotations

from dataclasses import dataclass
import os

from .runtime_environment import resolve_paddle_device, runtime_setting


def _choice(env_name: str, setting_name: str, default: str, allowed: set[str]) -> str:
    raw = os.environ.get(env_name) or runtime_setting(setting_name, default)
    value = str(raw or default).strip().lower()
    return value if value in allowed else default


def _positive_int(env_name: str, setting_name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(env_name) or runtime_setting(setting_name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


@dataclass(frozen=True)
class InferencePolicy:
    device: str
    mkldnn: str
    cpu_workers: int
    cpu_threads: int

    @property
    def enable_mkldnn(self) -> bool:
        # oneDNN only applies to CPU execution, never to a CUDA predictor.
        return self.device == "cpu" and self.mkldnn != "off"


def resolve_inference_policy(*, page_count: int = 1) -> InferencePolicy:
    """Resolve local runtime settings, not project-persisted preferences.

    Auto MKL-DNN optimistically enables acceleration; constructors can retry
    with it disabled if a known backend incompatibility prevents startup.
    """
    device = resolve_paddle_device()
    mkldnn = _choice(
        "PICTURE_CAPTURE_PADDLE_MKLDNN", "paddle_mkldnn",
        "auto", {"auto", "on", "off"},
    )
    raw_workers = str(os.environ.get("PICTURE_CAPTURE_PADDLE_CPU_WORKERS") or runtime_setting("paddle_cpu_workers", "auto") or "auto").strip().lower()
    cpu_count = max(1, os.cpu_count() or 1)
    if raw_workers == "auto":
        # Conservative until per-process model memory is measured.
        count = max(1, min(cpu_count // 4, int(page_count)))
    else:
        try:
            requested = int(raw_workers)
        except ValueError:
            requested = max(1, cpu_count // 4)
        count = max(1, min(requested, cpu_count, max(1, int(page_count))))
    # Prevent six workers from *each* using all available CPU threads.
    default_threads = max(1, min(4, cpu_count // max(1, count)))
    threads = _positive_int(
        "PICTURE_CAPTURE_PADDLE_CPU_THREADS", "paddle_cpu_threads",
        default_threads, cpu_count,
    )
    return InferencePolicy(
        device=device, mkldnn=mkldnn, cpu_workers=count,
        cpu_threads=threads,
    )


def paddle_constructor_variants(kwargs: dict, policy: InferencePolicy) -> list[dict]:
    """Construct explicit CPU acceleration and compatibility attempts.

    Never silently drop a requested device: dropping 'device' could load a
    default GPU model in a CPU-only worker.
    """
    base = dict(kwargs)
    base["device"] = policy.device
    if policy.device == "cpu":
        base.update(
            enable_mkldnn=policy.enable_mkldnn,
            cpu_threads=policy.cpu_threads,
        )
    attempts = [base]
    # Only Auto may fall back after a backend failure. An explicit 'on'
    # remains explicit so the user can diagnose a broken runtime.
    if policy.device == "cpu" and policy.mkldnn == "auto":
        attempts.append({**base, "enable_mkldnn": False})
    return attempts
