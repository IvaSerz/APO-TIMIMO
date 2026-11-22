import csv
import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from software_audit.collector import (_linux_dpkg, _mac_app_bundles, _mac_profiler, scan_inventory)
from software_audit.export import export_csv, export_html, export_json, export_pdf
from software_audit.models import Inventory, Software, compare, deduplicate
from software_audit.storage import latest_snapshot, list_snapshots, save_snapshot


class ModelTests(unittest.TestCase):
    def test_deduplicate_same_location_and_version(self):
        items = [Software("Chrome", "1", source="macOS App Bundle", install_path="/Applications/Chrome.app"),
                 Software("Chrome", "1", source="macOS system_profiler", install_path="/Applications/Chrome.app")]
        unique = deduplicate(items)
        self.assertEqual(len(unique), 1)
        self.assertIn("macOS App Bundle", unique[0].source)
        self.assertIn("macOS system_profiler", unique[0].source)

    def test_do_not_merge_versions(self):
        items = [Software("Test", "1"), Software("Test", "2")]
        self.assertEqual(len(deduplicate(items)), 2)

    def test_detect_version_update_removal_and_addition(self):
        old = Inventory(records=[Software("Editor", "1", publisher="Company"),
                                 Software("Removed", "1")])
        new = Inventory(records=[Software("Editor", "2", publisher="Company"),
                                 Software("New", "1")])
        change = compare(old, new)
        self.assertEqual([x.name for x in change.added], ["New"])
        self.assertEqual([x.name for x in change.removed], ["Removed"])
        self.assertEqual([(a.version, b.version) for a, b in change.updated], [("1", "2")])

    def test_inventory_json_round_trip(self):
        sample = Inventory(records=[Software(name="Тест", version="1.0", install_path="/opt/тест")])
        self.assertEqual(Inventory.from_dict(json.loads(json.dumps(sample.to_dict(), ensure_ascii=False))).to_dict(),
                         sample.to_dict())


class CollectorTests(unittest.TestCase):
    def test_mac_bundle_metadata(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            app = root / "Utilities" / "Example.app" / "Contents"
            app.mkdir(parents=True)
            with (app / "Info.plist").open("wb") as f:
                plistlib.dump({"CFBundleName": "Пример", "CFBundleShortVersionString": "3.5",
                               "CFBundleIdentifier": "org.example.test"}, f)
            with patch("software_audit.collector._mac_app_dirs", return_value=[root]):
                found = _mac_app_bundles([])
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].name, "Пример")
            self.assertEqual(found[0].version, "3.5")
            self.assertEqual(found[0].identifier, "org.example.test")

    def test_mac_profiler_parses_json(self):
        payload = json.dumps({"SPApplicationsDataType": [{"_name": "App", "version": "3",
                                                          "path": "/Applications/App.app"}]})
        with patch("software_audit.collector._run", return_value=(payload, "")):
            apps = _mac_profiler([])
        self.assertEqual(apps[0].install_path, "/Applications/App.app")

    def test_linux_dpkg_only_installed(self):
        response = "one\t1.0\tPublisher\tii \ntwo\t2.0\tPublisher\trc \n"
        with patch("software_audit.collector._run", return_value=(response, "")):
            apps = _linux_dpkg([])
        self.assertEqual([item.name for item in apps], ["one"])

    def test_unsupported_os_returns_warning(self):
        result = scan_inventory(system="UnknownOS")
        self.assertFalse(result.records)
        self.assertTrue(result.warnings)


class StorageExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.result = Inventory(records=[Software(name="Антивирус", version="2.0",
                                                 publisher="=SUM(1,1)", source="Sample")])

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshots_saved_and_loaded(self):
        save_snapshot(self.result, self.folder)
        self.assertEqual(len(list_snapshots(self.folder)), 1)
        self.assertEqual(latest_snapshot(self.folder).records[0].name, "Антивирус")

    def test_csv_formula_protected_and_unicode(self):
        path = self.folder / "software.csv"
        export_csv(self.result, path)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][0], "Антивирус")
        self.assertEqual(rows[1][2], "'=SUM(1,1)")

    def test_json_html_formats(self):
        json_path = self.folder / "software.json"
        html_path = self.folder / "software.html"
        export_json(self.result, json_path)
        export_html(self.result, html_path)
        self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["records"][0]["name"],
                         "Антивирус")
        self.assertIn("Антивирус", html_path.read_text(encoding="utf-8"))

    def test_pdf_unicode_if_reportlab_available(self):
        try:
            import reportlab  # noqa
        except ImportError:
            self.skipTest("reportlab is optional")
        path = self.folder / "software.pdf"
        export_pdf(self.result, path)
        self.assertTrue(path.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
