"""Shared pending overview ordering for web and e-ink, including future tasks."""
from datetime import date
import math

TASKS_PER_PAGE = 3


def pending_overview(tasks, today=None, page=0):
    today = today or date.today()
    day = today.isoformat()
    pending = [dict(task) for task in tasks if not task.get('completed')]
    pending.sort(key=lambda task: (
        task.get('due') is None, task.get('due') or '9999-12-31',
        task.get('start_time') or '23:59', -task.get('priority', 1), task.get('id', 0)))
    pages = max(1, math.ceil(len(pending) / TASKS_PER_PAGE))
    selected = max(0, min(page, pages - 1))
    return {'tasks': pending, 'visible': pending[selected * TASKS_PER_PAGE:(selected + 1) * TASKS_PER_PAGE],
            'page': selected, 'pages': pages, 'pending_count': len(pending),
            'today_count': sum(task.get('due') == day for task in pending),
            'overdue_count': sum(bool(task.get('due') and task['due'] < day) for task in pending)}


def schedule_text(task, today):
    due = task.get('due')
    if not due:
        label = '未设日期'
    elif due == today.isoformat():
        label = '今天'
    else:
        parsed = date.fromisoformat(due)
        label = parsed.strftime('%Y-%m-%d' if parsed.year != today.year else '%m月%d日') + ' 周' + '一二三四五六日'[parsed.weekday()]
        if parsed < today:
            label = '逾期 ' + label
    if task.get('start_time'):
        label += '  ' + task['start_time']
        if task.get('end_time'):
            label += '–' + task['end_time']
    return label
