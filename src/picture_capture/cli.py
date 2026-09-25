from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageOps

from .formats import pdic_path, read_pdic, write_pdic
from .image_utils import normalize_page_rgb
from .models import ProjectState
from .paddle_headwords import HEADWORD_FILTER_RULES_FILENAME
from .project_storage import headword_filter_rules_path, ocr_cache_root, qt_root, replace_rules_path
from .page_sections import read_page_sections
from .processing import (
    append_crop_log,
    detect_entries,
    export_ocred,
    load_replace_rules,
    ocr_entries,
    sort_entries_reading_order,
    derive_geometry,
    split_single_lines,
    split_whole_entries,
)


def _pages(project: ProjectState, name: str | None) -> list[Path]:
    if not name:
        return project.images
    matches = [page for page in project.images if page.name == name or page.stem == name]
    if not matches:
        raise ValueError(f"项目中没有页面：{name}")
    return matches


def _neighbors(project: ProjectState, page: Path) -> tuple[str, str, str]:
    index = project.images.index(page)
    previous = project.images[index - 1].stem if index > 0 else "@"
    following = project.images[index + 1].stem if index + 1 < len(project.images) else "@"
    return page.stem, previous, following


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Picture Capture Python restoration")
    parser.add_argument("project", type=Path, help="包含扫描页和 wordslist.txt 的项目目录")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect", help="列出项目和兼容文件")
    for name, help_text in [
        ("autodraw", "自动检测词条并写入 .pdic"),
        ("ocr", "OCR 现有 .pdic 中的词条"),
        ("split-lines", "导出词条所在行"),
        ("split-whole", "导出完整词条内容"),
    ]:
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--page", help="只处理指定文件名或不带扩展名的页")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project = ProjectState.open(args.project)
        if args.command == "inspect":
            print(f"目录: {project.root}")
            print(f"页面: {len(project.images)}")
            print(f"词表: {len(project.words)}")
            print(f"已有 PDIC: {sum(pdic_path(page).exists() for page in project.images)}")
            print(f"OCR 语言: {project.settings.ocr_language}")
            return 0

        pages = _pages(project, args.page)
        for number, page in enumerate(pages, 1):
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            if args.command == "autodraw":
                cache_path = (
                    ocr_cache_root(project.root) / f"{page.stem}.json"
                    if project.settings.detection_method == "paddleocr" else None
                )
                entries, _ = detect_entries(
                    image, project.settings, paddle_cache_path=cache_path,
                    paddle_filter_rules_path=headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME),
                    profile_page_index=project.images.index(page),
                    page_sections=read_page_sections(page),
                )
                write_pdic(pdic_path(page), entries, image.width, _neighbors(project, page))
                print(f"[{number}/{len(pages)}] {page.name}: {len(entries)} 个标记")
                continue

            entries = read_pdic(pdic_path(page))
            if not entries:
                print(f"[{number}/{len(pages)}] {page.name}: 无 PDIC 标记，跳过")
                continue
            if args.command == "ocr":
                rules = load_replace_rules(replace_rules_path(project.root))
                texts = ocr_entries(
                    image, entries, project.settings, rules,
                    page_sections=read_page_sections(page),
                )
                for entry, text in zip(entries, texts):
                    entry.word = text
                export_ocred(qt_root(project.root) / f"{page.stem}.OCRed", texts)
                write_pdic(pdic_path(page), entries, image.width, _neighbors(project, page))
                print(f"[{number}/{len(pages)}] {page.name}: OCR {len(texts)} 个词条")
            elif args.command == "split-lines":
                records = split_single_lines(page, entries, project.settings, qt_root(project.root) / "PSW")
                append_crop_log(project.root, records)
                print(f"[{number}/{len(pages)}] {page.name}: 导出 {len(records)} 张单行图")
            elif args.command == "split-whole":
                records = split_whole_entries(page, entries, project.settings, qt_root(project.root) / "PWW")
                append_crop_log(project.root, records)
                print(f"[{number}/{len(pages)}] {page.name}: 导出 {len(records)} 张词条图")
        return 0
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
