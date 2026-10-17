from pathlib import Path


def test_illustration_package_exists():
    root = Path(__file__).resolve().parents[1] / 'src' / 'picture_capture'
    assert (root / 'illustration' / '__init__.py').is_file()
