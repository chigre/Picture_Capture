"""Opt-in volatile, content-free aggregate stage timings for focused review.

This is an in-memory instrument (no file, network, text, coordinates, page
names or personal content). It does not measure active human review time,
OCR quality, or improvements over another mode. The risk stage is a subset
of scan time; do not sum those two as independent totals.
"""
from __future__ import annotations

import math

_STAGES = ("scan", "risk", "crop", "save")


class ReviewTimingSession:
    def __init__(self, *, epoch: int):
        if type(epoch) is not int or epoch < 0:
            raise ValueError("epoch must be a nonnegative int")
        self.epoch = epoch
        self._seconds = {stage: 0.0 for stage in _STAGES}
        self._counts = {stage: 0 for stage in _STAGES}

    def add(self, stage: str, seconds: float, count: int = 1, *, epoch: int) -> bool:
        if (
            epoch != self.epoch or stage not in _STAGES
            or type(seconds) not in (int, float)
            or not math.isfinite(seconds) or seconds < 0
            or type(count) is not int or count < 0
        ):
            return False
        self._seconds[stage] += float(seconds)
        self._counts[stage] += count
        return True

    def snapshot(self) -> dict:
        return {
            "format": "focused-review-local-aggregate-v1",
            "scope": "volatile-local-memory",
            "stages": {
                stage: {"seconds": self._seconds[stage], "count": self._counts[stage]}
                for stage in _STAGES
            },
        }

    @property
    def label(self) -> str:
        return (
            "本次本地阶段统计（非人工校对耗时；不保存文本）："
            f"扫描 {self._seconds['scan']:.3f}秒/{self._counts['scan']}页；"
            f"风险校验（含于扫描）{self._seconds['risk']:.3f}秒/{self._counts['risk']}页；"
            f"预览生成 {self._seconds['crop']:.3f}秒/{self._counts['crop']}批；"
            f"PDIC保存 {self._seconds['save']:.3f}秒/{self._counts['save']}条。"
        )
