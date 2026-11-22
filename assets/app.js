'use strict';

/* P6 本地评测前端：题面渲染、文件提交、实时结果与历史记录。 */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

const STATUS = {
  AC: { label: 'ACCEPTED', cls: 'ac' },
  WA: { label: 'WRONG ANSWER', cls: 'wa' },
  TLE: { label: 'TIME LIMIT EXCEEDED', cls: 'tle' },
  CE: { label: 'COMPILE ERROR', cls: 'ce' },
  RE: { label: 'RUNTIME ERROR', cls: 're' },
};

const HISTORY_KEY = 'p6web.history.v1';
const MAX_HISTORY = 20;

const state = {
  catalog: {},
  key: null,
  encoding: 'practice',
  jobId: null,
  job: null,
  rowsKey: null,
  rowsJob: null,
  files: [],
  timer: null,
  busy: false,
  collapsed: false,
  history: [],
};

/* ---------------- 基础工具 ---------------- */

const pad = (value) => String(value).padStart(2, '0');

function formatTime(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatShortTime(ms) {
  const date = new Date(ms);
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function shortId(id) {
  return String(id || '').slice(0, 8);
}

function currentSpec() {
  return state.catalog[state.key] || null;
}

function toast(message, tone = '') {
  const box = document.createElement('div');
  box.className = `toast${tone ? ` is-${tone}` : ''}`;
  box.textContent = message;
  $('#toasts').append(box);
  setTimeout(() => box.classList.add('is-out'), 2800);
  setTimeout(() => box.remove(), 3300);
}

function showMessage(text, tone = '') {
  const node = $('#message');
  node.textContent = text || '';
  node.className = `form-msg${tone ? ` is-${tone}` : ''}`;
}

function updateClock() {
  $('#clock').textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
}

/* ---------------- 本地历史 ---------------- */

function loadHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    return Array.isArray(raw) ? raw.slice(0, MAX_HISTORY) : [];
  } catch {
    return [];
  }
}

function saveHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history.slice(0, MAX_HISTORY)));
  } catch {
    /* 存储被禁用时只保留内存中的记录 */
  }
}

function pushHistory(job) {
  if (!job.summary) return;
  const results = (job.summary.results || []).map((result) => (
    result.detail && result.detail.length > 3000
      ? { ...result, detail: `${result.detail.slice(0, 3000)}\n…（历史记录已截断，完整日志见 runs/ 目录）` }
      : result
  ));
  const entry = {
    id: job.id,
    problem: job.problem,
    name: state.catalog[job.problem] ? state.catalog[job.problem].name : '',
    encoding: job.encoding,
    time: job.created ? job.created * 1000 : Date.now(),
    passed: job.summary.passed,
    total: job.summary.total,
    seconds: job.summary.seconds,
    record: job.summary.record || '',
    results,
  };
  state.history = [entry, ...state.history.filter((item) => item.id !== job.id)].slice(0, MAX_HISTORY);
  saveHistory();
  renderBadge();
}

function renderBadge() {
  const badge = $('#badge');
  const count = state.history.length;
  badge.hidden = count === 0;
  badge.textContent = count > 9 ? '9+' : String(count);
}

/* ---------------- 题面 ---------------- */

function bitsFor(spec, encoding) {
  if (encoding === 'original' && spec.original_bits) return spec.original_bits;
  return spec.encoding_bits;
}

function exampleFor(format) {
  const match = String(format).match(/^(\S+)\s*(.*)$/);
  if (!match) return format;
  const [, mnemonic, rest] = match;
  if (!rest) return mnemonic;
  const registers = { rd: '$t0', rs: '$t1', rt: '$t2', base: '$t3', offset: 'label', target: 'label' };
  const operands = rest.split(',').map((raw) => {
    const part = raw.trim();
    if (part === 'offset(base)') return '0($t3)';
    return registers[part] || part;
  });
  return `${mnemonic} ${operands.join(', ')}`;
}

