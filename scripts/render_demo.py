"""Generate clearly labelled synthetic previews; no accounts, sensors, DB or USB."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.settings import DEFAULTS
from app.renderer.dashboard import DashboardRenderer
from PIL import Image, ImageDraw, ImageFont


def main():
    now = datetime(2026, 11, 24, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    hardware = {
        'sampled_at': now.timestamp(),
        'cpu': {'usage_percent': 18, 'frequency_mhz': 4200, 'temperature_c': None, 'power_w': None},
        'memory': {'total': 48 * 2**30, 'used': 16 * 2**30, 'available': 32 * 2**30},
        'gpus': [{'name': 'NVIDIA GPU · DEMO', 'usage_percent': 24, 'temperature_c': 46,
                  'power_w': 85, 'clock_mhz': 1600, 'memory_total_mib': 24576,
                  'memory_used_mib': 6144, 'memory_free_mib': 18432}],
    }
    codex = {'status': 'demo', 'buckets': [{'id': 'codex', 'windows': [
        {'name': 'primary', 'window_minutes': 300, 'used_percent': 32, 'remaining_percent': 68,
         'resets_at': (now + timedelta(hours=3)).timestamp()},
        {'name': 'secondary', 'window_minutes': 10080, 'used_percent': 45, 'remaining_percent': 55,
         'resets_at': (now + timedelta(days=4)).timestamp()},
    ]}]}
    tasks = [
        {'id': 1, 'title': '演示：整理本周工作安排', 'due': '2026-11-24', 'start_time': '10:00',
         'end_time': '10:30', 'location': '书桌', 'priority': 2, 'completed': False},
        {'id': 2, 'title': '演示：与同事讨论下周计划', 'due': '2026-11-25', 'start_time': '14:00',
         'end_time': None, 'location': '会议室', 'priority': 1, 'completed': False},
        {'id': 3, 'title': '演示：阅读与学习', 'due': '2026-11-27', 'start_time': None,
         'end_time': None, 'location': '', 'priority': 0, 'completed': False},
    ]
    history = [{'cpu': 20 + (i * 7 % 35), 'gpu': 10 + (i * 3 % 40)} for i in range(60)]
    renderer = DashboardRenderer(DEFAULTS['font_path'])
    out = ROOT / 'docs/images'
    out.mkdir(parents=True, exist_ok=True)
    from io import BytesIO
    for page in ('work', 'pc'):
        image = Image.open(BytesIO(renderer.render(page, hardware, codex, tasks, history, now=now)))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1072, 32), fill=0)
        draw.text((48, 0), '演示数据 / DEMO DATA · 非真实账号和传感器读数',
                  fill=255, font=ImageFont.truetype(DEFAULTS['font_path'], 22))
        path = out / (page + '-demo.png')
        image.save(path)
        print(path.name)
    # Compact readme comparison. No existing user screenshot is used.
    width = 536
    work = Image.open(out / 'work-demo.png').resize((width, 724))
    pc = Image.open(out / 'pc-demo.png').resize((width, 724))
    combined = Image.new('L', (width * 2 + 20, 724), 255)
    combined.paste(work, (0, 0))
    combined.paste(pc, (width + 20, 0))
    combined.save(out / 'overview-demo.png')


if __name__ == '__main__':
    main()
