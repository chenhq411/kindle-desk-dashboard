import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('usb_inspector', Path(__file__).resolve().parents[1] / 'scripts' / 'inspect_usb_packages.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ArchivePathTests(unittest.TestCase):
    def test_valid_relative(self):
        self.assertTrue(module.safe_member('./extensions/MRInstaller/bin/mrinstaller.sh'))

    def test_escape_rejected(self):
        for name in ('../../outside', '/etc/passwd', 'C:/outside', 'folder\\..\\outside'):
            with self.subTest(name=name):
                self.assertFalse(module.safe_member(name))

if __name__ == '__main__':
    unittest.main()