function encodingTable(spec) {
  const raw = bitsFor(spec, state.encoding);
  if (!raw) return '<div class="muted">本题没有这种编码。</div>';
  const parts = raw.trim().split(/\s+/);
  const isR = parts.length === 6;
  const isJ = parts.length === 2;
  const ranges = isJ ? ['31 26', '25 0'] : isR ? ['31 26', '25 21', '20 16', '15 11', '10 6', '5 0'] : ['31 26', '25 21', '20 16', '15 0'];
  const widths = isJ ? [6, 26] : isR ? [6, 5, 5, 5, 5, 6] : [6, 5, 5, 16];
  const columns = isJ ? ['20%', '80%'] : isR ? ['19%', '15%', '15%', '16%', '16%', '19%'] : ['17%', '14%', '14%', '55%'];

  const cells = parts.map((part, index) => {
    const bitsOnly = /^[01]+$/.test(part);
    let name = '';
    let bits = '';
    if (index === 0) {
      name = isR ? 'SPECIAL' : spec.name;
      bits = part;
    } else if (isR && index === parts.length - 1) {
      name = spec.name;
      bits = part;
    } else if (bitsOnly) {
      bits = part;
    } else {
      name = part;
    }
    const html = `${name ? `<span class="enc-name">${esc(name)}</span>` : ''}${bits ? `<span class="enc-bits">${esc(bits)}</span>` : ''}`;
    return `<td>${html}</td>`;
  }).join('');

  return `<table class="enc">
    <colgroup>${columns.map((width) => `<col style="width:${width}">`).join('')}</colgroup>
    <thead><tr>${ranges.map((range) => `<th scope="col">${range}</th>`).join('')}</tr></thead>
    <tbody>
      <tr class="enc-fields">${cells}</tr>
      <tr class="enc-widths">${widths.map((width) => `<td>${width}</td>`).join('')}</tr>
    </tbody>
  </table>`;
}

function renderStatement() {
  const spec = currentSpec();
  if (!spec) return;
  const label = `${spec.stage}-${spec.id}`;
  $('#problemId').textContent = label;
  $('#problemName').textContent = spec.name;
  $('#problemMeta').textContent = `题目编号 ${label}`;
  $('#submitTitle').textContent = `${label} ${spec.name}`;
  $('#source').textContent = spec.source ? `来源 ${spec.source}` : '';
  document.title = `${label} ${spec.name} · P3 / P4 / P5 / P6 上机评测`;
  const hint = $('#uploadHint');
  if (hint) hint.textContent = spec.stage === 'P3' ? '选择一个 Logisim .circ，20 MB 以内' : 'ZIP 或全部 .v / .vh，20 MB 以内';

  const rows = [
    { label: '编码', body: encodingTable(spec), cls: 'enc-row' },
    { label: '格式', body: `<div class="fmt">${esc(spec.format)}</div>` },
    { label: '描述', body: `<div>${esc(spec.description)}</div>` },
    { label: '操作', body: `<pre class="code">${esc(spec.rtl)}</pre>`, cls: 'code-row' },
    { label: '示例', body: `<div class="fmt">${esc(exampleFor(spec.format))}</div>` },
    { label: '其他', body: `<div>${esc(spec.other || '按题目册公共说明执行。')}</div>` },
  ];
  $('#statement').innerHTML = rows.map((row) => `
    <tr${row.cls ? ` class="${row.cls}"` : ''}>
      <th scope="row">${row.label}</th>
      <td>${row.body}</td>
    </tr>`).join('');
}

function renderEncodingOptions() {
  const spec = currentSpec();
  if (!spec) return;
  const select = $('#encoding');
  select.innerHTML = [
    '<option value="practice">工作区练习编码</option>',
    `<option value="original"${spec.original ? '' : ' disabled'}>原平台存档编码</option>`,
  ].join('');
  select.value = state.encoding;
  select.disabled = state.busy;
  if (spec.stage === 'P3') {
    $('#encodingNote').textContent = 'P3 使用题目册规定的固定编码；提交 Logisim 2.7.1 的 .circ 电路。';
  } else if (spec.stage === 'P4') {
    $('#encodingNote').textContent = spec.group === 'exam2025'
      ? '2025 真题使用考试中的固定编码；CPU 需按课程格式输出写入日志。'
      : 'P4 加指令练习使用题目册规定的练习编码；CPU 需按课程格式输出写入日志。';
  } else if (spec.stage === 'P5') {
    $('#encodingNote').textContent = 'P5 题目只提供题目册中的练习编码，没有原平台存档编码。';
  } else {
    $('#encodingNote').textContent = spec.original
      ? '本题提供原平台存档编码。请按 Controller 实际使用的 funct 选择，两种编码不会自动混用。'
      : '';
  }
}

/* ---------------- 题库抽屉 ---------------- */

