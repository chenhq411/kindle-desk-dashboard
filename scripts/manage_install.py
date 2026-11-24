"""Explicit per-user Windows startup registration; never changes global security."""
import argparse
from pathlib import Path
import subprocess
import sys
import time
import winreg
import json

from run_dashboard import ROOT, local_api

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE = 'KindleDeskDashboard'


def current_entry():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, VALUE)[0]
    except FileNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall', 'status'))
    args = parser.parse_args()
    existing = current_entry()
    if existing and str(ROOT).lower() not in existing.lower():
        raise RuntimeError('An unrelated startup entry uses this name; it was not changed.')
    if args.action == 'install':
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        if not pythonw.is_file():
            raise RuntimeError('pythonw.exe unavailable; no startup entry installed')
        command = subprocess.list2cmdline([str(pythonw), str(ROOT / 'scripts/run_dashboard.py'), '--foreground'])
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, command)
        if current_entry() != command:
            raise RuntimeError('Startup entry read-back did not match; registration is not verified')
        report = ROOT / 'docs' / 'evidence' / ('windows-autostart-installed-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({'scope': 'current_user_login', 'registry_value': VALUE,
                                      'command': command, 'read_back_verified': True,
                                      'reboot_login_verified': False,
                                      'kindle_boot_autostart_installed': False}, indent=2), encoding='utf-8')
        print('Current-user login startup installed. Reboot/login recovery is not yet tested.')
        print('REGISTRY READ-BACK VERIFIED.')
        print('REPORT SAVED: ' + str(report))
    elif args.action == 'uninstall':
        if existing:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE)
        try:
            bootstrap = local_api('/api/bootstrap')
            if bootstrap.get('app_id') != 'KindleDeskDashboard':
                raise RuntimeError('Unexpected local service; no shutdown requested')
            local_api('/api/settings', {'device_enabled': False}, bootstrap['token'])
            try:
                from scripts.kindle_display_probe import check_usb, ssh
                check_usb()
                ssh('test -f /mnt/us/kdd/KDD_client.sh && sh /mnt/us/kdd/KDD_client.sh stop')
                print('Kindle client stop requested; display restoration needs visual confirmation.')
            except Exception:
                print('Kindle was not stopped. Reconnect USB and use run_dashboard.py --stop-kindle.')
            local_api('/api/shutdown', {}, bootstrap['token'])
            print('Host shutdown requested.')
        except OSError:
            print('No reachable local service; startup entry removed.')
        print('Project files, tasks, keys, USBNetwork and RNDIS driver preserved.')
    else:
        print('Login startup: ' + ('installed' if existing else 'not installed'))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print('STOPPED: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
