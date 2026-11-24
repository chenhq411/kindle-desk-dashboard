"""Read-only Phase 0 inspection. No Kindle writes, credentials, or full serial logs."""
from __future__ import annotations
import argparse
import ctypes
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def redact(value: str) -> str:
    # PnP instance suffixes contain serials. Drop all instance identifier lines,
    # not just known Kindle prefixes (future generations must also be safe).
    lines = []
    for line in value.splitlines():
        if re.search(r'(?:USB|USBSTOR|STORAGE|SWD)\\', line, re.I):
            ids = re.search(r'VID_[0-9A-F]{4}&PID_[0-9A-F]{4}', line, re.I)
            line = 'Instance: ' + (ids.group(0) if ids else '[device identifier removed]')
        line = re.sub(r'\bG090G1[A-Z0-9]+\b', 'G090G1[REDACTED]', line, flags=re.I)
        lines.append(line)
    return '\n'.join(lines)

def command(args: list[str]) -> dict:
    try:
        cp = subprocess.run(args, capture_output=True, timeout=25)
        # Native Windows tools are OEM encoded; PowerShell is explicitly UTF-8.
        encoding = 'utf-8' if args[0].lower().startswith(('powershell','pwsh')) else 'oem'
        try:
            out = cp.stdout.decode(encoding, errors='replace')
            err = cp.stderr.decode(encoding, errors='replace')
        except LookupError:
            out = cp.stdout.decode(errors='replace'); err = cp.stderr.decode(errors='replace')
        return {'exit_code': cp.returncode, 'stdout': redact(out), 'stderr': redact(err)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'exit_code': None, 'stdout': '', 'stderr': redact(str(exc))}

def inspect() -> dict:
    import psutil
    pnp = command(['pnputil', '/enum-devices', '/connected'])
    # Retain only Kindle, Amazon VID, RNDIS and devices reporting an error.
    blocks = re.split(r'\n\s*\n', pnp['stdout'])
    pnp['stdout'] = '\n\n'.join(b for b in blocks if re.search(
        r'Kindle|VID_1949|VID_0525&PID_A4A2|RNDIS|Remote NDIS|CDC Ethernet|Ethernet Gadget|Problem Code|问题代码', b, re.I))
    gpu = command(['nvidia-smi', '--query-gpu=name,memory.total,driver_version,utilization.gpu,temperature.gpu,power.draw,clocks.gr', '--format=csv,noheader'])
    cpu = None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            cpu = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    except OSError:
        pass
    mem = psutil.virtual_memory()
    partitions = []
    for part in psutil.disk_partitions(all=False):
        item = {'mountpoint': part.mountpoint, 'filesystem': part.fstype, 'options': part.opts}
        try:
            item['readable'] = os.access(part.mountpoint, os.R_OK)
            item['total_bytes'] = psutil.disk_usage(part.mountpoint).total
        except OSError as exc:
            item['readable'] = False; item['error'] = redact(str(exc))
        partitions.append(item)
    return {
        'inspected_at': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        'environment': 'local Windows execution; sandbox restrictions may hide WMI and removable storage',
        'os_version': str(sys.getwindowsversion()), 'python': sys.version,
        'cpu_registry': cpu, 'memory_total_bytes': mem.total, 'memory_available_bytes': mem.available,
        'gpu': gpu, 'usb_devices_redacted': pnp,
        'cim_probe': command(['powershell', '-NoProfile', '-Command',
            '[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); '
            'try { Get-CimInstance Win32_ComputerSystem -ErrorAction Stop | '
            'Select-Object Manufacturer,Model,TotalPhysicalMemory | ConvertTo-Json } '
            'catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }']),
        'network_route': command(['route', 'print', '-4']),
        'partitions': partitions,
        'commands': {name: bool(shutil.which(name)) for name in ['python','git','codex','nvidia-smi','ssh','scp']},
        'python_modules': {name: bool(importlib.util.find_spec(name)) for name in ['psutil','PIL','fastapi','uvicorn','pytest']},
        'kindle': {'firmware': None, 'screen_resolution': None, 'charging': None,
                   'storage_drive': None, 'model': 'PW3 candidate; prefix supplied by user G090G1',
                   'reason_unknown': 'No device shell access or verified device-info screen; no firmware writes performed'},
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    report = inspect()
    target = options.output or ROOT / 'docs' / 'evidence' / ('inspection-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')
    if not target.resolve().is_relative_to(ROOT):
        parser.error('Output must stay within project directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(target)
