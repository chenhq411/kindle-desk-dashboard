'use strict';
let token = '', state = null, editing = null, lastRevision = -1, lastPage = '';
let taskFilter = 'pending', taskSignature = '';
let structuredTasksReady = false;
const $ = id => document.getElementById(id);
const text = (tag, value, cls) => { const e = document.createElement(tag); e.textContent = value; if (cls) e.className = cls; return e; };
const fmt = (value, unit = '', digits = 0) => value == null ? 'N/A' : Number(value).toFixed(digits) + unit;
const gb = value => fmt(value == null ? null : value / 2 ** 30, ' GiB', 1);
function notice(value) { $('notice').textContent = value; $('notice').style.display = 'block'; setTimeout(() => $('notice').style.display = 'none', 4500); }
async function api(path, method = 'GET', body) {
  const result = await fetch(path, {method, headers: {'Content-Type': 'application/json', 'X-KDD-Token': token}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (!result.ok) { const error = await result.json().catch(() => ({})); throw new Error(error.detail || `请求失败 ${result.status}`); }
  return result.json();
}
function localDate(day = new Date()) { return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`; }
function quickDateValue(kind, anchor = new Date()) {
  if (kind === 'none') return '';
  const offset = {today: 0, tomorrow: 1, day_after: 2}[kind];
  if (typeof offset !== 'number') return null;
  const day = new Date(anchor); day.setDate(day.getDate() + offset);
  return localDate(day);
}
function syncDate() {
  const due = $('task-due').value, enabled = Boolean(due);
  if (!enabled) { $('task-start').value = ''; $('task-end').value = ''; }
  $('task-start').disabled = !enabled; $('task-end').disabled = !enabled;
  document.querySelectorAll('[data-time]').forEach(button => button.disabled = !enabled);
  $('date-description').textContent = enabled ? new Date(due + 'T12:00:00').toLocaleDateString('zh-CN', {month: 'long', day: 'numeric', weekday: 'long'}) : '不设日期的事项仍会出现在总览中';
  const now = new Date();
  const relativeDates = ['today', 'tomorrow', 'day_after'].map(kind => quickDateValue(kind, now));
  document.querySelectorAll('[data-date]').forEach(button => button.classList.toggle('active',
    button.dataset.date === 'custom' ? Boolean(due) && !relativeDates.includes(due) : due === quickDateValue(button.dataset.date, now)));
  $('task-end').min = $('task-start').value || '';
}
function taskBody(task) { return {title: task.title, priority: task.priority, due: task.due, completed: task.completed, start_time: task.start_time || null, end_time: task.end_time || null, location: task.location || ''}; }
function resetForm() { editing = null; $('task-form').reset(); $('task-due').value = localDate(); $('task-priority').value = '1'; $('task-save').textContent = '添加待办'; $('cancel-edit').hidden = true; syncDate(); }
function taskSchedule(task) {
  let label = task.due ? new Date(task.due + 'T12:00:00').toLocaleDateString('zh-CN', {month: 'long', day: 'numeric', weekday: 'short'}) : '未设日期';
  if (task.start_time) label += ` ${task.start_time}${task.end_time ? '–' + task.end_time : ''}`;
  return label;
}
function renderTasks() {
  const summary = state.task_overview || {pending_count: state.tasks.filter(t => !t.completed).length, today_count: 0, overdue_count: 0};
  $('task-count').textContent = `待完成 ${summary.pending_count} · 今天 ${summary.today_count} · 逾期 ${summary.overdue_count}`;
  const signature = JSON.stringify(state.tasks) + taskFilter;
  if (signature === taskSignature) return;
  taskSignature = signature;
  const list = $('tasks'); list.replaceChildren();
  const filtered = state.tasks.filter(task => taskFilter === 'completed' ? task.completed : !task.completed && (taskFilter !== 'today' || task.today));
  if (!filtered.length) list.append(text('div', taskFilter === 'today' ? '今天没有未完成事项；点击“全部待完成”查看后续安排。' : taskFilter === 'completed' ? '还没有已完成事项。' : '暂无待办。添加第一项工作。', 'tasks-empty'));
  let group = '';
  filtered.forEach(task => {
    const label = task.completed ? '已完成' : task.overdue ? '逾期' : task.today ? '今天' : task.due ? '后续安排' : '未设日期';
    if (label !== group) { list.append(text('div', label, 'task-group')); group = label; }
    const row = text('div', '', 'task'), check = document.createElement('input'); check.type = 'checkbox'; check.checked = task.completed; check.setAttribute('aria-label', '完成：' + task.title);
    check.addEventListener('change', () => action(async () => { await api(`/api/tasks/${task.id}`, 'PUT', {...taskBody(task), completed: check.checked}); await poll(); }));
    const content = text('div', ''); content.append(text('div', task.title, 'task-title ' + (task.completed ? 'done' : '')));
    content.append(text('div', `${['普通', '中等', '重要'][task.priority]} · ${taskSchedule(task)}`, 'task-meta ' + (task.overdue ? 'overdue' : '')));
    if (task.location) content.append(text('div', '地点：' + task.location, 'task-location'));
    const buttons = text('div', '', 'row'), edit = text('button', '编辑', 'small'), del = text('button', '删除', 'small danger');
    edit.onclick = () => { editing = task.id; $('task-title').value = task.title; $('task-priority').value = task.priority; $('task-due').value = task.due || ''; $('task-start').value = task.start_time || ''; $('task-end').value = task.end_time || ''; $('task-location').value = task.location || ''; $('task-save').textContent = '保存修改'; $('cancel-edit').hidden = false; syncDate(); $('task-title').focus(); $('task-form').scrollIntoView({behavior: 'smooth', block: 'center'}); };
    del.onclick = () => { if (confirm(`删除“${task.title}”？`)) action(async () => { await api(`/api/tasks/${task.id}`, 'DELETE'); if (editing === task.id) resetForm(); await poll(); }); };
    buttons.append(edit, del); row.append(check, content, buttons); list.append(row);
  });
}
function display(next) {
  state = next;
  structuredTasksReady = state.task_schema_version === 2;
  const hw = state.hardware, cpu = hw.cpu || {}, gpu = (hw.gpus || [{}])[0], mem = hw.memory || {};
  $('metrics').replaceChildren();
  [['CPU', fmt(cpu.usage_percent, '%')], ['GPU', fmt(gpu.usage_percent, '%')], ['GPU 温度', fmt(gpu.temperature_c, ' °C')], ['显存已用', fmt(gpu.memory_used_mib == null ? null : gpu.memory_used_mib / 1024, ' GiB', 1)], ['内存', gb(mem.used)], ['GPU 功耗', fmt(gpu.power_w, ' W', 1)]].forEach(([label, value]) => {
    const e = text('div', '', 'metric'); e.append(text('span', label), text('strong', value)); $('metrics').append(e);
  });
  $('sample-time').textContent = hw.sampled_at ? new Date(hw.sampled_at * 1000).toLocaleTimeString() : '等待采集';
  $('hardware-detail').textContent = `${gpu.name || 'GPU N/A'} · 显存总量 ${fmt(gpu.memory_total_mib, ' MiB')} · CPU温度/功耗 ${fmt(cpu.temperature_c, ' °C')} / ${fmt(cpu.power_w, ' W')}`;
  $('kindle-status').textContent = state.kindle.status === 'connected' ? '● Kindle 已连接' : '○ Kindle 客户端未连接';
  $('kindle-status').className = 'pill ' + (state.kindle.status === 'connected' ? 'ok' : '');
  $('service-toggle').textContent = state.running ? '暂停采集' : '恢复采集';
  renderTasks();
  const overview = state.task_overview || {page: 0, pages: 1};
  $('task-page-label').textContent = `待办 ${overview.page + 1} / ${overview.pages}`;
  $('task-prev').disabled = overview.page === 0; $('task-next').disabled = overview.page + 1 >= overview.pages;
  $('task-pager').hidden = state.settings.page !== 'work';
  const codex = $('codex'); codex.replaceChildren();
  if (state.codex.status !== 'ok') codex.append(text('p', `${state.codex.detail || '额度 N/A'}（${state.codex.status}）`));
  for (const bucket of state.codex.buckets || []) {
    codex.append(text('h3', `${bucket.name}${bucket.plan ? ' · ' + bucket.plan : ''}`));
    for (const win of bucket.windows) {
      const row = text('div', '', 'quota'), duration = win.window_minutes == null ? win.name : `${win.window_minutes} 分钟`;
      row.append(text('div', `${duration} · 已用 ${fmt(win.used_percent, '%')} · 剩余 ${fmt(win.remaining_percent, '%')}`));
      row.append(text('div', `重置：${win.resets_at ? new Date(win.resets_at * 1000).toLocaleString() : 'N/A'}`, 'muted'));
      const track = text('div', '', 'track'), fill = text('div', ''); fill.style.width = `${win.used_percent || 0}%`; track.append(fill); row.append(track); codex.append(row);
    }
    if (bucket.credits) codex.append(text('p', `额外额度：${bucket.credits.unlimited ? '不限量' : bucket.credits.balance ?? 'N/A'}`, 'muted'));
  }
  const settings = state.settings;
  if (!document.activeElement || !['auto-refresh', 'device-enabled', 'refresh-seconds', 'full-refresh'].includes(document.activeElement.id)) {
    $('auto-refresh').checked = settings.automatic_refresh; $('refresh-seconds').value = settings.refresh_seconds; $('full-refresh').value = settings.full_refresh_every;
    $('device-enabled').checked = settings.device_enabled;
  }
  document.querySelectorAll('[data-page]').forEach(b => b.classList.toggle('active', b.dataset.page === settings.page));
  if (state.frame_revision !== lastRevision || settings.page !== lastPage) {
    $('preview').src = `/preview/${settings.page}.png?v=${state.frame_revision}`; lastRevision = state.frame_revision; lastPage = settings.page;
  }
  $('render-time').textContent = state.render_error ? `生成失败：${state.render_error}` : state.rendered_at ? `更新于 ${new Date(state.rendered_at).toLocaleString()}` : '等待生成';
}
async function poll() { display(await api('/api/state')); }
async function action(callback) { try { await callback(); } catch (error) { notice(error.message); } }
$('task-form').onsubmit = event => { event.preventDefault(); action(async () => {
  if (!structuredTasksReady) throw new Error('新版待办需要先重启后台，当前输入尚未保存。');
  const old = state.tasks.find(t => t.id === editing), start = $('task-start').value, end = $('task-end').value;
  if (end && (!start || end < start)) throw new Error('结束时间不能早于开始时间，请检查时间安排。');
  const saved = await api(editing ? `/api/tasks/${editing}` : '/api/tasks', editing ? 'PUT' : 'POST', {title: $('task-title').value, priority: Number($('task-priority').value), due: $('task-due').value || null, completed: old?.completed || false, start_time: start || null, end_time: end || null, location: $('task-location').value});
  resetForm(); await poll();
  const position = state.tasks.filter(task => !task.completed).findIndex(task => task.id === saved.id);
  if (position >= 0) { await api('/api/settings', 'POST', {task_page: Math.floor(position / 3)}); await poll(); }
  notice('待办已保存，已更新总览。');
}); };
$('cancel-edit').onclick = resetForm;
$('task-due').onchange = syncDate;
$('task-start').onchange = () => { $('task-end').min = $('task-start').value || ''; };
document.querySelectorAll('[data-date]').forEach(button => button.onclick = () => {
  if (button.dataset.date === 'custom') {
    const picker = $('task-due'); picker.focus();
    if (typeof picker.showPicker === 'function') { try { picker.showPicker(); } catch (_) { picker.focus(); } }
    return;
  }
  const selected = quickDateValue(button.dataset.date);
  if (selected !== null) { $('task-due').value = selected; syncDate(); }
});
document.querySelectorAll('[data-time]').forEach(button => button.onclick = () => { $('task-start').value = button.dataset.time; if (!button.dataset.time) $('task-end').value = ''; $('task-end').min = $('task-start').value || ''; });
document.querySelectorAll('[data-task-filter]').forEach(button => button.onclick = () => { taskFilter = button.dataset.taskFilter; document.querySelectorAll('[data-task-filter]').forEach(b => b.classList.toggle('active', b === button)); renderTasks(); });
for (const [id, delta] of [['task-prev', -1], ['task-next', 1]]) $(id).onclick = () => action(async () => { const info = state.task_overview; await api('/api/settings', 'POST', {task_page: Math.max(0, Math.min(info.pages - 1, info.page + delta))}); await poll(); });
$('refresh-now').onclick = () => action(async () => { await api('/api/refresh', 'POST'); notice('已请求刷新'); });
$('service-toggle').onclick = () => action(async () => { await api(`/api/service/${state.running ? 'stop' : 'start'}`, 'POST'); await poll(); });
$('save-settings').onclick = () => action(async () => { await api('/api/settings', 'POST', {automatic_refresh: $('auto-refresh').checked, device_enabled: $('device-enabled').checked, refresh_seconds: Number($('refresh-seconds').value), full_refresh_every: Number($('full-refresh').value)}); notice('设置已保存'); await poll(); });
document.querySelectorAll('[data-page]').forEach(button => button.onclick = () => action(async () => { await api('/api/settings', 'POST', {page: button.dataset.page}); await poll(); }));
$('load-logs').onclick = () => action(async () => { $('logs').textContent = (await api('/api/logs')).lines.join('\n'); });
action(async () => { const data = await api('/api/bootstrap'); token = data.token; display(data.state); resetForm();
  if (!structuredTasksReady) { $('task-save').disabled = true; notice('新版页面已就绪，请重启后台启用结构化待办。'); }
  setInterval(() => action(poll), 5000);
});