function buildBankList(filter = '') {
  const query = filter.trim().toLowerCase();
  const groups = [
    { stage: 'P3', group: 'practice', label: '加指令练习' },
    { stage: 'P4', group: 'practice', label: '加指令练习' },
    { stage: 'P4', group: 'exam2025', label: '2025 真题' },
    { stage: 'P5', prefix: 'Q', label: '往年题' }, { stage: 'P5', prefix: 'M', label: '模拟题' }, { stage: 'P5', prefix: 'X', label: 'BLZTAL 补充题' },
    { stage: 'P6', prefix: 'Q', label: '往年题' }, { stage: 'P6', prefix: 'M', label: '模拟题' },
  ];
  let html = '';
  let shown = 0;

  for (const desc of groups) {
    const items = Object.entries(state.catalog).filter(([, spec]) => (desc.group
      ? spec.stage === desc.stage && spec.group === desc.group
      : spec.stage === desc.stage && spec.id.startsWith(desc.prefix)));
    const matched = items.filter(([key, spec]) => {
      if (!query) return true;
      return key.toLowerCase().includes(query)
        || spec.name.toLowerCase().includes(query)
        || spec.format.toLowerCase().includes(query)
        || spec.description.toLowerCase().includes(query);
    });
    if (!matched.length) continue;
    shown += matched.length;
    html += `<div class="bank-group">${desc.stage} ${desc.label} · ${matched.length}</div>`;
    html += matched.map(([key, spec]) => `
      <button class="bank-item${key === state.key ? ' is-active' : ''}${state.busy ? ' is-disabled' : ''}"
              type="button" data-problem="${key}"${state.busy ? ' disabled' : ''}>
        <span class="bank-id">${key}</span>
        <span class="bank-name">${esc(spec.name)}</span>
        <span class="bank-desc">${esc(spec.description)}</span>
      </button>`).join('');
  }

  if (!html) html = '<div class="bank-empty">没有匹配的题目</div>';
  $('#problemList').innerHTML = html;
  const total = Object.values(state.catalog).reduce((sum, spec) => sum + spec.cases.length, 0);
  $('#drawerFoot').textContent = `${shown} 道题 · 共 ${total} 个测试点`;
}

function openDrawer() {
  $('#drawer').hidden = false;
  $('#scrim').hidden = false;
  buildBankList($('#search').value);
  $('#search').focus();
}

function closeDrawer() {
  $('#drawer').hidden = true;
  $('#scrim').hidden = true;
}

/* ---------------- 提交记录 ---------------- */

function resetRecord() {
  state.jobId = null;
  state.job = null;
  state.rowsJob = null;
  state.collapsed = false;
  $('#record').hidden = true;
  $('#emptyState').hidden = false;
  $('#cases').innerHTML = '';
  $('#summary').textContent = '';
  $('#progress').hidden = true;
  $('#bar').style.width = '0%';
  $('#verdictIcon').innerHTML = '';
  $('#verdictText').textContent = '';
  $('#download').hidden = true;
  $('#recordPath').textContent = '';
  $('#recordPath').title = '';
  setVerdict('idle');
}

function buildCaseRows(spec) {
  $('#cases').innerHTML = spec.cases.map((item) => {
    const label = item.label || (/^\d+$/.test(item.id) ? item.id : (item.title || item.id));
    return `
    <li class="case" data-id="${esc(item.id)}" title="${esc(item.title)}">
      <div class="case-main">
        <span class="case-title">测试点 ${esc(label)}</span>
        <span class="case-msg" data-msg>等待评测</span>
      </div>
      <span class="case-status" data-status>—</span>
      <div class="case-detail" data-detail hidden></div>
    </li>`;
  }).join('');
  state.rowsKey = state.key;
}

function detailMarkup(result) {
  const lines = [];
  if (result.cycles !== undefined) {
    lines.push(`<div class="kv"><span>周期</span><b>${esc(result.cycles)} / ${esc(result.budget ?? '—')}</b></div>`);
  }
  if (result.title) {
    lines.push(`<div class="kv"><span>测试点</span><b>${esc(result.id)} ${esc(result.title)}</b></div>`);
  }
  if (result.expected || result.actual) {
    lines.push(`<pre>${esc(`Expected: ${result.expected ?? '—'}\nActual:   ${result.actual ?? '—'}`)}</pre>`);
  }
  if (result.detail) {
    lines.push(`<pre>${esc(result.detail)}</pre>`);
  }
  return lines.join('');
}

function updateCase(result) {
  const row = $(`#cases .case[data-id="${CSS.escape(String(result.id))}"]`);
  if (!row) return;
  const status = STATUS[result.status] || { label: result.status || '—', cls: '' };
  const statusNode = row.querySelector('[data-status]');
  statusNode.textContent = status.label;
  statusNode.className = `case-status${status.cls ? ` ${status.cls}` : ''}`;
  row.querySelector('[data-msg]').textContent = result.message || status.label;

  const detail = detailMarkup(result);
  const detailNode = row.querySelector('[data-detail]');
  if (detail) {
    detailNode.innerHTML = detail;
    row.classList.add('has-detail');
  } else {
    detailNode.innerHTML = '';
    row.classList.remove('has-detail');
  }
}

