from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
import subprocess
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cc_cedict import (
    DOWNLOAD_PAGE_URL as CC_CEDICT_DOWNLOAD_PAGE_URL,
    install_from_file as install_cc_cedict_from_file,
    status as cc_cedict_status,
)
from .chinese_simplify import opencc_runtime_status
from .ocr_engines import lens_status, tesseract_status
from .models import resolved_tesseract_language


TESSERACT_DOC_URL = "https://tesseract-ocr.github.io/tessdoc/Installation.html"
TESSDATA_FAST_URL = "https://github.com/tesseract-ocr/tessdata_fast"


@dataclass(frozen=True)
class TesseractInstallPlan:
    platform_name: str
    manager: str
    commands: tuple[str, ...]
    note: str
    url: str = TESSERACT_DOC_URL


def _language_parts(language: str) -> list[str]:
    return [part.strip() for part in str(language or "").split("+") if part.strip()]


def _apt_language_package(language: str) -> str:
    return "tesseract-ocr-" + language.replace("_", "-")


def tesseract_install_plan(
    language: str,
    *,
    system: str | None = None,
    which=shutil.which,
) -> TesseractInstallPlan:
    """Return conservative, user-facing Tesseract installation guidance.

    Picture Capture deliberately does not execute system package managers on the
    user's behalf.  The plan is displayed/copyable and the user explicitly runs
    it outside the application.
    """
    system_name = (system or platform.system()).strip()
    languages = _language_parts(language)

    if system_name == "Windows":
        commands = ("winget install --id tesseract-ocr.tesseract -e",) if which("winget") else ()
        note = (
            "Windows 检测到 WinGet，可用下方命令安装 Tesseract。安装完成后回到环境中心重新检测。"
            if commands
            else "未检测到 WinGet。请打开 Tesseract 安装文档，安装后回到环境中心重新检测。"
        )
        if languages:
            note += " 所需语言：" + " + ".join(languages) + "；若安装后仍提示缺失，请按“语言包帮助”补充 traineddata。"
        return TesseractInstallPlan("Windows", "winget" if commands else "", commands, note)

    if system_name == "Darwin":
        if which("brew"):
            commands = ("brew install tesseract",)
            if any(lang not in {"eng", "osd"} for lang in languages):
                commands += ("brew install tesseract-lang",)
            note = "Homebrew 的 tesseract 默认包含 eng/osd；其他语言使用 tesseract-lang。"
            return TesseractInstallPlan("macOS", "Homebrew", commands, note)
        return TesseractInstallPlan(
            "macOS", "", (),
            "未检测到 Homebrew。可打开 Tesseract 安装文档；如果使用 Homebrew，安装 tesseract，其他语言再安装 tesseract-lang。",
        )

    if system_name == "Linux":
        if which("apt") or which("apt-get"):
            packages = ["tesseract-ocr"] + [_apt_language_package(lang) for lang in languages]
            command = "sudo apt install " + " ".join(dict.fromkeys(packages))
            return TesseractInstallPlan(
                "Linux", "apt", (command,),
                "检测到 apt。命令同时安装 Tesseract 和当前项目所需语言包。",
            )
        if which("dnf"):
            return TesseractInstallPlan(
                "Linux", "dnf", ("sudo dnf install tesseract",),
                "检测到 dnf。先安装 Tesseract；不同发行版的语言包命名可能不同，缺少语言时请打开语言包帮助。",
            )
        if which("pacman"):
            return TesseractInstallPlan(
                "Linux", "pacman", ("sudo pacman -S tesseract",),
                "检测到 pacman。先安装 Tesseract；语言数据包请按发行版仓库命名安装。",
            )
        return TesseractInstallPlan(
            "Linux", "", (),
            "未识别 apt/dnf/pacman。请使用当前发行版的软件包管理器安装 Tesseract 及所需语言包。",
        )

    return TesseractInstallPlan(
        system_name or "Unknown", "", (),
        "当前平台没有内置安装命令建议，请参考 Tesseract 官方安装文档。",
    )


def ocr_installer_path(root: Path, system: str | None = None) -> Path | None:
    system_name = (system or platform.system()).strip()
    if system_name == "Windows":
        path = root / "install_ocr_windows.bat"
    elif system_name == "Darwin":
        path = root / "install_ocr_macos.command"
    elif system_name == "Linux":
        path = root / "install_ocr_linux.sh"
    else:
        return None
    return path if path.is_file() else None


