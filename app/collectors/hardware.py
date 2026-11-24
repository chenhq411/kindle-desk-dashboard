"""Real sensors only. Unsupported Windows CPU sensors remain null."""
import csv
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

import psutil


def number(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError):
        return None


def gpu_sample():
    executable = shutil.which('nvidia-smi')
    if not executable:
        path = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'nvidia-smi.exe'
        executable = str(path) if path.is_file() else None
    if not executable:
        raise RuntimeError('nvidia-smi unavailable')
    fields = 'name,utilization.gpu,temperature.gpu,power.draw,memory.total,memory.used,clocks.current.graphics'
    result = subprocess.run([executable, '--query-gpu=' + fields, '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=8,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('NVIDIA driver query failed')
    rows = list(csv.reader(result.stdout.strip().splitlines(), skipinitialspace=True))
    output = []
    for row in rows:
        if len(row) != 7:
            continue
        values = [number(x.strip()) for x in row[1:]]
        output.append(dict(zip(['name', 'usage_percent', 'temperature_c', 'power_w', 'memory_total_mib', 'memory_used_mib', 'clock_mhz'],
                               [row[0].strip(), *values])))
        total, used = output[-1]['memory_total_mib'], output[-1]['memory_used_mib']
        output[-1]['memory_free_mib'] = max(0, total - used) if total is not None and used is not None else None
    if not output:
        raise RuntimeError('NVIDIA query returned no valid GPU')
    return output


class HardwareCollector:
    def __init__(self, disk_path=None):
        # Legacy constructor parameter remains accepted; no storage/network sampling.
        self.previous = None
        psutil.cpu_percent(interval=None)

    def collect(self):
        current = {'sampled_at': time.time(), 'errors': {}}
        def source(name, action):
            try:
                current[name] = action()
            except Exception as error:
                current[name] = None
                current['errors'][name] = type(error).__name__
        def cpu():
            frequency = psutil.cpu_freq()
            usage = psutil.cpu_percent(interval=None)
            return {'usage_percent': usage if self.previous is not None else None,
                    'frequency_mhz': frequency.current if frequency else None,
                    'temperature_c': None, 'power_w': None,
                    'sensor_status': 'CPU temperature/power sensor unavailable; N/A',
                    'source': 'psutil / Windows system interfaces'}
        def memory():
            value = psutil.virtual_memory()
            return {'total': value.total, 'used': value.used, 'available': value.available, 'usage_percent': value.percent}
        source('cpu', cpu)
        source('memory', memory)
        source('gpus', gpu_sample)
        self.previous = time.monotonic()
        return current
