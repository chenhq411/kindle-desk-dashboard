"""Inspect or configure only the active, hardware-verified Kindle USB adapter.

Run --configure from an Administrator terminal; leaves Dashboard unprivileged.
"""
import argparse
import base64
import ctypes
from datetime import datetime
import ipaddress
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.kindle_display_probe import check_usb, ssh

HOST_IP = '192.168.15.201'
SUBNET = ipaddress.ip_network('192.168.15.0/24')


def powershell(script, timeout=25):
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        # Never print a raw CIM device object or its unique identifier.
        detail = re.sub(r'(USB\\VID_[^\\\s]+\\)[^\s\r\n]+', r'\1[REDACTED]', result.stderr, flags=re.I)
        detail = re.sub(r'\{[0-9a-f-]{36}\}', '[GUID]', detail, flags=re.I)
        raise RuntimeError('Windows USB command failed: ' + detail.strip()[:1400])
    return result.stdout.lstrip('\ufeff')


def snapshot():
    script = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$hw=@(Get-CimInstance Win32_NetworkAdapter)
$adapters=@(Get-NetAdapter -IncludeHidden | Where-Object {
 $_.InterfaceDescription -match '^USB Ethernet/RNDIS Gadget(?: #[0-9]+)?$'
} | ForEach-Object {
 $a=$_; $c=$hw | Where-Object {$_.InterfaceIndex -eq $a.ifIndex} | Select-Object -First 1
 @{index=[int]$a.ifIndex;description=[string]$a.InterfaceDescription;status=[string]$a.Status;
 hardware_match=([string]$c.PNPDeviceID -like 'USB\VID_0525&PID_A4A2\*')}
})
$addresses=@(Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object {
 @{index=[int]$_.InterfaceIndex;ip=[string]$_.IPAddress;prefix=[int]$_.PrefixLength}
})
$routes=@(Get-NetRoute -AddressFamily IPv4 | ForEach-Object {
 @{index=[int]$_.InterfaceIndex;prefix=[string]$_.DestinationPrefix;next_hop=[string]$_.NextHop}
})
@{adapters=$adapters;addresses=$addresses;routes=$routes} | ConvertTo-Json -Depth 6 -Compress
'''
    return json.loads(powershell(script))


def plan(snapshot):
    adapters = snapshot['adapters']
    active = [a for a in adapters if a.get('hardware_match') and a.get('status') == 'Up']
    if len(active) != 1:
        raise ValueError('Expected one active hardware-verified Kindle USB adapter. Check cable; do not toggle USB mode.')
    current = active[0]
    index = int(current['index'])
    inactive = {int(a['index']) for a in adapters if a.get('hardware_match') and a.get('status') != 'Up'}
    addresses = snapshot['addresses']
    migration = set()
    for address in addresses:
        other = int(address['index'])
        ip = ipaddress.ip_address(address['ip'])
        prefix = int(address['prefix'])
        if other == index:
            if not (ip in ipaddress.ip_network('169.254.0.0/16') or (str(ip) == HOST_IP and prefix == 24)):
                raise ValueError('Active USB adapter has a custom IPv4 address. Nothing was overwritten.')
            continue
        if ip.is_unspecified:
            continue
        if not ipaddress.ip_network(f'{ip}/{prefix}', strict=False).overlaps(SUBNET):
            continue
        if other in inactive and str(ip) == HOST_IP and prefix == 24:
            migration.add(other)
        else:
            raise ValueError('USB subnet overlaps another adapter. Stop and review; no network settings changed.')
    for route in snapshot.get('routes', []):
        other = int(route['index'])
        network = ipaddress.ip_network(route['prefix'], strict=False)
        if other != index and network.prefixlen >= 24 and network.overlaps(SUBNET) and other not in migration:
            raise ValueError('Another interface owns a conflicting USB route. No network settings changed.')
    return {'interface_index': index, 'description': current['description'],
            'remove_old_usb_ip_from': sorted(migration), 'host_ip': HOST_IP, 'prefix': 24}


def apply(plan):
    index = int(plan['interface_index'])
    old = ','.join(str(int(i)) for i in plan['remove_old_usb_ip_from'])
    script = r'''
