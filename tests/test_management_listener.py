import errno
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.api.web import create_app
from app.core.listener import reserve_loopback, single_instance
from app.core.service import DashboardService
from app.core.settings import ROOT, Settings, management_url


class FakeSocket:
    def __init__(self, error=None, selected=51234):
        self.error = error
        self.selected = selected
        self.closed = False
        self.address = None

    def setsockopt(self, *args):
        pass

    def bind(self, address):
        self.address = address
        if self.error:
            raise self.error

    def listen(self, backlog):
        self.backlog = backlog

    def setblocking(self, value):
        self.blocking = value

    def getsockname(self):
        return ('127.0.0.1', self.selected)

    def close(self):
        self.closed = True


class ManagementListenerTests(unittest.TestCase):
    def test_reserved_port_uses_os_choice_and_stays_loopback_only(self):
        first = FakeSocket(PermissionError(errno.EACCES, 'reserved port'))
        second = FakeSocket()
        pool = iter((first, second))
        listener, port, code = reserve_loopback(8766, factory=lambda *args: next(pool))
        self.assertIs(listener, second)
        self.assertEqual((port, code), (51234, errno.EACCES))
        self.assertEqual((first.address, second.address), (('127.0.0.1', 8766), ('127.0.0.1', 0)))
        self.assertTrue(first.closed)
        self.assertFalse(second.blocking)

    def test_occupied_port_falls_back_but_blanket_denial_stops(self):
        sockets = [FakeSocket(OSError(errno.EADDRINUSE, 'occupied')), FakeSocket()]
        pool = iter(sockets)
        self.assertEqual(reserve_loopback(8766, factory=lambda *args: next(pool))[1], 51234)
        sockets = [FakeSocket(PermissionError(errno.EACCES, 'denied')) for _ in range(2)]
        pool = iter(sockets)
        with self.assertRaises(PermissionError):
            reserve_loopback(8766, factory=lambda *args: next(pool))
        self.assertTrue(all(s.closed for s in sockets))

    def test_unexpected_socket_error_does_not_scan_more_ports(self):
        first = FakeSocket(OSError(errno.EINVAL, 'bad socket'))
        calls = []
        def factory(*args):
            calls.append(args)
            return first
        with self.assertRaises(OSError):
            reserve_loopback(8766, factory=factory)
        self.assertEqual(len(calls), 1)

    def test_native_project_lock_rejects_duplicates_and_releases(self):
        with tempfile.TemporaryDirectory(prefix='kdd-lock-', dir=ROOT / 'data') as folder:
            with single_instance(folder):
                with self.assertRaises(RuntimeError):
                    with single_instance(folder):
                        self.fail('Duplicate lock acquired')
            with single_instance(folder):
                pass

    def test_new_port_persists_and_host_origin_guards_follow_it(self):
        with tempfile.TemporaryDirectory(prefix='kdd-port-', dir=ROOT / 'data') as folder:
            settings = Settings(folder)
            settings.set_management_port(51234)
            self.assertEqual(management_url(folder), 'http://127.0.0.1:51234')
            self.assertEqual(Settings(folder).snapshot()['management_port'], 51234)
            service = DashboardService(settings)
            try:
                with TestClient(create_app(service, workers=False), base_url=management_url(folder)) as client:
                    bootstrap = client.get('/api/bootstrap')
                    self.assertEqual(bootstrap.status_code, 200)
                    self.assertEqual(client.get('/api/state', headers={'host': '127.0.0.1:8766'}).status_code, 403)
                    headers = {'x-kdd-token': bootstrap.json()['token'], 'origin': 'http://127.0.0.1:8766'}
                    self.assertEqual(client.post('/api/refresh', headers=headers).status_code, 403)
            finally:
                service.close()


if __name__ == '__main__':
    unittest.main()
