"""GUI entrypoint for source runs and packaged desktop applications."""
from __future__ import annotations

import sys


def self_test() -> int:
    """Headless smoke test for generated Windows/macOS/Linux applications."""
    from software_audit.branding import APP_NAME, APP_VERSION, ASSETS_DIR
    from software_audit.collector import scan_inventory
    from software_audit.export import export_pdf
    from software_audit.models import Inventory, Software
    from pathlib import Path
    import tempfile

    if APP_NAME != "АПО.ТИМИМО":
        raise RuntimeError("Wrong product identity")
    for asset in ("app-icon.png", "logo-original.png", "logo-about.png"):
        if not (ASSETS_DIR / asset).is_file():
            raise FileNotFoundError(f"Missing bundled image: {asset}")
    # A small real PDF ensures that ReportLab and its dependencies were bundled.
    with tempfile.TemporaryDirectory() as folder:
        filename = Path(folder) / "smoke.pdf"
        export_pdf(Inventory(records=[Software(name="Проверка ПО", version="1.0")]), filename)
        if not filename.read_bytes().startswith(b"%PDF"):
            raise RuntimeError("PDF export smoke test failed")
    print(f"{APP_NAME} {APP_VERSION}: self-test OK")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    from software_audit.gui import main
    main()
