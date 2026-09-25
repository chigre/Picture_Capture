from __future__ import annotations

from pathlib import Path

from picture_capture.environment_center import (
    _apt_language_package,
    ocr_installer_path,
    tesseract_install_plan,
)


def which_from(names: set[str]):
    def fake(name: str):
        return f"/usr/bin/{name}" if name in names else None
    return fake


def test_windows_tesseract_plan_prefers_winget():
    plan = tesseract_install_plan(
        "spa+eng",
        system="Windows",
        which=which_from({"winget"}),
    )
    assert plan.manager == "winget"
    assert plan.commands == ("winget install --id tesseract-ocr.tesseract -e",)
    assert "spa + eng" in plan.note


def test_macos_tesseract_plan_adds_language_formula_when_needed():
    plan = tesseract_install_plan(
        "spa+eng",
        system="Darwin",
        which=which_from({"brew"}),
    )
    assert plan.manager == "Homebrew"
    assert plan.commands == ("brew install tesseract", "brew install tesseract-lang")

    english_only = tesseract_install_plan(
        "eng",
        system="Darwin",
        which=which_from({"brew"}),
    )
    assert english_only.commands == ("brew install tesseract",)


def test_apt_plan_maps_tesseract_language_names():
    assert _apt_language_package("chi_sim") == "tesseract-ocr-chi-sim"
    assert _apt_language_package("jpn_vert") == "tesseract-ocr-jpn-vert"
    plan = tesseract_install_plan(
        "spa+eng",
        system="Linux",
        which=which_from({"apt"}),
    )
    assert plan.manager == "apt"
    assert plan.commands == (
        "sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng",
    )


def test_unknown_linux_manager_does_not_guess_package_names():
    plan = tesseract_install_plan("spa", system="Linux", which=which_from(set()))
    assert plan.commands == ()
    assert "发行版" in plan.note


def test_ocr_installer_path_is_platform_specific(tmp_path: Path):
    win = tmp_path / "install_ocr_windows.bat"
    linux = tmp_path / "install_ocr_linux.sh"
    mac = tmp_path / "install_ocr_macos.command"
    for path in (win, linux, mac):
        path.write_text("", encoding="utf-8")

    assert ocr_installer_path(tmp_path, "Windows") == win
    assert ocr_installer_path(tmp_path, "Linux") == linux
    assert ocr_installer_path(tmp_path, "Darwin") == mac
    assert ocr_installer_path(tmp_path, "Plan9") is None
