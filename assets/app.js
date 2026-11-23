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
const PROFILE_KEY = 'p6web.profile.v1';
const POSTS_KEY = 'p6web.posts.v1';
const MAX_HISTORY = 100;

const STAGES = ['P3', 'P4', 'P5', 'P6'];
const STAGE_INFO = {
  P3: { title: 'Logisim 单周期 CPU', backend: 'Java + Logisim', color: 'P3' },
  P4: { title: 'Verilog 单周期 CPU', backend: 'Icarus WebAssembly', color: 'P4' },
  P5: { title: '五级流水线 CPU', backend: 'Icarus WebAssembly', color: 'P5' },
  P6: { title: '流水线 + 外置 IM/DM', backend: 'Icarus WebAssembly', color: 'P6' },
};

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
  view: 'announcements',
  stage: null,
  stageLast: {},
  profile: null,
  posts: [],
  submissions: [],
  submissionStage: 'all',
  postFilter: 'all',
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

function readJSON(key, fallback) {
  try {
    const raw = JSON.parse(localStorage.getItem(key) || 'null');
    return raw ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 本地存储被禁用时只保留内存状态 */
  }
}

function uid(prefix = 'id') {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function defaultProfile() {
  return {
    name: '本地同学',
    username: 'student',
    email: '',
    course: '2026 秋季课程',
    color: '#5c6bc0',
    joined: Date.now(),
  };
}

function loadProfile() {
  const saved = readJSON(PROFILE_KEY, null);
  return { ...defaultProfile(), ...(saved && typeof saved === 'object' ? saved : {}) };
}

function saveProfile() {
  writeJSON(PROFILE_KEY, state.profile);
}

function avatarInitial(name) {
  const text = String(name || '').trim();
  return text ? text.slice(0, 1).toUpperCase() : '?';
}

function applyProfile() {
  const profile = state.profile || defaultProfile();
  const avatar = $('#topAvatar');
  if (avatar) {
    avatar.textContent = avatarInitial(profile.name);
    avatar.style.background = profile.color || '#5c6bc0';
  }
  const big = $('#profileAvatar');
  if (big) {
    big.textContent = avatarInitial(profile.name);
    big.style.background = profile.color || '#5c6bc0';
  }
  if ($('#profilePreviewName')) $('#profilePreviewName').textContent = profile.name;
  if ($('#profilePreviewMeta')) {
    $('#profilePreviewMeta').textContent = [profile.username, profile.course].filter(Boolean).join(' · ') || '未填写';
  }
  if ($('#profileFactJoined')) {
    const joined = new Date(profile.joined || Date.now());
    $('#profileFactJoined').textContent = `${joined.getFullYear()}-${pad(joined.getMonth() + 1)}-${pad(joined.getDate())}`;
  }
}

function seedPosts() {
  const now = Date.now();
  const day = 24 * 60 * 60 * 1000;
  return [
    {
      id: 'seed-p3-base',
      title: 'P3 加指令练习：先用 BASE 跑通，再一条条加',
      body: '建议每次改完电路先跑 P3-BASE 的 4 个测试点，确认基础八条指令和复位没有回归，再跑当前 E 题。\n\n加指令时最容易漏的是：Controller 的 ALUOp / RegWrite / MemWrite 和 Datapath 的新通路要同时改；改完先在 Logisim 里单步看一条指令，再提交。',
      tags: ['P3', '经验'],
      author: '本地示例',
      createdAt: now - 3 * day,
      seed: true,
      comments: [
        { id: 'seed-c1', author: '本地示例', body: 'P3 评测器只支持单 32 位 RAM，四块 8 位 RAM 分银行会报“存储器尺寸不匹配”。', createdAt: now - 2 * day },
      ],
    },
    {
      id: 'seed-p4-trace',
      title: 'P4 2025 真题：写入日志的 PC 和寄存器顺序',
      body: 'P4 的日志按写回顺序比较，PC 用十六进制、寄存器用 $0–$31。建议先把单条指令的 trace 和题目册对照，再跑整套。\n\n如果 CPU 不打印，但保留了 regwrite / RegAddr / RegData / Memwrite / addr / WD / pc，评测器会自动用探针 testbench 采集。',
      tags: ['P4', '经验'],
      author: '本地示例',
      createdAt: now - 2 * day,
      seed: true,
      comments: [],
    },
    {
      id: 'seed-p5-pipeline',
      title: 'P5 流水线：先确认转发和阻塞，再谈冒险',
      body: 'P5 的 24 个点里，复位和第一条指令最容易暴露时序问题。建议先跑 Q01，确认流水线在空泡和转发下的写回顺序，再看分支/加载-use 的阻塞。',
      tags: ['P5', '经验'],
      author: '本地示例',
      createdAt: now - day,
      seed: true,
      comments: [],
    },
  ];
}

function loadPosts() {
  const saved = readJSON(POSTS_KEY, null);
  if (Array.isArray(saved)) return saved;
  const seeded = seedPosts();
  writeJSON(POSTS_KEY, seeded);
  return seeded;
}

function savePosts() {
  writeJSON(POSTS_KEY, state.posts);
}

function stageProblems(stage) {
  return Object.entries(state.catalog)
    .filter(([, spec]) => spec.stage === stage)
    .map(([key]) => key);
}

function totalCases(stage) {
  return stageProblems(stage).reduce((sum, key) => sum + (state.catalog[key].cases?.length || 0), 0);
}

function problemResult(entry) {
  if (!entry) return null;
  const passed = Number(entry.passed) || 0;
  const total = Number(entry.total) || 0;
  return { passed, total, ok: total > 0 && passed === total };
}

function historyForProblem(key) {
  return state.history.filter((entry) => entry.problem === key);
}

function bestHistoryForProblem(key) {
  const entries = historyForProblem(key);
  if (!entries.length) return null;
  const ok = entries.find((entry) => problemResult(entry)?.ok);
  return ok || entries[0];
}

function stageSummary(stage) {
  const keys = stageProblems(stage);
  let passed = 0;
  let attempted = 0;
  for (const key of keys) {
    const best = bestHistoryForProblem(key);
    if (best) {
      attempted += 1;
      if (problemResult(best)?.ok) passed += 1;
    }
  }
  return { total: keys.length, cases: totalCases(stage), passed, attempted };
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
  if (!raw) return `<div class="muted">${spec.id === 'BASE' ? 'BASE 不新增指令编码。' : '本题没有这种编码。'}</div>`;
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
  ].filter((desc) => !state.stage || desc.stage === state.stage);
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
  const total = state.stage
    ? stageProblems(state.stage).reduce((sum, key) => sum + (state.catalog[key].cases?.length || 0), 0)
    : Object.values(state.catalog).reduce((sum, spec) => sum + spec.cases.length, 0);
  $('#drawerTitle').textContent = state.stage ? `${state.stage} 题库` : '题库';
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
    updateUrl({ job: data.id });
    if (location.hash !== `#/problem/${state.key}`) history.replaceState(null, '', `#/problem/${state.key}`);
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
      updateUrl({ job: job.id });
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
  state.stage = spec.stage;
  state.stageLast[spec.stage] = key;
  state.encoding = encoding === 'original' && spec.original ? 'original' : 'practice';
  renderStatement();
  renderEncodingOptions();
  renderStageContext(spec);
  $$('#problemList .bank-item').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.problem === key);
  });
  return true;
}

