"""Offline Debian 13 x86-64 Linux bundle with a private Python 3.13 interpreter.

This produces a *tested Linux executable package* without using PyInstaller.
It does not claim distribution-wide compatibility: glibc and X11 are required.
This must be run on the matching Debian build host only.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import tarfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "releases" / "APO_TIMIMO_Linux_Debian13_x86_64"
RELEASES = ROOT / "releases"
SYSTEM = Path("/usr/lib/python3.13")
SITE = Path("/opt/pyvenv/lib/python3.13/site-packages")


def ignore_runtime(directory, names):
    ignored = {name for name in names if name in {
        "__pycache__", "test", "tests", "config-3.13-x86_64-linux-gnu",
        "idlelib", "turtledemo", "ensurepip", "venv", "pydoc_data",
    } or name.endswith((".pyc", ".pyo"))}
    return ignored


def main():
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Linux x86_64 build host required")
    if not SYSTEM.exists() or not Path('/usr/bin/python3.13').exists():
        raise RuntimeError("Requires Debian 13 Python 3.13 base runtime")
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    dest = BUNDLE / "runtime"
    (dest / "bin").mkdir(parents=True)
    (dest / "lib").mkdir(parents=True)
    (dest / "share").mkdir(parents=True)
    shutil.copy2("/usr/bin/python3.13", dest / "bin/python3.13")
    shutil.copytree(SYSTEM, dest / "lib/python3.13", ignore=ignore_runtime, symlinks=True)
    shutil.copytree("/usr/share/tcltk", dest / "share/tcltk", symlinks=True)
    (dest / "lib/python3.13/site-packages").mkdir(exist_ok=True)
    for package in ("reportlab", "PIL", "pillow.libs", "charset_normalizer"):
        shutil.copytree(SITE / package, dest / "lib/python3.13/site-packages" / package,
                        ignore=ignore_runtime, symlinks=True)
    for metadata in ("reportlab-4.4.9.dist-info", "pillow-12.3.0.dist-info", "charset_normalizer-3.4.7.dist-info"):
        if (SITE / metadata).exists():
            shutil.copytree(SITE / metadata, dest / "lib/python3.13/site-packages" / metadata,
                            ignore=ignore_runtime)
    (dest / "lib/native").mkdir(exist_ok=True)
    for library in ("libtk8.6.so", "libtcl8.6.so"):
        shutil.copy2(Path("/usr/lib/x86_64-linux-gnu") / library, dest / "lib/native" / library)
    (BUNDLE / "app").mkdir()
    shutil.copytree(ROOT / "software_audit", BUNDLE / "app/software_audit", ignore=ignore_runtime)
    shutil.copy2(ROOT / "launcher.py", BUNDLE / "app/launcher.py")
    readme = """АПО.ТИМИМО — Linux x86_64 (Debian 13-based standalone runtime)

Запуск: ./APO_TIMIMO
Не требует предварительной установки Python или PyInstaller.
Требуются x86_64, GNU/Linux с glibc >= 2.41, X11 и соответствующие
системные графические библиотеки. На Ubuntu 22/24 и старых дистрибутивах
может не запускаться. На других дистрибутивах используйте GitHub Actions
сборку Linux либо исходный код.
Проверка без графики: ./APO_TIMIMO --self-test
Необходимые для PDF системные шрифты должны быть установлены.
Программа локальная и ничего не устанавливает/удаляет.
Разработка: команда КАИРО; разработчик: Иващенко Сергей Сергеевич.
"""
    (BUNDLE / "README.txt").write_text(readme, encoding="utf-8")
    launch = """#!/bin/sh
set -eu
BASE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
export PYTHONHOME="$BASE/runtime"
export PYTHONPATH="$BASE/app:$BASE/runtime/lib/python3.13/site-packages"
export TCL_LIBRARY="$BASE/runtime/share/tcltk/tcl8.6"
export TK_LIBRARY="$BASE/runtime/share/tcltk/tk8.6"
export LD_LIBRARY_PATH="$BASE/runtime/lib/native${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$BASE/runtime/bin/python3.13" "$BASE/app/launcher.py" "$@"
"""
    script = BUNDLE / "APO_TIMIMO"
    script.write_text(launch, encoding="utf-8")
    script.chmod(0o755)
    shutil.copy2(ROOT / "software_audit/assets/app-icon.png", BUNDLE / "app-icon.png")
    # License metadata from Python and binary distributions.
    (BUNDLE / "LICENSES").mkdir()
    shutil.copy2("/usr/share/doc/python3.13/copyright", BUNDLE / "LICENSES/python3.13-debian-copyright")
    tarfile_path = RELEASES / "APO_TIMIMO_v0.1.1_Linux_Debian13_x86_64.tar.gz"
    with tarfile.open(tarfile_path, "w:gz") as archive:
        archive.add(BUNDLE, arcname=BUNDLE.name, recursive=True)
    print(f"CREATED: {tarfile_path} ({tarfile_path.stat().st_size:,} bytes)")


if __name__ == '__main__':
    main()
