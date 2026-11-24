from datetime import date, timedelta
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.api.web import create_app
from app.collectors.codex import parse_limits, percent
from app.collectors.hardware import HardwareCollector
from app.core.service import DashboardService
from app.core.settings import ROOT, Settings
from app.tasks.store import TaskStore


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='kdd-test-', dir=ROOT / 'data')
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_tasks_persist_edit_complete_delete_and_overdue(self):
        path = self.root / 'tasks.sqlite3'
        store = TaskStore(path)
        old_date = (date.today() - timedelta(days=2)).isoformat()
        first = store.write({'title': '中文待办', 'priority': 2, 'due': old_date})
        second = TaskStore(path)
        self.assertTrue(second.list()[0]['overdue'])
        second.write({'title': '已修改', 'priority': 0, 'completed': True}, first['id'])
        self.assertTrue(store.list()[0]['completed'])
        self.assertEqual(store.list()[0]['title'], '已修改')
        store.delete(first['id'])
        self.assertEqual(store.list(), [])

    def test_invalid_task_input_does_not_write(self):
        store = TaskStore(self.root / 'tasks.sqlite3')
        for values in ({'title': ''}, {'title': 'x', 'due': '2026-02-30'}, {'title': 'x', 'priority': True}):
            with self.assertRaises(ValueError):
                store.write(values)
        self.assertEqual(store.list(), [])

    def test_codex_missing_and_invalid_usage_is_not_zero(self):
        values = parse_limits({'rateLimitsByLimitId': {
            'codex': {'primary': {'windowDurationMins': 300, 'resetsAt': 1795500000}},
            'other': {'secondary': {'usedPercent': 25, 'windowDurationMins': 10080}}
        }})
        self.assertIsNone(values[0]['windows'][0]['used_percent'])
        self.assertIsNone(values[0]['windows'][0]['remaining_percent'])
        self.assertEqual(values[1]['windows'][0]['remaining_percent'], 75)
        for bad in (float('nan'), float('inf'), -1, 101, True, '10'):
            self.assertIsNone(percent(bad))

    def test_gpu_failure_does_not_stop_other_collectors(self):
        with patch('app.collectors.hardware.gpu_sample', side_effect=RuntimeError('driver missing')):
            result = HardwareCollector('D:\\').collect()
        self.assertIsNone(result['gpus'])
        self.assertGreater(result['memory']['total'], 0)
        self.assertIsNone(result['cpu']['temperature_c'])
        self.assertIsNone(result['cpu']['power_w'])

    def test_local_api_crud_csrf_host_and_grayscale_previews(self):
        settings = Settings(self.root)
        service = DashboardService(settings)
        try:
            service.render()
            with TestClient(create_app(service, workers=False), base_url='http://127.0.0.1:8766') as client:
                initial = client.get('/api/bootstrap').json()
                headers = {'x-kdd-token': initial['token']}
                self.assertEqual(client.post('/api/tasks', json={'title': 'blocked'}).status_code, 403)
                self.assertEqual(client.post('/api/tasks', headers=headers | {'origin': 'https://attacker.example'}, json={'title': 'blocked'}).status_code, 403)
                self.assertEqual(client.get('/api/state', headers={'host': 'attacker.example:8766'}).status_code, 403)
                result = client.post('/api/tasks', headers=headers, json={'title': '<script>alert(1)</script> 中文', 'priority': 2})
                self.assertEqual(result.status_code, 200)
                task_id = result.json()['id']
                self.assertEqual(client.put(f'/api/tasks/{task_id}', headers=headers, json={'title': '完成', 'completed': True}).status_code, 200)
                self.assertTrue(client.get('/api/state').json()['tasks'][0]['completed'])
                self.assertEqual(client.post('/api/settings', headers=headers, json={'refresh_seconds': 10}).status_code, 422)
                self.assertEqual(settings.snapshot()['refresh_seconds'], 60)
                self.assertEqual(client.post('/api/settings', headers=headers, json={'page': 'pc'}).status_code, 200)
                for page in ('work', 'pc'):
                    response = client.get(f'/preview/{page}.png')
                    self.assertEqual(response.status_code, 200)
                    with Image.open(BytesIO(response.content)) as image:
                        self.assertEqual(image.size, (1072, 1448))
                        self.assertEqual(image.mode, 'L')
                self.assertEqual(client.delete(f'/api/tasks/{task_id}', headers=headers).status_code, 200)
                self.assertEqual(client.get('/api/state').json()['tasks'], [])
        finally:
            service.close()


if __name__ == '__main__':
    unittest.main()
