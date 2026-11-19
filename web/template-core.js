(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.H3TemplateCore = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const REPOSITORY = 'https://github.com/MiniMax-AI/MiniMax-H3';
  const REVISION = /^[0-9a-f]{40}$/;
  const IDENTIFIER = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/;
  const FIELD_IDENTIFIER = /^[a-zA-Z][a-zA-Z0-9_]{0,63}$/;
  const PRESETS = new Set(['text-image', 'image-image', 'text-video', 'image-video', 'reference-video']);
  const RESERVED = new Set(['__proto__', 'constructor', 'prototype']);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

  function fail(message) { throw new Error(message); }
  function object(value, name) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${name} 必须是对象`);
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) fail(`${name} 必须是普通对象`);
    return value;
  }
  function text(value, name, maximum = 16000, allowEmpty = false) {
    if (typeof value !== 'string' || value.length > maximum || (!allowEmpty && !value.trim())) fail(`${name} 为空或长度超限`);
    return value;
  }
  function identifier(value, name, field = false) {
    if (typeof value !== 'string' || !(field ? FIELD_IDENTIFIER : IDENTIFIER).test(value) || RESERVED.has(value)) fail(`${name} 标识无效`);
    return value;
  }
  function sourceUrl(value, revision) {
    text(value, '来源链接', 1000);
    let parsed;
    try { parsed = new URL(value); } catch (_) { fail('来源必须是固定版本的官方 GitHub 链接'); }
    const match = parsed.pathname.match(/^\/MiniMax-AI\/MiniMax-H3\/(?:blob|tree)\/([0-9a-f]{40})(?:\/[^?#]*)?$/);
    if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || parsed.port || parsed.username || parsed.password || parsed.search || parsed.hash || !match || (revision && match[1] !== revision)) {
      fail('来源必须是固定版本的官方 GitHub 链接');
    }
    return match[1];
  }
  function source(value) {
    object(value, '来源');
    if (value.repository !== REPOSITORY || !REVISION.test(value.revision || '')) fail('来源仓库或固定 revision 无效');
    sourceUrl(value.url, value.revision);
    return value;
  }
  function stringList(value, name, fields) {
    if (!Array.isArray(value) || value.length > 100) fail(`${name} 必须是文本列表`);
    value.forEach((item, index) => {
      text(item, `${name}[${index}]`, 16000);
      checkPlaceholders(item, fields);
    });
    return value;
  }
  function checkPlaceholders(value, fields) {
    // Only catalog strings are scanned. Inserted field values are never scanned again.
    const remaining = value.replace(/\{\{([^{}]*)\}\}/g, function (_, id) {
      if (!fields.has(id)) fail(`未知模板字段：${id}`);
      return '';
    });
    if (remaining.includes('{{') || remaining.includes('}}')) fail('模板占位符格式无效');
  }
  function settings(value, preset) {
    object(value, '镜头设置');
    const image = preset === 'text-image' || preset === 'image-image';
    for (const key of ['width', 'height']) {
      if (!Number.isInteger(value[key]) || value[key] < 256 || value[key] > 4096 || value[key] % 32) fail(`${key} 必须是 256–4096 范围内 32 的倍数`);
    }
    if (!Number.isInteger(value.steps) || value.steps < 1 || value.steps > 100 || (image && value.steps !== 6)) fail('图像固定 6 步，视频步数须介于 1–100');
    if (!Number.isInteger(value.duration) || value.duration < (image ? 1 : 4) || value.duration > 15) fail('视频时长须介于 4–15 秒');
    if (!image && value.width * value.height > 1280 * 768) fail('视频尺寸超过本地部署约 1MP 限制');
    return { width: value.width, height: value.height, steps: value.steps, duration: value.duration };
  }
  function validateShot(shot, fields) {
    object(shot, '镜头');
    identifier(shot.id, '镜头');
    text(shot.title, '镜头标题', 500);
    text(shot.description, '镜头描述', 4000);
    if (!PRESETS.has(shot.preset)) fail('未知工作流预设');
    settings(shot.settings, shot.preset);
    object(shot.prompt, '镜头提示词');
    for (const key of ['visual', 'soundscape', 'music']) {
      text(shot.prompt[key], `提示词 ${key}`, 16000, key !== 'visual');
      checkPlaceholders(shot.prompt[key], fields);
    }
    if (shot.preset === 'reference-video') {
      object(shot.prompt.reference, 'Ref2VA 参考描述');
      for (const key of ['subject_definitions', 'summary', 'retention_analysis']) {
        text(shot.prompt.reference[key], `Ref2VA ${key}`, 16000);
        checkPlaceholders(shot.prompt.reference[key], fields);
      }
    }
    checkPlaceholders(shot.title, fields);
    checkPlaceholders(shot.description, fields);
  }
  function validateTemplate(template, revision) {
    object(template, '模板');
    identifier(template.id, '模板');
    text(template.name, '模板名称', 500);
    text(template.category, '模板分类', 500);
    text(template.summary, '模板摘要', 4000);
    sourceUrl(template.source_url, revision);
    if (!Array.isArray(template.fields) || !template.fields.length || template.fields.length > 40) fail('模板字段列表无效');
    const fields = new Set();
    for (const field of template.fields) {
      object(field, '字段');
      identifier(field.id, '字段', true);
      if (fields.has(field.id)) fail(`重复模板字段：${field.id}`);
      fields.add(field.id);
      text(field.label, '字段名称', 500);
      if (field.type !== 'text' && field.type !== 'textarea') fail('字段类型无效');
      if (field.required !== true) fail('模板字段必须标记 required: true');
      text(field.default, `字段 ${field.id} 默认值`, 2000);
    }
    for (const name of ['stages', 'checklist', 'notes']) stringList(template[name], name, fields);
    if (!Array.isArray(template.shots) || !template.shots.length || template.shots.length > 100) fail('镜头列表无效');
    const shots = new Set();
    for (const shot of template.shots) {
      validateShot(shot, fields);
      if (shots.has(shot.id)) fail(`重复镜头：${shot.id}`);
      shots.add(shot.id);
    }
    return fields;
  }
  function resolveFields(template, values) {
    if (values === undefined) values = {};
    object(values, '字段值');
    const known = new Set(template.fields.map(field => field.id));
    for (const id of Object.keys(values)) if (!known.has(id)) fail(`未知模板字段：${id}`);
    const resolved = {};
    for (const field of template.fields) {
      const value = own(values, field.id) ? values[field.id] : field.default;
      text(value, `字段 ${field.label}`, 2000);
      resolved[field.id] = value;
    }
    return resolved;
  }
  function replace(value, fields) {
    return value.replace(/\{\{([^{}]*)\}\}/g, function (_, id) {
      if (!own(fields, id)) fail(`未知模板字段：${id}`);
      return fields[id];
    });
  }
  function renderResolved(shot, fields) {
    const visual = replace(shot.prompt.visual, fields);
    const image = shot.preset === 'text-image' || shot.preset === 'image-image';
    let prompt = visual;
    if (!image) {
      const sections = shot.preset === 'reference-video' ? [
        ['subject_definitions', replace(shot.prompt.reference.subject_definitions, fields)],
        ['summary', replace(shot.prompt.reference.summary, fields)],
        ['retention_analysis', replace(shot.prompt.reference.retention_analysis, fields)],
        ['detailed_description', visual],
      ] : [['integrated_multimodal_description', visual]];
      sections.push(['overall_soundscape', replace(shot.prompt.soundscape, fields)], ['non_diegetic_music', replace(shot.prompt.music, fields)]);
      prompt = sections.map(section => `${section[0]}: ${section[1]}`).join('\n\n');
      if (shot.preset === 'image-video') {
        prompt = 'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n' + prompt;
      }
    }
    text(prompt, '完整提示词', 16000);
    return { prompt, preset: shot.preset, settings: settings(shot.settings, shot.preset) };
  }
  function validateCatalog(raw) {
    object(raw, '模板目录');
    if (raw.schema_version !== 1 || !Array.isArray(raw.templates) || raw.templates.length !== 9) fail('模板目录必须是 schema_version 1 的九项模板');
    source(raw.source);
    const ids = new Set();
    for (const template of raw.templates) {
      validateTemplate(template, raw.source.revision);
      if (ids.has(template.id)) fail(`重复模板：${template.id}`);
      ids.add(template.id);
      const fields = resolveFields(template, {});
      for (const shot of template.shots) renderResolved(shot, fields);
    }
    return raw;
  }
  function renderShot(template, shot, fieldValues) {
    const fields = validateTemplate(template);
    validateShot(shot, fields);
    return renderResolved(shot, resolveFields(template, fieldValues));
  }
  function buildPlan(catalog, template, fieldValues) {
    validateCatalog(catalog);
    const id = typeof template === 'string' ? template : object(template, '模板').id;
    const selected = catalog.templates.find(item => item.id === id);
    if (!selected) fail(`模板不在目录中：${id}`);
    const fields = resolveFields(selected, fieldValues);
    const plan = {
      schema_version: 1,
      source: { repository: catalog.source.repository, revision: catalog.source.revision, url: catalog.source.url },
      template: { id: selected.id, name: selected.name, category: selected.category, summary: selected.summary, source_url: selected.source_url },
      fields,
      shots: selected.shots.map(shot => ({
        id: shot.id, title: replace(shot.title, fields), description: replace(shot.description, fields),
        ...renderResolved(shot, fields),
      })),
    };
    for (const key of ['stages', 'checklist', 'notes']) plan[key] = selected[key].map(item => replace(item, fields));
    return plan;
  }

  return Object.freeze({ validateCatalog, renderShot, buildPlan });
}));
