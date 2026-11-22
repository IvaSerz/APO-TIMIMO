import unittest

from software_audit.branding import (APP_NAME, APP_DESCRIPTION, APP_TEAM,
                                    APP_DEVELOPER, APP_VERSION, ASSETS_DIR)


class BrandingTests(unittest.TestCase):
    def test_credits(self):
        self.assertEqual(APP_NAME, "АПО.ТИМИМО")
        self.assertEqual(APP_TEAM, "Команда КАИРО")
        self.assertEqual(APP_DEVELOPER, "Иващенко Сергей Сергеевич")
        self.assertTrue(APP_DESCRIPTION)
        self.assertEqual(APP_VERSION, "0.1.2")

    def test_images(self):
        for name in ("logo-original.png", "logo-header.png", "logo-about.png", "app-icon.png"):
            with self.subTest(name=name):
                image = ASSETS_DIR / name
                self.assertTrue(image.is_file())
                self.assertTrue(image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
