"""Issue #562: canonical preprocessing ownership, with no root compatibility shims."""
from pathlib import Path


def test_preprocessing_owners_are_physical_and_root_facade_is_retained() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    canonical = {"image_preprocessing_canvas":"canvas","image_preprocessing_constants":"constants","image_preprocessing_models":"models","image_preprocessing_persistence":"persistence","image_preprocessing_reporting":"reporting","image_preprocessing_storage":"storage","preprocess_geometry":"geometry","orthogonal_dewarp":"orthogonal_dewarp","text_line_geometry":"text_line_geometry","image_metadata_status":"image_metadata_status"}
    for old, new in canonical.items():
        assert not (root / (old + ".py")).exists(), old
        assert (root / "preprocess" / (new + ".py")).is_file(), new
    assert not (root / "adaptive_denoise.py").exists()
    assert (root / "preprocess" / "adaptive_denoise.py").is_file()
    for preserved in ("image_preprocessing.py", "image_utils.py", "document_unwarping.py"):
        assert (root / preserved).is_file(), preserved
