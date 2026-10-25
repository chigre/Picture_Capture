"""Lazy import forwarding for physically retired root modules.

Unlike eager aliases in picture_capture.__init__, this finder does not load
PaddleOCR/NumPy on startup or during unrelated GUI/CLI imports. A registered
legacy module becomes the *same live module object* as its canonical owner,
preserving module-level monkeypatches with no duplicate globals.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys


ALIASES = {
    "picture_capture.paddle_headwords_core": "picture_capture.ocr.headword_core_runtime",
}


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, canonical: str) -> None:
        self.canonical = canonical

    def create_module(self, spec):
        return importlib.import_module(self.canonical)

    def exec_module(self, module) -> None:
        # The canonical module has already been imported exactly once.
        return None


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        canonical = ALIASES.get(fullname)
        if canonical is None:
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(canonical))


def install_legacy_aliases() -> None:
    if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())
