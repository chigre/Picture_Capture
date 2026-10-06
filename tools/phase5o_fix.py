from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/picture_capture/models.py",
    '''    @property\n    def row_height(self) -> int:\n        return max(1, self.character_height + self.row_padding)\n''',
    '''    def __setattr__(self, name: str, value: object) -> None:\n        # Preserve the former runtime-property contract now that these values\n        # are native dataclass fields: construction and later assignments are\n        # both normalized immediately rather than only at render/save time.\n        if name in {"guide_opacity", "headword_marker_opacity"}:\n            value = _normalize_display_opacity(value)\n        object.__setattr__(self, name, value)\n\n    @property\n    def row_height(self) -> int:\n        return max(1, self.character_height + self.row_padding)\n''',
)

replace_once(
    "tests/test_overlay_opacity.py",
    '''def test_native_json_persistence_preserves_runtime_clamping_contract(tmp_path: Path):\n    settings = AppSettings(guide_opacity=-20, headword_marker_opacity=180)\n    path = tmp_path / "settings.json"\n''',
    '''def test_native_json_persistence_preserves_runtime_clamping_contract(tmp_path: Path):\n    settings = AppSettings(guide_opacity=-20, headword_marker_opacity=180)\n    assert settings.guide_opacity == 0.0\n    assert settings.headword_marker_opacity == 100.0\n    settings.guide_opacity = 250\n    settings.headword_marker_opacity = -5\n    assert settings.guide_opacity == 100.0\n    assert settings.headword_marker_opacity == 0.0\n    settings.guide_opacity = -20\n    settings.headword_marker_opacity = 180\n    path = tmp_path / "settings.json"\n''',
)

print("Phase 5O clamp compatibility fix applied")