def launch_ocr_installer(root: Path, *, parent: tk.Misc | None = None) -> bool:
    """Launch the platform installer when a visible interactive route is safe."""
    script = ocr_installer_path(root)
    if script is None:
        messagebox.showwarning("OCR 安装器", "未找到当前平台的 OCR 安装脚本。", parent=parent)
        return False

    system_name = platform.system()
    try:
        if system_name == "Windows":
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                raise OSError("当前 Python 不支持 os.startfile")
            startfile(str(script))
            return True
        if system_name == "Darwin":
            subprocess.Popen(["open", str(script)], cwd=root)
            return True
        # Linux desktop terminals differ widely. Avoid launching an interactive
        # shell invisibly; provide one explicit command for the user instead.
        command = f'cd "{root}" && ./{script.name}'
        if parent is not None:
            try:
                parent.clipboard_clear()
                parent.clipboard_append(command)
                parent.update_idletasks()
            except tk.TclError:
                pass
        messagebox.showinfo(
            "OCR 安装器",
            "Linux 安装命令已复制到剪贴板：\n\n" + command +
            "\n\n请在终端粘贴运行。完成后回到环境中心点击【重新检测】。",
            parent=parent,
        )
        return True
    except Exception as exc:
        messagebox.showerror("无法启动 OCR 安装器", str(exc), parent=parent)
        return False


