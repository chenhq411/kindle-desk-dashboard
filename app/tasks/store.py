from datetime import date, datetime
from pathlib import Path
from contextlib import contextmanager
import sqlite3
import re


class TaskStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.is_file()
        with self.connect() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, priority INTEGER NOT NULL,
                due TEXT, completed INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL, updated TEXT NOT NULL)''')
            columns = {row['name'] for row in con.execute('PRAGMA table_info(tasks)')}
            additions = [('start_time', 'TEXT'), ('end_time', 'TEXT'), ('location', "TEXT NOT NULL DEFAULT ''")]
            missing = [(name, definition) for name, definition in additions if name not in columns]
            if missing and existed:
                backup_dir = self.path.parent / 'backups'
                backup_dir.mkdir(exist_ok=True)
                backup = backup_dir / ('tasks-before-v0.2-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
                target = sqlite3.connect(backup)
                try:
                    con.backup(target)
                finally:
                    target.close()
            for name, definition in missing:
                if not con.in_transaction:
                    con.execute('BEGIN IMMEDIATE')
                if name in {row['name'] for row in con.execute('PRAGMA table_info(tasks)')}:
                    continue
                con.execute(f'ALTER TABLE tasks ADD COLUMN {name} {definition}')
            con.execute('PRAGMA user_version=2')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def list(self):
        with self.connect() as con:
            rows = con.execute('SELECT * FROM tasks ORDER BY completed, '
                               'CASE WHEN due IS NULL THEN 1 ELSE 0 END, due, '
                               "COALESCE(start_time,'23:59'), priority DESC, id").fetchall()
        today = date.today().isoformat()
        return [dict(row) | {'completed': bool(row['completed']),
                            'overdue': bool(row['due'] and row['due'] < today and not row['completed']),
                            'today': row['due'] == today} for row in rows]

    def write(self, values, task_id=None):
        previous = {}
        if task_id is not None:
            with self.connect() as con:
                row = con.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            previous = dict(row)
        title = values.get('title')
        priority = values.get('priority', 1)
        completed = values.get('completed', False)
        due = values.get('due') or None
        start_time = values.get('start_time', previous.get('start_time')) or None
        end_time = values.get('end_time', previous.get('end_time')) or None
        location = values.get('location', previous.get('location', ''))
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 240:
            raise ValueError('Title must contain 1..240 characters')
        if type(priority) is not int or priority not in (0, 1, 2) or type(completed) is not bool:
            raise ValueError('Invalid priority or completion')
        if due is not None:
            if not isinstance(due, str) or date.fromisoformat(due).isoformat() != due:
                raise ValueError('Due date must use YYYY-MM-DD')
        for clock in (start_time, end_time):
            if clock is not None and (not isinstance(clock, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock)):
                raise ValueError('Time must use HH:MM')
        if (start_time or end_time) and not due:
            raise ValueError('A date is required when setting a time')
        if end_time and (not start_time or end_time < start_time):
            raise ValueError('End time must follow start time')
        if not isinstance(location, str) or len(location.strip()) > 160:
            raise ValueError('Location must contain at most 160 characters')
        stamp = datetime.now().astimezone().isoformat()
        with self.connect() as con:
            if task_id is None:
                result = con.execute('INSERT INTO tasks(title, priority, due, completed, created, updated, start_time, end_time, location) VALUES(?,?,?,?,?,?,?,?,?)',
                                     (title.strip(), priority, due, int(completed), stamp, stamp, start_time, end_time, location.strip()))
                task_id = result.lastrowid
            else:
                result = con.execute('UPDATE tasks SET title=?,priority=?,due=?,completed=?,updated=?,start_time=?,end_time=?,location=? WHERE id=?',
                                     (title.strip(), priority, due, int(completed), stamp, start_time, end_time, location.strip(), task_id))
                if not result.rowcount:
                    raise KeyError(task_id)
        return next(task for task in self.list() if task['id'] == task_id)

    def delete(self, task_id):
        with self.connect() as con:
            if not con.execute('DELETE FROM tasks WHERE id=?', (task_id,)).rowcount:
                raise KeyError(task_id)
