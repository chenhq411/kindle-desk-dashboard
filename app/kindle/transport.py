"""Reuse the accepted native SSH/SCP USB path; no incoming host firewall rule."""
import hashlib
from pathlib import Path
import re
import time

from scripts.kindle_display_probe import check_usb, ssh, ssh_options, run, NATIVE, HOST

REMOTE = '/mnt/us/kdd'


class KindleTransport:
    def __init__(self, root):
        self.root = Path(root)
        self.sent_hash = None

    def publish(self, frame, page, full_every):
        check_usb()
        if not re.fullmatch('[a-f0-9]{64}', frame['sha256']) or page not in ('work', 'pc'):
            raise ValueError('Invalid frame')
        if not 1 <= full_every <= 120:
            raise ValueError('Invalid full refresh policy')
        if 'KDD_CLIENT_READY' not in ssh(f'test -f {REMOTE}/client.ready && test -r /tmp/kdd-client.lock/pid && kill -0 "$(cat /tmp/kdd-client.lock/pid)" && printf KDD_CLIENT_READY'):
            raise RuntimeError('Kindle client is not running')
        if self.sent_hash != frame['sha256']:
            path = self.root / 'data' / 'device-frame.png'
            path.write_bytes(frame['png'])
            options = ssh_options()
            options[options.index('-p')] = '-P'
            run([NATIVE / 'scp.exe', '-O', *options, path, f'root@{HOST}:{REMOTE}/frame.upload.png'])
            digest = frame['sha256']
            # Only the validated digest/page/integer enters this fixed remote operation.
            result = ssh(f"set -e; test \"$(sha256sum {REMOTE}/frame.upload.png | cut -d' ' -f1)\" = {digest}; "
                         f"mv {REMOTE}/frame.upload.png {REMOTE}/frame.png; "
                         f"printf '%s %s %s\\n' {digest} {page} {full_every} > {REMOTE}/frame.state.tmp; "
                         f"mv {REMOTE}/frame.state.tmp {REMOTE}/frame.state; "
                         f"date +%s > {REMOTE}/heartbeat.tmp; mv {REMOTE}/heartbeat.tmp {REMOTE}/heartbeat; printf KDD_PUBLISHED")
            if 'KDD_PUBLISHED' not in result:
                raise RuntimeError('Frame publication marker missing')
            self.sent_hash = digest
        else:
            ssh(f'date +%s > {REMOTE}/heartbeat.tmp; mv {REMOTE}/heartbeat.tmp {REMOTE}/heartbeat')
        status = ssh(f'cat {REMOTE}/client.status 2>/dev/null || true').strip()
        return {'status': 'connected', 'last_seen': time.time(), 'client_status': status[:120]}
