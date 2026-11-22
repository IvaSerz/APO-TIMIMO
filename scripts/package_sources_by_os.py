"""Create transparent Python-required fallback launch bundles + one CI source archive."""
from __future__ import annotations

from pathlib import Path
import os
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "releases"
VERSION = "0.1.1"


def add_tree(archive: zipfile.ZipFile, src: Path, prefix: str = "") -> None:
    for file in sorted(src.rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts and not file.name.endswith((".pyc", ".pyo")):
            archive.write(file, f"{prefix}{file.relative_to(ROOT).as_posix()}")


def add_content(archive: zipfile.ZipFile, name: str, content: str, executable: bool = False) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = ((stat.S_IFREG | (0o755 if executable else 0o644)) & 0xffff) << 16
    archive.writestr(info, content.encode("utf-8"))


def main() -> None:
    DEST.mkdir(exist_ok=True)
    windows = DEST / f"APO_TIMIMO_Windows_SOURCE_v{VERSION}.zip"
    with zipfile.ZipFile(windows, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        add_tree(archive, ROOT / "software_audit")
        archive.write(ROOT / "launcher.py", "launcher.py")
        add_content(archive, "START_WINDOWS.cmd", '@echo off\r\ncd /d "%~dp0"\r\npy -3 launcher.py\r\nif errorlevel 1 pause\r\n')
        add_content(archive, "README_WINDOWS.txt", "АПО.ТИМИМО — исходный пакет для Windows.\nТребуется Python 3.10+ (python.org) с Tkinter.\nЗапуск: START_WINDOWS.cmd.\nДля PDF дополнительно: py -3 -m pip install reportlab.\nЭто НЕ готовый EXE. Настоящий EXE создаётся через GitHub Actions — BUILDING.md в полном архиве.\n")
    mac = DEST / f"APO_TIMIMO_macOS_SOURCE_v{VERSION}.zip"
    with zipfile.ZipFile(mac, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        add_tree(archive, ROOT / "software_audit")
        archive.write(ROOT / "launcher.py", "launcher.py")
        add_content(archive, "START_MACOS.command", '#!/bin/sh\ncd "$(dirname "$0")" || exit 1\npython3 launcher.py\n', executable=True)
        add_content(archive, "README_MACOS.txt", "АПО.ТИМИМО — исходный пакет для macOS (Intel и Apple Silicon).\nТребуется Python 3.10+ с Tkinter (python.org).\nЗапуск из Terminal: sh START_MACOS.command\nДля PDF: python3 -m pip install reportlab.\nЭто НЕ готовое .app. Настоящее .app создаётся через GitHub Actions — BUILDING.md в полном архиве.\n")
    source = DEST / f"APO_TIMIMO_Source_and_Build_All_OS_v{VERSION}.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        add_tree(archive, ROOT / "software_audit")
        add_tree(archive, ROOT / "tests")
        add_tree(archive, ROOT / "scripts")
        add_tree(archive, ROOT / "packaging")
        add_tree(archive, ROOT / ".github")
        for name in ("launcher.py", "README.md", "ABOUT.md", "BUILDING.md", "run_windows.bat", "run_macos_linux.command", "requirements-optional.txt", ".gitignore"):
            archive.write(ROOT / name, name)
    for archive in (windows, mac, source):
        print(archive.name, archive.stat().st_size)


if __name__ == '__main__':
    main()
