from __future__ import annotations

from pathlib import Path

import picture_capture.runtime_environment as runtime
from picture_capture.ocr_engines import find_tesseract
from picture_capture.picdic import build_picdic_package
from picture_capture.project_storage import pdic_path_for_image, ppp_read_path_for_image, qt_root


def test_platform_native_user_roots(tmp_path: Path):
    home = tmp_path / "home"
    win_env = {"APPDATA": str(tmp_path / "roaming"), "LOCALAPPDATA": str(tmp_path / "local")}
    assert runtime.user_config_root(system="Windows", environ=win_env, home=home) == tmp_path / "roaming" / "PictureCapture"
    assert runtime.user_data_root(system="Windows", environ=win_env, home=home) == tmp_path / "local" / "PictureCapture"

    assert runtime.user_config_root(system="Darwin", environ={}, home=home) == home / "Library" / "Application Support" / "PictureCapture"
    assert runtime.user_data_root(system="Darwin", environ={}, home=home) == home / "Library" / "Application Support" / "PictureCapture"

    linux_env = {"XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_DATA_HOME": str(tmp_path / "data")}
    assert runtime.user_config_root(system="Linux", environ=linux_env, home=home) == tmp_path / "cfg" / "PictureCapture"
    assert runtime.user_data_root(system="Linux", environ=linux_env, home=home) == tmp_path / "data" / "PictureCapture"


def test_foreign_absolute_paths_are_detected():
    assert runtime.is_foreign_absolute_path(r"C:\\Dictionary\\wordslist.txt", system="Linux")
    assert runtime.is_foreign_absolute_path(r"C:\\Dictionary\\wordslist.txt", system="Darwin")
    assert not runtime.is_foreign_absolute_path(r"C:\\Dictionary\\wordslist.txt", system="Windows")
    assert runtime.is_foreign_absolute_path("/Users/example/wordslist.txt", system="Windows")
    assert not runtime.is_foreign_absolute_path("/Users/example/wordslist.txt", system="Darwin")


def test_foreign_wordslist_path_falls_back_to_project_local_case_insensitively(tmp_path: Path, monkeypatch):
    local = tmp_path / "WordsList.TXT"
    local.write_text("alpha\n", encoding="utf-8")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    resolved = runtime.portable_project_file(
        tmp_path,
        r"D:\\old-machine\\wordslist.txt",
        fallback_name="wordslist.txt",
    )
    assert resolved.is_file()
    assert resolved.samefile(local)


def test_runtime_setting_is_machine_local_and_atomic(tmp_path: Path):
    target = tmp_path / "runtime.json"
    runtime.save_runtime_setting("tesseract_executable", "/usr/bin/tesseract", target)
    runtime.save_runtime_setting("paddle_device", "cpu", target)
    assert runtime.load_runtime_settings(target) == {
        "tesseract_executable": "/usr/bin/tesseract",
        "paddle_device": "cpu",
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_paddle_device_environment_override_is_authoritative(monkeypatch):
    runtime.clear_runtime_caches()
    monkeypatch.setenv("PICTURE_CAPTURE_PADDLE_DEVICE", "gpu")
    assert runtime.resolve_paddle_device() == "gpu"
    runtime.clear_runtime_caches()
    monkeypatch.setenv("PICTURE_CAPTURE_PADDLE_DEVICE", "cpu")
    assert runtime.resolve_paddle_device() == "cpu"
    runtime.clear_runtime_caches()


def test_tesseract_stale_foreign_path_falls_back_to_path(monkeypatch):
    monkeypatch.setattr(
        "picture_capture.ocr_engines.effective_tesseract_configured",
        lambda _value: r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    )

    def fake_which(value: str):
        return "/opt/homebrew/bin/tesseract" if value == "tesseract" else None

    monkeypatch.setattr("picture_capture.ocr_engines.shutil.which", fake_which)
    assert find_tesseract("ignored") == "/opt/homebrew/bin/tesseract"


def test_legacy_pdic_and_ppp_casing_resolves_on_case_sensitive_filesystem(tmp_path: Path):
    image = tmp_path / "Page001.jpg"
    image.write_bytes(b"")
    (tmp_path / "Page001.PDIC").write_text("", encoding="utf-8")
    (tmp_path / "Page001.PpP").write_text("", encoding="utf-8")
    pdic = pdic_path_for_image(image)
    ppp = ppp_read_path_for_image(image)
    assert pdic.is_file() and pdic.samefile(tmp_path / "Page001.PDIC")
    assert ppp.is_file() and ppp.samefile(tmp_path / "Page001.PpP")


def test_picdic_accepts_legacy_manifest_and_image_case(tmp_path: Path):
    pww = qt_root(tmp_path) / "PWW"
    pww.mkdir(parents=True)
    actual_image = pww / "Page_0001.PNG"
    actual_image.write_bytes(b"synthetic")
    (pww / "PAGE.PWWORDS").write_text(
        "page|1|alpha|page_0001.png\n",
        encoding="utf-8",
    )

    dsl, archive, words, images = build_picdic_package(tmp_path, "eng")
    assert dsl.is_file()
    assert archive.is_file()
    assert words == 1
    assert images == 1

    import zipfile
    with zipfile.ZipFile(archive) as zf:
        assert zf.namelist() == ["page_0001.png"]