function setVerdict(kind) {
  const icon = $('#verdictIcon');
  const text = $('#verdictText');
  icon.className = 'verdict-icon';
  text.textContent = '';
  if (kind === 'running' || kind === 'queued') {
    icon.innerHTML = '<span class="spinner"></span>';
    text.textContent = kind === 'queued' ? '排队中' : '评测中';
  } else if (kind === 'ac') {
    icon.classList.add('is-ac');
    icon.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-check-circle"/></svg>';
    icon.title = '全部测试点通过';
  } else if (kind === 'fail') {
    icon.classList.add('is-fail');
    icon.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-alert-circle"/></svg>';
    icon.title = '存在未通过的测试点';
  } else if (kind === 'error') {
    icon.classList.add('is-fail');
    icon.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-alert-circle"/></svg>';
    text.textContent = '评测失败';
  } else {
    icon.innerHTML = '';
  }
}

function renderProgress(job) {
  const total = currentSpec() ? currentSpec().cases.length : 24;
  const done = job.results ? job.results.length : 0;
  const bar = $('#bar');
  const progress = $('#progress');
  if (job.state === 'queued') {
    progress.hidden = false;
    progress.classList.add('is-queued');
    bar.style.width = '35%';
  } else if (job.state === 'running') {
    progress.hidden = false;
    progress.classList.remove('is-queued');
    bar.style.width = `${Math.max(3, (done / total) * 100)}%`;
  } else {
    progress.hidden = true;
    progress.classList.remove('is-queued');
    bar.style.width = '0%';
  }
}

function renderSummary(job) {
  const summary = $('#summary');
  if (job.state === 'error') {
    summary.innerHTML = `<span class="bad">${esc(job.message || '评测失败')}</span>`;
    return;
  }
  if (job.state === 'done' && job.summary) {
    const allPassed = job.summary.passed === job.summary.total;
    summary.innerHTML = `通过 <strong class="${allPassed ? 'ok' : 'bad'}">${esc(job.summary.passed)} / ${esc(job.summary.total)}</strong> · 用时 ${esc(job.summary.seconds)} 秒`;
    return;
  }
  const total = currentSpec() ? currentSpec().cases.length : 24;
  const done = job.results ? job.results.length : 0;
  summary.textContent = job.state === 'queued' ? '排队等待本地评测进程…' : `已完成 ${done} / ${total}`;
}

function applyJob(job, options = {}) {
  const previous = state.job;
  state.job = job;
  state.jobId = job.id;

  $('#emptyState').hidden = true;
  $('#record').hidden = false;
  $('#jobId').textContent = shortId(job.id);
  $('#jobId').title = job.id;

  const created = job.created ? new Date(job.created * 1000) : new Date();
  $('#jobTime').textContent = formatTime(created);

  if (state.rowsJob !== job.id || state.rowsKey !== job.problem) {
    buildCaseRows(currentSpec());
    state.rowsJob = job.id;
  }

  for (const result of job.results || []) updateCase(result);

  renderProgress(job);
  renderSummary(job);

  if (job.state === 'queued' || job.state === 'running') {
    setVerdict(job.state);
    showMessage(job.message || '正在评测…', 'busy');
  } else if (job.state === 'done') {
    setVerdict(job.summary && job.summary.passed === job.summary.total ? 'ac' : 'fail');
    showMessage('');
    $('#download').hidden = false;
    const record = job.summary ? job.summary.record : '';
    $('#recordPath').textContent = record ? record.split(/[\\/]/).pop() : '';
    $('#recordPath').title = record || '';
    if (!state.history.some((item) => item.id === job.id)) {
      pushHistory(job);
    }
    if (previous && previous.state === 'running' && !options.restored) {
      const passed = job.summary ? job.summary.passed : 0;
      const total = job.summary ? job.summary.total : 0;
      toast(`评测完成：通过 ${passed} / ${total}`, passed === total ? 'ok' : 'error');
    }
  } else if (job.state === 'error') {
    setVerdict('error');
    showMessage(job.message || '评测失败', 'error');
    if (previous && previous.state === 'running' && !options.restored) toast(job.message || '评测失败', 'error');
  }

  applyCollapse();
}

function applyCollapse() {
  $('#cases').hidden = state.collapsed;
  $('#summary').hidden = state.collapsed && state.job && state.job.state === 'done';
  const button = $('#toggleCases');
  const use = button.querySelector('use');
  use.setAttribute('href', state.collapsed ? '#i-chevron-down' : '#i-chevron-up');
  button.setAttribute('aria-label', state.collapsed ? '展开测试点结果' : '收起测试点结果');
  button.title = state.collapsed ? '展开测试点结果' : '收起测试点结果';
}

