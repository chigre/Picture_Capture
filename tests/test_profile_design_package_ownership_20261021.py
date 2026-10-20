"""Physical package ownership and bundled asset regression — Issue #562."""

from importlib import import_module
from pathlib import Path


OWNERS = {
    "profile_indent_ui": "profile/indent_ui",
    "profile_layout_bootstrap": "profile/layout_bootstrap",
    "profile_ordinary_evidence_ui": "profile/ordinary_evidence_ui",
    "profile_semantics": "profile/semantics",
    "profile_setup": "profile/setup",
    "profile_validation_modes": "profile/validation_modes",
    "profile_wizard": "profile/wizard",
    "dictionary_profile": "profile/dictionary",
    "parameter_help_ui": "profile/parameter_help_ui",
    "dictionary_page_design": "design/page_design",
    "dictionary_page_design_refined": "design/page_design_refined",
    "dictionary_page_layout_policy": "design/layout_policy",
    "visual_marker_templates": "visual/marker_templates",
    "visual_marker_ui": "visual/marker_ui",
    "app_settings_migrations": "profile/settings_migrations"
}


def test_profile_design_owners_have_only_canonical_paths():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    for retired, owner in OWNERS.items():
        old_path = root / (retired + ".py")
        canonical = root / (owner + ".py")
        assert not old_path.exists(), old_path
        assert canonical.is_file(), canonical
        module = import_module("picture_capture." + owner.replace("/", "."))
        assert Path(module.__file__).resolve() == canonical.resolve()


def test_moved_bundled_profile_assets_retain_original_paths():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    library = import_module("picture_capture.profile.dictionary")
    assert library.bundled_profile_path() == root / "data" / "default_dictionary_profile.json"
    assert library.profile_library_path() == root / "data" / "dictionary_profiles_v3.json"
    assert library.bundled_profile_path().is_file()
    assert library.profile_library_path().is_file()
    setup = import_module("picture_capture.profile.setup")
    assert (Path(setup.__file__).resolve().parent.parent / "data" / "headword_examples").is_dir()