function renderStageContext(spec) {
  const info = STAGE_INFO[spec.stage] || { title: '', backend: '' };
  const label = `${spec.stage} 上机考试`;
  $('#examStageLabel').textContent = label;
  $$('#stageTabs a').forEach((link) => link.classList.toggle('is-active', link.dataset.stage === spec.stage));
  const title = $('#pageTitle');
  if (title) {
    title.textContent = label;
    title.classList.add('is-link');
    title.title = '打开题库';
  }
  if ($('#pageSub')) $('#pageSub').textContent = `${info.title} · ${stageProblems(spec.stage).length} 题组`;
  const drawer = $('#drawerTitle');
  if (drawer) drawer.textContent = `${spec.stage} 题库`;
}

function updateUrl(params) {
  const url = new URL(location.href);
  if ('job' in params) {
    if (params.job) url.searchParams.set('job', params.job);
    else url.searchParams.delete('job');
  }
  history.replaceState({}, '', url);
}

function selectProblem(key, options = {}) {
  if (state.busy) {
    toast('评测进行中，请等待完成后再切换题目');
    return false;
  }
  if (!renderProblem(key, 'practice')) return false;
  resetRecord();
  clearFiles();
  showMessage('');
  setView('problem');
  if (!options.keepHash) {
    const hash = `#/problem/${key}`;
    if (location.hash !== hash) history.pushState(null, '', hash);
  }
  updateUrl({ job: null });
  return true;
}

async function loadJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store' });
    if (!response.ok) {
      const saved = await fetch('/api/submissions', { cache: 'no-store' })
        .then((item) => item.json())
        .then((list) => (Array.isArray(list) ? list : list.submissions || []).find((entry) => entry.id === jobId))
        .catch(() => null);
      if (saved && state.catalog[saved.problem] && saved.results?.length) {
        renderProblem(saved.problem, saved.encoding);
        setView('problem');
        applyJob({
          id: saved.id,
          problem: saved.problem,
          encoding: saved.encoding || 'practice',
          state: 'done',
          created: saved.created || Math.floor(Date.now() / 1000),
          results: saved.results,
          summary: {
            passed: saved.summary?.passed ?? 0,
            total: saved.summary?.total ?? saved.results.length,
            seconds: saved.summary?.seconds ?? 0,
            record: saved.summary?.record || '',
            results: saved.results,
          },
        }, { restored: true });
        history.replaceState(null, '', `#/problem/${saved.problem}`);
        updateUrl({ job: saved.id });
        return;
      }
      throw new Error('找不到这条提交记录，服务重启后旧记录会失效');
    }
    const job = await response.json();
    if (!state.catalog[job.problem]) throw new Error('记录中的题号不在当前题库中');
    renderProblem(job.problem, job.encoding);
    setView('problem');
    applyJob(job, { restored: true });
    if (location.hash !== `#/problem/${job.problem}`) history.replaceState(null, '', `#/problem/${job.problem}`);
    updateUrl({ job: job.id });
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
      selectProblem(key, { keepHash: true });
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
    setView('problem');
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
    history.replaceState(null, '', `#/problem/${entry.problem}`);
    updateUrl({ job: entry.id });
  } else {
    await loadJob(entry.id);
  }
}

/* ---------------- 多页面视图 ---------------- */

const VIEW_META = {
  announcements: { title: '课程公告', sub: '本地练习平台 · 版本与说明' },
  submissions: { title: '课下提交', sub: '本机保存的代码与结果' },
  exams: { title: '课上考试', sub: 'P3 / P4 / P5 / P6' },
  discussion: { title: '讨论区', sub: '做题经验与评论' },
  profile: { title: '用户中心', sub: '本地个人信息' },
  stats: { title: '统计图', sub: '练习覆盖与通过率' },
  tutorial: { title: '实验教程', sub: '启动、提交与判题规则' },
};

