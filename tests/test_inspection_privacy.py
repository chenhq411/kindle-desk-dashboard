import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('inspection', Path(__file__).resolve().parents[1] / 'scripts' / 'inspect_host.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PrivacyTests(unittest.TestCase):
    def test_unknown_serial_removed(self):
        text = 'Instance ID: USB\\VID_1949&PID_0004\\FAKE_PRIVATE_SERIAL\nStatus: Started'
        result = module.redact(text)
        self.assertNotIn('FAKE_PRIVATE_SERIAL', result)
        self.assertIn('VID_1949&PID_0004', result)
        self.assertIn('Started', result)

    def test_disk_serial_removed(self):
        result = module.redact('USBSTOR\\Disk&Ven_Kindle\\FAKE_PRIVATE_SERIAL&0')
        self.assertNotIn('FAKE_PRIVATE_SERIAL', result)

    def test_plain_prefix_redacted(self):
        self.assertEqual(module.redact('G090G1FAKEONLY'), 'G090G1[REDACTED]')

if __name__ == '__main__':
    unittest.main()
