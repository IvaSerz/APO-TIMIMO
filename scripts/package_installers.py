"""Create native installers from the built PyInstaller application.

Windows: Inno Setup per-user Setup.exe; macOS: drag-and-drop DMG;
Linux: Debian package. Run only on native host after scripts/build_release.py.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASES = ROOT / "releases"
ASSETS = ROOT / "software_audit" / "assets"
APP = "APO_TIMIMO"
VERSION = "0.1.2"


def run(args: list[str], **kwargs) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def package_windows() -> Path:
    exe = DIST / f"{APP}.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"Missing PyInstaller binary: {exe}")
    candidates = [
        shutil.which("ISCC.exe"),
        os.environ.get("INNO_SETUP_COMPILER"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    compiler = next((x for x in candidates if x and Path(x).is_file()), None)
    if not compiler:
        raise RuntimeError("Inno Setup 6 not installed; install it on the Windows build host")
    env = os.environ.copy()
    env["APO_REPO_ROOT"] = str(ROOT)
    run([compiler, str(ROOT / "packaging" / "windows" / "apo_timimo.iss")], env=env)
    output = RELEASES / f"{APP}_v{VERSION}_Windows_x64_Setup.exe"
    if not output.is_file():
        raise FileNotFoundError(output)
    return output


def package_macos() -> Path:
    app = DIST / f"{APP}.app"
    if not app.is_dir():
        raise FileNotFoundError(f"Missing PyInstaller application: {app}")
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    output = RELEASES / f"{APP}_v{VERSION}_macOS_{arch}.dmg"
    with tempfile.TemporaryDirectory(prefix="apo-dmg-") as tmp:
        stage = Path(tmp) / "Install APO.TIMIMO"
        stage.mkdir()
        shutil.copytree(app, stage / app.name, symlinks=True)
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        run(["hdiutil", "create", "-volname", "APO.TIMIMO", "-srcfolder", str(stage),
             "-ov", "-format", "UDZO", str(output)])
    if not output.is_file():
        raise FileNotFoundError(output)
    return output


def package_linux() -> Path:
    built = DIST / APP
    if not (built / APP).is_file():
        raise FileNotFoundError(f"Missing PyInstaller binary: {built / APP}")
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64"):
        raise RuntimeError("DEB packaging currently supports x86_64 Ubuntu build runners only")
    output = RELEASES / f"{APP}_v{VERSION}_Linux_amd64.deb"
    with tempfile.TemporaryDirectory(prefix="apo-deb-") as tmp:
        root = Path(tmp) / f"apo-timimo_{VERSION}_amd64"
        appdir = root / "opt" / "apo-timimo"
        shutil.copytree(built, appdir, symlinks=True)
        (root / "DEBIAN").mkdir(parents=True)
        (root / "DEBIAN" / "control").write_text(
            "Package: apo-timimo\n"
            f"Version: {VERSION}\n"
            "Section: utils\n"
            "Priority: optional\n"
            "Architecture: amd64\n"
            "Maintainer: KAIRO Team <noreply@github.com>\n"
            "Depends: libc6 (>= 2.35), libx11-6, libxext6, libxrender1\n"
            "Description: APO.TIMIMO - locally installed software inventory and audit\n"
            " Scan installed applications on a single computer, save snapshots and export reports.\n",
            encoding="utf-8")
        bindir = root / "usr" / "bin"
        bindir.mkdir(parents=True)
        runner = bindir / "apo-timimo"
        runner.write_text('#!/bin/sh\nexec /opt/apo-timimo/APO_TIMIMO "$@"\n', encoding="utf-8")
        runner.chmod(0o755)
        icons = root / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        icons.mkdir(parents=True)
        shutil.copy2(ASSETS / "app-icon.png", icons / "apo-timimo.png")
        entries = root / "usr" / "share" / "applications"
        entries.mkdir(parents=True)
        (entries / "apo-timimo.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=АПО.ТИМИМО\n"
            "Comment=Аудит установленного программного обеспечения\n"
            "Exec=apo-timimo\nIcon=apo-timimo\nTerminal=false\nCategories=Utility;System;\n",
            encoding="utf-8")
        run(["dpkg-deb", "--build", "--root-owner-group", str(root), str(output)])
    if not output.is_file():
        raise FileNotFoundError(output)
    return output


def main() -> None:
    RELEASES.mkdir(exist_ok=True)
    host = platform.system()
    if host == "Windows":
        path = package_windows()
    elif host == "Darwin":
        path = package_macos()
    elif host == "Linux":
        path = package_linux()
    else:
        raise RuntimeError(f"Unsupported OS: {host}")
    print(f"INSTALLER READY: {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
