"""Fresh-clone regressions: no historical config or diagnostic directories."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.settings import ROOT, Settings

spec = importlib.util.spec_from_file_location('kdd_public_launcher', ROOT / 'scripts/run_dashboard.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class FreshCloneTests(unittest.TestCase):
    def test_default_configuration_creates_only_local_settings_and_keeps_device_disabled(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder))
            self.assertTrue((Path(folder) / 'config/settings.json').is_file())
            self.assertFalse(settings.snapshot()['device_enabled'])
            self.assertNotIn('disk_path', settings.snapshot())

    def test_restart_report_creates_missing_evidence_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = {'hardware': {'sampled_at': 1}, 'codex': {'status': 'ok'},
                     'kindle': {'status': 'offline'}, 'settings': {'device_enabled': False}}
            with patch.object(launcher, 'ROOT', root), patch.object(launcher, 'local_api', return_value=state):
                launcher.save_host_report('fresh-clone')
            self.assertEqual(len(list((root / 'docs/evidence').glob('fresh-clone-*.json'))), 1)

    def test_first_usb_configuration_creates_missing_connection_record(self):
        import scripts.recover_usb_port as recovery
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan = {'interface_index': 1, 'description': 'USB Ethernet/RNDIS Gadget',
                    'host_ip': '192.168.15.201', 'prefix': 24, 'remove_old_usb_ip_from': []}
            state = {'adapters': [{'index': 1}], 'addresses': []}
            with patch.object(recovery, 'ROOT', root), patch('sys.argv', ['recover_usb_port.py', '--configure']), \
                 patch.object(recovery.ctypes.windll.shell32, 'IsUserAnAdmin', return_value=True), \
                 patch.object(recovery, 'snapshot', return_value=state), patch.object(recovery, 'plan', return_value=plan), \
                 patch.object(recovery, 'apply'), patch.object(recovery, 'check_usb', return_value={}), \
                 patch.object(recovery, 'ssh', return_value='KDD_USB_OK'):
                recovery.main()
            self.assertTrue((root / 'config/connection.json').is_file())


if __name__ == '__main__':
    unittest.main()
