"""Read-only software inventory using OS-maintained sources.

No package installation, removal, WMI Win32_Product query, remote network calls,
or execution of files discovered during scanning.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
from typing import Callable

from .models import Inventory, Software, deduplicate

Progress = Callable[[str], None]


def _run(args: list[str], timeout: int = 45) -> tuple[str, str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=timeout, check=False,
                                   creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", str(exc)
    if completed.returncode != 0:
        return "", (completed.stderr or f"Код завершения {completed.returncode}").strip()[:300]
    return completed.stdout, ""


def _notify(callback: Progress | None, message: str) -> None:
    if callback:
        callback(message)


def scan_inventory(*, include_store: bool = True, include_profiler: bool = True,
                   progress: Progress | None = None, system: str | None = None) -> Inventory:
    os_name = system or platform.system()
    result = Inventory()
    entries: list[Software] = []

    def collect(title: str, method: Callable[[], list[Software]]) -> None:
        _notify(progress, title)
        try:
            entries.extend(method())
            result.methods.append(title)
        except Exception as exc:
            result.warnings.append(f"{title}: {type(exc).__name__}: {exc}")

    if os_name == "Windows":
        collect("Реестр Windows (пользователь и компьютер)", _windows_registry)
        if include_store:
            collect("Приложения Microsoft Store", lambda: _windows_store(result.warnings))
    elif os_name == "Darwin":
        collect("Приложения macOS (.app)", lambda: _mac_app_bundles(result.warnings))
        if include_profiler:
            collect("Каталог macOS system_profiler", lambda: _mac_profiler(result.warnings))
        if shutil.which("brew") or Path("/opt/homebrew/bin/brew").is_file() or Path("/usr/local/bin/brew").is_file():
            collect("Пакеты Homebrew", lambda: _homebrew(result.warnings))
    elif os_name == "Linux":
        for command, label, reader in (
            ("dpkg-query", "Пакеты dpkg", _linux_dpkg),
            ("rpm", "Пакеты RPM", _linux_rpm),
            ("pacman", "Пакеты pacman", _linux_pacman),
            ("flatpak", "Приложения Flatpak", _linux_flatpak),
            ("snap", "Пакеты Snap", _linux_snap),
        ):
            if shutil.which(command):
                collect(label, lambda reader=reader: reader(result.warnings))
    else:
        result.warnings.append(f"Операционная система {os_name!r} пока не поддерживается")
    result.records = deduplicate(entries)
    _notify(progress, f"Обнаружено записей: {len(result.records)}")
    return result


def _windows_registry() -> list[Software]:
    import winreg  # Only available on Windows

    registry_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    entries: list[Software] = []

    def value(key, name: str, default=""):
        try:
            return winreg.QueryValueEx(key, name)[0]
        except (FileNotFoundError, OSError):
            return default

    for hive, scope in ((winreg.HKEY_LOCAL_MACHINE, "Все пользователи"),
                        (winreg.HKEY_CURRENT_USER, "Текущий пользователь")):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                parent = winreg.OpenKey(hive, registry_key, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with parent:
                index = 0
                while True:
                    try:
                        child_name = winreg.EnumKey(parent, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        child = winreg.OpenKey(parent, child_name, 0, winreg.KEY_READ | view)
                    except OSError:
                        continue
                    with child:
                        name = str(value(child, "DisplayName")).strip()
                        if not name or value(child, "SystemComponent", 0) == 1:
                            continue
                        # Updates and registry component entries are not standalone applications.
                        if value(child, "ParentKeyName"):
                            continue
                        installed = str(value(child, "InstallDate"))
                        if re.fullmatch(r"\d{8}", installed):
                            installed = f"{installed[:4]}-{installed[4:6]}-{installed[6:]}"
                        entries.append(Software(
                            name=name, version=str(value(child, "DisplayVersion")),
                            publisher=str(value(child, "Publisher")), source="Windows Registry",
                            install_path=str(value(child, "InstallLocation")).strip(' "'),
                            installed_at=installed, scope=scope,
                        ))
    return entries


def _windows_store(warnings: list[str]) -> list[Software]:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        warnings.append("PowerShell не найден: Microsoft Store не просканирован")
        return []
    script = ("Get-AppxPackage | Where-Object { -not $_.IsFramework } | "
              "Select-Object Name,Version,Publisher,InstallLocation,PackageFamilyName | "
              "ConvertTo-Json -Depth 3 -Compress")
    output, err = _run([powershell, "-NoProfile", "-NonInteractive", "-Command", script], 60)
    if err:
        warnings.append(f"Microsoft Store: {err}")
        return []
    if not output.strip():
        return []
    try:
        parsed = json.loads(output.lstrip("\ufeff"))
    except json.JSONDecodeError:
        warnings.append("Microsoft Store: не удалось разобрать ответ PowerShell")
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    return [Software(name=str(item.get("Name") or ""), version=str(item.get("Version") or ""),
                     publisher=str(item.get("Publisher") or ""),
                     install_path=str(item.get("InstallLocation") or ""),
                     identifier=str(item.get("PackageFamilyName") or ""),
                     source="Microsoft Store", scope="Текущий пользователь")
            for item in parsed if isinstance(item, dict) and item.get("Name")]


def _mac_app_dirs() -> list[Path]:
    return [Path("/Applications"), Path("/System/Applications"),
            Path.home() / "Applications", Path("/Library/Applications")]


def _read_app_bundle(path: Path) -> Software:
    plist = path / "Contents" / "Info.plist"
    metadata = {}
    try:
        with plist.open("rb") as file:
            metadata = plistlib.load(file)
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
        pass
    name = (metadata.get("CFBundleDisplayName") or metadata.get("CFBundleName")
            or path.stem)
    version = metadata.get("CFBundleShortVersionString") or metadata.get("CFBundleVersion") or ""
    # macOS bundle identifiers are identifiers, not proof of publisher identity.
    return Software(name=str(name), version=str(version), publisher="",
                    source="macOS App Bundle", install_path=str(path),
                    identifier=str(metadata.get("CFBundleIdentifier") or ""),
                    scope="Пользователь" if str(path).startswith(str(Path.home())) else "Система")


def _mac_app_bundles(warnings: list[str]) -> list[Software]:
    entries: list[Software] = []
    for root in _mac_app_dirs():
        if not root.exists():
            continue
        try:
            for current, directories, _ in os.walk(root, topdown=True, followlinks=False):
                level = len(Path(current).relative_to(root).parts)
                if level > 5:
                    directories[:] = []
                    continue
                for dirname in list(directories):
                    if dirname.endswith(".app"):
                        entries.append(_read_app_bundle(Path(current) / dirname))
                        directories.remove(dirname)  # Never traverse inside an app bundle.
                    elif dirname.startswith("."):
                        directories.remove(dirname)
        except OSError as exc:
            warnings.append(f"Нет доступа к каталогу {root}: {exc}")
    return entries


def _mac_profiler(warnings: list[str]) -> list[Software]:
    output, err = _run(["system_profiler", "SPApplicationsDataType", "-json"], 100)
    if err:
        warnings.append(f"system_profiler: {err}")
        return []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        warnings.append("system_profiler: получен некорректный JSON")
        return []
    records = []
    for item in data.get("SPApplicationsDataType", []):
        if not isinstance(item, dict):
            continue
        name = item.get("_name", "")
        if not name:
            continue
        records.append(Software(name=str(name), version=str(item.get("version") or ""),
                                source="macOS system_profiler",
                                install_path=str(item.get("path") or ""),
                                scope="Система"))
    return records


def _homebrew(warnings: list[str]) -> list[Software]:
    brew = shutil.which("brew")
    if brew is None:
        for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
            if Path(candidate).is_file():
                brew = candidate
                break
    if not brew:
        return []
    entries = []
    for kind in ("--formula", "--cask"):
        output, err = _run([brew, "list", kind, "--versions"], 30)
        if err:
            warnings.append(f"Homebrew {kind}: {err}")
            continue
        for line in output.splitlines():
            bits = line.strip().split(maxsplit=1)
            if bits:
                entries.append(Software(name=bits[0], version=bits[1] if len(bits) > 1 else "",
                                        source=f"Homebrew {'Cask' if kind == '--cask' else 'Formula'}"))
    return entries


def _tsv_rows(output: str, columns: int) -> list[list[str]]:
    result = []
    for line in output.splitlines():
        values = line.split("\t")
        if len(values) >= columns and values[0].strip():
            result.append(values)
    return result


def _linux_dpkg(warnings: list[str]) -> list[Software]:
    output, err = _run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Maintainer}\t${db:Status-Abbrev}\n"], 25)
    if err:
        warnings.append(f"dpkg: {err}")
        return []
    return [Software(name=r[0], version=r[1], publisher=r[2], source="dpkg")
            for r in _tsv_rows(output, 4) if r[3].startswith("ii")]


def _linux_rpm(warnings: list[str]) -> list[Software]:
    output, err = _run(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VENDOR}\n"], 25)
    if err:
        warnings.append(f"rpm: {err}")
        return []
    return [Software(name=r[0], version=r[1], publisher=r[2], source="rpm")
            for r in _tsv_rows(output, 3)]


def _linux_pacman(warnings: list[str]) -> list[Software]:
    output, err = _run(["pacman", "-Q"], 25)
    if err:
        warnings.append(f"pacman: {err}")
        return []
    records = []
    for line in output.splitlines():
        bits = line.split(maxsplit=1)
        if len(bits) == 2:
            records.append(Software(name=bits[0], version=bits[1], source="pacman"))
    return records


def _linux_flatpak(warnings: list[str]) -> list[Software]:
    output, err = _run(["flatpak", "list", "--app", "--columns=name,application,version,origin"], 25)
    if err:
        warnings.append(f"Flatpak: {err}")
        return []
    return [Software(name=r[0], identifier=r[1], version=r[2], publisher=r[3], source="Flatpak")
            for r in _tsv_rows(output, 4)]


def _linux_snap(warnings: list[str]) -> list[Software]:
    output, err = _run(["snap", "list"], 25)
    if err:
        warnings.append(f"Snap: {err}")
        return []
    records = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 5:
            records.append(Software(name=parts[0], version=parts[1], publisher=parts[4], source="Snap"))
    return records
