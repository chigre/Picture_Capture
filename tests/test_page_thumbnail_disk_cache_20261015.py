"""Persistent page-index thumbnails: synthetic scans only (no private pixels)."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import picture_capture.page_thumbnail_cache as disk
from picture_capture.ui.page_thumbnails import PageThumbnailController


def make_scan(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (480, 680), color).save(path)
    return path


def test_cache_is_project_local_and_contains_real_pixels(tmp_path):
    scan = make_scan(tmp_path / "scans" / "001.png", (245, 21, 31))
    original = scan.read_bytes()
    preview = disk.get_page_thumbnail(tmp_path, scan)
    assert preview.height == 120
    assert 0 < preview.width <= 120
    assert preview.getpixel((5, 5)) == (245, 21, 31)
    cache = disk.thumbnail_cache_path(tmp_path, scan)
    assert cache.is_file()
    assert cache.parent == disk.thumbnail_cache_dir(tmp_path)
    assert cache.name == "001.png"
    assert not any(p.is_dir() for p in disk.thumbnail_cache_dir(tmp_path).iterdir())
    with Image.open(cache) as saved:
        assert saved.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(scan)
        assert saved.info[disk.SOURCE_KEY] == disk._path_hash(scan)
        assert saved.info[disk.SOURCE_FILENAME_KEY] == scan.name
        assert saved.getpixel((5, 5)) == (245, 21, 31)
    assert scan.read_bytes() == original


def test_second_open_and_size_changes_read_cache_not_original(tmp_path, monkeypatch):
    scan = make_scan(tmp_path / "a.png", (15, 220, 48))
    disk.get_page_thumbnail(tmp_path, scan)

    def should_not_decode(_source):
        raise AssertionError("Full resolution scan was decoded again")

    monkeypatch.setattr(disk, "_build_thumbnail", should_not_decode)
    for width in (40, 80, 120, 160):
        thumb = disk.display_page_thumbnail(tmp_path, scan, width)
        assert thumb.getpixel((1, 1)) == (15, 220, 48)
        assert thumb.width <= width
        assert thumb.height <= round(width * 1.4)


def test_modified_scan_invalidates_cache_and_rebuilds(tmp_path):
    scan = make_scan(tmp_path / "a.png", (245, 21, 31))
    disk.get_page_thumbnail(tmp_path, scan)
    cached = disk.thumbnail_cache_path(tmp_path, scan)
    old_signature = disk.source_fingerprint(scan)
    make_scan(scan, (15, 30, 245))
    assert disk.source_fingerprint(scan) != old_signature
    fresh = disk.get_page_thumbnail(tmp_path, scan)
    assert fresh.getpixel((5, 5)) == (15, 30, 245)
    with Image.open(cached) as saved:
        assert saved.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(scan)


def test_corrupt_thumbnail_rebuilds_without_touching_original(tmp_path):
    scan = make_scan(tmp_path / "a.png", (110, 40, 180))
    original = scan.read_bytes()
    disk.get_page_thumbnail(tmp_path, scan)
    cached = disk.thumbnail_cache_path(tmp_path, scan)
    cached.write_bytes(b"interrupted png")
    fresh = disk.get_page_thumbnail(tmp_path, scan)
    assert fresh.getpixel((5, 5)) == (110, 40, 180)
    with Image.open(cached) as saved:
        assert saved.format == "PNG"
    assert scan.read_bytes() == original
    assert not list(cached.parent.glob(".thumbnail-*.tmp"))


def test_read_only_cache_falls_back_to_real_preview(tmp_path, monkeypatch):
    scan = make_scan(tmp_path / "a.png", (22, 80, 180))
    def deny_cache(*_args, **_kwargs):
        raise PermissionError("read only")
    monkeypatch.setattr(disk, "_publish_cache", deny_cache)
    image = disk.get_page_thumbnail(tmp_path, scan)
    assert image.getpixel((5, 5)) == (22, 80, 180)
    assert not disk.thumbnail_cache_path(tmp_path, scan).exists()


def test_progressively_caches_all_pages_not_only_visible_ones(tmp_path):
    from picture_capture.page_thumbnail_tasks import ThumbnailTasks
    import time

    scans = [
        make_scan(tmp_path / "pages" / f"page{i}.png", (20 + i, 40 + i, 60 + i))
        for i in range(7)
    ]
    pool = ThumbnailTasks(workers=2)
    names = disk.thumbnail_name_map(scans)
    finished = set()
    next_index = 0
    deadline = time.monotonic() + 10
    try:
        while len(finished) < len(scans) and time.monotonic() < deadline:
            while next_index < len(scans) and pool.active < 2:
                assert pool.submit(
                    next_index, ("synthetic", next_index), tmp_path,
                    scans[next_index], names,
                ) is not None
                next_index += 1
            for result in pool.collect():
                assert result.error is None, result.error
                assert result.image.getpixel((0, 0)) == (
                    20 + result.page_index,
                    40 + result.page_index,
                    60 + result.page_index,
                )
                finished.add(result.page_index)
            time.sleep(0.005)
    finally:
        pool.shutdown()
    assert len(finished) == len(scans)
    assert all(disk.thumbnail_cache_path(tmp_path, page, names).exists() for page in scans)


def test_filename_identity_prevents_cache_swap_between_same_stems(tmp_path):
    a = make_scan(tmp_path / "volume1" / "001.png", (255, 0, 0))
    b = make_scan(tmp_path / "volume2" / "001.png", (0, 0, 255))
    names = disk.thumbnail_name_map([a, b])
    cache_a = disk.thumbnail_cache_path(tmp_path, a, names)
    cache_b = disk.thumbnail_cache_path(tmp_path, b, names)
    assert cache_a != cache_b
    assert cache_a.parent == cache_b.parent == disk.thumbnail_cache_dir(tmp_path)
    assert cache_a.name.startswith("001__")
    assert cache_b.name.startswith("001__")
    assert disk.get_page_thumbnail(tmp_path, a, names).getpixel((0, 0)) == (255, 0, 0)
    assert disk.get_page_thumbnail(tmp_path, b, names).getpixel((0, 0)) == (0, 0, 255)
    assert cache_a.is_file() and cache_b.is_file()


def test_original_page_names_and_suffix_conflicts_are_flat(tmp_path):
    a = make_scan(tmp_path / "vol1" / "080127.jpg", (210, 40, 30))
    b = make_scan(tmp_path / "vol1" / "080128.png", (210, 80, 30))
    c = make_scan(tmp_path / "vol2" / "080127.png", (30, 60, 210))
    name_map = disk.thumbnail_name_map([a, b, c])
    assert disk.thumbnail_cache_path(tmp_path, b, name_map).name == "080128.png"
    for scan in (a, b, c):
        preview = disk.get_page_thumbnail(tmp_path, scan, name_map)
        assert preview.size[0] <= 120
        assert disk.thumbnail_cache_path(tmp_path, scan, name_map).is_file()
    names = [p.name for p in disk.thumbnail_cache_dir(tmp_path).iterdir()]
    assert len(names) == 3 and len(set(name.casefold() for name in names)) == 3
    assert all(name.endswith(".png") for name in names)
    assert all(path.is_file() for path in disk.thumbnail_cache_dir(tmp_path).iterdir())


def test_switching_or_copying_cache_png_cannot_swap_source_pixels(tmp_path):
    a = make_scan(tmp_path / "a.png", (230, 15, 10))
    b = make_scan(tmp_path / "b.png", (10, 20, 230))
    disk.get_page_thumbnail(tmp_path, a)
    disk.get_page_thumbnail(tmp_path, b)
    target = disk.thumbnail_cache_path(tmp_path, b)
    target.write_bytes(disk.thumbnail_cache_path(tmp_path, a).read_bytes())
    assert disk.get_page_thumbnail(tmp_path, b).getpixel((1, 1)) == (10, 20, 230)
    with Image.open(target) as verified:
        assert verified.info[disk.SOURCE_KEY] == disk._path_hash(b)


def test_content_sensitive_fingerprint_rejects_mtime_restored_edit(tmp_path):
    import os
    scan = make_scan(tmp_path / "page.bmp", (200, 80, 20))
    stat = scan.stat()
    disk.get_page_thumbnail(tmp_path, scan)
    before = disk.source_fingerprint(scan)
    make_scan(scan, (25, 80, 200))
    os.utime(scan, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert scan.stat().st_size == stat.st_size
    assert scan.stat().st_mtime_ns == stat.st_mtime_ns
    assert disk.source_fingerprint(scan) != before
    assert disk.get_page_thumbnail(tmp_path, scan).getpixel((2, 2)) == (25, 80, 200)


def test_v1_nested_cache_rebuilds_actual_source_and_removes_old_dir(tmp_path):
    from PIL import PngImagePlugin
    scan = make_scan(tmp_path / "scan-017.jpg", (10, 200, 90))
    legacy = disk._legacy_cache_path(tmp_path, scan)
    legacy.parent.mkdir(parents=True)
    old_meta = PngImagePlugin.PngInfo()
    # Old caches did not verify source-content samples. Even a plausible
    # legacy cache can show a wrong scan, so it must be rebuilt from source.
    old_meta.add_text(disk.FINGERPRINT_KEY, "a" * 64)
    Image.new("RGB", (158, 224), (220, 10, 10)).save(
        legacy, format="PNG", pnginfo=old_meta,
    )
    expected_pixel = disk._build_thumbnail(scan).getpixel((0, 0))
    result = disk.get_page_thumbnail(tmp_path, scan)
    assert result.getpixel((0, 0)) == expected_pixel
    assert result.getpixel((0, 0)) != (220, 10, 10)
    assert disk.thumbnail_cache_path(tmp_path, scan).name == "scan-017.png"
    assert disk.thumbnail_cache_path(tmp_path, scan).is_file()
    assert not legacy.exists()
    assert not legacy.parent.exists()


def test_name_collision_is_case_insensitive_even_on_linux(tmp_path):
    a = tmp_path / "setA" / "PAGE.JPG"
    b = tmp_path / "setB" / "page.png"
    names = disk.thumbnail_name_map([a, b])
    assert names[str(a.resolve())].casefold() != names[str(b.resolve())].casefold()


def test_read_only_duplicate_name_respects_original_pixels(tmp_path, monkeypatch):
    a = make_scan(tmp_path / "a" / "001.png", (255, 0, 0))
    b = make_scan(tmp_path / "b" / "001.png", (0, 0, 255))
    names = disk.thumbnail_name_map([a, b])
    monkeypatch.setattr(disk, "_publish_cache", lambda *_args: (_ for _ in ()).throw(PermissionError()))
    assert disk.get_page_thumbnail(tmp_path, a, names).getpixel((1, 1)) == (255, 0, 0)
    assert disk.get_page_thumbnail(tmp_path, b, names).getpixel((1, 1)) == (0, 0, 255)


def test_master_thumbnail_keeps_all_corners_instead_of_center_cropping(tmp_path):
    source = tmp_path / "wide-layout.png"
    image = Image.new("RGB", (1200, 720), "white")
    # Illustration marks at the page edges must remain visible in index.
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 150, 140), fill=(255, 0, 0))
    draw.rectangle((1050, 580, 1199, 719), fill=(0, 0, 255))
    image.save(source)
    preview = disk.get_page_thumbnail(tmp_path, source)
    assert preview.size[0] == 120
    assert preview.size[1] < 120  # The full landscape aspect ratio is kept.
    assert preview.getpixel((2, 2)) == (255, 0, 0)
    assert preview.getpixel((preview.width - 3, preview.height - 3)) == (0, 0, 255)


def test_fixed_v3_size_cache_rebuilds_old_v2_png_in_place(tmp_path):
    from PIL import PngImagePlugin
    source = make_scan(tmp_path / "page0.png", (80, 150, 200))
    cache = disk.thumbnail_cache_path(tmp_path, source)
    cache.parent.mkdir(parents=True, exist_ok=True)
    old = Image.new("RGB", (158, 224), (200, 80, 80))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text(disk.FINGERPRINT_KEY, "v2-stale")
    metadata.add_text(disk.SOURCE_KEY, disk._path_hash(source))
    metadata.add_text(disk.SOURCE_FILENAME_KEY, source.name)
    old.save(cache, format="PNG", pnginfo=metadata)
    preview = disk.get_page_thumbnail(tmp_path, source)
    assert preview.getpixel((5, 5)) == (80, 150, 200)
    assert preview.height == 120
    with Image.open(cache) as saved:
        assert saved.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(source)
        assert saved.height == 120


def test_every_v4_png_master_has_longest_dimension_at_most_120(tmp_path):
    cases = ((1200, 1800), (1800, 1200), (512, 512), (160, 3000))
    for index, (width, height) in enumerate(cases):
        page = tmp_path / f"original-{index}.png"
        Image.new("RGB", (width, height), (20 + index, 40, 60)).save(page)
        preview = disk.get_page_thumbnail(tmp_path, page)
        assert max(preview.size) <= 120
        assert min(preview.size) >= 1
        with Image.open(disk.thumbnail_cache_path(tmp_path, page)) as stored:
            assert max(stored.size) <= 120
            assert stored.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(page)


def _dense_monochrome_page() -> Image.Image:
    """Tiny synthetic black printed strokes on an otherwise white page."""
    from PIL import ImageDraw

    page = Image.new("RGB", (480, 680), "white")
    draw = ImageDraw.Draw(page)
    for y in range(45, 640, 9):
        for x in range(15, 440, 11):
            draw.rectangle((x, y, x + 3, y + 1), fill="black")
    return page


def test_bilevel_and_palette_scans_get_real_lanczos_antialiasing(tmp_path):
    """Regression: resizing mode 1/P before RGB conversion used nearest neighbor.

    The same monochrome pixels must produce the same smooth preview whether
    stored as RGB, grayscale, 1-bit monochrome, or palette-indexed PNG.
    """
    page = _dense_monochrome_page()
    variants = {
        "rgb": page.copy(),
        "gray": page.convert("L"),
        "bilevel": page.convert("1"),
        "palette": page.quantize(colors=2, method=Image.Quantize.FASTOCTREE),
    }
    reference = page.copy()
    reference.thumbnail(disk.CACHE_BOUNDS, Image.Resampling.LANCZOS)
    assert reference.mode == "RGB"
    for name, original in variants.items():
        path = tmp_path / f"{name}.png"
        original.save(path)
        before = path.read_bytes()
        with Image.open(path) as loaded:
            assert loaded.mode == original.mode
        preview = disk.get_page_thumbnail(tmp_path, path)
        assert preview.mode == "RGB"
        assert preview.size == reference.size
        assert preview.tobytes() == reference.tobytes(), name
        assert path.read_bytes() == before
        # True antialiasing introduces gray intermediate pixel values.
        grays = {
            preview.getpixel((x, y))[0]
            for y in range(preview.height)
            for x in range(preview.width)
        }
        assert any(0 < value < 255 for value in grays), name
        with Image.open(disk.thumbnail_cache_path(tmp_path, path)) as cached:
            assert cached.mode == "RGB"
            assert cached.tobytes() == reference.tobytes()
            assert cached.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(path)


def test_transparent_palette_page_has_white_paper_not_black_holes(tmp_path):
    source = tmp_path / "paletted-transparent.png"
    paletted = Image.new("P", (480, 680), 0)
    paletted.putpalette([0, 0, 0, 10, 20, 30] + [0] * 762)
    paletted.info["transparency"] = 0
    for x in range(100, 380):
        for y in range(150, 155):
            paletted.putpixel((x, y), 1)
    paletted.save(source, transparency=0)
    preview = disk.get_page_thumbnail(tmp_path, source)
    assert preview.mode == "RGB"
    assert preview.getpixel((0, 0)) == (255, 255, 255)
    assert preview.getpixel((preview.width // 2, preview.height // 4)) == (255, 255, 255)


def test_previous_v4_bilevel_cache_is_invalidated_in_flat_folder(tmp_path, monkeypatch):
    from PIL import PngImagePlugin

    source = tmp_path / "080001.png"
    _dense_monochrome_page().convert("1").save(source)
    monkeypatch.setattr(disk, "CACHE_VERSION", "page-index-v4")
    old_signature = disk.source_fingerprint(source)
    old_preview = Image.new("RGB", (85, 120), "red")
    destination = disk.thumbnail_cache_path(tmp_path, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    meta = PngImagePlugin.PngInfo()
    meta.add_text(disk.FINGERPRINT_KEY, old_signature)
    meta.add_text(disk.SOURCE_KEY, disk._path_hash(source))
    meta.add_text(disk.SOURCE_FILENAME_KEY, source.name)
    old_preview.save(destination, format="PNG", pnginfo=meta)

    monkeypatch.setattr(disk, "CACHE_VERSION", "page-index-v5")
    assert disk.source_fingerprint(source) != old_signature
    rebuilt = disk.get_page_thumbnail(tmp_path, source)
    assert rebuilt.getpixel((0, 0)) != (255, 0, 0)
    assert rebuilt.mode == "RGB"
    assert max(rebuilt.size) == 120
    assert destination.exists()
    with Image.open(destination) as cached:
        assert cached.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(source)
        assert cached.getpixel((0, 0)) != (255, 0, 0)
    assert len(list(disk.thumbnail_cache_dir(tmp_path).glob("*.png"))) == 1