/* ---------------- 提交 ---------------- */

function clearFiles() {
  state.files = [];
  $('#files').value = '';
  renderFiles();
  updateSubmitState();
}

function renderFiles() {
  $('#fileList').innerHTML = state.files.map((file, index) => `
    <li class="file-chip">
      <span class="name" title="${esc(file.name)}">${esc(file.name)}</span>
      <span class="size">${formatBytes(file.size)}</span>
      <button class="remove" type="button" data-remove="${index}" aria-label="移除 ${esc(file.name)}">
        <svg class="icon" aria-hidden="true"><use href="#i-x"/></svg>
      </button>
    </li>`).join('');
  $('#dropText').textContent = state.files.length ? `已选择 ${state.files.length} 个文件` : '点击/拖拽选择文件';
}

function validateFiles(files) {
  if (!files.length) return '请选择源码文件';
  const spec = currentSpec();
  if (spec && spec.stage === 'P3') {
    if (files.length !== 1) return 'P3 只提交一个 .circ 文件';
    if (!/\.circ$/i.test(files[0].name)) return 'P3 只接收 Logisim .circ 文件';
    if (files[0].size > 20 * 1024 * 1024) return '电路文件超过 20 MB';
    return '';
  }
  if (files.length > 100) return '一次最多提交 100 个文件';
  const zips = files.filter((file) => file.name.toLowerCase().endsWith('.zip'));
  if (zips.length && files.length !== 1) return 'ZIP 必须单独提交，不能和其他文件一起选择';
  const allowed = files.every((file) => /\.(zip|v|vh)$/i.test(file.name));
  if (!allowed) return '只接收 ZIP、.v、.vh 文件';
  const total = files.reduce((sum, file) => sum + file.size, 0);
  if (total > 20 * 1024 * 1024) return '源码总大小超过 20 MB';
  return '';
}

function setFiles(list) {
  if (state.busy) return;
  const files = Array.from(list || []);
  if (!files.length) return;
  const error = validateFiles(files);
  if (error) {
    showMessage(error, 'error');
    toast(error, 'error');
    return;
  }
  state.files = files;
  const path = $('#sourcePath');
  if (path.value.trim()) {
    path.value = '';
    toast('已切换为文件上传');
  }
  renderFiles();
  showMessage('');
  updateSubmitState();
}

function updateSubmitState() {
  const hasSource = $('#sourcePath').value.trim().length > 0;
  $('#submit').disabled = state.busy || (!state.files.length && !hasSource);
  const zone = $('#dropzone');
  zone.classList.toggle('is-disabled', state.busy);
  $('#encoding').disabled = state.busy;
  $('#sourcePath').disabled = state.busy;
}

function setBusy(value) {
  state.busy = value;
  updateSubmitState();
  if (value) {
    $('#dropzone').classList.add('is-disabled');
  }
  $$('#problemList .bank-item').forEach((item) => {
    item.classList.toggle('is-disabled', value);
    item.disabled = value;
  });
}

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let index = 0; index < bytes.length; index += 8192) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 8192));
  }
  return btoa(binary);
}

async function startJudge() {
  if (state.busy || !currentSpec()) return;
  const sourcePath = $('#sourcePath').value.trim();
  if (!state.files.length && !sourcePath) {
    showMessage('请选择源码文件，或填写本机源码目录', 'error');
    return;
  }

  const body = { problem: state.key, encoding: state.encoding };
  setBusy(true);
  resetRecord();
  showMessage('正在提交…', 'busy');

  try {
    if (sourcePath) {
      body.source_path = sourcePath;
    } else {
      body.files = await Promise.all(state.files.map(async (file) => ({ name: file.name, data: await fileToBase64(file) })));
    }
    const response = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `提交失败（HTTP ${response.status}）`);
    state.jobId = data.id;
    $('#jobId').textContent = shortId(data.id);
    $('#jobId').title = data.id;
    $('#jobTime').textContent = formatTime(new Date());
    $('#emptyState').hidden = true;
    $('#record').hidden = false;
    updateUrl({ problem: state.key, job: data.id });
    showMessage('等待评测进程…', 'busy');
    startPolling();
  } catch (error) {
    showMessage(error.message, 'error');
    toast(error.message, 'error');
    setBusy(false);
    resetRecord();
  }
}

function startPolling() {
  if (state.timer) clearTimeout(state.timer);
  state.timer = null;
  poll();
}