class EnvironmentCenterWindow(tk.Toplevel):
    """Unified environment status + next-action window for optional components."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app
        self.title("Picture Capture 环境中心")
        self.geometry("860x650")
        self.minsize(720, 520)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._status_labels: dict[str, ttk.Label] = {}
        self._diagnostic_text = ""
        self._build()
        self.after(10, self.refresh)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="环境中心", font=("TkDefaultFont", 15, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="集中检查 OCR、简繁转换和本地词典。缺失组件会直接给出下一步操作；不会后台偷偷安装系统程序。",
            wraplength=800,
        ).pack(anchor="w", pady=(3, 10))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="重新检测", command=self.refresh).pack(side="left")
        ttk.Button(actions, text="安装/切换 Paddle OCR", command=self._launch_ocr_installer).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="OCR 设置", command=self._open_ocr_settings).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="复制诊断信息", command=self._copy_diagnostics).pack(side="right")

        self.status_var = tk.StringVar(value="准备检测…")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(0, 6))

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(canvas_window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._add_card(
            body, "paddle", "PaddleOCR / PaddlePaddle",
            [("安装 / 切换", self._launch_ocr_installer)],
        )
        self._add_card(
            body, "lens", "Google Lens",
            [("OCR 设置", self._open_ocr_settings), ("安装 / 修复", self._launch_ocr_installer)],
        )
        self._add_card(
            body, "tesseract", "Tesseract",
            [
                ("选择程序", self._choose_tesseract),
                ("安装帮助", self._show_tesseract_install_help),
                ("语言包帮助", self._show_tesseract_language_help),
            ],
        )
        self._add_card(body, "opencc", "OpenCC", [("修复核心环境", self._show_opencc_help)])
        self._add_card(body, "cedict", "CC-CEDICT", [("安装 / 更新", self._install_cedict)])
        self._add_card(body, "network", "网络词典", [("说明", self._show_network_help)])

    def _add_card(self, parent: ttk.Frame, key: str, title: str, actions) -> None:
        card = ttk.LabelFrame(parent, text=title, padding=10)
        card.pack(fill="x", pady=(0, 8))
        label = ttk.Label(card, text="尚未检测", justify="left", wraplength=650)
        label.pack(side="left", fill="x", expand=True, anchor="w")
        buttons = ttk.Frame(card)
        buttons.pack(side="right", padx=(10, 0))
        for text, command in actions:
            ttk.Button(buttons, text=text, command=command).pack(anchor="e", pady=2)
        self._status_labels[key] = label

    def refresh(self) -> None:
        self.status_var.set("正在后台检测环境…")
        settings = self.app.settings
        language = resolved_tesseract_language(settings)
        executable = str(settings.ocr_executable)

        def worker():
            paddle_text = self.app._paddle_environment_text(settings)
            tess = tesseract_status(executable, language)
            lens = lens_status()
            official_opencc = self.app._distribution_version("opencc")
            legacy_opencc = self.app._distribution_version("opencc-python-reimplemented")
            opencc_runtime = opencc_runtime_status(retry=True)
            try:
                cedict = cc_cedict_status()
                cedict_error = ""
            except Exception as exc:
                cedict = None
                cedict_error = str(exc)
            return paddle_text, tess, lens, official_opencc, legacy_opencc, opencc_runtime, cedict, cedict_error

        def done(payload) -> None:
            if not self.winfo_exists():
                return
            paddle_text, tess, lens, official_opencc, legacy_opencc, opencc_runtime, cedict, cedict_error = payload

            self._status_labels["paddle"].configure(text=paddle_text)

            if lens.get("available"):
                lens_text = (
                    f"✓ chrome-lens-py {lens.get('version') or '版本未知'} 已准备\n"
                    "默认不会自动联网调用；需要时在 OCR 设置中开启 Lens 模式。"
                )
            else:
                lens_text = f"✗ Google Lens 组件不可用：{lens.get('error') or '未知错误'}"
            self._status_labels["lens"].configure(text=lens_text)

            requested = tess.get("requested_languages", [])
            if tess.get("available"):
                tess_text = (
                    f"✓ {tess.get('version') or 'Tesseract'}\n"
                    f"路径：{tess.get('resolved')}\n"
                    f"当前项目语言：{', '.join(requested) or '未指定'}"
                )
                self.app.settings.ocr_executable = str(tess.get("resolved") or executable)
                if self.app.project:
                    self.app.save_settings()
            elif tess.get("resolved"):
                missing = ", ".join(tess.get("missing_languages", [])) or "未知"
                tess_text = (
                    f"⚠ Tesseract 已安装，但当前项目所需语言包不完整\n"
                    f"路径：{tess.get('resolved')}\n缺少：{missing}"
                )
            else:
                tess_text = (
                    "○ Tesseract 未安装或未找到\n"
                    f"当前项目建议语言：{', '.join(requested) or language or 'eng'}\n"
                    "它是可选第二 OCR，不影响 PaddleOCR 主流程。"
                )
            self._status_labels["tesseract"].configure(text=tess_text)

            if opencc_runtime.get("available") and official_opencc:
                opencc_text = f"✓ OpenCC {official_opencc}（官方）运行正常\n简化配置：t2s.json（词组优先）"
                if legacy_opencc:
                    opencc_text += f"\n⚠ 另检测到旧包 opencc-python-reimplemented {legacy_opencc}"
            elif official_opencc:
                opencc_text = f"⚠ OpenCC {official_opencc} 已安装但初始化失败：{opencc_runtime.get('error') or '未知错误'}"
            else:
                opencc_text = "✗ OpenCC 核心依赖未安装。"
            self._status_labels["opencc"].configure(text=opencc_text)

            if cedict is not None and cedict.installed:
                cedict_text = f"✓ 已安装 {cedict.entry_count:,} 条\n位置：{cedict.path}"
            elif cedict is not None:
                cedict_text = f"○ 未安装\n目标位置：{cedict.path}\n仅需下载一次，所有项目共用。"
            else:
                cedict_text = f"⚠ 状态检查失败：{cedict_error or '未知错误'}"
            self._status_labels["cedict"].configure(text=cedict_text)

            self._status_labels["network"].configure(
                text="✓ 萌典 / Wiktionary / 网络搜索无需额外安装；仅在使用相关功能时联网。"
            )

            self._diagnostic_text = "\n\n".join([
                "[PaddleOCR]\n" + paddle_text,
                "[Google Lens]\n" + lens_text,
                "[Tesseract]\n" + tess_text,
                "[OpenCC]\n" + opencc_text,
                "[CC-CEDICT]\n" + cedict_text,
            ])
            self.status_var.set("✓ 环境检测完成")

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if self.winfo_exists():
                self.status_var.set("⚠ 环境检测失败")
                messagebox.showerror("环境检测失败", str(exc), parent=self)

        self.app._start_ui_worker(f"environment-center-{id(self)}", worker, done, failed)

    def _open_ocr_settings(self) -> None:
        self.app.open_settings()

    def _launch_ocr_installer(self) -> None:
        root = Path(__file__).resolve().parents[2]
        launch_ocr_installer(root, parent=self)

    def _choose_tesseract(self) -> None:
        initial = str(getattr(self.app.settings, "ocr_executable", "") or "")
        initialdir = str(Path(initial).expanduser().parent) if Path(initial).expanduser().is_file() else ""
        path = filedialog.askopenfilename(
            parent=self,
            title="选择 Tesseract 可执行程序",
            initialdir=initialdir or None,
            filetypes=[("Tesseract", "tesseract.exe" if platform.system() == "Windows" else "tesseract"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.app.settings.ocr_executable = path
        if self.app.project:
            self.app.save_settings()
        self.refresh()

    def _copy(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except tk.TclError:
            return

    def _show_tesseract_install_help(self) -> None:
        language = resolved_tesseract_language(self.app.settings)
        plan = tesseract_install_plan(language)
        commands = "\n".join(plan.commands)
        if commands:
            self._copy(commands)
            command_text = f"\n\n建议命令（已复制）：\n{commands}"
        else:
            command_text = ""
        if messagebox.askyesno(
            "Tesseract 安装帮助",
            plan.note + command_text + "\n\n是否打开官方安装文档？",
            parent=self,
        ):
            webbrowser.open(plan.url)

    def _show_tesseract_language_help(self) -> None:
        language = resolved_tesseract_language(self.app.settings)
        plan = tesseract_install_plan(language)
        languages = _language_parts(language)
        if platform.system() == "Darwin" and shutil.which("brew"):
            commands = "brew install tesseract-lang"
            self._copy(commands)
            detail = "Homebrew 语言包命令已复制：\n" + commands
        elif platform.system() == "Linux" and (shutil.which("apt") or shutil.which("apt-get")):
            packages = [_apt_language_package(lang) for lang in languages]
            command = "sudo apt install " + " ".join(dict.fromkeys(packages))
            self._copy(command)
            detail = "当前项目语言包命令已复制：\n" + command
        else:
            names = ", ".join(f"{lang}.traineddata" for lang in languages) or "对应 .traineddata"
            detail = (
                "当前项目需要：" + names +
                "\n\n如果系统包管理器没有现成语言包，可从 tessdata_fast 获取并放入 Tesseract 的 tessdata 目录。"
            )
        if messagebox.askyesno("Tesseract 语言包帮助", detail + "\n\n是否打开 tessdata_fast？", parent=self):
            webbrowser.open(TESSDATA_FAST_URL)

    def _show_opencc_help(self) -> None:
        command = "uv sync --locked --no-dev"
        self._copy(command)
        messagebox.showinfo(
            "OpenCC 修复",
            "OpenCC 是 Picture Capture 核心依赖，不需要单独下载安装。\n\n"
            "核心环境修复命令已复制：\n" + command +
            "\n\n若仍异常，可重新运行当前平台的 OCR 安装器建立项目环境。",
            parent=self,
        )

    def _install_cedict(self) -> None:
        try:
            state = cc_cedict_status()
        except Exception:
            state = None
        installed_text = ""
        if state is not None and state.installed:
            installed_text = f"\n\n当前已安装：{state.entry_count:,} 条\n{state.path}"
        choose_local = messagebox.askyesno(
            "CC-CEDICT 安装 / 更新",
            "是否已经从 CC-CEDICT 官方下载页取得数据文件？\n\n"
            "【是】选择本地 ZIP / GZ / TXT / U8 文件并安装\n"
            "【否】打开官方下载页" + installed_text,
            parent=self,
        )
        if not choose_local:
            webbrowser.open(CC_CEDICT_DOWNLOAD_PAGE_URL)
            return
        source = filedialog.askopenfilename(
            parent=self,
            title="选择已下载的 CC-CEDICT 数据文件",
            filetypes=[
                ("CC-CEDICT 数据", "*.zip *.gz *.txt *.u8"),
                ("ZIP", "*.zip"),
                ("GZip", "*.gz"),
                ("文本", "*.txt *.u8"),
                ("所有文件", "*.*"),
            ],
        )
        if not source:
            return
        try:
            installed = install_cc_cedict_from_file(source)
        except Exception as exc:
            messagebox.showerror("CC-CEDICT 安装失败", str(exc), parent=self)
            return
        messagebox.showinfo(
            "CC-CEDICT 已安装",
            f"已安装 {installed.entry_count:,} 条。\n\n位置：\n{installed.path}\n\n"
            "该词典为所有 Picture Capture 项目共用。",
            parent=self,
        )
        self.refresh()

    def _show_network_help(self) -> None:
        messagebox.showinfo(
            "网络词典",
            "萌典、Wiktionary 与网络搜索不需要安装额外组件。\n\n"
            "它们只在校对时按需联网；网络不可用时不会阻止本地 OCR、OpenCC 或 CC-CEDICT 工作。",
            parent=self,
        )

    def _copy_diagnostics(self) -> None:
        if not self._diagnostic_text:
            messagebox.showinfo("复制诊断信息", "请先完成一次环境检测。", parent=self)
            return
        self._copy(self._diagnostic_text)
        self.status_var.set("✓ 诊断信息已复制到剪贴板")
