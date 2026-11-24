"""Safety and actual PNG contract tests; no device access or private keys."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image

SOURCE = Path(__file__).resolve().parents[1] / 'scripts' / 'kindle_display_probe.py'
spec = importlib.util.spec_from_file_location('display_probe', SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class DisplayProbeTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            'hardware_match': True, 'interface_index': 77, 'up': True, 'host_ip_ok': True,
            'routes': [
                {'prefix': '0.0.0.0/0', 'index': 4, 'next_hop': '192.168.8.1'},
                {'prefix': '192.168.15.0/24', 'index': 77, 'next_hop': '0.0.0.0'},
            ],
        }

    def test_usb_route_allows_unrelated_wifi_default(self):
        self.assertTrue(probe.validate_usb_snapshot(self.snapshot)['direct_usb_route'])

    def test_more_specific_vpn_route_is_refused(self):
        self.snapshot['routes'].append({'prefix': '192.168.15.244/32', 'index': 5, 'next_hop': '10.0.0.1'})
        with self.assertRaises(RuntimeError):
            probe.validate_usb_snapshot(self.snapshot)

    def test_ambiguous_equal_length_route_is_refused(self):
        self.snapshot['routes'].append({'prefix': '192.168.15.0/24', 'index': 5, 'next_hop': '0.0.0.0'})
        with self.assertRaises(RuntimeError):
            probe.validate_usb_snapshot(self.snapshot)

    def test_wrong_device_or_address_is_refused(self):
        for field in ('hardware_match', 'up', 'host_ip_ok'):
            snapshot = copy.deepcopy(self.snapshot)
            snapshot[field] = False
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                probe.validate_usb_snapshot(snapshot)

    def test_display_dimensions_use_visible_not_virtual_resolution(self):
        info = 'xres: 1072 yres:\n1448\nxres_virtual: 1088\nyres_virtual: 6144\nbits_per_pixel: 8\n'
        probe.validate_framebuffer(info)
        with self.assertRaises(RuntimeError):
            probe.validate_framebuffer(info.replace('xres: 1072', 'xres: 1088'))
        with self.assertRaises(RuntimeError):
            probe.validate_framebuffer(info.replace('bits_per_pixel: 8', 'bits_per_pixel: 16'))

    def test_actual_png_is_8bit_grayscale_and_correct_size(self):
        with tempfile.TemporaryDirectory(dir=SOURCE.parents[1] / 'data') as directory:
            path = Path(directory) / 'probe.png'
            digest = probe.make_test_image(path)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1072, 1448))
                self.assertEqual(image.mode, 'L')
                self.assertEqual(image.getpixel((8, 8)), 0)
                self.assertEqual(image.getpixel((0, 0)), 255)
            self.assertEqual(len(digest), 64)
            self.assertEqual(path.read_bytes()[24:26], bytes([8, 0]))

    def test_public_key_rejects_shell_metacharacters(self):
        with tempfile.TemporaryDirectory(dir=SOURCE.parents[1] / 'data') as directory:
            path = Path(directory) / 'public.pub'
            path.write_text('ssh-ed25519 AAAA;reboot', encoding='ascii')
            with self.assertRaises(RuntimeError):
                probe.read_public_key(path)


if __name__ == '__main__':
    unittest.main()
