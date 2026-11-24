import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import uvicorn

from app.core.settings import ROOT


spec = importlib.util.spec_from_file_location('kdd_background_test', ROOT / 'scripts/run_dashboard.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class BackgroundStartupTests(unittest.TestCase):
    def test_windowless_startup_captures_stdout_stderr_before_app_initialization(self):
        with tempfile.TemporaryDirectory(prefix='kdd-headless-', dir=ROOT / 'data') as folder:
            with patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
                stream = launcher.prepare_background_stdio(Path(folder))
                try:
                    print('startup-test-message', flush=True)
                    self.assertIs(sys.stderr, stream)
                    config = uvicorn.Config(lambda scope, receive, send: None, use_colors=False,
                                            access_log=False, log_level='warning')
                    self.assertEqual(config.host, '127.0.0.1')
                finally:
                    stream.close()
            value = (Path(folder) / 'logs/startup.log').read_text(encoding='utf-8')
            self.assertIn('console_streams_missing=True', value)
            self.assertIn('startup-test-message', value)

    def test_explicit_non_color_uvicorn_configuration_does_not_require_a_console(self):
        with patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
            config = uvicorn.Config(lambda scope, receive, send: None, use_colors=False,
                                    access_log=False, log_level='warning')
        self.assertFalse(config.use_colors)


if __name__ == '__main__':
    unittest.main()