async function poll() {
  state.timer = null;
  if (!state.jobId) return;
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(state.jobId)}`, { cache: 'no-store' });
    if (response.status === 404) throw new Error('评测记录不存在，评测服务可能已经重启');
    if (!response.ok) throw new Error(`读取评测进度失败（HTTP ${response.status}）`);
    const job = await response.json();
    applyJob(job);
    if (job.state === 'done' || job.state === 'error') {
      setBusy(false);
      updateUrl({ problem: state.key, job: job.id });
      return;
    }
  } catch (error) {
    showMessage(error.message, 'error');
    toast(error.message, 'error');
    setVerdict('error');
    setBusy(false);
    return;
  }
  state.timer = setTimeout(poll, 350);
}

/* ---------------- 题目切换 / 记录恢复 ---------------- */

function renderProblem(key, encoding) {
  const spec = state.catalog[key];
  if (!spec) return false;
  state.key = key;
  state.encoding = encoding === 'original' && spec.original ? 'original' : 'practice';
  renderStatement();
  renderEncodingOptions();
  $$('#problemList .bank-item').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.problem === key);
  });
  return true;
}

function updateUrl(params) {
  const url = new URL(location.href);
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  history.replaceState({}, '', url);
}

function selectProblem(key) {
  if (state.busy) {
    toast('评测进行中，请等待完成后再切换题目');
    return;
  }
  if (!renderProblem(key, 'practice')) return;
  resetRecord();
  clearFiles();
  showMessage('');
  updateUrl({ problem: key, job: null });
}

async function loadJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('找不到这条提交记录，服务重启后旧记录会失效');
    const job = await response.json();
    if (!state.catalog[job.problem]) throw new Error('记录中的题号不在当前题库中');
    renderProblem(job.problem, job.encoding);
    applyJob(job, { restored: true });
    updateUrl({ problem: job.problem, job: job.id });
    if (job.state === 'queued' || job.state === 'running') {
      setBusy(true);
      startPolling();
    }
  } catch (error) {
    showMessage(error.message, 'error');
    const params = new URLSearchParams(location.search);
    const fallback = (params.get('problem') || '').toUpperCase();
    const normalized = fallback && !fallback.includes('-') ? `P6-${fallback}` : fallback;
    const key = state.catalog[normalized] ? normalized : Object.keys(state.catalog)[0];
    if (key) {
      selectProblem(key);
      toast(error.message, 'error');
    }
  }
}

async function openHistoryEntry(id) {
  const entry = state.history.find((item) => item.id === id);
  if (!entry) return;
  closeModal();
  if (state.busy) {
    toast('评测进行中，请等待完成后再查看历史记录');
    return;
  }
  if (entry.results) {
    renderProblem(entry.problem, entry.encoding);
    applyJob({
      id: entry.id,
      problem: entry.problem,
      encoding: entry.encoding,
      state: 'done',
      created: Math.floor(entry.time / 1000),
      results: entry.results,
      summary: {
        passed: entry.passed,
        total: entry.total,
        seconds: entry.seconds,
        record: entry.record,
        results: entry.results,
      },
    }, { restored: true });
    updateUrl({ problem: entry.problem, job: entry.id });
  } else {
    await loadJob(entry.id);
  }
}

/* ---------------- 弹窗 ---------------- */

function openModal(title, html) {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = html;
  $('#modalWrap').hidden = false;
  $('#modalClose').focus();
}

function closeModal() {
  $('#modalWrap').hidden = true;
}

function openHistory() {
  const rows = state.history.map((entry) => {
    const passed = entry.passed ?? 0;
    const total = entry.total ?? 0;
    const ok = total > 0 && passed === total;
    return `<button class="history-item" type="button" data-history="${esc(entry.id)}">
      <span class="history-time">${formatShortTime(entry.time)}</span>
      <span class="history-name">${esc(entry.problem)} ${esc(entry.name || '')}</span>
      <span class="history-verdict${ok ? '' : ' is-fail'}">${esc(passed)} / ${esc(total)}</span>
    </button>`;
  }).join('');
  openModal('提交历史', rows || '<div class="history-empty">本次浏览器还没有提交记录。</div>');
}

const HELP_HTML = `
  <h3>这是什么</h3>
  <p>本页面是 P3 / P4 / P5 / P6 练习包的本机评测页：P3 的 26 个题组（283 点）、P4 的 18 个题组（60 点）、P5 的 40 道题（960 点）、P6 的 39 道题（936 点），共 123 个题组、2239 个测试点。页面只监听 <code>127.0.0.1</code>。</p>
  <h3>使用步骤</h3>
  <p>1. 在题库中选择题目，确认编码模式；<br>
     2. P3 提交一个 Logisim <code>.circ</code> 文件；P4 / P5 / P6 提交 ZIP 或全部 <code>.v</code> / <code>.vh</code> 文件；<br>
     3. 点击「提交」，页面会实时显示该题的全部测试点结果。</p>
  <h3>四种接口</h3>
  <p>P3 顶层为 <code>main</code>，是 Logisim 2.7.1 单周期电路；输出为 <code>Instr / pc / RegWrite / RegAddr / RegData / MemWrite / MemAddr / MemData</code>，IM 为 4096×32 ROM，DM 为 32 位 RAM（有效 3072 字），无延迟槽。P3 评测调用随包的 Java + Logisim 2.7.1 引擎，需要 Java 8 或更新版本。</p>
  <p>P4 顶层为 <code>mips(clk, reset)</code>，IM / DM 在 CPU 内部，IM 从仿真目录的 <code>code.txt</code> 读取机器码，无延迟槽。CPU 需按课程格式打印 <code>@PC: $寄存器 &lt;= 数据</code>；如果 CPU 不打印、但保留了 <code>regwrite / RegAddr / RegData / Memwrite / addr / WD / pc</code> 这些标准信号，评测器会自动用探针 testbench 采集写入。</p>
  <p>P5 顶层同样是 <code>mips(clk, reset)</code>，IM / DM 在内部，GRF 和 DM 写入由课程日志输出，允许 <code>$display</code> 和 <code>readmemh</code>。</p>
  <p>P6 使用外置 IM / DM 端口和随包 testbench，CPU 内不要打印，也不要把内部存储器或读文件任务带进提交。</p>
  <h3>编码模式</h3>
  <p>P3 使用题目册规定的固定编码；P4 使用练习编码，2025 真题使用考试固定编码；P5 全部只有练习编码；P6 的「原平台存档编码」只在 Q11—Q19 提供。编码不会自动混用。</p>
  <h3>判定状态</h3>
  <ul class="status-list">
    <li><span class="status-pill ac">AC</span>所有写入事件一致，并在周期上限内完成；P3 为全部预定周期和复位检查通过。</li>
    <li><span class="status-pill wa">WA</span>PC、目的或数据不一致，或出现多余写入。</li>
    <li><span class="status-pill tle">TLE</span>事件前缀正确，但未在周期或墙钟上限内完成。</li>
    <li><span class="status-pill ce">CE</span>编译失败、缺少唯一的 <code>mips</code> 顶层，或含禁止的仿真任务。</li>
    <li><span class="status-pill re">RE</span>仿真进程异常退出或 P3 电路适配失败。</li>
  </ul>
  <h3>提交区与日志</h3>
  <p>上传的文件保存在 <code>submissions/</code>；P3 的报告在 <code>p3/results/</code>，P6 的完整日志与 <code>result.json</code> 在 <code>runs/</code>，P5 在 <code>p5/runs/</code>，P4 在 <code>p4/runs/</code>。结果用于本地练习，不代表官方隐藏测试。</p>
  <h3>评测环境</h3>
  <p>P4 / P5 / P6 使用随包 Icarus WebAssembly，需要本机 Node.js 20 或更新版本；P4 / P5 也保留 native 后端，P6 可设置 <code>P6_IVERILOG</code> 改用原生 Icarus。P3 需要 Java 8 或更新版本。Python 只需要标准库。</p>
  <h3>测试数据</h3>
  <p>P3 的题目与测试在 <code>p3/tests/</code> 与 <code>p3/cases.tsv</code>；P6 在 <code>tests/</code>，P5 在 <code>p5/tests/</code>，P4 在 <code>p4/practice/tests/</code> 与 <code>p4/exam2025/tests/</code>。</p>
