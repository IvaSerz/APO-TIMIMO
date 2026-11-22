"""Verify required installer formats exist and are non-empty for this native runner."""
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / 'releases'
VERSION = '0.1.2'
APP = 'APO_TIMIMO'

system = platform.system()
if system == 'Windows':
    names = [f'{APP}_v{VERSION}_Windows_x64_Setup.exe', f'{APP}_v{VERSION}_Windows_x64.zip']
elif system == 'Darwin':
    arch = 'arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
    names = [f'{APP}_v{VERSION}_macOS_{arch}.dmg', f'{APP}_v{VERSION}_macOS_{arch}.zip']
elif system == 'Linux':
    names = [f'{APP}_v{VERSION}_Linux_amd64.deb', f'{APP}_v{VERSION}_Linux_x64.tar.gz']
else:
    raise RuntimeError(f'Unsupported platform {system}')
for name in names:
    p = RELEASES / name
    if not p.is_file() or p.stat().st_size < 10_000:
        raise RuntimeError(f'Missing or suspiciously small: {p}')
    print(f'Verified: {p.name} ({p.stat().st_size:,} bytes)')
