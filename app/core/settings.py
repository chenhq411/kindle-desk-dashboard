from pathlib import Path
import json
import os
import threading

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "collect_seconds": 15, "refresh_seconds": 60, "codex_seconds": 300,
    "automatic_refresh": True, "page": "work", "full_refresh_every": 15,
    "font_path": str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / "msyh.ttc"),
    "codex_executable": "", "management_port": 8766,
    "device_enabled": False, "task_page": 0,
}


def management_url(root=ROOT):
    path = Path(root) / 'config' / 'settings.json'
    port = DEFAULTS['management_port']
    if path.is_file():
        port = json.loads(path.read_text(encoding='utf-8-sig')).get('management_port', port)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid configured management port')
    return f'http://127.0.0.1:{port}'


class Settings:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.path = self.root / 'config' / 'settings.json'
        self.lock = threading.RLock()
        self.values = dict(DEFAULTS)
        resources = os.environ.get('CODEX_ELECTRON_RESOURCES_PATH')
        if resources and (Path(resources) / 'codex.exe').is_file():
            self.values['codex_executable'] = str(Path(resources) / 'codex.exe')
        if self.path.exists():
            self.values.update(json.loads(self.path.read_text(encoding='utf-8-sig')))
        else:
            self.save({})

    def snapshot(self):
        with self.lock:
            return dict(self.values)

    def _persist(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, self.path)
        self.values = values

    def set_management_port(self, port):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid management port')
        with self.lock:
            self._persist({**self.values, 'management_port': port})

    def save(self, changes):
        allowed = {'automatic_refresh', 'page', 'refresh_seconds', 'full_refresh_every', 'device_enabled', 'task_page'}
        if set(changes) - allowed:
            raise ValueError('Unsupported setting')
        with self.lock:
            values = {**self.values, **changes}
            if type(values['automatic_refresh']) is not bool or values['page'] not in ('work', 'pc'):
                raise ValueError('Invalid refresh/page setting')
            if type(values['device_enabled']) is not bool:
                raise ValueError('Invalid device setting')
            if type(values['task_page']) is not int or not 0 <= values['task_page'] <= 999:
                raise ValueError('Invalid task page')
            if type(values['refresh_seconds']) is not int or not 60 <= values['refresh_seconds'] <= 3600:
                raise ValueError('Refresh interval must be 60..3600 seconds')
            if type(values['full_refresh_every']) is not int or not 1 <= values['full_refresh_every'] <= 120:
                raise ValueError('Full refresh must be 1..120 frames')
            self._persist(values)