`;

function openHelp() {
  openModal('使用说明', HELP_HTML);
}

/* ---------------- 事件绑定 ---------------- */

function bindEvents() {
  $('#encoding').addEventListener('change', (event) => {
    state.encoding = event.target.value === 'original' ? 'original' : 'practice';
    renderStatement();
    renderEncodingOptions();
    if (state.job) {
      resetRecord();
      updateUrl({ problem: state.key, job: null });
      showMessage('已切换编码，请重新提交');
    }
  });

  const dropzone = $('#dropzone');
  const fileInput = $('#files');
  dropzone.addEventListener('click', () => { if (!state.busy) fileInput.click(); });
  dropzone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (!state.busy) fileInput.click();
    }
  });
  fileInput.addEventListener('change', () => {
    setFiles(fileInput.files);
    fileInput.value = '';
  });

  for (const type of ['dragenter', 'dragover']) {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      if (!state.busy) dropzone.classList.add('is-over');
    });
  }
  for (const type of ['dragleave', 'dragend']) {
    dropzone.addEventListener(type, () => dropzone.classList.remove('is-over'));
  }
  dropzone.addEventListener('drop', (event) => {
    event.preventDefault();
    dropzone.classList.remove('is-over');
    if (!state.busy) setFiles(event.dataTransfer.files);
  });
  window.addEventListener('dragover', (event) => event.preventDefault());
  window.addEventListener('drop', (event) => event.preventDefault());

  $('#fileList').addEventListener('click', (event) => {
    const button = event.target.closest('[data-remove]');
    if (!button || state.busy) return;
    state.files.splice(Number(button.dataset.remove), 1);
    renderFiles();
    updateSubmitState();
  });

  $('#sourcePath').addEventListener('input', () => {
    if ($('#sourcePath').value.trim() && state.files.length) {
      clearFiles();
      toast('已切换为本机源码目录');
    }
    updateSubmitState();
  });

  $('#togglePath').addEventListener('click', () => {
    const row = $('#pathRow');
    row.hidden = !row.hidden;
    if (!row.hidden) $('#sourcePath').focus();
  });

  $('#submit').addEventListener('click', startJudge);
  $('#toggleCases').addEventListener('click', () => {
    state.collapsed = !state.collapsed;
    applyCollapse();
  });

  $('#cases').addEventListener('click', (event) => {
    const row = event.target.closest('.case');
    if (!row || !row.classList.contains('has-detail')) return;
    row.classList.toggle('is-open');
    const detail = row.querySelector('[data-detail]');
    detail.hidden = !row.classList.contains('is-open');
  });

  $('#historyLink').addEventListener('click', openHistory);
  $('#bankTitle').addEventListener('click', openDrawer);
  $('#bell').addEventListener('click', openHistory);
  $('#download').addEventListener('click', () => {
    if (!state.job) return;
    const blob = new Blob([JSON.stringify(state.job, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${state.job.problem}-${shortId(state.job.id)}-result.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 600);
  });

  // 左侧图标栏
  $$('.rail-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.action;
      if (action === 'bank') {
        if ($('#drawer').hidden) openDrawer(); else closeDrawer();
      } else if (action === 'help') {
        openHelp();
      } else if (action === 'records') {
        $('#recordsCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else if (action === 'files') {
        if (!state.busy) $('#files').click();
      } else if (action === 'history') {
        openHistory();
      }
    });
  });

  $('#drawerClose').addEventListener('click', closeDrawer);
  $('#scrim').addEventListener('click', closeDrawer);
  $('#problemList').addEventListener('click', (event) => {
    const item = event.target.closest('[data-problem]');
    if (!item) return;
    if (state.busy) { toast('评测进行中，请等待完成后再切换题目'); return; }
    closeDrawer();
    if (item.dataset.problem !== state.key) selectProblem(item.dataset.problem);
  });
  $('#search').addEventListener('input', (event) => buildBankList(event.target.value));

  $('#modalClose').addEventListener('click', closeModal);
  $('#modalWrap').addEventListener('click', (event) => {
    if (event.target === $('#modalWrap')) closeModal();
  });
  $('#modalBody').addEventListener('click', (event) => {
    const item = event.target.closest('[data-history]');
    if (item) openHistoryEntry(item.dataset.history);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!$('#modalWrap').hidden) closeModal();
    else if (!$('#drawer').hidden) closeDrawer();
  });
}

/* ---------------- 启动 ---------------- */

async function init() {
  bindEvents();
  updateClock();
  setInterval(updateClock, 1000);
  state.history = loadHistory();
  renderBadge();
  resetRecord();

  try {
    const response = await fetch('/api/problems', { cache: 'no-store' });
    if (!response.ok) throw new Error(`读取题目列表失败（HTTP ${response.status}）`);
    state.catalog = await response.json();
  } catch (error) {
    showMessage(`${error.message}。请通过「启动评测机.cmd」打开页面。`, 'error');
    $('#statement').innerHTML = `<tbody><tr><th scope="row">题面</th><td class="stmt-loading">${esc(error.message)}</td></tr></tbody>`;
    return;
  }

  const params = new URLSearchParams(location.search);
  const requestedJob = params.get('job');
  if (requestedJob) {
    await loadJob(requestedJob);
    return;
  }

  let requested = (params.get('problem') || '').toUpperCase();
  if (requested && !requested.includes('-')) requested = `P6-${requested}`;
  const key = state.catalog[requested] ? requested : Object.keys(state.catalog)[0];
  if (key) selectProblem(key);
}

document.addEventListener('DOMContentLoaded', init);
