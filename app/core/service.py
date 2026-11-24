from collections import deque
import copy
from datetime import datetime
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import threading
import time

from app.collectors.hardware import HardwareCollector
from app.collectors import codex
from app.renderer.dashboard import DashboardRenderer
from app.tasks.store import TaskStore
from app.tasks.presentation import pending_overview


class DashboardService:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.root
        for name in ('data', 'logs'):
            (self.root / name).mkdir(exist_ok=True)
        self.tasks = TaskStore(self.root / 'data' / 'tasks.sqlite3')
        self.hardware = HardwareCollector()
        self.renderer = DashboardRenderer(settings.snapshot()['font_path'])
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.shutdown_requested = threading.Event()
        self.wake = threading.Event()
        self.running = False
        self.threads = []
        self.state = {'hardware': {}, 'codex': {'status': 'waiting', 'detail': '额度读取等待中', 'buckets': []},
                      'kindle': {'status': 'not_connected', 'last_seen': None}, 'render_error': None}
        self.history = deque(maxlen=60)
        self.frames = {}
        self.frame_revision = 0
        self.last_render = 0
        self.log = logging.getLogger('kdd.' + str(id(self)))
        self.log.setLevel(logging.INFO)
        handler = RotatingFileHandler(self.root / 'logs' / 'dashboard.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.log.addHandler(handler)
        self.dirty = True

    def start(self):
        if self.threads:
            return
        self.running = True
        self.stop.clear()
        def hardware_loop():
            while not self.stop.is_set():
                tick = time.monotonic()
                if self.running:
                    try:
                        sample = self.hardware.collect()
                        with self.lock:
                            first_sample = not self.state['hardware']
                            self.state['hardware'] = sample
                            self.history.append({'cpu': (sample.get('cpu') or {}).get('usage_percent'),
                                                 'gpu': ((sample.get('gpus') or [{}])[0]).get('usage_percent')})
                        if first_sample:
                            self.request_refresh()
                    except Exception as error:
                        self.log.warning('Hardware collector failed: %s', type(error).__name__)
                self.stop.wait(max(.1, self.settings.snapshot()['collect_seconds'] - (time.monotonic() - tick)))
        def codex_loop():
            while not self.stop.is_set():
                if self.running:
                    try:
                        snapshot = codex.collect(self.settings.snapshot()['codex_executable'])
                        with self.lock:
                            prior = self.state['codex']
                            changed = (prior.get('status'), prior.get('buckets')) != (snapshot.get('status'), snapshot.get('buckets'))
                            self.state['codex'] = snapshot
                        if changed:
                            self.request_refresh()
                    except Exception as error:
                        with self.lock:
                            self.state['codex'] = {'status': 'error', 'detail': '额度模块暂不可用', 'buckets': []}
                        self.log.warning('Codex collector failed: %s', type(error).__name__)
                self.stop.wait(self.settings.snapshot()['codex_seconds'])
        def render_loop():
            while not self.stop.is_set():
                settings = self.settings.snapshot()
                due = settings['automatic_refresh'] and time.monotonic() - self.last_render >= settings['refresh_seconds']
                if self.running and (self.dirty or due):
                    with self.lock:
                        self.dirty = False
                    try:
                        self.render()
                    except Exception as error:
                        with self.lock:
                            self.state['render_error'] = type(error).__name__
                        self.log.warning('Render failed: %s', type(error).__name__)
                self.wake.wait(.5)
                self.wake.clear()
        def device_loop():
            from app.kindle.transport import KindleTransport
            transport = KindleTransport(self.root)
            last_attempt = 0
            while not self.stop.is_set():
                settings = self.settings.snapshot()
                frame = self.frame(settings['page'])
                changed = bool(frame) and frame['sha256'] != transport.sent_hash
                if self.running and settings['device_enabled'] and frame and (changed or time.monotonic() - last_attempt >= 30):
                    try:
                        status = transport.publish(frame, settings['page'], settings['full_refresh_every'])
                        with self.lock:
                            self.state['kindle'] = status
                    except Exception as error:
                        with self.lock:
                            self.state['kindle']['error'] = type(error).__name__
                        self.log.warning('Kindle transport unavailable: %s', type(error).__name__)
                        self.stop.wait(15)
                    last_attempt = time.monotonic()
                self.stop.wait(2)
        for name, action in [('hardware', hardware_loop), ('codex', codex_loop), ('render', render_loop), ('kindle', device_loop)]:
            thread = threading.Thread(target=action, name='kdd-' + name, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.log.info('Dashboard collectors started')

    def close(self):
        self.stop.set()
        self.wake.set()
        for thread in self.threads:
            thread.join(timeout=25)
        self.threads.clear()
        self.log.info('Dashboard stopped')
        for handler in list(self.log.handlers):
            handler.close()
            self.log.removeHandler(handler)

    def request_refresh(self):
        with self.lock:
            self.dirty = True
        self.wake.set()

    def set_running(self, running):
        self.running = running
        if running:
            self.request_refresh()

    def render(self):
        with self.lock:
            state = copy.deepcopy(self.state)
            history = list(self.history)
        tasks = self.tasks.list()
        now = datetime.now().astimezone()
        frames = {}
        for page in ('work', 'pc'):
            png = self.renderer.render(page, state['hardware'], state['codex'], tasks, history, now=now,
                                       task_page=self.settings.snapshot()['task_page'])
            frames[page] = {'png': png, 'sha256': hashlib.sha256(png).hexdigest(), 'generated_at': now.isoformat()}
        with self.lock:
            self.frames = frames
            self.frame_revision += 1
            self.last_render = time.monotonic()
            self.state['render_error'] = None
        self.log.info('Rendered both pages revision=%d', self.frame_revision)

    def frame(self, page):
        with self.lock:
            return dict(self.frames.get(page) or {})

    def snapshot(self):
        with self.lock:
            state = copy.deepcopy(self.state)
            state['frame_revision'] = self.frame_revision
            state['rendered_at'] = next(iter(self.frames.values()))['generated_at'] if self.frames else None
        seen = state['kindle'].get('last_seen')
        state['kindle']['status'] = 'connected' if seen and time.time() - seen < 100 else 'offline'
        settings = self.settings.snapshot()
        tasks = self.tasks.list()
        overview = pending_overview(tasks, page=settings['task_page'])
        summary = {key: overview[key] for key in ('page', 'pages', 'pending_count', 'today_count', 'overdue_count')}
        return state | {'running': self.running, 'settings': settings, 'tasks': tasks,
                        'task_overview': summary, 'task_schema_version': 2}

    def seen(self):
        with self.lock:
            self.state['kindle']['last_seen'] = time.time()

    def logs(self):
        path = self.root / 'logs' / 'dashboard.log'
        return path.read_text(encoding='utf-8', errors='replace').splitlines()[-120:] if path.exists() else []
