from datetime import date
from io import BytesIO
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.api.web import create_app
from app.collectors.hardware import HardwareCollector
from app.core.service import DashboardService
from app.core.settings import ROOT, Settings
from app.renderer.dashboard import DashboardRenderer
from app.tasks.presentation import pending_overview, schedule_text
from app.tasks.store import TaskStore


class TaskUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='kdd-v02-', dir=ROOT / 'data')
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_legacy_database_upgrade_is_additive_and_backed_up(self):
        path = self.root / 'tasks.sqlite3'
        original = '原有事项：会议时间地点等原始文字全部保留'
        with sqlite3.connect(path) as con:
            con.execute('CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,priority INTEGER NOT NULL,due TEXT,completed INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,updated TEXT NOT NULL)')
            con.execute('INSERT INTO tasks VALUES(7,?,2,?,0,?,?)', (original, '2026-11-27', 'old-created', 'old-updated'))
        con.close()
        store = TaskStore(path)
        record = store.list()[0]
        self.assertEqual((record['id'], record['title'], record['created'], record['due']), (7, original, 'old-created', '2026-11-27'))
        self.assertIsNone(record['start_time'])
        backups = list((self.root / 'backups').glob('*.sqlite3'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as con:
            self.assertEqual(con.execute('SELECT title FROM tasks').fetchone()[0], original)
            self.assertNotIn('location', {row[1] for row in con.execute('PRAGMA table_info(tasks)')})
        TaskStore(path)
        self.assertEqual(len(list((self.root / 'backups').glob('*.sqlite3'))), 1)

    def test_structured_schedule_persists_and_old_clients_preserve_new_fields(self):
        store = TaskStore(self.root / 'tasks.sqlite3')
        record = store.write({'title': '采访', 'priority': 2, 'due': '2026-11-27', 'start_time': '08:30', 'end_time': '10:30', 'location': ' 医院会议室 '})
        store.write({'title': '采访', 'priority': 2, 'due': '2026-11-27', 'completed': True}, record['id'])
        saved = TaskStore(store.path).list()[0]
        self.assertEqual((saved['start_time'], saved['end_time'], saved['location']), ('08:30', '10:30', '医院会议室'))
        self.assertTrue(saved['completed'])
        store.write({'title': '采访', 'priority': 2, 'due': None, 'start_time': None, 'end_time': None, 'location': ''}, record['id'])
        self.assertIsNone(store.list()[0]['start_time'])

    def test_invalid_clock_ranges_do_not_create_tasks(self):
        store = TaskStore(self.root / 'tasks.sqlite3')
        for fields in ({'start_time': '25:00'}, {'start_time': '08:30', 'end_time': '08:00'}, {'end_time': '09:00'}, {'due': None, 'start_time': '09:00'}, {'location': 'x' * 161}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                store.write({'title': 'invalid', 'due': '2026-11-27', **fields})
        self.assertEqual(store.list(), [])

    def test_all_future_tasks_are_reachable_and_deletion_clamps_pagination(self):
        tasks = [{'id': n, 'title': f'未来事项{n}', 'due': '2026-11-27', 'priority': 1, 'completed': False} for n in range(7)]
        collected = []
        for page in range(3):
            overview = pending_overview(tasks, date(2026, 11, 24), page)
            collected.extend(t['id'] for t in overview['visible'])
            self.assertEqual(overview['pending_count'], 7)
            self.assertEqual(overview['today_count'], 0)
        self.assertEqual(collected, list(range(7)))
        self.assertEqual(pending_overview(tasks[:1], date(2026, 11, 24), 2)['page'], 0)

    def test_eink_future_task_and_structured_metadata_actually_drawn(self):
        task = {'id': 1, 'title': '未来采访事项必须可见', 'due': '2026-11-27', 'priority': 2, 'completed': False,
                'start_time': '08:30', 'end_time': '10:30', 'location': '指定会议室'}
        renderer = DashboardRenderer(r'C:\Windows\Fonts\msyh.ttc')
        from datetime import datetime
        from PIL import ImageDraw
        original = ImageDraw.ImageDraw.text
        captured = []
        def capture(draw, xy, text, *args, **kwargs):
            captured.append(str(text))
            return original(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', capture):
            png = renderer.render('work', {}, {}, [task], [], now=datetime(2026, 11, 24, 13, 0))
        text = '\n'.join(captured)
        self.assertIn(task['title'], text)
        self.assertIn('08:30–10:30', text)
        self.assertIn(task['location'], text)
        self.assertNotIn('今日暂无待办', text)
        with Image.open(BytesIO(png)) as image:
            self.assertEqual((image.mode, image.size), ('L', (1072, 1448)))

    def test_storage_and_network_telemetry_are_never_sampled(self):
        guards = ('disk_usage', 'disk_io_counters', 'net_io_counters', 'net_if_stats', 'net_if_addrs')
        from contextlib import ExitStack
        with ExitStack() as stack:
            spies = [stack.enter_context(patch('psutil.' + name, side_effect=AssertionError('removed telemetry'))) for name in guards]
            stack.enter_context(patch('app.collectors.hardware.gpu_sample', return_value=[]))
            result = HardwareCollector().collect()
            for spy in spies:
                spy.assert_not_called()
        self.assertNotIn('disk', result)
        self.assertNotIn('network', result)

    def test_api_schedule_fields_and_pager_survive_completion(self):
        service = DashboardService(Settings(self.root))
        try:
            with TestClient(create_app(service, workers=False), base_url='http://127.0.0.1:8766') as client:
                token = client.get('/api/bootstrap').json()['token']
                headers = {'x-kdd-token': token}
                body = {'title': 'API会议', 'priority': 2, 'due': '2026-11-27', 'start_time': '08:30', 'end_time': '10:30', 'location': '会议室'}
                saved = client.post('/api/tasks', headers=headers, json=body).json()
                self.assertEqual(saved['location'], '会议室')
                self.assertEqual(client.post('/api/settings', headers=headers, json={'task_page': 3}).status_code, 200)
                summary = client.get('/api/state').json()['task_overview']
                self.assertEqual((summary['page'], summary['pages']), (0, 1))
                client.put(f'/api/tasks/{saved["id"]}', headers=headers, json=body | {'completed': True})
                self.assertEqual(client.get('/api/state').json()['task_overview']['pending_count'], 0)
        finally:
            service.close()


if __name__ == '__main__':
    unittest.main()
