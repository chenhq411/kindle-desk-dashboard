from datetime import datetime, date
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from app.tasks.presentation import pending_overview, schedule_text


def value(number, suffix='', decimals=0):
    return 'N/A' if number is None else f'{number:.{decimals}f}{suffix}'


def gib(number):
    return value(number / 2**30 if number is not None else None, ' GiB', 1)


class DashboardRenderer:
    WIDTH, HEIGHT = 1072, 1448

    def __init__(self, font_path):
        if not Path(font_path).is_file():
            raise RuntimeError('Chinese font unavailable')
        self.font_path = font_path
        self.fonts = {}

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = ImageFont.truetype(self.font_path, size)
        return self.fonts[size]

    def render(self, page, hardware, codex, tasks, history, connection=None, now=None, task_page=0):
        now = now or datetime.now().astimezone()
        image = Image.new('L', (self.WIDTH, self.HEIGHT), 255)
        draw = ImageDraw.Draw(image)
        margin, right = 48, 1024
        def text(x, y, content, size=30, fill=0, max_width=None):
            content = str(content)
            if max_width:
                while content and draw.textlength(content, font=self.font(size)) > max_width:
                    content = content[:-2] + '…' if len(content) > 2 else '…'
                    if content == '…':
                        break
            draw.text((x, y), content, font=self.font(size), fill=fill)
        def rule(y, width=3):
            draw.line((margin, y, right, y), fill=0, width=width)
        def wrapped_title(content, x, y, size=32, max_width=928, lines=2):
            content = ' '.join(str(content).split())
            chunks = []
            while content and len(chunks) < lines:
                count = 1
                while count < len(content) and draw.textlength(content[:count + 1], font=self.font(size)) <= max_width:
                    count += 1
                chunks.append(content[:count])
                content = content[count:]
            if content and chunks:
                chunks[-1] = chunks[-1][:-1] + '…'
            for index, chunk in enumerate(chunks):
                text(x, y + 40 * index, chunk, size, max_width=max_width)
            return len(chunks)
        def bar(x, y, width, used):
            draw.rectangle((x, y, x + width, y + 15), outline=0, width=2)
            if used is not None:
                draw.rectangle((x + 3, y + 3, x + max(3, int((width - 3) * min(100, max(0, used)) / 100)), y + 12), fill=0)
        hw = hardware or {}
        cpu, memory = [hw.get(k) or {} for k in ('cpu', 'memory')]
        gpu = (hw.get('gpus') or [{}])[0]
        text(margin, 32, 'KINDLE DESK  /  ' + ('WORK OVERVIEW' if page == 'work' else 'PC MONITOR'), 23)
        rule(85)
        if page == 'work':
            text(margin, 95, now.strftime('%H:%M'), 132)
            weekday = '一二三四五六日'[now.weekday()]
            text(565, 124, now.strftime('%Y年%m月%d日'), 34)
            text(565, 183, '星期' + weekday, 35)
            rule(274, 5)
            overview = pending_overview(tasks, today=now.date(), page=task_page)
            text(margin, 295, '待办总览', 42)
            text(770, 305, f'待完成 {overview["pending_count"]}', 27)
            text(margin, 355, f'逾期 {overview["overdue_count"]}  ·  今天 {overview["today_count"]}  ·  全部未完成事项', 23)
            text(835, 355, f'{overview["page"] + 1} / {overview["pages"]} 页', 23)
            if not overview['tasks']:
                text(margin, 437, '暂无未完成事项', 39)
            count = len(overview['visible'])
            card_height = 450 // max(1, count)
            title_lines = 6 if count == 1 else 3 if count == 2 else 2
            for index, task in enumerate(overview['visible']):
                y = 392 + index * card_height
                draw.rectangle((margin, y + 8, margin + 22, y + 30), outline=0, width=3)
                lines_drawn = wrapped_title(task['title'], 88, y, lines=title_lines)
                priority = ('普通', '中等', '重要')[task['priority']]
                metadata_y = y + max(44, 40 * lines_drawn + 4)
                text(88, metadata_y, priority + '  ·  ' + schedule_text(task, now.date()), 24, max_width=930)
                if task.get('location'):
                    text(88, metadata_y + 33, '地点：' + task['location'], 24, max_width=930)
            rule(855)
            text(margin, 876, 'CODEX 使用额度', 36)
            buckets = codex.get('buckets') or []
            bucket = next((b for b in buckets if b['id'] == 'codex'), buckets[0] if buckets else None)
            if bucket and bucket['windows']:
                for index, window in enumerate(bucket['windows'][:2]):
                    y = 944 + 95 * index
                    minutes = window['window_minutes']
                    label = f'{minutes // 60}小时窗口' if minutes and minutes % 60 == 0 else (f'{minutes}分钟窗口' if minutes else window['name'])
                    text(margin, y, label + '  剩余 ' + value(window['remaining_percent'], '%'), 30)
                    bar(675, y + 12, 345, window['used_percent'])
                    reset = datetime.fromtimestamp(window['resets_at']).astimezone().strftime('%m-%d %H:%M') if window['resets_at'] else 'N/A'
                    text(margin, y + 46, '已用 ' + value(window['used_percent'], '%') + '   重置 ' + reset, 24)
            else:
                text(margin, 963, codex.get('detail', '额度数据等待中'), 31, max_width=970)
                text(margin, 1022, '未知额度显示 N/A，来源为官方 App Server', 25)
            rule(1140)
            text(margin, 1160, '电脑状态', 32)
            text(margin, 1220, 'CPU ' + value(cpu.get('usage_percent'), '%') + '    GPU ' + value(gpu.get('usage_percent'), '%') + '    ' + value(gpu.get('temperature_c'), '°C'), 34)
            text(margin, 1275, '显存 ' + value(gpu.get('memory_used_mib'), ' MiB') + ' / ' + value(gpu.get('memory_total_mib'), ' MiB'), 29)
            text(margin, 1323, '内存 ' + gib(memory.get('used')) + ' / ' + gib(memory.get('total')), 29)
        else:
            text(margin, 100, '电脑运行状态', 54)
            text(margin, 182, gpu.get('name') or 'GPU N/A', 30, max_width=960)
            rule(238, 5)
            groups = [
                ('CPU', [('使用率', value(cpu.get('usage_percent'), '%')), ('温度', value(cpu.get('temperature_c'), '°C')), ('频率', value(cpu.get('frequency_mhz'), ' MHz')), ('功耗', value(cpu.get('power_w'), ' W'))]),
                ('GPU', [('使用率', value(gpu.get('usage_percent'), '%')), ('温度', value(gpu.get('temperature_c'), '°C')), ('频率', value(gpu.get('clock_mhz'), ' MHz')), ('功耗', value(gpu.get('power_w'), ' W'))]),
                ('显存 / 内存', [('显存总量', value(gpu.get('memory_total_mib'), ' MiB')), ('显存已用', value(gpu.get('memory_used_mib'), ' MiB')), ('显存剩余', value(gpu.get('memory_free_mib'), ' MiB')), ('内存总量', gib(memory.get('total'))), ('内存已用', gib(memory.get('used'))), ('内存可用', gib(memory.get('available')))]),
            ]
            y = 263
            for title, fields in groups:
                text(margin, y, title, 34)
                for index, (label, result) in enumerate(fields):
                    x = margin if index % 2 == 0 else 555
                    line_y = y + 58 + (index // 2) * 57
                    text(x, line_y, label, 27)
                    text(x + 170, line_y - 2, result, 30, max_width=290)
                y += 58 + ((len(fields) + 1) // 2) * 57 + 27
                rule(y - 13, 2)
            text(margin, 987, 'CPU / GPU 使用率趋势（最近采集样本）', 25)
            for key, offset, color in [('cpu', 0, 0), ('gpu', 140, 90)]:
                points = [(i, row.get(key)) for i, row in enumerate(history[-60:]) if row.get(key) is not None]
                base = 1080 + offset
                text(margin, base - 15, key.upper(), 22)
                draw.line((160, base + 35, 1015, base + 35), fill=150, width=2)
                if len(points) > 1:
                    coords = [(160 + i * 855 / max(1, len(history[-60:]) - 1), base + 35 - max(0, min(100, n)) * .7) for i, n in points]
                    draw.line(coords, fill=color, width=4)
        sampled = hw.get('sampled_at')
        stamp = datetime.fromtimestamp(sampled).astimezone().strftime('%H:%M:%S') if sampled else 'N/A'
        status = '采集在线' if sampled and now.timestamp() - sampled < 90 else '采集离线'
        rule(1380, 2)
        text(margin, 1390, f'{status}  {stamp}    {now.strftime("%Y-%m-%d %H:%M")}    {"1 / 2" if page == "work" else "2 / 2"}', 23)
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()
