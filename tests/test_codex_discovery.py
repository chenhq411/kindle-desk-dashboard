import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from app.collectors.codex import discover_executable
from app.core.settings import ROOT


class CodexDiscoveryTests(unittest.TestCase):
    def test_stale_path_uses_registered_updated_package_without_desktop_env(self):
        with tempfile.TemporaryDirectory(prefix='kdd-discovery-', dir=ROOT / 'data') as folder:
            package = Path(folder) / 'OpenAI.Codex_new-version'
            exe = package / 'app/resources/codex.exe'
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b'fixture-only-not-executed')
            import json
            response = subprocess.CompletedProcess([], 0, json.dumps([str(package)]), '')
            with patch.dict(os.environ, {}, clear=True), patch('shutil.which', return_value=None), patch('subprocess.run', return_value=response) as query:
                result = discover_executable(str(Path(folder) / 'old-version/codex.exe'))
            self.assertEqual(result, str(exe.resolve()))
            self.assertIn('Get-AppxPackage', query.call_args.args[0][-1])

    def test_valid_explicit_executable_never_queries_or_changes_registry(self):
        with tempfile.TemporaryDirectory(prefix='kdd-discovery-', dir=ROOT / 'data') as folder:
            exe = Path(folder) / 'codex.exe'
            exe.write_bytes(b'fixture-only-not-executed')
            with patch('subprocess.run') as query:
                self.assertEqual(discover_executable(str(exe)), str(exe.resolve()))
                query.assert_not_called()

    def test_package_discovery_timeout_fails_as_unavailable(self):
        with patch.dict(os.environ, {}, clear=True), patch('shutil.which', return_value=None), patch('subprocess.run', side_effect=subprocess.TimeoutExpired('powershell', 6)):
            self.assertIsNone(discover_executable())

    def test_restart_refuses_other_local_app(self):
        path = ROOT / 'scripts/run_dashboard.py'
        spec = importlib.util.spec_from_file_location('kdd_restart_test', path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with patch.object(launcher, 'local_api', return_value={'app_id': 'another-application'}) as api:
            with self.assertRaises(RuntimeError):
                launcher.restart_server()
            api.assert_called_once_with('/api/bootstrap')


if __name__ == '__main__':
    unittest.main()
