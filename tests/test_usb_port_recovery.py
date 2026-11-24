import copy
import unittest
from unittest.mock import patch
import subprocess

from scripts.recover_usb_port import plan, powershell


class PortRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.state = {'adapters': [
            {'index': 79, 'description': 'USB Ethernet/RNDIS Gadget #3', 'status': 'Up', 'hardware_match': True},
        ], 'addresses': [
            {'index': 79, 'ip': '169.254.12.34', 'prefix': 16},
            {'index': 9, 'ip': '192.168.8.100', 'prefix': 24},
        ], 'routes': [{'index': 9, 'prefix': '0.0.0.0/0', 'next_hop': '192.168.8.1'}]}

    def test_new_port_number_and_name_suffix_are_accepted(self):
        result = plan(self.state)
        self.assertEqual(result['interface_index'], 79)
        self.assertEqual(result['remove_old_usb_ip_from'], [])

    def test_only_verified_inactive_old_usb_address_is_migratable(self):
        self.state['adapters'].append({'index': 77, 'description': 'USB Ethernet/RNDIS Gadget', 'status': 'Not Present', 'hardware_match': True})
        self.state['addresses'].append({'index': 77, 'ip': '192.168.15.201', 'prefix': 24})
        self.state['routes'].append({'index': 77, 'prefix': '192.168.15.0/24', 'next_hop': '0.0.0.0'})
        self.assertEqual(plan(self.state)['remove_old_usb_ip_from'], [77])
        self.state['adapters'][1]['hardware_match'] = False
        with self.assertRaises(ValueError):
            plan(self.state)

    def test_unknown_network_and_custom_current_ip_are_refused(self):
        for address in ({'index': 9, 'ip': '192.168.15.2', 'prefix': 24},
                        {'index': 9, 'ip': '192.168.0.10', 'prefix': 16},
                        {'index': 79, 'ip': '10.0.0.2', 'prefix': 24}):
            state = copy.deepcopy(self.state)
            state['addresses'].append(address)
            with self.subTest(address=address), self.assertRaises(ValueError):
                plan(state)

    def test_multiple_up_usb_adapters_and_specific_vpn_route_are_refused(self):
        state = copy.deepcopy(self.state)
        state['adapters'].append({'index': 77, 'description': 'USB Ethernet/RNDIS Gadget', 'status': 'Up', 'hardware_match': True})
        with self.assertRaises(ValueError):
            plan(state)
        self.state['routes'].append({'index': 5, 'prefix': '192.168.15.244/32', 'next_hop': '10.0.0.1'})
        with self.assertRaises(ValueError):
            plan(self.state)

    def test_windows_errors_redact_device_unique_identifier(self):
        response = subprocess.CompletedProcess([], 1, '', r'Error USB\VID_0525&PID_A4A2\PRIVATE_DEVICE_INSTANCE_ID failed')
        with patch('subprocess.run', return_value=response):
            with self.assertRaises(RuntimeError) as error:
                powershell('fixed script')
        self.assertNotIn('PRIVATE_DEVICE_INSTANCE_ID', str(error.exception))


if __name__ == '__main__':
    unittest.main()
