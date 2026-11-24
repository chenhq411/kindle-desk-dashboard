"""Official Codex App Server read-only account methods; no credential-file access."""
import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time


def discover_executable(configured=''):
    candidates = [configured, shutil.which('codex.exe'), shutil.which('codex')]
    resources = os.environ.get('CODEX_ELECTRON_RESOURCES_PATH')
    if resources:
        candidates.append(str(Path(resources) / 'codex.exe'))
    for value in candidates:
        try:
            if value and Path(value).is_file():
                return str(Path(value).resolve())
        except OSError:
            continue
    # Store-installed Codex changes its versioned directory on update. A normal
    # terminal does not inherit the desktop's CODEX_ELECTRON_RESOURCES_PATH.
    # Ask Windows for the registered package; do not scan credentials or modify it.
    script = ("$ErrorActionPreference='Stop'; "
              "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
              "@(Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | "
              "ForEach-Object { $_.InstallLocation }) | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=6, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        locations = json.loads(result.stdout.lstrip('\ufeff')) if result.returncode == 0 else []
        if isinstance(locations, str):
            locations = [locations]
        if not isinstance(locations, list):
            locations = []
        for location in locations:
            if not isinstance(location, str) or not Path(location).is_absolute():
                continue
            executable = Path(location) / 'app' / 'resources' / 'codex.exe'
            if executable.is_file():
                return str(executable.resolve())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= 100 else None


def parse_limits(payload):
    buckets = payload.get('rateLimitsByLimitId')
    if not isinstance(buckets, dict) or not buckets:
        single = payload.get('rateLimits')
        buckets = {single.get('limitId') or 'codex': single} if isinstance(single, dict) else {}
    output = []
    for key, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        windows = []
        for name in ('primary', 'secondary'):
            window = bucket.get(name)
            if not isinstance(window, dict):
                continue
            used = percent(window.get('usedPercent'))
            reset = window.get('resetsAt')
            minutes = window.get('windowDurationMins')
            windows.append({'name': name, 'used_percent': used,
                            'remaining_percent': 100 - used if used is not None else None,
                            'window_minutes': minutes if type(minutes) is int and minutes > 0 else None,
                            'resets_at': reset if type(reset) is int and reset > 0 else None})
        credit = bucket.get('credits')
        safe_credit = {k: credit.get(k) for k in ('hasCredits', 'unlimited', 'balance')} if isinstance(credit, dict) else None
        output.append({'id': str(key), 'name': bucket.get('limitName') or str(key),
                       'plan': bucket.get('planType'), 'windows': windows, 'credits': safe_credit})
    return output


def collect(configured='', timeout=18):
    executable = discover_executable(configured)
    base = {'source': 'official Codex App Server account/rateLimits/read', 'sampled_at': time.time(), 'buckets': []}
    if not executable:
        return base | {'status': 'cli_unavailable', 'detail': '未找到本地 Codex CLI'}
    process = None
    try:
        process = subprocess.Popen([executable, 'app-server', '--stdio'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, encoding='utf-8', errors='replace',
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        messages = queue.Queue(maxsize=128)
        def reader():
            try:
                while True:
                    line = process.stdout.readline(2_000_001)
                    if not line or len(line) > 2_000_000:
                        break
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict) and 'id' in value:
                        messages.put(value, timeout=1)
            finally:
                try:
                    messages.put(None, timeout=1)
                except queue.Full:
                    pass
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        deadline = time.monotonic() + timeout
        def send(value):
            process.stdin.write(json.dumps(value) + '\n')
            process.stdin.flush()
        def request(identifier, method, params):
            base['last_method'] = method
            send({'id': identifier, 'method': method, 'params': params})
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError()
                response = messages.get(timeout=left)
                if response is None:
                    raise RuntimeError('server_closed')
                if response.get('id') != identifier:
                    continue
                if 'error' in response:
                    base['failed_method'] = method
                    code = response['error'].get('code') if isinstance(response['error'], dict) else None
                    base['rpc_error_code'] = code if isinstance(code, int) else None
                    # Inspect for classification only; never retain raw error payloads.
                    message = str(response['error']).lower()
                    kind = 'authentication_required' if any(k in message for k in ('auth', 'sign in', 'login', '401', '403', 'expired')) else 'read_failed'
                    raise RuntimeError(kind)
                return response.get('result', {})
        request(1, 'initialize', {'clientInfo': {'name': 'kindle_desk_dashboard', 'title': 'Kindle Desk Dashboard', 'version': '0.1.0'}})
        send({'method': 'initialized', 'params': {}})
        account = request(2, 'account/read', {'refreshToken': False})
        active = account.get('account')
        if not active:
            return base | {'status': 'authentication_required', 'detail': 'Codex 尚未登录或认证已失效'}
        if active.get('type') != 'chatgpt':
            return base | {'status': 'unsupported_account', 'detail': '当前不是 ChatGPT 订阅认证；不使用付费 API'}
        limits = request(3, 'account/rateLimits/read', None)
        buckets = parse_limits(limits)
        valid = any(w['used_percent'] is not None for b in buckets for w in b['windows'])
        return base | {'status': 'ok' if valid else 'no_limits',
                       'detail': '官方额度快照' if valid else '官方接口未返回可用额度窗口',
                       'buckets': buckets}
    except (TimeoutError, queue.Empty):
        return base | {'status': 'timeout', 'detail': '官方额度读取超时，其他模块继续运行'}
    except (OSError, RuntimeError, ValueError) as error:
        status = str(error) if str(error) in ('authentication_required', 'read_failed', 'server_closed') else 'unavailable'
        return base | {'status': status, 'detail': '需重新登录 Codex' if status == 'authentication_required' else '官方额度接口暂不可用'}
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
