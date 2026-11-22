"""Build + smoke test + package a genuine native app on the current OS.

Run with PyInstaller installed. This is deliberately NOT cross-compilation.
"""
from __future__ import annotations

from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "software_audit" / "assets"
DIST = ROOT / "dist"
RELEASES = ROOT / "releases"
APP = "APO_TIMIMO"
VERSION = "0.1.1"


def checked(args: list[str], **kwargs) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def build() -> Path:
    system = platform.system()
    if system not in ("Windows", "Darwin", "Linux"):
        raise RuntimeError(f"Unsupported build host: {system}")
    RELEASES.mkdir(exist_ok=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--name", APP, "--collect-all", "reportlab",
               "--add-data", f"{ASSETS}{os.pathsep}software_audit/assets"]
    if system == "Windows":
        command += ["--onefile", "--windowed", "--icon", str(ASSETS / "app-icon.ico")]
    elif system == "Darwin":
        command += ["--onedir", "--windowed", "--icon", str(ASSETS / "app-icon.icns")]
    else:
        command += ["--onedir", "--windowed"]
    command.append(str(ROOT / "launcher.py"))
    checked(command)

    if system == "Darwin":
        built = DIST / f"{APP}.app"
        executable = built / "Contents" / "MacOS" / APP
        name = "macOS_arm64" if platform.machine().lower() in ("arm64", "aarch64") else "macOS_x64"
    elif system == "Windows":
        built = DIST / f"{APP}.exe"
        executable = built
        name = "Windows_x64" if platform.machine().lower() in ("amd64", "x86_64") else "Windows_arm64"
    else:
        built = DIST / APP
        executable = built / APP
        name = "Linux_x64" if platform.machine().lower() in ("x86_64", "amd64") else "Linux_arm64"

    if not executable.is_file():
        raise RuntimeError(f"PyInstaller output missing: {executable}")
    checked([str(executable), "--self-test"])
    base = f"{APP}_v{VERSION}_{name}"

    if system == "Darwin":
        output = RELEASES / f"{base}.zip"
        checked(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(built), str(output)])
    elif system == "Windows":
        output = RELEASES / f"{base}.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
            archive.write(built, built.name)
            archive.writestr("README.txt", "АПО.ТИМИМО\nRun APO_TIMIMO.exe.\nUnsigned build: SmartScreen may show a warning.\n")
    else:
        output = RELEASES / f"{base}.tar.gz"
        with tarfile.open(output, "w:gz") as archive:
            archive.add(built, arcname=APP)
            start_script = ROOT / "packaging" / "linux" / "Start_APO_TIMIMO.sh"
            if start_script.exists():
                archive.add(start_script, arcname="Start_APO_TIMIMO.sh")
            desktop = ROOT / "packaging" / "linux" / "Install_Desktop_Shortcut.sh"
            if desktop.exists():
                archive.add(desktop, arcname="Install_Desktop_Shortcut.sh")
            archive.add(ASSETS / "app-icon.png", arcname="app-icon.png")
    print("RELEASE:", output, f"({output.stat().st_size} bytes)")
    return output


if __name__ == "__main__":
    build()
