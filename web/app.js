'use strict';

(() => {
  const $ = (query, root = document) => root.querySelector(query);
  const $$ = (query, root = document) => Array.from(root.querySelectorAll(query));
  const STORAGE_KEY = '智能座舱AIGC.workflow.v1';
  const TYPES = ['prompt', 'reference', 'settings', 'generate', 'output'];
  const META = {
    prompt: { title: '文本提示词', color: 'pink', width: 350, height: 315 },
    reference: { title: '参考图像', color: 'blue', width: 350, height: 280 },
    settings: { title: '模型与尺寸', color: 'purple', width: 300, height: 300 },
    generate: { title: '本地采样器', color: 'green', width: 300, height: 345 },
    output: { title: '结果预览', color: 'amber', width: 350, height: 345 },
  };
  const PRESETS = {
    'text-image': { title: '图像创作工作流', subtitle: '让想象从一句话开始，在节点间自由连接。', model: 'image', reference: false, number: '01' },
    'image-image': { title: '图像再创作工作流', subtitle: '从一张参考图出发，探索全新的视觉表达。', model: 'image', reference: true, number: '02' },
    'text-video': { title: '视频创作工作流', subtitle: '描述一个场景，让你的想象随时间展开。', model: 'video', reference: false, number: '03' },
    'image-video': { title: '图像动态工作流', subtitle: '上传参考画面，用提示词描述镜头与运动。', model: 'video', reference: true, number: '04' },
    'reference-video': { title: '多参考视频工作流', subtitle: '以多张参考图保持角色、物体与场景的一致性。', model: 'video', mode: 'ref2va', reference: true, number: '05' },
  };
  const STATUS_NAMES = { queued: '排队中', running: '生成中', succeeded: '已完成', failed: '失败', cancelled: '已取消' };
  const state = {
    workflow: null, system: null, connected: false, jobs: [], filter: 'all', selected: null,
    view: { x: 24, y: 24, scale: .85 }, drag: null, link: null, submitting: false, uploading: false,
    lastResult: null, saveTimer: null, historyBusy: false,
  };
  const viewport = $('#canvas-viewport');
  const world = $('#canvas-world');
  let pendingConfirmation = null;

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }
  function safeUrl(value) {
    if (typeof value !== 'string') return null;
    try {
      const url = new URL(value, location.href);
      return url.origin === location.origin && ['http:', 'https:'].includes(url.protocol) ? url.href : null;
    } catch { return null; }
  }
  function finite(value, fallback, min = -10000, max = 10000) {
    const number = Number(value);
    return Number.isFinite(number) && number >= min && number <= max ? number : fallback;
  }
  function toast(message, error = false) {
    const item = document.createElement('div');
    item.className = `toast${error ? ' error' : ''}`;
    item.textContent = message;
    $('#toast-region').append(item);
    setTimeout(() => item.remove(), error ? 8500 : 4000);
  }
  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 20000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } });
      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('json') ? await response.json() : { message: (await response.text()).slice(0, 500) };
      if (!response.ok) {
        const detail = data.detail || data.error || data.message || `本地服务返回 ${response.status}`;
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('本地服务响应超时，请检查终端中的运行日志。');
      if (error instanceof TypeError) throw new Error('无法连接本地服务，请确认启动终端仍在运行。');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function createWorkflow(preset = 'text-image') {
    const definition = PRESETS[preset];
    const nodes = [
      { id: 'prompt', type: 'prompt', x: 30, y: 30 },
      { id: 'settings', type: 'settings', x: 30, y: 410 },
      { id: 'generate', type: 'generate', x: 455, y: 55 },
      { id: 'output', type: 'output', x: 845, y: 30 },
    ];
    const edges = [
      { from: 'prompt', to: 'generate', input: 'prompt' },
      { from: 'settings', to: 'generate', input: 'settings' },
      { from: 'generate', to: 'output', input: 'result' },
    ];
    if (definition.reference) {
      nodes.push({ id: 'reference', type: 'reference', x: 455, y: 470 });
      edges.push({ from: 'reference', to: 'generate', input: 'reference' });
    }
    return {
      version: 1, preset, nodes, edges, prompt: '', reference: null, references: [],
      settings: { model: definition.model, mode: definition.mode || 'standard', width: definition.model === 'video' ? 512 : 1024, height: definition.model === 'video' ? 512 : 1024, steps: definition.model === 'video' ? 20 : 6, seed: -1, duration: 4 },
    };
  }
  function sanitizeWorkflow(raw) {
    if (!raw || raw.version !== 1 || !Array.isArray(raw.nodes) || !Array.isArray(raw.edges) || !raw.settings) throw new Error('工作流格式不正确，请导入本工作台导出的 JSON 文件。');
    if (raw.nodes.length > 20 || raw.edges.length > 40) throw new Error('工作流包含过多节点或连接。');
    const preset = PRESETS[raw.preset] ? raw.preset : 'text-image';
    const base = createWorkflow(preset);
    const seen = new Set();
    base.nodes = raw.nodes.filter(node => TYPES.includes(node.type) && !seen.has(node.type) && seen.add(node.type)).map(node => ({ id: node.type, type: node.type, x: finite(node.x, 30), y: finite(node.y, 30) }));
    base.edges = raw.edges.filter(edge => base.nodes.some(node => node.id === edge.from) && base.nodes.some(node => node.id === edge.to) && isValidConnection(edge.from, edge.to, edge.input)).map(edge => ({ from: edge.from, to: edge.to, input: edge.input }));
    base.edges = base.edges.filter((edge, index, edges) => edges.findIndex(other => other.to === edge.to && other.input === edge.input) === index);
    base.prompt = String(raw.prompt || '').slice(0, 16000);
    base.settings = {
      model: raw.settings.model === 'video' ? 'video' : 'image',
      mode: preset === 'reference-video' ? 'ref2va' : 'standard',
      width: finite(raw.settings.width, base.settings.width, 256, 4096),
      height: finite(raw.settings.height, base.settings.height, 256, 4096),
      steps: finite(raw.settings.steps, base.settings.steps, 1, 100),
      seed: finite(raw.settings.seed, -1, -1, 2147483647),
      duration: finite(raw.settings.duration, 4, 4, 15),
    };
    if (base.settings.model === 'image') base.settings.steps = 6;
    if (base.settings.mode === 'ref2va') base.settings.model = 'video';
    if (raw.reference && typeof raw.reference.id === 'string' && raw.reference.id.length < 300 && safeUrl(raw.reference.url)) base.reference = { id: raw.reference.id, url: safeUrl(raw.reference.url), name: String(raw.reference.name || '参考图像').slice(0, 200) };
    if (Array.isArray(raw.references)) base.references = raw.references.filter(asset => asset && typeof asset.id === 'string' && asset.id.length < 300 && safeUrl(asset.url)).slice(0, 9).map(asset => ({ id: asset.id, url: safeUrl(asset.url), name: String(asset.name || '参考图像').slice(0, 200) }));
    return base;
  }
  function save() {
    clearTimeout(state.saveTimer);
    $('#saved-indicator').style.background = '#c0b47f';
    state.saveTimer = setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state.workflow));
        $('#saved-indicator').style.background = '#8da76c';
        $('#saved-indicator').title = '已保存到此浏览器';
      } catch {
        $('#saved-indicator').style.background = '#c18b79';
        $('#saved-indicator').title = '浏览器存储不可用，请导出工作流保存';
      }
    }, 300);
  }
  function requestReplace(callback) {
    if (!state.workflow.prompt.trim() && !state.workflow.reference && !state.workflow.references?.length) { callback(); return; }
    pendingConfirmation = callback;
    $('#confirm-dialog').showModal();
  }
  function applyWorkflow(workflow) {
    state.workflow = workflow;
    state.selected = null;
    state.lastResult = null;
    updateHeading();
    syncInspector();
    renderNodes();
    requestAnimationFrame(focusWorkflow);
    save();
  }
  function updateHeading() {
    const preset = PRESETS[state.workflow.preset];
    $('#workflow-title').innerHTML = `${escapeHtml(preset.title)} <span>${preset.number}</span>`;
    $('#workflow-subtitle').textContent = preset.subtitle;
    $$('.preset').forEach(button => button.classList.toggle('active', button.dataset.preset === state.workflow.preset));
  }
  function syncInspector() {
    const settings = state.workflow.settings;
    $('#model-select').value = settings.mode === 'ref2va' ? 'ref2va' : settings.model;
    $('#reference-file').multiple = settings.mode === 'ref2va';
    ['width', 'height', 'steps', 'seed', 'duration'].forEach(key => $(`#${key}-input`).value = settings[key]);
    $('#steps-input').disabled = settings.model === 'image';
    $('#steps-input').title = settings.model === 'image' ? '官方图像模型固定使用 6 步' : '视频模型采样步数';
    $('#steps-note').hidden = settings.model !== 'image';
    $('#duration-note').hidden = settings.model !== 'video';
    $('#width-input').step = '32';
    $('#height-input').step = '32';
    $$('.duration-setting').forEach(element => element.hidden = settings.model !== 'video');
    $('#summary-mode').textContent = settings.mode === 'ref2va' ? 'Ref2VA 参考生视频' : settings.model === 'video' ? '视频生成' : '图像生成';
    $('#summary-size').textContent = `${settings.width} × ${settings.height}`;
    $$('.resolution-presets button').forEach(button => button.classList.toggle('active', button.dataset.resolution === `${settings.width},${settings.height}`));
  }
  function modelName(model) {
    const id = model === 'video' && state.workflow.settings.mode === 'ref2va' ? 'ref2va' : model;
    const modelEntry = state.system?.models?.find(item => item.id === id);
    return modelEntry?.name || (id === 'ref2va' ? 'MiniMax-H3 · Ref2VA' : model === 'video' ? 'MiniMax-H3' : 'MiniMax-H3-image');
  }
  function port(direction, color, input = '') {
    return `<button type="button" class="port ${direction} ${color}" data-direction="${direction}"${input ? ` data-input="${input}"` : ''} aria-label="${direction === 'output' ? '拖动输出端口开始连线' : `连接${{ prompt: '提示词', settings: '设置', reference: '参考图', result: '结果' }[input]}输入`}" title="${direction === 'output' ? '拖动到输入端口' : '拖入连线；右键断开'}"></button>`;
  }
  function nodeContent(type) {
    const s = state.workflow.settings;
    if (type === 'prompt') return `<div class="node-type-label">POSITIVE PROMPT</div><textarea class="node-prompt" placeholder="描述你想创作的画面、风格、光线与细节…" aria-label="生成提示词" maxlength="16000">${escapeHtml(state.workflow.prompt)}</textarea><div class="prompt-footer"><span>支持中文 / English</span><span data-prompt-count>${state.workflow.prompt.length} 字符</span></div><div class="node-port-row right">文本提示词${port('output', 'pink')}</div>`;
    if (type === 'reference') {
      if (state.workflow.settings.mode === 'ref2va') {
        const references = state.workflow.references || [];
        return `<div class="node-type-label">REF2VA · 多参考图</div><div class="reference-list">${references.map((asset, index) => `<div class="reference-item" data-reference-id="${escapeHtml(asset.id)}"><img data-reference-index="${index}" alt="参考图 ${index + 1}"><span><strong>参考图 ${index + 1}</strong><small>${escapeHtml(asset.name)}</small></span><button data-remove-reference-id="${escapeHtml(asset.id)}" aria-label="移除参考图 ${index + 1}">×</button></div>`).join('')}</div><button class="reference-drop compact" data-upload><span>＋</span>${references.length ? '追加参考图' : '上传参考图，可多选'}<small>使用独立 Ref2VA 模型 · 最多 9 张</small><small>按顺序使用 &lt;Picture 1&gt;、&lt;Picture 2&gt; 指定用途</small></button><div class="node-port-row right">${references.length} 张参考图${port('output', 'blue')}</div>`;
      }
      const reference = state.workflow.reference;
      const image = reference && safeUrl(reference.url) ? `<img class="reference-image" alt="已上传的参考图"><div class="reference-actions"><span>${escapeHtml(reference.name)}</span><button data-upload>替换</button><button data-remove-reference>移除</button></div>` : '<button class="reference-drop" data-upload><span>＋</span>点击上传参考图<small>PNG / JPG / WebP · 保存在本机</small></button>';
      return `${image}<div class="node-port-row right">参考图像${port('output', 'blue')}</div>`;
    }
    if (type === 'settings') return `<div class="node-type-label">LOCAL MODEL</div><div class="node-model"><span>◈</span><span data-model-name>${escapeHtml(modelName(s.model))}</span><span>⌄</span></div><div class="node-values"><div class="node-value"><span>输出尺寸</span><strong data-node-size>${s.width} × ${s.height}</strong></div><div class="node-value"><span>运行设备</span><strong>本地 GPU</strong></div><div class="node-value"><span>模式</span><span class="node-tag">完全离线</span></div></div><div class="node-port-row right">模型设置${port('output', 'purple')}</div>`;
    if (type === 'generate') return `<div class="generate-state"><span><span class="status-dot"></span><span data-generation-state>等待运行</span></span><span class="node-tag">LOCAL</span></div><div class="node-port-row">提示词${port('input', 'pink', 'prompt')}</div><div class="node-port-row">模型设置${port('input', 'purple', 'settings')}</div><div class="node-port-row">参考图 <span style="color:#566777;font-size:12px;margin-left:auto">${PRESETS[state.workflow.preset].reference ? '必需' : '可选'}</span>${port('input', 'blue', 'reference')}</div><div class="node-values"><div class="node-value"><span>采样步数</span><strong data-node-steps>${s.steps}</strong></div><div class="node-value"><span>随机种子</span><strong data-node-seed>${s.seed === -1 ? '随机' : s.seed}</strong></div></div><button class="node-generate" data-run>▶ 运行工作流</button><div class="node-progress" hidden><div></div></div><div class="node-port-row right">生成结果${port('output', 'green')}</div>`;
    return `<div class="node-port-row">生成结果${port('input', 'green', 'result')}<span class="node-type-label" style="margin:0">OUTPUT</span></div><div data-output-container><div class="output-placeholder"><span>▧</span><strong>你的下一件作品，从这里开始</strong><small>生成完成后在这里预览<br>结果由本地模型实际生成</small></div></div>`;
  }
  function renderNodes() {
    $('#nodes').innerHTML = state.workflow.nodes.map((node, index) => `<article class="graph-node${state.selected === node.id ? ' selected' : ''}" data-node-id="${node.id}" data-type="${node.type}" style="left:${node.x}px;top:${node.y}px" aria-label="${META[node.type].title}节点"><header class="node-header"><span class="library-dot ${META[node.type].color}"></span><span class="node-title">${META[node.type].title}</span><span class="node-id">#${String(index + 1).padStart(2, '0')}</span><button class="node-menu" data-delete-node aria-label="删除${META[node.type].title}节点" title="删除节点">×</button></header><div class="node-body">${nodeContent(node.type)}</div></article>`).join('');
    const image = $('.reference-image');
    if (image && state.workflow.reference) {
      image.src = safeUrl(state.workflow.reference.url);
      image.addEventListener('error', () => { image.alt = '参考图已失效，请重新上传'; toast('参考图文件无法读取，请重新上传。导入的工作流不会包含图像文件。', true); }, { once: true });
    }
    $$('[data-reference-index]').forEach(imageElement => {
      const asset = state.workflow.references?.[Number(imageElement.dataset.referenceIndex)];
      if (asset) imageElement.src = safeUrl(asset.url);
      imageElement.addEventListener('error', () => { imageElement.alt = '图像失效，请重传'; }, { once: true });
    });
    $('#node-count').textContent = `${state.workflow.nodes.length} NODES`;
    $('#canvas-empty').hidden = state.workflow.nodes.length > 0;
    renderOutput();
    updateGenerationStatus();
    requestAnimationFrame(drawConnections);
    updateGraphStatus();
  }
  function syncNodeDisplay() {
    const s = state.workflow.settings;
    $$('[data-model-name]').forEach(element => element.textContent = modelName(s.model));
    $$('[data-node-size]').forEach(element => element.textContent = `${s.width} × ${s.height}`);
    $$('[data-node-steps]').forEach(element => element.textContent = s.steps);
    $$('[data-node-seed]').forEach(element => element.textContent = s.seed === -1 ? '随机' : s.seed);
    drawConnections();
  }
  function applyView() {
    world.style.transform = `translate(${state.view.x}px,${state.view.y}px) scale(${state.view.scale})`;
    $('#zoom-value').textContent = `${Math.round(state.view.scale * 100)}%`;
    const step = 18 * state.view.scale;
    viewport.style.backgroundSize = `${step}px ${step}px`;
    viewport.style.backgroundPosition = `${state.view.x}px ${state.view.y}px`;
  }
  function focusWorkflow() {
    const scale = viewport.clientWidth < 600 ? 1 : .9;
    state.view = { x: 18 - 30 * scale, y: 22 - 30 * scale, scale };
    applyView();
    drawConnections();
  }
  function fitView() {
    if (!state.workflow.nodes.length) return;
    const minX = Math.min(...state.workflow.nodes.map(node => node.x));
    const minY = Math.min(...state.workflow.nodes.map(node => node.y));
    const maxX = Math.max(...state.workflow.nodes.map(node => node.x + META[node.type].width));
    const maxY = Math.max(...state.workflow.nodes.map(node => node.y + ($(`[data-node-id="${node.id}"]`)?.offsetHeight || META[node.type].height)));
    const availableWidth = Math.max(100, viewport.clientWidth - 55);
    const availableHeight = Math.max(100, viewport.clientHeight - 75);
    const scale = Math.min(1, Math.max(.25, Math.min(availableWidth / (maxX - minX), availableHeight / (maxY - minY))));
    state.view = { scale, x: (viewport.clientWidth - (maxX - minX) * scale) / 2 - minX * scale, y: (viewport.clientHeight - 30 - (maxY - minY) * scale) / 2 - minY * scale };
    applyView();
    drawConnections();
  }
  function toWorld(clientX, clientY) {
    const rect = viewport.getBoundingClientRect();
    return { x: (clientX - rect.left - state.view.x) / state.view.scale, y: (clientY - rect.top - state.view.y) / state.view.scale };
  }
  function portPosition(nodeId, direction, input) {
    const nodeElement = $(`[data-node-id="${nodeId}"]`);
    const target = nodeElement && $(`.port.${direction}${input ? `[data-input="${input}"]` : ''}`, nodeElement);
    if (!target) return null;
    const rect = target.getBoundingClientRect();
    return toWorld(rect.left + rect.width / 2, rect.top + rect.height / 2);
  }
  function curve(from, to) {
    const offset = Math.max(65, Math.abs(to.x - from.x) * .45);
    return `M${from.x},${from.y} C${from.x + offset},${from.y} ${to.x - offset},${to.y} ${to.x},${to.y}`;
  }
  function drawConnections() {
    let paths = '';
    state.workflow.edges.forEach(edge => {
      const from = portPosition(edge.from, 'output');
      const to = portPosition(edge.to, 'input', edge.input);
      if (!from || !to) return;
      const color = { prompt: '#d392be', reference: '#7eafd6', settings: '#a69ce6', generate: '#c1fa71' }[edge.from] || '#8c9bab';
      paths += `<path class="connection-path" d="${curve(from, to)}" stroke="${color}"/>`;
    });
    if (state.link) {
      const from = portPosition(state.link.from, 'output');
      if (from) paths += `<path class="connection-path draft" d="${curve(from, state.link.position)}"/>`;
    }
    $('#connections').innerHTML = paths;
  }
  function zoom(factor, centerX, centerY) {
    const rect = viewport.getBoundingClientRect();
    const x = centerX ?? rect.left + rect.width / 2;
    const y = centerY ?? rect.top + rect.height / 2;
    const point = toWorld(x, y);
    const scale = Math.min(1.7, Math.max(.25, state.view.scale * factor));
    state.view.x = x - rect.left - point.x * scale;
    state.view.y = y - rect.top - point.y * scale;
    state.view.scale = scale;
    applyView();
  }
  function selectNode(id) {
    state.selected = id;
    $$('.graph-node').forEach(node => node.classList.toggle('selected', node.dataset.nodeId === id));
  }
  function isValidConnection(from, to, input) {
    return (to === 'generate' && ['prompt', 'reference', 'settings'].includes(from) && input === from) || (from === 'generate' && to === 'output' && input === 'result');
  }
  function graphErrors() {
    const errors = [];
    ['prompt', 'settings', 'generate', 'output'].forEach(type => { if (!state.workflow.nodes.some(node => node.type === type)) errors.push(`缺少「${META[type].title}」节点`); });
    [['prompt', 'generate', 'prompt'], ['settings', 'generate', 'settings'], ['generate', 'output', 'result']].forEach(([from, to, input]) => {
      if (!state.workflow.edges.some(edge => edge.from === from && edge.to === to && edge.input === input)) errors.push(`请连接「${META[from].title}」到「${META[to].title}」`);
    });
    if (PRESETS[state.workflow.preset].reference && !state.workflow.edges.some(edge => edge.from === 'reference' && edge.to === 'generate')) errors.push('该预设需要连接参考图像');
    return errors;
  }
  function updateGraphStatus() {
    const errors = graphErrors();
    $('#graph-status').textContent = errors.length ? `缺少 ${errors.length} 项节点 / 连接` : '工作流已连接';
    $('#graph-status').style.color = errors.length ? '#c2ad83' : '';
  }
  function deleteNode(id) {
    state.workflow.nodes = state.workflow.nodes.filter(node => node.id !== id);
    state.workflow.edges = state.workflow.edges.filter(edge => edge.from !== id && edge.to !== id);
    if (state.selected === id) state.selected = null;
    renderNodes();
    save();
  }
  function addNode(type) {
    const existing = state.workflow.nodes.find(node => node.type === type);
    if (existing) {
      selectNode(existing.id);
      state.view.scale = Math.max(.85, state.view.scale);
      state.view.x = 24 - existing.x * state.view.scale;
      state.view.y = 24 - existing.y * state.view.scale;
      applyView();
      toast(`已定位「${META[type].title}」节点`);
      return;
    }
    const center = toWorld(viewport.getBoundingClientRect().left + viewport.clientWidth / 2, viewport.getBoundingClientRect().top + viewport.clientHeight / 2);
    state.workflow.nodes.push({ id: type, type, x: Math.round(center.x - META[type].width / 2), y: Math.round(center.y - 100) });
    state.selected = type;
    renderNodes();
    save();
  }
  function systemLocalStatus() {
    return state.system?.backends?.local || { available: false, message: '本地后端尚未完成检查。' };
  }
  async function loadSystem(showToast = false) {
    $('#recheck-system').disabled = true;
    try {
      state.system = await api('/api/system');
      state.connected = true;
      const gpu = state.system.gpu;
      $('#gpu-name').textContent = gpu?.name || '未检测到可用 GPU';
      const details = [];
      if (Number.isFinite(gpu?.vram_gb)) details.push(`${gpu.vram_gb} GB 显存`);
      if (Number.isFinite(state.system.ram_gb)) details.push(`${state.system.ram_gb} GB 内存`);
      $('#hardware-meta').textContent = details.join(' · ') || state.system.platform || '硬件信息未提供';
      const local = systemLocalStatus();
      $('#deployment-banner').className = `deployment-banner${local.available ? ' ready' : ' error'}`;
      $('#deployment-banner strong').textContent = local.available ? '本地后端检查通过' : '本地后端尚未就绪';
      $('#deployment-message').textContent = `${local.message || '请查看部署检查了解详情。'} 原版完整模型在 16 GB 显存上的可用性尚未验证。`;
      $('#connection-status').textContent = '本地服务已连接';
      $('#connection-dot').style.background = '#c1fa71';
      if (Array.isArray(state.system.models)) state.system.models.forEach(model => {
        const option = $$('#model-select option').find(item => item.value === model.id);
        if (option && typeof model.name === 'string') option.textContent = model.name;
      });
      syncNodeDisplay();
      renderSystemDetails();
      if (showToast) toast(local.available ? '本地部署检查已更新' : '检查完成：请查看未就绪原因', !local.available);
    } catch (error) {
      state.connected = false;
      $('#gpu-name').textContent = '本地服务未连接';
      $('#hardware-meta').textContent = '请检查启动终端';
      $('#deployment-banner').className = 'deployment-banner error';
      $('#deployment-banner strong').textContent = '无法连接本地服务';
      $('#deployment-message').textContent = error.message;
      $('#connection-status').textContent = '本地服务连接中断';
      $('#connection-dot').style.background = '#d09987';
      renderSystemDetails(error.message);
      if (showToast) toast(error.message, true);
    } finally { $('#recheck-system').disabled = false; }
  }
  function renderSystemDetails(error) {
    const system = state.system;
    const local = systemLocalStatus();
    const inventory = (system?.models || []).map(model => {
      const files = Array.isArray(model.files) ? model.files : [];
      return `<details class="model-check"><summary><span>${escapeHtml(model.name || model.id)}</span><strong class="${model.ready ? 'ready' : ''}">${model.ready ? '权重就绪' : '权重缺失'}</strong></summary><ul>${files.map(file => `<li><span class="${file.ready ? 'ready' : ''}">${file.ready ? '已就绪' : '缺失'}</span><code>${escapeHtml(file.filename)}</code>${Number.isFinite(file.size_bytes) ? `<small>${(file.size_bytes / 1024 ** 3).toFixed(1)} GiB</small>` : ''}</li>`).join('')}</ul>${model.message ? `<p>${escapeHtml(model.message)}</p>` : ''}</details>`;
    }).join('');
    $('#system-details').innerHTML = `<div class="system-row"><span>运行模式</span><strong>完全离线 · 本地推理</strong></div><div class="system-row"><span>服务状态</span><strong>${state.connected ? '已连接' : '未连接'}</strong></div><div class="system-row"><span>操作系统</span><strong>${escapeHtml(system?.platform || '未提供')}</strong></div><div class="system-row"><span>显卡</span><strong>${escapeHtml(system?.gpu?.name || '未检测到')}</strong></div><div class="system-row"><span>显存 / 内存</span><strong>${Number.isFinite(system?.gpu?.vram_gb) ? `${system.gpu.vram_gb} GB` : '未知'} / ${Number.isFinite(system?.ram_gb) ? `${system.ram_gb} GB` : '未知'}</strong></div><div class="system-row"><span>本地后端</span><strong>${local.available && state.connected ? '检查通过' : '未就绪'}</strong></div><div class="system-message">${escapeHtml(error || local.message || '本地后端未返回检查详情。')}</div>${inventory ? `<div class="model-inventory"><h3>模型文件检查</h3>${inventory}</div>` : ''}<div class="system-warning">${escapeHtml(system?.warning || '原版完整模型在 16 GB 显存上的可用性尚未验证。')} 界面可正常运行不代表模型已成功部署；只有实际任务成功并返回输出文件才算生成完成。图生图、视频时长和分辨率的支持范围由本地推理后端决定。</div>`;
  }
  async function uploadReference(file) {
    if (!file || state.uploading) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) { toast('请选择 PNG、JPG 或 WebP 图像。', true); return; }
    if (file.size > 30 * 1024 * 1024) { toast('参考图超过 30 MB，请压缩后再上传。', true); return; }
    const targetWorkflow = state.workflow;
    if (targetWorkflow.settings.mode === 'ref2va' && targetWorkflow.references?.length >= 9) { toast('最多支持 9 张参考图，请先移除部分图像。', true); return; }
    state.uploading = true;
    updateRunButtons();
    toast('正在把参考图保存到本地服务…');
    try {
      const body = new FormData();
      body.append('file', file);
      const asset = await api('/api/assets', { method: 'POST', body, timeout: 60000 });
      if (!asset.id || !safeUrl(asset.url)) throw new Error('服务未返回有效的本地文件地址。');
      if (state.workflow !== targetWorkflow) throw new Error('工作流已切换，请在当前工作流中重新选择参考图。');
      const savedAsset = { id: String(asset.id), name: asset.name || file.name, url: safeUrl(asset.url) };
      if (state.workflow.settings.mode === 'ref2va') {
        state.workflow.references ||= [];
        if (state.workflow.references.length >= 9) throw new Error('最多支持 9 张参考图，请先移除部分图像。');
        state.workflow.references.push(savedAsset);
      } else state.workflow.reference = savedAsset;
      if (!state.workflow.nodes.some(node => node.type === 'reference')) state.workflow.nodes.push({ id: 'reference', type: 'reference', x: 30, y: 350 });
      if (!state.workflow.edges.some(edge => edge.from === 'reference' && edge.to === 'generate') && state.workflow.nodes.some(node => node.type === 'generate')) state.workflow.edges.push({ from: 'reference', to: 'generate', input: 'reference' });
      renderNodes();
      save();
      toast('参考图已保存在本机');
    } catch (error) { toast(error.message, true); }
    finally { state.uploading = false; updateRunButtons(); $('#reference-file').value = ''; }
  }
  function validateRequest() {
    const errors = graphErrors();
    if (errors.length) throw new Error(errors[0]);
    if (!state.workflow.prompt.trim()) throw new Error('请先在「文本提示词」节点中描述你要生成的内容。');
    if (state.workflow.prompt.length > 16000) throw new Error('提示词最多 16000 字符。');
    const s = state.workflow.settings;
    const alignment = 32;
    for (const key of ['width', 'height']) if (!Number.isInteger(s[key]) || s[key] < 256 || s[key] > 4096 || s[key] % alignment !== 0) throw new Error(`宽度和高度必须是 256–4096 之间、${alignment} 的整数倍。`);
    if (s.model === 'video' && s.width * s.height > 1280 * 768) throw new Error('视频分辨率面积不能超过 1280 × 768 像素，请降低宽度或高度。');
    if (!Number.isInteger(s.steps) || s.steps < 1 || s.steps > 100) throw new Error('采样步数需要是 1–100 之间的整数。');
    if (s.model === 'image' && s.steps !== 6) throw new Error('官方图像模型必须使用 6 步采样。');
    if (!Number.isInteger(s.seed) || s.seed < -1 || s.seed > 2147483647) throw new Error('随机种子需为 −1 或 0–2147483647 之间的整数。');
    if (s.model === 'video' && (!Number.isInteger(s.duration) || s.duration < 4 || s.duration > 15)) throw new Error('视频时长需要是 4–15 之间的整数秒；实际帧数由本地后端对齐。');
    const hasReference = state.workflow.edges.some(edge => edge.from === 'reference' && edge.to === 'generate');
    if (s.mode === 'ref2va') {
      if (!hasReference || !state.workflow.references?.length) throw new Error('Ref2VA 需要至少一张参考图，并连接参考图节点。');
      if (state.workflow.references.length > 9) throw new Error('Ref2VA 最多支持 9 张参考图片。');
      const inventory = state.system?.models?.find(model => model.id === 'ref2va');
      if (!inventory || inventory.ready === false) throw new Error('独立 Ref2VA 参考模型尚未就绪，请检查本地 Ref2VA 权重与后端。');
    } else if ((hasReference || PRESETS[state.workflow.preset].reference) && !state.workflow.reference?.id) throw new Error('请先上传参考图像，或断开参考图节点并切换到文生预设。');
    if (state.uploading) throw new Error('参考图正在上传，请等待完成后运行。');
    return hasReference;
  }
  async function submitJob() {
    if (state.submitting) return;
    let useReference;
    try { useReference = validateRequest(); }
    catch (error) { toast(error.message, true); return; }
    if (!state.connected || !systemLocalStatus().available) {
      toast(!state.connected ? '本地服务未连接，请先启动服务并重新检查。' : systemLocalStatus().message || '本地推理后端尚未就绪，请先完成部署检查。', true);
      $('#system-dialog').showModal();
      return;
    }
    state.submitting = true;
    updateRunButtons();
    try {
      const s = state.workflow.settings;
      const request = { model: s.model, backend: 'local', prompt: state.workflow.prompt.trim(), width: s.width, height: s.height, seed: s.seed, steps: s.steps, duration: s.duration, workflow: JSON.parse(JSON.stringify(state.workflow)) };
      if (s.mode === 'ref2va') { request.mode = 'ref2va'; request.reference_asset_ids = state.workflow.references.map(asset => asset.id); }
      else if (useReference) request.reference_asset_id = state.workflow.reference.id;
      const job = await api('/api/jobs', { method: 'POST', body: JSON.stringify(request) });
      if (!job.id || !STATUS_NAMES[job.status]) throw new Error('本地服务未返回有效任务。');
      upsertJob(job);
      toast(job.status === 'failed' ? job.error || job.message || '任务失败，请查看任务记录。' : '任务已加入本地生成队列', job.status === 'failed');
      $('#jobs-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (error) { toast(error.message, true); }
    finally { state.submitting = false; updateRunButtons(); }
  }
  function updateRunButtons() {
    $$('#run-top, #run-main, [data-run]').forEach(button => button.disabled = state.submitting || state.uploading);
    $('#run-main>span:first-of-type').textContent = state.submitting ? '正在提交…' : '加入生成队列';
  }
  function upsertJob(job, shouldRender = true) {
    const index = state.jobs.findIndex(existing => existing.id === job.id);
    if (index < 0) state.jobs.unshift(job); else state.jobs[index] = job;
    state.jobs.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
    if (job.status === 'succeeded' && job.outputs?.length) {
      const previous = state.lastResult;
      if (!previous || String(job.created_at || '') >= String(previous.created_at || '')) state.lastResult = job;
    }
    if (shouldRender) { renderJobs(); updateGenerationStatus(); renderOutput(); }
  }
  function outputOf(job) { return job?.outputs?.find(output => ['image', 'video'].includes(output.kind) && safeUrl(output.url)); }
  function renderOutput() {
    const container = $('[data-output-container]');
    if (!container) return;
    const output = outputOf(state.lastResult);
    if (!output) return;
    if (container.dataset.jobId === state.lastResult.id && container.dataset.outputUrl === output.url) return;
    container.dataset.jobId = state.lastResult.id;
    container.dataset.outputUrl = output.url;
    container.replaceChildren();
    const media = document.createElement(output.kind === 'video' ? 'video' : 'img');
    media.className = 'node-result';
    media.src = safeUrl(output.url);
    if (output.kind === 'video') { media.controls = true; media.preload = 'metadata'; }
    else { media.alt = state.lastResult.request?.prompt || '本地生成结果'; media.addEventListener('click', () => openPreview(state.lastResult.id)); }
    container.append(media);
    const links = document.createElement('div');
    links.className = 'node-result-links';
    const open = document.createElement('button');
    open.textContent = '查看结果';
    open.addEventListener('click', () => openPreview(state.lastResult.id));
    const download = document.createElement('a');
    download.href = safeUrl(output.url); download.download = output.name || 'output'; download.textContent = '↓ 下载';
    links.append(open, download); container.append(links);
    requestAnimationFrame(drawConnections);
  }
  function updateGenerationStatus() {
    const current = state.jobs.find(job => ['running', 'queued'].includes(job.status));
    const latest = current || state.jobs[0];
    const label = $('[data-generation-state]');
    if (label) label.textContent = latest ? STATUS_NAMES[latest.status] || latest.status : '等待运行';
    const progress = $('.node-progress');
    if (progress) { progress.hidden = !current; $('div', progress).style.width = `${finite(current?.progress, 0, 0, 100)}%`; }
  }
  function formattedTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  }
  function renderJobs() {
    const activeCount = state.jobs.filter(job => ['queued', 'running'].includes(job.status)).length;
    $('#job-count').textContent = state.jobs.length;
    $('#queue-count').textContent = `${activeCount} 个进行中`;
    const jobs = state.jobs.filter(job => state.filter === 'all' || (state.filter === 'active' ? ['queued', 'running'].includes(job.status) : job.status === state.filter));
    const list = $('#jobs-list');
    if (!jobs.length) {
      list.innerHTML = `<div class="empty-jobs"><span>⌁</span><div>${state.jobs.length ? '暂无符合条件的任务' : '还没有生成任务'}<small>${state.jobs.length ? '切换筛选查看其他任务。' : '连接节点，写下提示词，让灵感开始流动。'}</small></div></div>`;
      return;
    }
    list.innerHTML = jobs.map(job => {
      const output = outputOf(job);
      const active = ['queued', 'running'].includes(job.status);
      const progress = finite(job.progress, 0, 0, 100);
      const detail = job.error || job.message || '';
      return `<article class="job-row" data-job-id="${escapeHtml(job.id)}"><div class="job-thumb">${output?.kind === 'image' ? '<img alt="生成结果缩略图" loading="lazy">' : job.request?.model === 'video' ? '▷' : '▧'}</div><div class="job-info"><strong>${escapeHtml(job.request?.prompt || '生成任务')}</strong><small>${escapeHtml(formattedTime(job.created_at))}${job.request?.width ? ` · ${escapeHtml(job.request.width)} × ${escapeHtml(job.request.height)}` : ''}${detail ? ` · ${escapeHtml(detail)}` : ''}</small>${active ? `<div class="job-progress"><span style="width:${progress}%"></span></div>` : ''}</div><div class="job-state ${escapeHtml(job.status)}">${escapeHtml(STATUS_NAMES[job.status] || job.status)}${active ? `<br><span>${progress}%</span>` : ''}</div>${active ? '<button class="job-button" data-cancel-job>取消</button>' : output ? '<button class="job-button" data-preview-job>查看</button>' : ''}</article>`;
    }).join('');
    $$('.job-row', list).forEach(row => {
      const img = $('img', row);
      const job = jobs.find(item => item.id === row.dataset.jobId);
      if (img) img.src = safeUrl(outputOf(job)?.url);
    });
  }
  async function loadHistory(showError = false) {
    if (state.historyBusy) return;
    state.historyBusy = true;
    try {
      const result = await api('/api/history');
      if (!Array.isArray(result.jobs)) throw new Error('任务历史返回格式不正确。');
      state.jobs = [];
      state.lastResult = null;
      result.jobs.forEach(job => { if (job.id && STATUS_NAMES[job.status]) upsertJob(job, false); });
      renderJobs(); updateGenerationStatus(); renderOutput();
    } catch (error) { if (showError) toast(error.message, true); }
    finally { state.historyBusy = false; }
  }
  async function pollJobs() {
    const active = state.jobs.filter(job => ['queued', 'running'].includes(job.status));
    const results = await Promise.allSettled(active.map(job => api(`/api/jobs/${encodeURIComponent(job.id)}`)));
    results.forEach((result, index) => {
      if (result.status !== 'fulfilled' || !result.value.id || !STATUS_NAMES[result.value.status]) return;
      const previous = active[index];
      const job = result.value;
      upsertJob(job, false);
      if (previous.status !== job.status && ['succeeded', 'failed', 'cancelled'].includes(job.status)) toast(job.status === 'succeeded' ? '本地生成任务已完成' : job.error || job.message || `任务${STATUS_NAMES[job.status]}`, job.status === 'failed');
    });
    if (active.length) { renderJobs(); updateGenerationStatus(); renderOutput(); }
    setTimeout(pollJobs, active.length ? 1600 : 3000);
  }
  async function cancelJob(id, button) {
    button.disabled = true;
    try { upsertJob(await api(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' })); toast('已请求取消任务'); }
    catch (error) { toast(error.message, true); button.disabled = false; }
  }
  function openPreview(id) {
    const job = state.jobs.find(item => item.id === id);
    const outputs = job?.outputs?.filter(output => ['image', 'video'].includes(output.kind) && safeUrl(output.url)) || [];
    if (!outputs.length) { toast('此任务没有可读取的输出文件。', true); return; }
    $('#preview-title').textContent = job.request?.model === 'video' ? '视频生成结果' : '图像生成结果';
    const container = $('#preview-content');
    container.replaceChildren();
    outputs.forEach(output => {
      const media = document.createElement(output.kind === 'video' ? 'video' : 'img');
      media.src = safeUrl(output.url);
      if (output.kind === 'video') { media.controls = true; media.preload = 'metadata'; } else media.alt = job.request?.prompt || '本地生成结果';
      const link = document.createElement('a');
      link.href = safeUrl(output.url); link.download = output.name || 'output'; link.textContent = `↓ 下载 ${output.name || '生成结果'}`;
      container.append(media, link);
    });
    $('#preview-dialog').showModal();
  }
  function exportWorkflow() {
    const blob = new Blob([JSON.stringify(state.workflow, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `智能座舱AIGC-${state.workflow.preset}-工作流.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast('工作流已导出；参考图文件请单独保留。');
  }

  viewport.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    const target = event.target;
    const node = target.closest('.graph-node');
    const outputPort = target.closest('.port.output');
    if (outputPort) {
      event.preventDefault();
      state.link = { from: node.dataset.nodeId, position: toWorld(event.clientX, event.clientY) };
      drawConnections();
      return;
    }
    if (node) {
      selectNode(node.dataset.nodeId);
      if (!target.closest('.node-header') || target.closest('button')) return;
      event.preventDefault();
      const data = state.workflow.nodes.find(item => item.id === node.dataset.nodeId);
      state.drag = { type: 'node', id: data.id, startX: event.clientX, startY: event.clientY, x: data.x, y: data.y };
      viewport.setPointerCapture(event.pointerId);
      return;
    }
    if (target.closest('button, .canvas-controls')) return;
    selectNode(null);
    state.drag = { type: 'pan', startX: event.clientX, startY: event.clientY, x: state.view.x, y: state.view.y };
    viewport.classList.add('panning');
    viewport.setPointerCapture(event.pointerId);
  });
  document.addEventListener('pointermove', event => {
    if (state.link) { state.link.position = toWorld(event.clientX, event.clientY); drawConnections(); }
    if (!state.drag) return;
    const drag = state.drag;
    if (drag.type === 'pan') {
      state.view.x = drag.x + event.clientX - drag.startX;
      state.view.y = drag.y + event.clientY - drag.startY;
      applyView();
    } else {
      const node = state.workflow.nodes.find(item => item.id === drag.id);
      node.x = Math.round(drag.x + (event.clientX - drag.startX) / state.view.scale);
      node.y = Math.round(drag.y + (event.clientY - drag.startY) / state.view.scale);
      const element = $(`[data-node-id="${node.id}"]`);
      element.style.left = `${node.x}px`; element.style.top = `${node.y}px`;
      drawConnections();
    }
  });
  document.addEventListener('pointerup', event => {
    if (state.link) {
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.port.input');
      if (target) {
        const to = target.closest('.graph-node').dataset.nodeId;
        const input = target.dataset.input;
        if (isValidConnection(state.link.from, to, input)) {
          state.workflow.edges = state.workflow.edges.filter(edge => edge.to !== to || edge.input !== input);
          state.workflow.edges.push({ from: state.link.from, to, input });
          save(); updateGraphStatus();
        } else toast('端口类型不匹配，请连接相同颜色的输入。', true);
      }
      state.link = null; drawConnections();
    }
    if (state.drag?.type === 'node') save();
    state.drag = null;
    viewport.classList.remove('panning');
  });
  document.addEventListener('pointercancel', () => { state.drag = null; state.link = null; viewport.classList.remove('panning'); drawConnections(); });
  viewport.addEventListener('wheel', event => {
    if (event.target.closest('textarea, select, input')) return;
    event.preventDefault();
    zoom(event.deltaY < 0 ? 1.08 : 1 / 1.08, event.clientX, event.clientY);
  }, { passive: false });
  viewport.addEventListener('contextmenu', event => {
    const portElement = event.target.closest('.port');
    if (!portElement) return;
    event.preventDefault();
    const id = portElement.closest('.graph-node').dataset.nodeId;
    state.workflow.edges = state.workflow.edges.filter(edge => portElement.dataset.direction === 'input' ? !(edge.to === id && edge.input === portElement.dataset.input) : edge.from !== id);
    drawConnections(); updateGraphStatus(); save(); toast('连接已断开');
  });
  $('#nodes').addEventListener('input', event => {
    if (!event.target.matches('.node-prompt')) return;
    state.workflow.prompt = event.target.value;
    $('[data-prompt-count]').textContent = `${event.target.value.length} 字符`;
    save();
  });
  $('#nodes').addEventListener('click', event => {
    const target = event.target;
    if (target.closest('[data-delete-node]')) deleteNode(target.closest('.graph-node').dataset.nodeId);
    if (target.closest('[data-run]')) submitJob();
    if (target.closest('[data-upload]')) $('#reference-file').click();
    if (target.closest('[data-remove-reference]')) { state.workflow.reference = null; renderNodes(); save(); }
    const removeMultiple = target.closest('[data-remove-reference-id]');
    if (removeMultiple) { state.workflow.references = (state.workflow.references || []).filter(asset => asset.id !== removeMultiple.dataset.removeReferenceId); renderNodes(); save(); }
  });
  $$('.preset').forEach(button => button.addEventListener('click', () => {
    if (button.dataset.preset === state.workflow.preset) return;
    requestReplace(() => applyWorkflow(createWorkflow(button.dataset.preset)));
  }));
  $$('[data-add-node]').forEach(button => button.addEventListener('click', () => addNode(button.dataset.addNode)));
  $('#model-select').addEventListener('change', event => {
    const selection = event.target.value;
    const nextModel = selection === 'ref2va' ? 'video' : selection;
    const s = state.workflow.settings;
    s.model = nextModel;
    s.mode = selection === 'ref2va' ? 'ref2va' : 'standard';
    s.steps = nextModel === 'video' ? 20 : 6;
    s.width = nextModel === 'video' ? 512 : 1024;
    s.height = nextModel === 'video' ? 512 : 1024;
    state.workflow.preset = selection === 'ref2va' ? 'reference-video' : `${PRESETS[state.workflow.preset].reference ? 'image' : 'text'}-${nextModel}`;
    if (selection === 'ref2va' && !state.workflow.nodes.some(node => node.type === 'reference')) {
      state.workflow.nodes.push({ id: 'reference', type: 'reference', x: 455, y: 470 });
      if (state.workflow.nodes.some(node => node.type === 'generate')) state.workflow.edges.push({ from: 'reference', to: 'generate', input: 'reference' });
    }
    syncInspector(); renderNodes(); updateHeading(); save();
  });
  ['width', 'height', 'steps', 'seed', 'duration'].forEach(key => $(`#${key}-input`).addEventListener('input', event => {
    state.workflow.settings[key] = event.target.value === '' ? NaN : Number(event.target.value);
    $('#summary-size').textContent = `${state.workflow.settings.width || '—'} × ${state.workflow.settings.height || '—'}`;
    syncNodeDisplay();
    $$('.resolution-presets button').forEach(button => button.classList.toggle('active', button.dataset.resolution === `${state.workflow.settings.width},${state.workflow.settings.height}`));
    save();
  }));
  $$('[data-resolution]').forEach(button => button.addEventListener('click', () => {
    const [width, height] = button.dataset.resolution.split(',').map(Number);
    Object.assign(state.workflow.settings, { width, height }); syncInspector(); syncNodeDisplay(); save();
  }));
  $('#randomize-seed').addEventListener('click', () => { state.workflow.settings.seed = -1; syncInspector(); syncNodeDisplay(); save(); });
  $('#run-top').addEventListener('click', submitJob);
  $('#run-main').addEventListener('click', submitJob);
  $('#zoom-out').addEventListener('click', () => zoom(1 / 1.2));
  $('#zoom-in').addEventListener('click', () => zoom(1.2));
  $('#fit-view').addEventListener('click', fitView);
  $('#export-workflow').addEventListener('click', exportWorkflow);
  $('#import-workflow').addEventListener('click', () => $('#workflow-file').click());
  $('#workflow-file').addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast('工作流 JSON 文件不能超过 2 MB。', true); event.target.value = ''; return; }
    try { const imported = sanitizeWorkflow(JSON.parse(await file.text())); requestReplace(() => { applyWorkflow(imported); toast('工作流已导入'); }); }
    catch (error) { toast(error instanceof SyntaxError ? '文件不是有效的 JSON。' : error.message, true); }
    event.target.value = '';
  });
  async function uploadFiles(files) {
    if (state.uploading) { toast('正在上传参考图，请等待当前上传完成。'); return; }
    const selected = Array.from(files || []);
    const uploads = state.workflow.settings.mode === 'ref2va' ? selected : selected.slice(0, 1);
    const targetWorkflow = state.workflow;
    for (const file of uploads) {
      if (state.workflow !== targetWorkflow) break;
      await uploadReference(file);
    }
  }
  $('#reference-file').addEventListener('change', event => uploadFiles(event.target.files));
  viewport.addEventListener('dragover', event => { if (event.dataTransfer?.types.includes('Files')) event.preventDefault(); });
  viewport.addEventListener('drop', event => { event.preventDefault(); uploadFiles(event.dataTransfer?.files); });
  $('#open-system').addEventListener('click', () => $('#system-dialog').showModal());
  $('#banner-system').addEventListener('click', () => $('#system-dialog').showModal());
  $('#recheck-system').addEventListener('click', () => loadSystem(true));
  $$('[data-close-dialog]').forEach(button => button.addEventListener('click', () => $(`#${button.dataset.closeDialog}`).close()));
  $('#preview-dialog').addEventListener('close', () => $$('#preview-content video').forEach(video => video.pause()));
  $('#confirm-no').addEventListener('click', () => { pendingConfirmation = null; $('#confirm-dialog').close(); });
  $('#confirm-yes').addEventListener('click', () => { const callback = pendingConfirmation; pendingConfirmation = null; $('#confirm-dialog').close(); if (callback) callback(); });
  $('#confirm-dialog').addEventListener('cancel', () => { pendingConfirmation = null; });
  $('#history-toggle').addEventListener('click', () => $('#jobs-panel').scrollIntoView({ behavior: 'smooth', block: 'center' }));
  $$('[data-job-filter]').forEach(button => button.addEventListener('click', () => { state.filter = button.dataset.jobFilter; $$('[data-job-filter]').forEach(tab => tab.classList.toggle('active', tab === button)); renderJobs(); }));
  $('#refresh-history').addEventListener('click', () => loadHistory(true));
  $('#jobs-list').addEventListener('click', event => {
    const row = event.target.closest('[data-job-id]');
    if (!row) return;
    if (event.target.closest('[data-cancel-job]')) cancelJob(row.dataset.jobId, event.target.closest('button'));
    if (event.target.closest('[data-preview-job]')) openPreview(row.dataset.jobId);
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !$('dialog[open]')) { event.preventDefault(); submitJob(); }
    if (event.key === 'Escape') { state.link = null; drawConnections(); }
    if ((event.key === 'Delete' || event.key === 'Backspace') && state.selected && !event.target.closest('input, textarea, select, [contenteditable]') && !$('dialog[open]')) { event.preventDefault(); deleteNode(state.selected); }
  });
  let previousViewportWidth = 0;
  new ResizeObserver(() => {
    const currentWidth = viewport.clientWidth;
    if (previousViewportWidth && Math.abs(currentWidth - previousViewportWidth) > 100) focusWorkflow();
    else drawConnections();
    previousViewportWidth = currentWidth;
  }).observe(viewport);

  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    state.workflow = saved ? sanitizeWorkflow(JSON.parse(saved)) : createWorkflow();
  } catch { state.workflow = createWorkflow(); }
  updateHeading(); syncInspector(); renderNodes(); applyView();
  renderSystemDetails();
  requestAnimationFrame(focusWorkflow);
  loadSystem(); loadHistory(); pollJobs();
  setInterval(() => { if (document.visibilityState === 'visible' && !state.jobs.some(job => ['queued', 'running'].includes(job.status))) loadHistory(); }, 20000);
})();