const ANNOUNCEMENTS = [
  {
    date: '2026-11-23',
    tag: '更新',
    title: 'v1.1.0：课程平台式导航上线',
    body: `<p>左侧导航改成课程平台的多页面结构，原来的题目 / 提交双栏仍然保留在「课上考试」里。</p>
      <ul>
        <li><b>课程公告</b>：版本更新、使用说明和 P3 电路适配提醒；</li>
        <li><b>课下提交</b>：保存本机的提交记录、上传的代码和结果入口；</li>
        <li><b>课上考试</b>：P3 / P4 / P5 / P6 四个独立入口，进入后题目抽屉只显示对应阶段；</li>
        <li><b>讨论区</b>：发布做题经验、评论；<b>用户中心</b>：本地昵称、学号、邮箱与头像；</li>
        <li><b>统计图</b>：练习覆盖热力图、能力雷达和各阶段进度。</li>
      </ul>`,
    actions: [['#/exams', '进入课上考试'], ['#/tutorial', '查看实验教程']],
  },
  {
    date: '2026-11-22',
    tag: '版本',
    cls: 'green',
    title: 'P3–P6 本地评测器 v1.0.0',
    body: `<p>P3 加指令练习、P4 加指令练习与 2025 真题、P5、P6 已合并到同一个本机页面，共 <b>123 个题组、2239 个测试点</b>。</p>
      <p>P3 使用 Logisim 2.7.1，需要 Java 8+；P4 / P5 / P6 使用随包的 Icarus WebAssembly，需要 Node.js 20+。</p>`,
    actions: [['#/exams', '开始练习']],
  },
  {
    date: '2026-11-20',
    tag: '说明',
    title: '怎么提交：P3 交 .circ，P4–P6 交 ZIP 或 .v',
    body: `<ul>
      <li>P3：在「课上考试 → P3」里选一道题，上传一个 Logisim <code>.circ</code>；顶层必须是 <code>main</code>。</li>
      <li>P4 / P5 / P6：上传当前工程的 ZIP，或全部 <code>.v</code> / <code>.vh</code>；也可以填写本机源码目录。</li>
      <li>提交后逐点显示 AC / WA / TLE / CE / RE；点测试点可以展开周期和首个差异。</li>
      <li>超过 20 MB 的工程请先在本地删掉 ISE 的临时目录，只保留 RTL 和必要的 IP。</li>
    </ul>`,
    actions: [['#/tutorial', '提交说明']],
  },
  {
    date: '2026-11-18',
    tag: 'P3',
    cls: 'green',
    title: 'P3 电路适配：单 32 位 RAM 与 8 个顶层输出',
    body: `<p>P3 评测器要求 <code>main</code> 顶层带 8 个输出：<code>Instr / pc / RegWrite / RegAddr / RegData / MemWrite / MemAddr / MemData</code>，DM 是单一 32 位 RAM（4096 字，有效 3072 字）。</p>
      <p>四块 8 位 RAM 分银行的电路会报“存储器尺寸不匹配”，需要先改成单 RAM 结构。P3 的 <code>.circ</code> 不会被修改。</p>`,
    actions: [['#/exam/P3', '打开 P3']],
  },
];

function setView(name) {
  const meta = VIEW_META[name];
  if (!meta && name !== 'problem') name = 'announcements';
  state.view = name;
  $$('.view').forEach((view) => { view.hidden = true; });
  const node = $(`#view-${name}`);
  if (node) node.hidden = false;

  $$('.nav-item').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.view === (name === 'problem' ? 'exams' : name));
  });

  const title = $('#pageTitle');
  title.classList.toggle('is-link', name === 'problem');
  title.title = name === 'problem' ? '打开题库' : '';
  if (name === 'problem') {
    const stage = state.stage || 'P3';
    title.textContent = `${stage} 上机考试`;
    $('#pageSub').textContent = `${(STAGE_INFO[stage] || {}).title || ''} · ${stageProblems(stage).length} 题组`;
    document.title = `${stage} 上机考试 · BUAA CO 本地评测`;
  } else {
    title.textContent = meta.title;
    $('#pageSub').textContent = meta.sub;
    document.title = `${meta.title} · BUAA CO 本地评测`;
    closeDrawer();
  }

  if (name === 'announcements') renderAnnouncements();
  else if (name === 'exams') renderExams();
  else if (name === 'submissions') { renderSubmissions(); loadSubmissions(); }
  else if (name === 'discussion') renderPosts();
  else if (name === 'profile') renderProfile();
  else if (name === 'stats') renderStats();
  else if (name === 'tutorial') renderTutorial();
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function navigate(path) {
  if (location.hash === path) return;
  location.hash = path;
}

