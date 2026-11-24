"""Fixed local launcher. Use --setup-kindle after reviewing docs/INSTALL.md."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import webbrowser
import atexit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.settings import management_url
from app.core.listener import single_instance


def prepare_background_stdio(root=ROOT):
    """pythonw has no console streams. Capture errors before importing the app."""
    log_dir = Path(root) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    missing = sys.stdout is None or sys.stderr is None
    output = None
    if missing:
        output = (log_dir / 'startup.log').open('a', encoding='utf-8', errors='replace', buffering=1)
        if sys.stdout is None:
            sys.stdout = output
        if sys.stderr is None:
            sys.stderr = output
        # stdout/stderr own this stream for the process lifetime; the interpreter
        # flushes it at exit. Closing it in atexit would break final stream flushing.
    if sys.stdin is None:
        stream = open(os.devnull, 'r')
        sys.stdin = stream
        atexit.register(stream.close)
    with (log_dir / 'startup.log').open('a', encoding='utf-8') as trace:
        trace.write(time.strftime('%Y-%m-%d %H:%M:%S') + f' START pid={os.getpid()} console_streams_missing={missing}\n')
    return output


def local_api(path, payload=None, token=None, timeout=4):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(management_url(ROOT) + path, data=data, headers={'Content-Type': 'application/json', 'X-KDD-Token': token or ''})
    # Local management never goes through system HTTP proxies.
    from urllib.request import build_opener, ProxyHandler
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def ensure_server():
    try:
        initial = local_api('/api/bootstrap')
        if initial.get('app_id') != 'KindleDeskDashboard':
            raise RuntimeError('The configured management endpoint belongs to another application')
        return initial
    except OSError:
        pass
    import importlib.util
    missing = [name for name in ('fastapi', 'uvicorn', 'psutil', 'PIL') if not importlib.util.find_spec(name)]
    if missing:
        raise RuntimeError('Missing dependencies: ' + ', '.join(missing) + '. Install requirements.txt first.')
    # A server can close its HTTP socket before its collectors finish shutting down.
    # Wait for the OS lock instead of launching a second writer in that interval.
    deadline = time.monotonic() + 30
    while True:
        try:
            with single_instance(ROOT):
                break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Previous Dashboard still owns its project lock; inspect startup.log.')
            time.sleep(.5)
    (ROOT / 'logs').mkdir(exist_ok=True)
    print('STARTING LOCAL DASHBOARD...', flush=True)
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    executable = str(pythonw) if pythonw.is_file() else sys.executable
    with (ROOT / 'logs' / 'launcher.log').open('ab') as output:
        subprocess.Popen([executable, str(Path(__file__).resolve()), '--foreground'], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        time.sleep(.5)
        try:
            value = local_api('/api/bootstrap', timeout=1)
            if value.get('app_id') != 'KindleDeskDashboard':
                raise RuntimeError('Unexpected service at the configured management endpoint')
            return value
        except OSError:
            pass
    raise RuntimeError('Local server did not start. See logs/startup.log and logs/launcher.log')


def restart_server():
    try:
        initial = local_api('/api/bootstrap')
    except OSError:
        print('No running Dashboard; starting a fresh instance.', flush=True)
        return ensure_server()
    if initial.get('app_id') != 'KindleDeskDashboard':
        raise RuntimeError('Unexpected service at the configured management endpoint; it was not stopped')
    local_api('/api/shutdown', {}, initial['token'])
    print('HOST RESTART REQUESTED. Kindle client and saved tasks are preserved.', flush=True)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        time.sleep(.5)
        try:
            local_api('/api/bootstrap', timeout=1)
        except OSError:
            return ensure_server()
    raise RuntimeError('Previous Dashboard did not release its listener; no forced termination performed')


def save_host_report(prefix):
    state = None
    print('Checking hardware, Codex and USB sender status (up to 30 seconds)...', flush=True)
    for _ in range(30):
        state = local_api('/api/state')
        sources_ready = state.get('codex', {}).get('status') != 'waiting' and bool(state.get('hardware'))
        device_ready = not state.get('settings', {}).get('device_enabled') or state.get('kindle', {}).get('status') == 'connected'
        if sources_ready and device_ready:
            break
        time.sleep(1)
    path = ROOT / 'docs' / 'evidence' / (prefix + '-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    summary = {key: state.get(key) for key in ('hardware', 'codex', 'kindle', 'rendered_at', 'frame_revision', 'render_error')}
    summary['management_url'] = management_url(ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print('CODEX STATUS: ' + state.get('codex', {}).get('status', 'unknown'), flush=True)
    print('USB STATUS: ' + state.get('kindle', {}).get('status', 'unknown'), flush=True)
    print('REPORT SAVED: ' + str(path), flush=True)


def setup_kindle():
    from scripts.kindle_display_probe import NATIVE, HOST, check_usb, run, ssh, ssh_options
    import hashlib
    check_usb()
    ssh('set -e; test "$(id -u)" = 0; grep -Fq 5.16.2.1.1 /etc/prettyversion.txt; test "$(uname -m)" = armv7l; mkdir -p /mnt/us/kdd')
    source = ROOT / 'kindle' / 'scripts' / 'KDD_client.sh'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    options = ssh_options()
    options[options.index('-p')] = '-P'
    run([NATIVE / 'scp.exe', '-O', *options, source, f'root@{HOST}:/mnt/us/kdd/KDD_client.new.sh'])
    # Verify before replacing our own client; retain one prior version, no recursive deletion.
    output = ssh(f'''set -e; test "$(sha256sum /mnt/us/kdd/KDD_client.new.sh | cut -d' ' -f1)" = {digest};
sh -n /mnt/us/kdd/KDD_client.new.sh;
if [ -f /mnt/us/kdd/KDD_client.sh ]; then
  sh /mnt/us/kdd/KDD_client.sh stop;
  n=0; while [ -r /tmp/kdd-client.lock/pid ] && [ "$n" -lt 12 ]; do sleep 1; n=$((n + 1)); done;
  test ! -r /tmp/kdd-client.lock/pid;
  cp /mnt/us/kdd/KDD_client.sh /mnt/us/kdd/KDD_client.previous.sh;
fi;
mv /mnt/us/kdd/KDD_client.new.sh /mnt/us/kdd/KDD_client.sh;
chmod 755 /mnt/us/kdd/KDD_client.sh;
nohup sh /mnt/us/kdd/KDD_client.sh run </dev/null >/mnt/us/kdd/client.log 2>&1 &
''')
    ready = False
    for _ in range(10):
        time.sleep(1)
        try:
            ready = 'KDD_READY' in ssh('test -f /mnt/us/kdd/client.ready && test -r /tmp/kdd-client.lock/pid && kill -0 "$(cat /tmp/kdd-client.lock/pid)" && printf KDD_READY')
        except RuntimeError:
            pass
        if ready:
            break
    if not ready:
        raise RuntimeError('Client did not become ready. Reader GUI should restore on exit; inspect /mnt/us/kdd/client.log before retrying.')
    evidence = ROOT / 'docs' / 'evidence' / ('client-deploy-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({'client_sha256': digest, 'remote_shell_syntax_passed': True,
                                   'client_ready': True, 'display_verified': False,
                                   'offline_clock_verified': False, 'autostart_installed': False}, indent=2), encoding='utf-8')
    print('KINDLE CLIENT READY. No boot autostart installed.', flush=True)
    print('REPORT SAVED: ' + str(evidence), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--foreground', action='store_true')
    group.add_argument('--setup-kindle', action='store_true')
    group.add_argument('--stop-kindle', action='store_true')
    group.add_argument('--restart', action='store_true', help='Gracefully restart only this Windows Dashboard')
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.foreground:
        prepare_background_stdio()
        from app.main import main as app_main
        sys.argv = [sys.argv[0]]
        app_main()
        return
    initial = restart_server() if args.restart else ensure_server()
    if args.restart:
        save_host_report('dashboard-restart')
    if args.setup_kindle:
        setup_kindle()
        local_api('/api/settings', {'device_enabled': True}, initial['token'])
        local_api('/api/refresh', {}, initial['token'])
        state = None
        for _ in range(20):
            state = local_api('/api/state')
            if state.get('kindle', {}).get('status') == 'connected':
                break
            time.sleep(1)
        if state:
            path = ROOT / 'docs' / 'evidence' / ('dashboard-first-run-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({key: state.get(key) for key in ('hardware', 'codex', 'kindle', 'rendered_at', 'frame_revision', 'render_error')}, ensure_ascii=False, indent=2), encoding='utf-8')
            print('USB AUTO-PUSH STATUS: ' + state.get('kindle', {}).get('status', 'unknown'), flush=True)
            print('REPORT SAVED: ' + str(path), flush=True)
    if args.stop_kindle:
        local_api('/api/settings', {'device_enabled': False}, initial['token'])
        from scripts.kindle_display_probe import check_usb, ssh
        check_usb()
        ssh('test -f /mnt/us/kdd/KDD_client.sh && sh /mnt/us/kdd/KDD_client.sh stop')
        print('Kindle client stop requested; the reader GUI restores when the client exits.', flush=True)
    print('Management: ' + management_url(ROOT), flush=True)
    if not args.stop_kindle:
        webbrowser.open(management_url(ROOT))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print('STOPPED: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