$ErrorActionPreference='Stop'
function Assert-KindleHardware([int]$i) {
 $c=Get-CimInstance Win32_NetworkAdapter -Filter ('InterfaceIndex = '+$i)
 if (-not $c -or -not ([string]$c.PNPDeviceID -like 'USB\VID_0525&PID_A4A2\*')) { throw 'Hardware verification failed' }
}
''' + f'$index={index}; $old=@({old})\n' + r'''
Assert-KindleHardware $index
$a=Get-NetAdapter -InterfaceIndex $index
if ($a.Status -ne 'Up') { throw 'USB adapter disconnected during repair' }
foreach ($i in $old) {
 Assert-KindleHardware $i
 $a=Get-NetAdapter -IncludeHidden -InterfaceIndex $i
 if ($a.Status -eq 'Up') { throw 'Prior adapter became active; stop migration' }
 Get-NetIPAddress -InterfaceIndex $i -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object {$_.IPAddress -eq '192.168.15.201' -and $_.PrefixLength -eq 24} |
  Remove-NetIPAddress -Confirm:$false -ErrorAction Stop
}
$existing=@(Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
 Where-Object {$_.IPAddress -eq '192.168.15.201' -and $_.PrefixLength -eq 24})
if (-not $existing.Count) {
 Set-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -Dhcp Disabled -ErrorAction Stop
 New-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -IPAddress '192.168.15.201' -PrefixLength 24 -ErrorAction Stop | Out-Null
}
for ($n=0; $n -lt 10; $n++) {
 $ip=Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 | Where-Object {$_.IPAddress -eq '192.168.15.201'} | Select-Object -First 1
 if ($ip.AddressState -eq 'Preferred') { break }
 if ($ip.AddressState -eq 'Duplicate') { throw 'Duplicate address detected' }
 Start-Sleep -Seconds 1
}
if (-not $ip -or $ip.AddressState -ne 'Preferred') { throw 'USB address did not become Preferred' }
'KDD_USB_ADDRESS_READY'
'''
    if 'KDD_USB_ADDRESS_READY' not in powershell(script):
        raise RuntimeError('USB address completion marker missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure', action='store_true', help='Administrator: restore only verified Kindle USB IP')
    args = parser.parse_args()
    if args.configure and not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('Open PowerShell as Administrator for --configure. No settings changed.')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path = ROOT / 'docs' / 'evidence' / ('usb-port-recovery-' + stamp + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {'configuration_requested': args.configure, 'configuration_succeeded': False,
              'ssh_verified': False, 'screen_verified': False, 'background_restart_required': True}
    try:
        before = snapshot()
        selected = plan(before)
        # Persist only USB-related rows, no full PNP IDs or unrelated topology.
        indexes = {int(a['index']) for a in before['adapters']}
        report['before'] = {'adapters': before['adapters'],
                            'usb_addresses': [a for a in before['addresses'] if int(a['index']) in indexes]}
        report['plan'] = selected
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Verified adapter: ' + selected['description'] + '; index=' + str(selected['interface_index']), flush=True)
        if not args.configure:
            print('Read-only inspection complete. Use --configure in an Administrator terminal if the fixed IP is missing.', flush=True)
            return
        apply(selected)
        report['configuration_succeeded'] = True
        report['after'] = check_usb()
        report['ssh_verified'] = 'KDD_USB_OK' in ssh('printf KDD_USB_OK')
        if not report['ssh_verified']:
            raise RuntimeError('SSH verification marker missing')
        connection_path = ROOT / 'config' / 'connection.json'
        connection_path.parent.mkdir(parents=True, exist_ok=True)
        connection = json.loads(connection_path.read_text(encoding='utf-8-sig')) if connection_path.exists() else {}
        connection['observed_interface_index'] = selected['interface_index']
        connection['current_adapter_description'] = selected['description']
        connection['last_port_recovery_evidence'] = str(path.relative_to(ROOT)).replace('\\', '/')
        temporary = connection_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(connection, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(connection_path)
        print('USB IP AND SSH VERIFIED. No drivers were reinstalled.', flush=True)
        print('Next, in NORMAL PowerShell: python "' + str(ROOT / 'scripts' / 'run_dashboard.py') + '" --restart', flush=True)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
        raise
    finally:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('REPORT SAVED: ' + str(path), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print('STOPPED: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