function route() {
  const raw = (location.hash || '#/announcements').replace(/^#\/?/, '');
  const parts = raw.split('?')[0].split('/').filter(Boolean);
  if (!state.catalog || !Object.keys(state.catalog).length) return;

  if (parts[0] === 'problem' && parts[1]) {
    const key = parts[1].toUpperCase();
    if (state.catalog[key]) {
      if (state.view !== 'problem' || state.key !== key) {
        if (state.busy) {
          toast('评测进行中，请等待完成后再切换题目');
          return;
        }
        renderProblem(key, 'practice');
        setView('problem');
      }
      return;
    }
  }

  if (parts[0] === 'exam' && STAGES.includes(parts[1])) {
    openStage(parts[1]);
    return;
  }

  if (parts[0] && VIEW_META[parts[0]]) {
    setView(parts[0]);
    return;
  }

  setView('announcements');
}

function openStage(stage) {
  if (!STAGES.includes(stage)) return;
  if (state.busy) {
    toast('评测进行中，请等待完成后再切换阶段');
    return;
  }
  const key = state.stageLast[stage] || stageProblems(stage)[0];
  if (!key) return;
  selectProblem(key, { keepHash: true });
  history.replaceState(null, '', `#/problem/${key}`);
}

/* ---------------- 课程公告 ---------------- */

function renderAnnouncements() {
  $('#noticeList').innerHTML = ANNOUNCEMENTS.map((item) => `
    <article class="notice-card">
      <div class="notice-head">
        <span class="notice-date">${esc(item.date)}</span>
        <span class="notice-tag${item.cls ? ` ${item.cls}` : ''}">${esc(item.tag)}</span>
      </div>
      <h2 class="notice-title">${esc(item.title)}</h2>
      <div class="notice-body">${item.body}</div>
      ${item.actions?.length ? `<div class="notice-actions">${item.actions.map(([href, text]) => `<a class="notice-link" href="${href}">${esc(text)}<svg class="icon"><use href="#i-chevron-right"/></svg></a>`).join('')}</div>` : ''}
    </article>`).join('');
}

/* ---------------- 课上考试 ---------------- */

function renderExams() {
  $('#examGrid').innerHTML = STAGES.map((stage) => {
    const info = STAGE_INFO[stage];
    const summary = stageSummary(stage);
    const percent = summary.total ? Math.round((summary.passed / summary.total) * 100) : 0;
    const status = summary.passed === summary.total && summary.total > 0
      ? '<span class="status-tag ok">已通过</span>'
      : summary.attempted > 0
        ? '<span class="status-tag hot">进行中</span>'
        : '<span class="status-tag">已开放</span>';
    const recent = state.history.find((entry) => entry.problem.startsWith(`${stage}-`));
    return `<article class="exam-card">
      <div class="exam-card-head">
        <span class="stage-badge ${stage}">${stage}</span>
        ${status}
      </div>
      <h3>${stage} 上机考试<small>${esc(info.title)}</small></h3>
      <p class="exam-desc">${summary.total} 个题组、${summary.cases} 个测试点 · ${esc(info.backend)}</p>
      <dl class="exam-facts">
        <div><dt>题组</dt><dd>${summary.total}</dd></div>
        <div><dt>测试点</dt><dd>${summary.cases}</dd></div>
        <div><dt>最近提交</dt><dd>${recent ? esc(formatShortTime(recent.time)) : '—'}</dd></div>
      </dl>
      <div class="exam-progress">
        <div class="bar-line"><i style="width:${percent}%"></i></div>
        <p><span>已通过 ${summary.passed} / ${summary.total}</span><span>${percent}%</span></p>
      </div>
      <a class="exam-link" href="#/exam/${stage}">查看考试<svg class="icon"><use href="#i-chevron-right"/></svg></a>
    </article>`;
  }).join('');
}

/* ---------------- 课下提交 ---------------- */

async function loadSubmissions(force = false) {
  if (state.submissions.length && !force) return;
  try {
    const response = await fetch('/api/submissions', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.submissions = Array.isArray(data) ? data : (data.submissions || []);
  } catch {
    state.submissions = state.history.map((entry) => ({
      id: entry.id,
      problem: entry.problem,
      stage: (entry.problem || '').split('-')[0],
      created: Math.floor(entry.time / 1000),
      state: 'done',
      summary: { passed: entry.passed, total: entry.total, seconds: entry.seconds, record: entry.record },
      results: entry.results || [],
      files: [],
    }));
  }
  if (state.view === 'submissions') renderSubmissions();
}

function submissionTime(entry) {
  const value = Number(entry.created || 0);
  const ms = value > 1e12 ? value : value * 1000;
  return ms ? formatTime(new Date(ms)) : '—';
}

function renderSubmissions() {
  const filter = state.submissionStage;
  const list = (state.submissions || [])
    .filter((entry) => filter === 'all' || (entry.stage || entry.problem?.split('-')[0]) === filter)
    .sort((a, b) => (b.created || 0) - (a.created || 0));
  if (!list.length) {
    $('#submissionList').innerHTML = `<div class="empty-panel"><b>还没有保存的提交</b>去「课上考试」选一道题开始；P3 交 .circ，P4–P6 交 ZIP 或 .v。<div class="notice-actions" style="justify-content:center"><a class="btn primary" href="#/exams">去题库</a></div></div>`;
    return;
  }
  $('#submissionList').innerHTML = list.map((entry) => {
    const spec = state.catalog[entry.problem] || {};
    const stage = entry.stage || (entry.problem || '').split('-')[0] || '—';
    const summary = entry.summary || {};
    const passed = Number(summary.passed) || 0;
    const total = Number(summary.total) || 0;
    const ok = total > 0 && passed === total;
    const files = (entry.files || []).map((file) => {
      const name = typeof file === 'string' ? file : file.name;
      const size = typeof file === 'string' ? 0 : file.size;
      return `<a class="file-link" href="/api/submissions/${encodeURIComponent(entry.id)}/file/${encodeURIComponent(name)}" download title="下载 ${esc(name)}"><svg class="icon"><use href="#i-download"/></svg>${esc(name)}${size ? ` · ${formatBytes(size)}` : ''}</a>`;
    }).join('');
    return `<article class="submission-row">
      <span class="stage-badge ${stage}">${esc(stage)}</span>
      <div class="submission-main">
        <div class="submission-title"><b>${esc(entry.problem)}</b><span>${esc(spec.name || '')}</span></div>
        <div class="submission-meta"><span>${submissionTime(entry)}</span><span>${esc(entry.encoding === 'original' ? '原平台编码' : '练习编码')}</span></div>
        ${files ? `<div class="submission-files">${files}</div>` : (entry.source_path ? `<div class="submission-meta"><span>本机路径：${esc(entry.source_path)}</span></div>` : '')}
        <div class="submission-actions">
          <button type="button" data-open-submission="${esc(entry.id)}">查看结果</button>
          <button type="button" data-resubmit="${esc(entry.problem)}">重新提交</button>
        </div>
      </div>
      <div class="submission-result">
        <b class="${ok ? 'ok' : 'fail'}">${passed} / ${total}</b>
        <small>${ok ? '全部通过' : (entry.state === 'error' ? '评测失败' : '未通过')}</small>
      </div>
    </article>`;
  }).join('');
}

function openStoredSubmission(id) {
  const entry = (state.submissions || []).find((item) => item.id === id);
  if (!entry) return;
  if (state.busy) {
    toast('评测进行中，请等待完成后再查看');
    return;
  }
  const key = entry.problem;
  if (!state.catalog[key]) {
    toast('这条记录对应的题目不在当前题库里');
    return;
  }
  selectProblem(key, { keepHash: true });
  history.replaceState(null, '', `#/problem/${key}`);
  if (entry.results?.length) {
    applyJob({
      id: entry.id,
      problem: key,
      encoding: entry.encoding || 'practice',
      state: 'done',
      created: entry.created || Math.floor(Date.now() / 1000),
      results: entry.results,
      summary: {
        passed: entry.summary?.passed ?? 0,
        total: entry.summary?.total ?? entry.results.length,
        seconds: entry.summary?.seconds ?? 0,
        record: entry.summary?.record || '',
        results: entry.results,
      },
    }, { restored: true });
    updateUrl({ job: entry.id });
  } else {
    updateUrl({ job: null });
    toast('已打开题目；这条记录没有保存逐点结果');
  }
}

/* ---------------- 讨论区 ---------------- */

function postMatches(post, filter) {
  if (filter === 'all') return true;
  return (post.tags || []).includes(filter);
}

function renderPosts() {
  const posts = (state.posts || []).filter((post) => postMatches(post, state.postFilter));
  if (!posts.length) {
    $('#postList').innerHTML = `<div class="empty-panel post-empty"><b>这个标签下还没有帖子</b>发布第一条做题经验吧。<div class="notice-actions" style="justify-content:center"><button class="btn primary" type="button" id="emptyNewPost">发布经验</button></div></div>`;
    return;
  }
  $('#postList').innerHTML = posts.map((post) => {
    const tags = (post.tags || []).map((tag) => `<span class="post-tag ${STAGES.includes(tag) ? tag : ''}">${esc(tag)}</span>`).join('');
    const date = post.createdAt ? formatShortTime(post.createdAt) : '';
    return `<article class="post-card" data-post="${esc(post.id)}">
      <div class="post-tags">${tags}</div>
      <h3>${esc(post.title)}</h3>
      <p class="post-excerpt">${esc(post.body)}</p>
      <div class="post-foot">
        <span class="post-author"><span class="post-avatar">${esc(avatarInitial(post.author))}</span>${esc(post.author)}</span>
        <span>${esc(date)} · ${post.comments?.length || 0} 条评论</span>
      </div>
    </article>`;
  }).join('');
}

function openPost(id) {
  const post = (state.posts || []).find((item) => item.id === id);
  if (!post) return;
  const comments = (post.comments || []).map((comment) => `
    <div class="comment-item">
      <div class="comment-head"><b>${esc(comment.author)}</b><span>${esc(formatShortTime(comment.createdAt))}</span></div>
      <div class="comment-body">${esc(comment.body)}</div>
    </div>`).join('');
  const canDelete = !post.seed;
  openModal(post.title, `
    <div class="post-detail-meta"><span>${esc(post.author)}</span><span>${esc(formatShortTime(post.createdAt))}</span><span>${(post.tags || []).map(esc).join(' · ')}</span></div>
    <div class="post-detail-body">${esc(post.body)}</div>
    ${canDelete ? `<div class="form-actions"><button class="btn ghost" type="button" data-delete-post="${esc(post.id)}"><svg class="icon"><use href="#i-trash"/></svg>删除帖子</button></div>` : ''}
    <div class="comment-list">${comments || '<div class="history-empty">还没有评论，写下第一条吧。</div>'}</div>
    <form class="comment-form" data-comment-post="${esc(post.id)}">
      <input name="comment" maxlength="300" placeholder="写下你的评论…" autocomplete="off" required>
      <button class="btn primary" type="submit"><svg class="icon"><use href="#i-send"/></svg>发送</button>
    </form>`);
}

function openNewPost() {
  openModal('发布经验', `
    <form class="modal-form" id="newPostForm">
      <label class="form-field"><span>标题</span><input name="title" maxlength="60" placeholder="例如：P3 加指令后 BASE 回归失败" required></label>
      <label class="form-field"><span>正文</span><textarea name="body" maxlength="4000" placeholder="记录现象、定位过程和解决办法…" required></textarea></label>
      <div class="form-field"><span>标签（可多选）</span>
        <div class="tag-row" style="margin:0">${['P3', 'P4', 'P5', 'P6', '经验', '求助'].map((tag) => `<label class="chip" style="display:inline-flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" name="tags" value="${tag}">${tag}</label>`).join('')}</div>
      </div>
      <div class="form-actions"><button class="btn primary" type="submit">发布</button><button class="btn ghost" type="button" data-close-modal>取消</button></div>
    </form>`);
}

function createPost(form) {
  const data = new FormData(form);
  const title = String(data.get('title') || '').trim();
  const body = String(data.get('body') || '').trim();
  const tags = data.getAll('tags').map(String);
  if (!title || !body) {
    toast('标题和正文不能为空', 'error');
    return;
  }
  state.posts.unshift({
    id: uid('post'),
    title,
    body,
    tags: tags.length ? tags : ['经验'],
    author: state.profile.name || '本地同学',
    createdAt: Date.now(),
    comments: [],
  });
  savePosts();
  closeModal();
  state.postFilter = 'all';
  setView('discussion');
  toast('已发布', 'ok');
}

function addComment(postId, text) {
  const post = (state.posts || []).find((item) => item.id === postId);
  const body = String(text || '').trim();
  if (!post || !body) return;
  post.comments = post.comments || [];
  post.comments.push({ id: uid('c'), author: state.profile.name || '本地同学', body, createdAt: Date.now() });
  savePosts();
  openPost(postId);
  const input = $('#modalBody .comment-form input');
  if (input) input.focus();
}

function deletePost(id) {
  state.posts = state.posts.filter((post) => post.id !== id || post.seed);
  savePosts();
  closeModal();
  renderPosts();
  toast('已删除', 'ok');
}

/* ---------------- 用户中心 ---------------- */

function renderProfile() {
  const profile = state.profile;
  applyProfile();
  if ($('#profileName')) $('#profileName').value = profile.name || '';
  if ($('#profileUsername')) $('#profileUsername').value = profile.username || '';
  if ($('#profileEmail')) $('#profileEmail').value = profile.email || '';
  if ($('#profileCourse')) $('#profileCourse').value = profile.course || '';
  if ($('#profileColor')) $('#profileColor').value = profile.color || '#5c6bc0';
  const passed = new Set(state.history.filter((entry) => problemResult(entry)?.ok).map((entry) => entry.problem)).size;
  if ($('#profileFactSubmissions')) $('#profileFactSubmissions').textContent = state.history.length;
  if ($('#profileFactPassed')) $('#profileFactPassed').textContent = passed;
  if ($('#profileFactJoined')) {
    const joined = new Date(profile.joined || Date.now());
    $('#profileFactJoined').textContent = `${joined.getFullYear()}-${pad(joined.getMonth() + 1)}-${pad(joined.getDate())}`;
  }
}

function saveProfileForm() {
  const profile = {
    ...state.profile,
    name: $('#profileName').value.trim() || '本地同学',
    username: $('#profileUsername').value.trim(),
    email: $('#profileEmail').value.trim(),
    course: $('#profileCourse').value.trim(),
    color: $('#profileColor').value || '#5c6bc0',
  };
  state.profile = profile;
  saveProfile();
  applyProfile();
  renderProfile();
  toast('设置已保存', 'ok');
}

/* ---------------- 统计图 ---------------- */

function statsData() {
  const uniqueAttempted = new Set(state.history.map((entry) => entry.problem));
  const uniquePassed = new Set(state.history.filter((entry) => problemResult(entry)?.ok).map((entry) => entry.problem));
  const totalCases = state.history.reduce((sum, entry) => sum + (Number(entry.total) || 0), 0);
  const passedCases = state.history.reduce((sum, entry) => sum + (Number(entry.passed) || 0), 0);
  const byStage = {};
  for (const stage of STAGES) {
    const summary = stageSummary(stage);
    const entries = state.history.filter((entry) => entry.problem.startsWith(`${stage}-`));
    byStage[stage] = {
      ...summary,
      submissions: entries.length,
      rate: summary.total ? Math.round((summary.passed / summary.total) * 100) : 0,
    };
  }
  return {
    attempts: state.history.length,
    attempted: uniqueAttempted.size,
    passed: uniquePassed.size,
    totalCases,
    passedCases,
    caseRate: totalCases ? Math.round((passedCases / totalCases) * 100) : 0,
    byStage,
  };
}

function renderStats() {
  const data = statsData();
  const allProblems = Object.keys(state.catalog).length;
  const cards = [
    ['已提交', data.attempts, `覆盖 ${data.attempted} / ${allProblems} 个题组`],
    ['已通过题组', data.passed, `共 ${allProblems} 个题组`],
    ['通过测试点', `${data.passedCases} / ${data.totalCases}`, `测试点通过率 ${data.caseRate}%`],
    ['最近活跃', state.history[0] ? formatShortTime(state.history[0].time) : '—', state.history[0] ? `${state.history[0].problem} · ${state.history[0].passed}/${state.history[0].total}` : '还没有提交'],
  ];
  $('#statCards').innerHTML = cards.map(([label, value, foot]) => `<div class="stat-card"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-foot">${esc(foot)}</div></div>`).join('');

  const rows = STAGES.map((stage) => {
    const cells = stageProblems(stage).map((key) => {
      const best = bestHistoryForProblem(key);
      const result = best ? problemResult(best) : null;
      let cls = '';
      let title = `${key} · 未提交`;
      if (result) {
        if (result.ok) { cls = 'pass'; title = `${key} · ${result.passed}/${result.total} AC`; }
        else if (result.total && result.passed === 0 && best.total === 0) { cls = 're'; title = `${key} · 评测失败`; }
        else { cls = 'attempt'; title = `${key} · ${result.passed}/${result.total}`; }
      }
      return `<span class="heat-cell ${cls}" title="${esc(title)}"></span>`;
    }).join('');
    return `<div class="heat-row"><span class="heat-label">${stage}</span><div class="heat-cells">${cells}</div></div>`;
  }).join('');
  $('#coverageHeatmap').innerHTML = `${rows}
    <div class="heat-legend"><span><i class="heat-dot" style="background:#66bb6a"></i>已通过</span><span><i class="heat-dot" style="background:#ffb74d"></i>已提交未通过</span><span><i class="heat-dot" style="background:#ef9a9a"></i>评测失败</span><span><i class="heat-dot" style="background:#eceff1"></i>未提交</span></div>
    <div class="heat-recent"><div class="heat-recent-title">最近提交</div>${state.history.length ? state.history.slice(0, 5).map((entry) => `<div class="heat-recent-row"><a href="#/problem/${esc(entry.problem)}">${esc(entry.problem)}</a><span>${esc(entry.passed)} / ${esc(entry.total)} · ${esc(formatShortTime(entry.time))}</span></div>`).join('') : '<div class="heat-recent-row"><span>还没有提交记录</span></div>'}</div>`;

  const values = [
    data.byStage.P3.rate,
    data.byStage.P4.rate,
    data.byStage.P5.rate,
    data.byStage.P6.rate,
    allProblems ? Math.round((data.passed / allProblems) * 100) : 0,
    Math.min(100, Math.round((data.attempts / 50) * 100)),
  ];
  const labels = ['P3', 'P4', 'P5', 'P6', '覆盖', '活跃'];
  const cx = 150;
  const cy = 136;
  const radius = 92;
  const point = (index, ratio) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / labels.length;
    return [cx + Math.cos(angle) * radius * ratio, cy + Math.sin(angle) * radius * ratio];
  };
  const rings = [0.25, 0.5, 0.75, 1].map((ratio) => `<polygon points="${labels.map((_, i) => point(i, ratio).map((v) => v.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="#e3e8ef" stroke-width="1"/>`).join('');
  const axes = labels.map((_, i) => {
    const [x, y] = point(i, 1);
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#e3e8ef"/>`;
  }).join('');
  const polygon = values.map((value, i) => point(i, Math.max(0.02, value / 100)).map((v) => v.toFixed(1)).join(',')).join(' ');
  const dots = values.map((value, i) => {
    const [x, y] = point(i, Math.max(0.02, value / 100));
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="#5c6bc0"/>`;
  }).join('');
  const text = labels.map((label, i) => {
    const [x, y] = point(i, 1.18);
    return `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="middle" font-size="10" fill="#78909c">${label}</text>`;
  }).join('');
  $('#radarChart').innerHTML = `<title>能力雷达</title>${rings}${axes}<polygon points="${polygon}" fill="rgba(92,107,192,.22)" stroke="#5c6bc0" stroke-width="2"/>${dots}${text}`;

  $('#stageStats').innerHTML = STAGES.map((stage) => {
    const item = data.byStage[stage];
    return `<div class="stage-row"><span class="stage-name">${stage}</span><div class="stage-bar"><i style="width:${item.rate}%"></i></div><span class="stage-num">${item.passed} / ${item.total}</span><span class="stage-rate">${item.rate}%</span></div>`;
  }).join('');
}

/* ---------------- 实验教程 ---------------- */

function renderTutorial() {
  $('#tutorialBody').innerHTML = `
    <section class="tutorial-card">
      <h2>启动</h2>
      <p>解压完整包后双击 <code>启动评测机.cmd</code>，或在本目录执行 <code>python server.py</code>，浏览器打开 <code>http://127.0.0.1:8766</code>。</p>
      <ul>
        <li>P3 需要 Java 8 或更新版本；P4 / P5 / P6 需要 Node.js 20+。</li>
        <li>如果提示端口被占用，先关闭旧的评测机窗口。</li>
        <li>源码仓库克隆后先运行一次 <code>python prepare_data.py</code> 生成 P5 / P6 测试点。</li>
      </ul>
      <h3>提交什么</h3>
      <ul>
        <li>P3：一个 Logisim 2.7.1 <code>.circ</code>，顶层 <code>main</code>。</li>
        <li>P4 / P5 / P6：工程 ZIP，或全部 <code>.v</code> / <code>.vh</code>；也可以填本机目录。</li>
        <li>只需要一个 <code>module mips</code> 顶层；工程自带 testbench 会被忽略。</li>
      </ul>
    </section>
    <section class="tutorial-card">
      <h2>判题状态</h2>
      <ul class="status-list">
        <li><span class="status-pill ac">AC</span>事件 / 状态全部一致，并在周期上限内完成。</li>
        <li><span class="status-pill wa">WA</span>PC、目的或数据不一致，或出现多余写入。</li>
        <li><span class="status-pill tle">TLE</span>事件前缀正确，但未在周期或墙钟上限内完成。</li>
        <li><span class="status-pill ce">CE</span>编译失败、缺少唯一的 <code>mips</code> 顶层，或含禁止的仿真任务。</li>
        <li><span class="status-pill re">RE</span>仿真进程异常退出，或 P3 电路适配失败。</li>
      </ul>
      <h3>P3 适配</h3>
      <p>P3 要求 <code>main</code> 顶层 8 个输出：<code>Instr / pc / RegWrite / RegAddr / RegData / MemWrite / MemAddr / MemData</code>；DM 是单一 32 位 RAM（4096 字，有效 3072 字），无延迟槽。四块 8 位 RAM 分银行会报“存储器尺寸不匹配”。</p>
    </section>
    <section class="tutorial-card">
      <h2>四种接口</h2>
      <p><b>P4</b> 顶层 <code>mips(clk, reset)</code>，IM / DM 在 CPU 内部，IM 从 <code>code.txt</code> 读取机器码，无延迟槽。CPU 按课程格式打印 <code>@PC: $寄存器 &lt;= 数据</code>；不打印但保留标准信号时，评测器会自动用探针 testbench。</p>
      <p><b>P5</b> 同样 <code>mips(clk, reset)</code>，内部 IM / DM，有延迟槽；GRF 和 DM 写入由课程日志输出。</p>
      <p><b>P6</b> 外置 IM / DM 端口和随包 testbench；CPU 内不要打印、不要读文件或自行结束。</p>
      <p><b>P3</b> Logisim 单周期，顶层 <code>main</code>；评测器在后台调用 Java + Logisim 2.7.1。</p>
    </section>
    <section class="tutorial-card">
      <h2>数据与日志</h2>
      <p>上传的文件保存在 <code>submissions/</code>；P3 报告在 <code>p3/results/</code>，P6 在 <code>runs/</code>，P5 在 <code>p5/runs/</code>，P4 在 <code>p4/runs/</code>。</p>
      <h3>课下提交页</h3>
      <p>「课下提交」会读取 <code>submissions/*/meta.json</code>，显示题号、时间、通过数和上传文件；点击文件名可下载当时提交的代码。</p>
      <h3>统计图</h3>
      <p>统计来自浏览器保存的最近 100 次提交；清除站点数据或换浏览器后不会保留。</p>
      <div class="notice-actions"><a class="btn primary" href="#/exams">去课上考试</a><a class="btn ghost" href="#/announcements">回到公告</a></div>
    </section>`;
}

/* ---------------- 通知 ---------------- */

function openNotifications() {
  const rows = state.history.slice(0, 6).map((entry) => {
    const ok = problemResult(entry)?.ok;
    return `<button class="history-item" type="button" data-history="${esc(entry.id)}">
      <span class="history-time">${formatShortTime(entry.time)}</span>
      <span class="history-name">${esc(entry.problem)} · ${esc(entry.name || '')}</span>
      <span class="history-verdict${ok ? '' : ' is-fail'}">${esc(entry.passed)} / ${esc(entry.total)}</span>
    </button>`;
  }).join('');
  openModal('通知', `
    <h3>提交动态</h3>
    ${rows || '<div class="history-empty">还没有提交记录。</div>'}
    <h3>公告</h3>
    <p><a href="#/announcements" data-close-modal>v1.1.0 课程平台式导航上线</a></p>
    <p><a href="#/submissions" data-close-modal>课下提交：查看保存的代码</a></p>
    <p><a href="#/stats" data-close-modal>统计图：练习覆盖与通过率</a></p>`);
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
  $('#pageTitle').addEventListener('click', () => {
    if (state.view === 'problem') {
      if ($('#drawer').hidden) openDrawer(); else closeDrawer();
    }
  });
  $$('[data-action="help"]').forEach((button) => button.addEventListener('click', openHelp));
  $('#bell').addEventListener('click', openNotifications);
  $('#topAvatar').addEventListener('click', () => navigate('#/profile'));
  $('#download').addEventListener('click', () => {
    if (!state.job) return;
    const blob = new Blob([JSON.stringify(state.job, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${state.job.problem}-${shortId(state.job.id)}-result.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 600);
  });

  $('#submissionFilter').addEventListener('click', (event) => {
    const button = event.target.closest('[data-stage]');
    if (!button) return;
    state.submissionStage = button.dataset.stage;
    $$('#submissionFilter button').forEach((item) => item.classList.toggle('is-active', item === button));
    renderSubmissions();
  });
  $('#refreshSubmissions').addEventListener('click', async () => {
    state.submissions = [];
    await loadSubmissions(true);
    toast('已刷新', 'ok');
  });
  $('#submissionList').addEventListener('click', (event) => {
    const open = event.target.closest('[data-open-submission]');
    if (open) { openStoredSubmission(open.dataset.openSubmission); return; }
    const again = event.target.closest('[data-resubmit]');
    if (again) { selectProblem(again.dataset.resubmit, { keepHash: true }); history.replaceState(null, '', `#/problem/${again.dataset.resubmit}`); }
  });

  $('#newPost').addEventListener('click', openNewPost);
  $('#postTags').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-tag]');
    if (!chip) return;
    state.postFilter = chip.dataset.tag;
    $$('#postTags .chip').forEach((item) => item.classList.toggle('is-active', item === chip));
    renderPosts();
  });
  $('#postList').addEventListener('click', (event) => {
    const empty = event.target.closest('#emptyNewPost');
    if (empty) { openNewPost(); return; }
    const card = event.target.closest('[data-post]');
    if (card) openPost(card.dataset.post);
  });

  $('#profileForm').addEventListener('submit', (event) => {
    event.preventDefault();
    saveProfileForm();
  });
  $('#profileReset').addEventListener('click', () => {
    state.profile = defaultProfile();
    saveProfile();
    renderProfile();
    toast('已恢复默认', 'ok');
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
    const history = event.target.closest('[data-history]');
    if (history) { openHistoryEntry(history.dataset.history); return; }
    const close = event.target.closest('[data-close-modal]');
    if (close) { closeModal(); return; }
    const remove = event.target.closest('[data-delete-post]');
    if (remove) { deletePost(remove.dataset.deletePost); return; }
  });
  $('#modalBody').addEventListener('submit', (event) => {
    event.preventDefault();
    if (event.target.id === 'newPostForm') {
      createPost(event.target);
      return;
    }
    const postId = event.target.dataset.commentPost;
    if (postId) {
      const input = event.target.querySelector('input[name="comment"]');
      addComment(postId, input ? input.value : '');
    }
  });

  window.addEventListener('hashchange', route);

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
  state.profile = loadProfile();
  state.posts = loadPosts();
  state.history = loadHistory();
  applyProfile();
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
  if (requested && state.catalog[requested] && !location.hash) {
    selectProblem(requested, { keepHash: true });
    history.replaceState(null, '', `#/problem/${requested}`);
    return;
  }

  route();
}

document.addEventListener('DOMContentLoaded', init);
